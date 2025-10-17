#!/usr/bin/env python3
"""
CLI結果比較スクリプト

このスクリプトは、異なるバージョンのCLIテスト結果を比較し、
互換性レポートを生成します。

機能:
- 2つのバージョンのCLIテスト結果を比較
- 出力形式の差分分析
- HTMLレポート生成
- WinMerge用比較ファイル生成
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CLIResultComparator:
    """CLI結果比較クラス"""
    
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.result_dir = self.test_dir / "result" / "cli"
        
    def load_test_results(self, version: str) -> Optional[Dict[str, Any]]:
        """指定バージョンのテスト結果を読み込み"""
        version_dir = self.result_dir / f"v-{version}"
        summary_file = version_dir / "cli_test_summary.json"
        
        if not summary_file.exists():
            logger.error(f"テスト結果が見つかりません: {summary_file}")
            return None
        
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"テスト結果の読み込みエラー: {e}")
            return None
    
    def normalize_cli_output(self, output: str) -> str:
        """CLI出力を正規化（比較用）"""
        if not output:
            return ""
        
        lines = output.split('\n')
        normalized_lines = []
        
        for line in lines:
            # 空行をスキップ
            if not line.strip():
                continue
            
            # タイムスタンプや実行時間を除去
            if re.search(r'\d{4}-\d{2}-\d{2}|\d+\.\d+\s*ms|elapsed|time:', line, re.IGNORECASE):
                continue
            
            # パス情報を正規化
            line = re.sub(r'[A-Z]:\\\\[^\\\\]+\\\\', 'PROJECT_ROOT\\\\', line)
            line = re.sub(r'/[^/]+/', 'PROJECT_ROOT/', line)
            
            # 行番号や位置情報を正規化
            line = re.sub(r':\d+:\d+', ':LINE:COL', line)
            
            normalized_lines.append(line.strip())
        
        return '\n'.join(normalized_lines)
    
    def compare_test_results(self, result1: Dict[str, Any], result2: Dict[str, Any]) -> Dict[str, Any]:
        """2つのテスト結果を比較"""
        version1 = result1.get("version", "unknown")
        version2 = result2.get("version", "unknown")
        
        logger.info(f"CLI結果比較: {version1} vs {version2}")
        
        # 基本統計の比較
        stats_comparison = {
            "version1": {
                "version": version1,
                "total_tests": result1.get("total_tests", 0),
                "successful_tests": result1.get("successful_tests", 0),
                "success_rate": result1.get("success_rate", 0)
            },
            "version2": {
                "version": version2,
                "total_tests": result2.get("total_tests", 0),
                "successful_tests": result2.get("successful_tests", 0),
                "success_rate": result2.get("success_rate", 0)
            }
        }
        
        # 個別テスト結果の比較
        results1 = {r["test_id"]: r for r in result1.get("results", [])}
        results2 = {r["test_id"]: r for r in result2.get("results", [])}
        
        test_comparisons = []
        all_test_ids = set(results1.keys()) | set(results2.keys())
        
        for test_id in sorted(all_test_ids):
            comparison = self.compare_single_test(
                test_id,
                results1.get(test_id),
                results2.get(test_id)
            )
            test_comparisons.append(comparison)
        
        # 互換性分析
        compatibility_analysis = self.analyze_compatibility(test_comparisons)
        
        return {
            "comparison_timestamp": datetime.now().isoformat(),
            "versions": {
                "version1": version1,
                "version2": version2
            },
            "stats_comparison": stats_comparison,
            "test_comparisons": test_comparisons,
            "compatibility_analysis": compatibility_analysis
        }
    
    def compare_single_test(self, test_id: str, result1: Optional[Dict], result2: Optional[Dict]) -> Dict[str, Any]:
        """単一テストの比較"""
        comparison = {
            "test_id": test_id,
            "status": "unknown",
            "differences": [],
            "compatibility": "unknown"
        }
        
        if result1 is None and result2 is None:
            comparison["status"] = "both_missing"
            comparison["compatibility"] = "incomparable"
        elif result1 is None:
            comparison["status"] = "missing_in_v1"
            comparison["compatibility"] = "new_in_v2"
        elif result2 is None:
            comparison["status"] = "missing_in_v2"
            comparison["compatibility"] = "removed_in_v2"
        else:
            comparison["status"] = "both_present"
            comparison["compatibility"] = self.determine_cli_compatibility(result1, result2)
            comparison["differences"] = self.find_cli_differences(result1, result2)
        
        return comparison
    
    def determine_cli_compatibility(self, result1: Dict, result2: Dict) -> str:
        """CLI互換性を判定"""
        success1 = result1.get("success", False)
        success2 = result2.get("success", False)
        returncode1 = result1.get("returncode", -1)
        returncode2 = result2.get("returncode", -1)
        
        # 成功状態の比較
        if success1 and success2:
            # 両方成功の場合、出力内容を比較
            if self.are_cli_outputs_equivalent(result1, result2):
                return "compatible"
            else:
                return "output_changed"
        elif success1 and not success2:
            return "regression"
        elif not success1 and success2:
            return "improvement"
        elif returncode1 == returncode2:
            return "both_failed_same"
        else:
            return "both_failed_different"
    
    def are_cli_outputs_equivalent(self, result1: Dict, result2: Dict) -> bool:
        """CLI出力が等価かどうかを判定"""
        # 標準出力の比較
        stdout1 = self.normalize_cli_output(result1.get("stdout", ""))
        stdout2 = self.normalize_cli_output(result2.get("stdout", ""))
        
        # JSON出力がある場合はJSONを比較
        json1 = result1.get("parsed_json")
        json2 = result2.get("parsed_json")
        
        if json1 is not None and json2 is not None:
            return self.compare_json_outputs(json1, json2)
        
        # テキスト出力の比較
        return self.compare_text_outputs(stdout1, stdout2)
    
    def compare_json_outputs(self, json1: Dict, json2: Dict) -> bool:
        """JSON出力を比較"""
        # 主要フィールドのみを比較（メタデータは除外）
        important_fields = [
            "file_info", "scale_metrics", "complexity_metrics",
            "table_output", "query_results", "partial_content_result"
        ]
        
        for field in important_fields:
            if field in json1 or field in json2:
                if json1.get(field) != json2.get(field):
                    return False
        
        return True
    
    def compare_text_outputs(self, text1: str, text2: str) -> bool:
        """テキスト出力を比較"""
        # 行ごとに比較
        lines1 = [line.strip() for line in text1.split('\n') if line.strip()]
        lines2 = [line.strip() for line in text2.split('\n') if line.strip()]
        
        # 行数が大きく異なる場合は非互換
        if abs(len(lines1) - len(lines2)) > max(len(lines1), len(lines2)) * 0.1:
            return False
        
        # 主要な内容行を比較
        content_lines1 = [line for line in lines1 if not self.is_metadata_line(line)]
        content_lines2 = [line for line in lines2 if not self.is_metadata_line(line)]
        
        return content_lines1 == content_lines2
    
    def is_metadata_line(self, line: str) -> bool:
        """メタデータ行かどうかを判定"""
        metadata_patterns = [
            r'^\s*$',  # 空行
            r'analysis\s+completed',
            r'processing\s+file',
            r'total\s+time',
            r'elapsed',
            r'timestamp',
        ]
        
        for pattern in metadata_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        
        return False
    
    def find_cli_differences(self, result1: Dict, result2: Dict) -> List[Dict[str, Any]]:
        """CLI結果の詳細な差分を検出"""
        differences = []
        
        # 基本情報の差分
        basic_fields = ["returncode", "success", "expected_success"]
        for field in basic_fields:
            if result1.get(field) != result2.get(field):
                differences.append({
                    "type": "basic_info",
                    "field": field,
                    "value1": result1.get(field),
                    "value2": result2.get(field)
                })
        
        # 出力の差分
        stdout1 = result1.get("stdout", "")
        stdout2 = result2.get("stdout", "")
        
        if stdout1 != stdout2:
            differences.append({
                "type": "stdout",
                "field": "stdout",
                "value1": self.truncate_output(stdout1),
                "value2": self.truncate_output(stdout2)
            })
        
        stderr1 = result1.get("stderr", "")
        stderr2 = result2.get("stderr", "")
        
        if stderr1 != stderr2:
            differences.append({
                "type": "stderr",
                "field": "stderr",
                "value1": self.truncate_output(stderr1),
                "value2": self.truncate_output(stderr2)
            })
        
        # JSON出力の差分
        json1 = result1.get("parsed_json")
        json2 = result2.get("parsed_json")
        
        if json1 != json2:
            differences.append({
                "type": "json_output",
                "field": "parsed_json",
                "value1": json1,
                "value2": json2
            })
        
        return differences
    
    def truncate_output(self, output: str, max_length: int = 500) -> str:
        """出力を切り詰め"""
        if len(output) <= max_length:
            return output
        return output[:max_length] + "... (truncated)"
    
    def analyze_compatibility(self, test_comparisons: List[Dict]) -> Dict[str, Any]:
        """互換性を分析"""
        total_tests = len(test_comparisons)
        
        compatibility_counts = {}
        for comparison in test_comparisons:
            compat = comparison["compatibility"]
            compatibility_counts[compat] = compatibility_counts.get(compat, 0) + 1
        
        compatible_tests = compatibility_counts.get("compatible", 0)
        compatibility_rate = compatible_tests / total_tests if total_tests > 0 else 0
        
        # CLI特有の互換性レベル判定（MCPより緩い基準）
        if compatibility_rate >= 0.90:
            compatibility_level = "excellent"
        elif compatibility_rate >= 0.80:
            compatibility_level = "good"
        elif compatibility_rate >= 0.70:
            compatibility_level = "acceptable"
        elif compatibility_rate >= 0.60:
            compatibility_level = "poor"
        else:
            compatibility_level = "critical"
        
        return {
            "total_tests": total_tests,
            "compatibility_counts": compatibility_counts,
            "compatible_tests": compatible_tests,
            "compatibility_rate": compatibility_rate,
            "compatibility_level": compatibility_level,
            "summary": self.generate_cli_compatibility_summary(compatibility_counts, compatibility_rate)
        }
    
    def generate_cli_compatibility_summary(self, counts: Dict[str, int], rate: float) -> str:
        """CLI互換性サマリーを生成"""
        summary_parts = []
        
        if counts.get("compatible", 0) > 0:
            summary_parts.append(f"{counts['compatible']}個のCLIコマンドが完全互換")
        
        if counts.get("output_changed", 0) > 0:
            summary_parts.append(f"{counts['output_changed']}個のコマンドで出力が変更")
        
        if counts.get("regression", 0) > 0:
            summary_parts.append(f"{counts['regression']}個のコマンドでリグレッション")
        
        if counts.get("improvement", 0) > 0:
            summary_parts.append(f"{counts['improvement']}個のコマンドで改善")
        
        summary = "、".join(summary_parts)
        summary += f"。全体のCLI互換性率: {rate:.1%}"
        
        return summary
    
    def generate_html_report(self, comparison: Dict[str, Any], output_file: str):
        """HTMLレポートを生成"""
        html_content = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CLI互換性比較レポート</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat-box {{ background-color: #e8f4f8; padding: 15px; border-radius: 5px; flex: 1; }}
        .compatibility-excellent {{ background-color: #d4edda; }}
        .compatibility-good {{ background-color: #d1ecf1; }}
        .compatibility-acceptable {{ background-color: #fff3cd; }}
        .compatibility-poor {{ background-color: #f8d7da; }}
        .compatibility-critical {{ background-color: #f5c6cb; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .compatible {{ background-color: #d4edda; }}
        .output-changed {{ background-color: #fff3cd; }}
        .regression {{ background-color: #f8d7da; }}
        .improvement {{ background-color: #d1ecf1; }}
        .both-failed-same {{ background-color: #f5c6cb; }}
        .both-failed-different {{ background-color: #f5c6cb; }}
        .code {{ font-family: monospace; background-color: #f8f9fa; padding: 2px 4px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>CLI互換性比較レポート</h1>
        <p>生成日時: {comparison['comparison_timestamp']}</p>
        <p>比較バージョン: {comparison['versions']['version1']} vs {comparison['versions']['version2']}</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <h3>{comparison['versions']['version1']}</h3>
            <p>総テスト数: {comparison['stats_comparison']['version1']['total_tests']}</p>
            <p>成功テスト数: {comparison['stats_comparison']['version1']['successful_tests']}</p>
            <p>成功率: {comparison['stats_comparison']['version1']['success_rate']:.1%}</p>
        </div>
        <div class="stat-box">
            <h3>{comparison['versions']['version2']}</h3>
            <p>総テスト数: {comparison['stats_comparison']['version2']['total_tests']}</p>
            <p>成功テスト数: {comparison['stats_comparison']['version2']['successful_tests']}</p>
            <p>成功率: {comparison['stats_comparison']['version2']['success_rate']:.1%}</p>
        </div>
    </div>
    
    <div class="stat-box compatibility-{comparison['compatibility_analysis']['compatibility_level']}">
        <h3>CLI互換性分析</h3>
        <p>{comparison['compatibility_analysis']['summary']}</p>
        <p>互換性レベル: {comparison['compatibility_analysis']['compatibility_level']}</p>
    </div>
    
    <h2>詳細CLIテスト比較</h2>
    <table>
        <thead>
            <tr>
                <th>テストID</th>
                <th>コマンド</th>
                <th>互換性</th>
                <th>差分数</th>
                <th>ステータス</th>
            </tr>
        </thead>
        <tbody>
"""
        
        for test_comp in comparison['test_comparisons']:
            compatibility_class = test_comp['compatibility'].replace('_', '-')
            # テストIDからコマンドタイプを推定
            test_id = test_comp['test_id']
            command_type = test_id.split('-')[1] if '-' in test_id else "unknown"
            
            html_content += f"""
            <tr class="{compatibility_class}">
                <td><span class="code">{test_comp['test_id']}</span></td>
                <td>{command_type}</td>
                <td>{test_comp['compatibility']}</td>
                <td>{len(test_comp.get('differences', []))}</td>
                <td>{test_comp['status']}</td>
            </tr>
"""
        
        html_content += """
        </tbody>
    </table>
    
    <h2>互換性カテゴリ説明</h2>
    <ul>
        <li><strong>compatible</strong>: 完全に互換性あり</li>
        <li><strong>output_changed</strong>: 成功するが出力が変更</li>
        <li><strong>regression</strong>: 以前は成功していたが失敗するように</li>
        <li><strong>improvement</strong>: 以前は失敗していたが成功するように</li>
        <li><strong>both_failed_same</strong>: 両方失敗、同じエラーコード</li>
        <li><strong>both_failed_different</strong>: 両方失敗、異なるエラーコード</li>
    </ul>
</body>
</html>
"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"CLI HTMLレポートを生成しました: {output_file}")
    
    def generate_winmerge_files(self, comparison: Dict[str, Any], output_dir: str):
        """WinMerge用比較ファイルを生成"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        version1 = comparison['versions']['version1']
        version2 = comparison['versions']['version2']
        
        # バージョン1と2の結果をまとめたファイル
        v1_content = []
        v2_content = []
        
        for test_comp in comparison['test_comparisons']:
            test_id = test_comp['test_id']
            v1_content.append(f"=== {test_id} ===")
            v2_content.append(f"=== {test_id} ===")
            
            if test_comp['status'] == 'both_present':
                # 差分がある場合の詳細を追加
                if test_comp.get('differences'):
                    for diff in test_comp['differences']:
                        if diff['type'] == 'stdout':
                            v1_content.append(f"STDOUT:\n{diff['value1']}")
                            v2_content.append(f"STDOUT:\n{diff['value2']}")
                        elif diff['type'] == 'stderr':
                            v1_content.append(f"STDERR:\n{diff['value1']}")
                            v2_content.append(f"STDERR:\n{diff['value2']}")
                        else:
                            v1_content.append(f"{diff['field']}: {diff['value1']}")
                            v2_content.append(f"{diff['field']}: {diff['value2']}")
                else:
                    v1_content.append("(同一出力)")
                    v2_content.append("(同一出力)")
            elif test_comp['status'] == 'missing_in_v1':
                v1_content.append("(テスト未実行)")
                v2_content.append("(テスト実行済み)")
            elif test_comp['status'] == 'missing_in_v2':
                v1_content.append("(テスト実行済み)")
                v2_content.append("(テスト未実行)")
            
            v1_content.append("")
            v2_content.append("")
        
        # ファイルに保存
        v1_file = output_path / f"cli_results_{version1}.txt"
        v2_file = output_path / f"cli_results_{version2}.txt"
        
        with open(v1_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(v1_content))
        
        with open(v2_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(v2_content))
        
        logger.info(f"CLI WinMerge用ファイルを生成しました: {v1_file}, {v2_file}")
    
    def compare_versions(self, version1: str, version2: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """バージョン間のCLI比較を実行"""
        # テスト結果を読み込み
        result1 = self.load_test_results(version1)
        result2 = self.load_test_results(version2)
        
        if result1 is None or result2 is None:
            raise ValueError("CLIテスト結果の読み込みに失敗しました")
        
        # 比較を実行
        comparison = self.compare_test_results(result1, result2)
        
        # 出力ディレクトリを設定
        if output_dir is None:
            output_dir = self.test_dir / "comparison" / f"cli_{version1}_vs_{version2}"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 比較結果を保存
        comparison_file = output_dir / "cli_comparison.json"
        with open(comparison_file, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)
        
        # HTMLレポートを生成
        html_file = output_dir / "cli_comparison_report.html"
        self.generate_html_report(comparison, str(html_file))
        
        # WinMerge用ファイルを生成
        self.generate_winmerge_files(comparison, str(output_dir / "winmerge"))
        
        return comparison

def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="CLI結果比較")
    parser.add_argument("version1", help="比較元バージョン")
    parser.add_argument("version2", help="比較先バージョン")
    parser.add_argument("--output", help="出力ディレクトリ")
    parser.add_argument("--verbose", action="store_true", help="詳細ログ出力")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    comparator = CLIResultComparator()
    
    try:
        comparison = comparator.compare_versions(args.version1, args.version2, args.output)
        
        compatibility_rate = comparison['compatibility_analysis']['compatibility_rate']
        logger.info(f"CLI比較完了: 互換性率 {compatibility_rate:.1%}")
        
        if compatibility_rate < 0.7:
            logger.warning("CLI互換性率が低いです。詳細レポートを確認してください。")
        
    except Exception as e:
        logger.error(f"CLI比較エラー: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())