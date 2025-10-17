#!/usr/bin/env python3
"""
MCP結果比較スクリプト

このスクリプトは、異なるバージョンのMCPテスト結果を比較し、
互換性レポートを生成します。

機能:
- 2つのバージョンのMCPテスト結果を比較
- 詳細な差分分析
- HTMLレポート生成
- WinMerge用比較ファイル生成
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MCPResultComparator:
    """MCP結果比較クラス"""
    
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.result_dir = self.test_dir / "result" / "mcp"
        
    def load_test_results(self, version: str) -> Optional[Dict[str, Any]]:
        """指定バージョンのテスト結果を読み込み"""
        version_dir = self.result_dir / f"v-{version}"
        summary_file = version_dir / "mcp_test_summary.json"
        
        if not summary_file.exists():
            logger.error(f"テスト結果が見つかりません: {summary_file}")
            return None
        
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"テスト結果の読み込みエラー: {e}")
            return None
    
    def compare_test_results(self, result1: Dict[str, Any], result2: Dict[str, Any]) -> Dict[str, Any]:
        """2つのテスト結果を比較"""
        version1 = result1.get("version", "unknown")
        version2 = result2.get("version", "unknown")
        
        logger.info(f"MCP結果比較: {version1} vs {version2}")
        
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
            comparison["compatibility"] = self.determine_compatibility(result1, result2)
            comparison["differences"] = self.find_differences(result1, result2)
        
        return comparison
    
    def determine_compatibility(self, result1: Dict, result2: Dict) -> str:
        """互換性を判定"""
        success1 = result1.get("success", False)
        success2 = result2.get("success", False)
        
        if success1 and success2:
            # 両方成功の場合、結果の内容を比較
            if self.are_results_equivalent(result1.get("result", {}), result2.get("result", {})):
                return "compatible"
            else:
                return "output_changed"
        elif success1 and not success2:
            return "regression"
        elif not success1 and success2:
            return "improvement"
        else:
            return "both_failed"
    
    def are_results_equivalent(self, result1: Dict, result2: Dict) -> bool:
        """結果が等価かどうかを判定"""
        # 型チェック - 辞書でない場合は直接比較
        if not isinstance(result1, dict) or not isinstance(result2, dict):
            return result1 == result2
        
        # エラーの場合
        if "error" in result1 or "error" in result2:
            return result1.get("error") == result2.get("error")
        
        # 主要フィールドの比較
        key_fields = ["file_info", "scale_metrics", "complexity_metrics", "table_output", "query_results"]
        
        for field in key_fields:
            if field in result1 or field in result2:
                if result1.get(field) != result2.get(field):
                    return False
        
        return True
    
    def find_differences(self, result1: Dict, result2: Dict) -> List[Dict[str, Any]]:
        """詳細な差分を検出"""
        differences = []
        
        # 成功状態の差分
        if result1.get("success") != result2.get("success"):
            differences.append({
                "type": "success_status",
                "field": "success",
                "value1": result1.get("success"),
                "value2": result2.get("success")
            })
        
        # 結果内容の差分
        result_data1 = result1.get("result", {})
        result_data2 = result2.get("result", {})
        
        differences.extend(self.compare_dict_recursive(result_data1, result_data2, "result"))
        
        return differences
    
    def compare_dict_recursive(self, dict1: Dict, dict2: Dict, path: str = "") -> List[Dict[str, Any]]:
        """辞書を再帰的に比較"""
        differences = []
        
        # 型チェック - 辞書でない場合は直接比較
        if not isinstance(dict1, dict) or not isinstance(dict2, dict):
            if dict1 != dict2:
                differences.append({
                    "type": "changed",
                    "field": path,
                    "value1": dict1,
                    "value2": dict2
                })
            return differences
        
        all_keys = set(dict1.keys()) | set(dict2.keys())
        
        for key in all_keys:
            current_path = f"{path}.{key}" if path else key
            
            if key not in dict1:
                differences.append({
                    "type": "added",
                    "field": current_path,
                    "value1": None,
                    "value2": dict2[key]
                })
            elif key not in dict2:
                differences.append({
                    "type": "removed",
                    "field": current_path,
                    "value1": dict1[key],
                    "value2": None
                })
            elif dict1[key] != dict2[key]:
                if isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
                    differences.extend(self.compare_dict_recursive(dict1[key], dict2[key], current_path))
                else:
                    differences.append({
                        "type": "changed",
                        "field": current_path,
                        "value1": dict1[key],
                        "value2": dict2[key]
                    })
        
        return differences
    
    def analyze_compatibility(self, test_comparisons: List[Dict]) -> Dict[str, Any]:
        """互換性を分析"""
        total_tests = len(test_comparisons)
        
        compatibility_counts = {}
        for comparison in test_comparisons:
            compat = comparison["compatibility"]
            compatibility_counts[compat] = compatibility_counts.get(compat, 0) + 1
        
        compatible_tests = compatibility_counts.get("compatible", 0)
        compatibility_rate = compatible_tests / total_tests if total_tests > 0 else 0
        
        # 互換性レベルを判定
        if compatibility_rate >= 0.95:
            compatibility_level = "excellent"
        elif compatibility_rate >= 0.90:
            compatibility_level = "good"
        elif compatibility_rate >= 0.80:
            compatibility_level = "acceptable"
        elif compatibility_rate >= 0.70:
            compatibility_level = "poor"
        else:
            compatibility_level = "critical"
        
        return {
            "total_tests": total_tests,
            "compatibility_counts": compatibility_counts,
            "compatible_tests": compatible_tests,
            "compatibility_rate": compatibility_rate,
            "compatibility_level": compatibility_level,
            "summary": self.generate_compatibility_summary(compatibility_counts, compatibility_rate)
        }
    
    def generate_compatibility_summary(self, counts: Dict[str, int], rate: float) -> str:
        """互換性サマリーを生成"""
        summary_parts = []
        
        if counts.get("compatible", 0) > 0:
            summary_parts.append(f"{counts['compatible']}個のテストが完全互換")
        
        if counts.get("output_changed", 0) > 0:
            summary_parts.append(f"{counts['output_changed']}個のテストで出力が変更")
        
        if counts.get("regression", 0) > 0:
            summary_parts.append(f"{counts['regression']}個のテストでリグレッション")
        
        if counts.get("improvement", 0) > 0:
            summary_parts.append(f"{counts['improvement']}個のテストで改善")
        
        summary = "、".join(summary_parts)
        summary += f"。全体の互換性率: {rate:.1%}"
        
        return summary
    
    def generate_html_report(self, comparison: Dict[str, Any], output_file: str):
        """HTMLレポートを生成"""
        html_content = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP互換性比較レポート</title>
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
        .both-failed {{ background-color: #f5c6cb; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>MCP互換性比較レポート</h1>
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
        <h3>互換性分析</h3>
        <p>{comparison['compatibility_analysis']['summary']}</p>
        <p>互換性レベル: {comparison['compatibility_analysis']['compatibility_level']}</p>
    </div>
    
    <h2>詳細テスト比較</h2>
    <table>
        <thead>
            <tr>
                <th>テストID</th>
                <th>互換性</th>
                <th>差分数</th>
                <th>ステータス</th>
            </tr>
        </thead>
        <tbody>
"""
        
        for test_comp in comparison['test_comparisons']:
            compatibility_class = test_comp['compatibility'].replace('_', '-')
            html_content += f"""
            <tr class="{compatibility_class}">
                <td>{test_comp['test_id']}</td>
                <td>{test_comp['compatibility']}</td>
                <td>{len(test_comp.get('differences', []))}</td>
                <td>{test_comp['status']}</td>
            </tr>
"""
        
        html_content += """
        </tbody>
    </table>
</body>
</html>
"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"HTMLレポートを生成しました: {output_file}")
    
    def generate_winmerge_files(self, comparison: Dict[str, Any], output_dir: str):
        """WinMerge用比較ファイルを生成"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        version1 = comparison['versions']['version1']
        version2 = comparison['versions']['version2']
        
        # バージョン1の結果をまとめたファイル
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
                        v1_content.append(f"{diff['field']}: {diff['value1']}")
                        v2_content.append(f"{diff['field']}: {diff['value2']}")
                else:
                    v1_content.append("(同一)")
                    v2_content.append("(同一)")
            elif test_comp['status'] == 'missing_in_v1':
                v1_content.append("(テスト未実行)")
                v2_content.append("(テスト実行済み)")
            elif test_comp['status'] == 'missing_in_v2':
                v1_content.append("(テスト実行済み)")
                v2_content.append("(テスト未実行)")
            
            v1_content.append("")
            v2_content.append("")
        
        # ファイルに保存
        v1_file = output_path / f"mcp_results_{version1}.txt"
        v2_file = output_path / f"mcp_results_{version2}.txt"
        
        with open(v1_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(v1_content))
        
        with open(v2_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(v2_content))
        
        logger.info(f"WinMerge用ファイルを生成しました: {v1_file}, {v2_file}")
    
    def compare_versions(self, version1: str, version2: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """バージョン間の比較を実行"""
        # テスト結果を読み込み
        result1 = self.load_test_results(version1)
        result2 = self.load_test_results(version2)
        
        if result1 is None or result2 is None:
            raise ValueError("テスト結果の読み込みに失敗しました")
        
        # 比較を実行
        comparison = self.compare_test_results(result1, result2)
        
        # 出力ディレクトリを設定
        if output_dir is None:
            output_dir = self.test_dir / "comparison" / f"mcp_{version1}_vs_{version2}"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 比較結果を保存
        comparison_file = output_dir / "mcp_comparison.json"
        with open(comparison_file, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)
        
        # HTMLレポートを生成
        html_file = output_dir / "mcp_comparison_report.html"
        self.generate_html_report(comparison, str(html_file))
        
        # WinMerge用ファイルを生成
        self.generate_winmerge_files(comparison, str(output_dir / "winmerge"))
        
        return comparison

def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP結果比較")
    parser.add_argument("--version1", default="1.6.1", help="比較元バージョン")
    parser.add_argument("--version2", default="1.9.2", help="比較先バージョン")
    parser.add_argument("--output", help="出力ディレクトリ")
    parser.add_argument("--html", action="store_true", help="HTMLレポートを生成")
    parser.add_argument("--verbose", action="store_true", help="詳細ログ出力")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    comparator = MCPResultComparator()
    
    try:
        comparison = comparator.compare_versions(args.version1, args.version2, args.output)
        
        compatibility_rate = comparison['compatibility_analysis']['compatibility_rate']
        logger.info(f"比較完了: 互換性率 {compatibility_rate:.1%}")
        
        if compatibility_rate < 0.8:
            logger.warning("互換性率が低いです。詳細レポートを確認してください。")
        
    except Exception as e:
        logger.error(f"比較エラー: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())