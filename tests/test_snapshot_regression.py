#!/usr/bin/env python3
"""
スナップショット回帰テストシステム

PyPiパッケージのベースラインと現在の実装を比較し、
回帰検出とレポート生成を行います。
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import pytest

# プロジェクトルートを追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SnapshotComparator:
    """スナップショット比較クラス"""
    
    def __init__(self, config_path: str = "test_snapshots/config/comparison_rules.json"):
        """初期化"""
        self.project_root = project_root
        self.config_path = self.project_root / config_path
        self.test_config_path = self.project_root / "test_snapshots/config/test_cases.json"
        self.comparison_rules = self._load_comparison_rules()
        self.test_config = self._load_test_config()
        self.differences = []
        self.summary = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "critical_issues": 0
        }
    
    def _load_comparison_rules(self) -> Dict[str, Any]:
        """比較ルール設定を読み込み"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"比較ルール設定の読み込みに失敗: {e}")
            raise
    
    def _load_test_config(self) -> Dict[str, Any]:
        """テスト設定を読み込み"""
        try:
            with open(self.test_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"テスト設定の読み込みに失敗: {e}")
            raise
    
    def _normalize_value(self, value: Any) -> Any:
        """値の正規化"""
        if isinstance(value, float):
            return round(value, 3)
        elif isinstance(value, dict):
            return {k: self._normalize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._normalize_value(v) for v in value]
        return value
    
    def _compare_values(self, baseline_val: Any, current_val: Any, field_path: str) -> Optional[Dict[str, Any]]:
        """値の比較"""
        rules = self.comparison_rules["comparison_rules"]
        
        # 無視フィールドのチェック
        if any(ignore_field in field_path for ignore_field in rules["ignore_fields"]):
            return None
        
        # 値の正規化
        baseline_val = self._normalize_value(baseline_val)
        current_val = self._normalize_value(current_val)
        
        # 厳密比較フィールド
        if field_path in rules["strict_fields"]:
            if baseline_val != current_val:
                return {
                    "type": "strict_mismatch",
                    "field": field_path,
                    "baseline": baseline_val,
                    "current": current_val,
                    "severity": "critical"
                }
        
        # 許容範囲フィールド
        elif field_path in rules["tolerance_fields"]:
            tolerance_config = rules["tolerance_fields"][field_path]
            
            if isinstance(baseline_val, (int, float)) and isinstance(current_val, (int, float)):
                if tolerance_config["type"] == "percentage":
                    threshold = abs(baseline_val * tolerance_config["threshold"] / 100)
                    if abs(baseline_val - current_val) > threshold:
                        return {
                            "type": "tolerance_exceeded",
                            "field": field_path,
                            "baseline": baseline_val,
                            "current": current_val,
                            "threshold": threshold,
                            "severity": "warning"
                        }
                elif tolerance_config["type"] == "absolute":
                    if abs(baseline_val - current_val) > tolerance_config["threshold"]:
                        return {
                            "type": "tolerance_exceeded",
                            "field": field_path,
                            "baseline": baseline_val,
                            "current": current_val,
                            "threshold": tolerance_config["threshold"],
                            "severity": "warning"
                        }
        
        # 一般的な値比較
        else:
            if baseline_val != current_val:
                # 回帰検出の重要度判定
                severity = "info"
                if field_path in rules["regression_detection"]["critical_changes"]:
                    severity = "critical"
                elif field_path in rules["regression_detection"]["warning_changes"]:
                    severity = "warning"
                
                return {
                    "type": "value_mismatch",
                    "field": field_path,
                    "baseline": baseline_val,
                    "current": current_val,
                    "severity": severity
                }
        
        return None
    
    def _compare_structures(self, baseline: Dict[str, Any], current: Dict[str, Any], path: str = "") -> List[Dict[str, Any]]:
        """構造の再帰的比較"""
        differences = []
        
        # ベースラインにあってカレントにないキー
        for key in baseline:
            current_path = f"{path}.{key}" if path else key
            
            if key not in current:
                differences.append({
                    "type": "missing_key",
                    "field": current_path,
                    "baseline": baseline[key],
                    "current": None,
                    "severity": "critical"
                })
            else:
                if isinstance(baseline[key], dict) and isinstance(current[key], dict):
                    # 再帰的に比較
                    differences.extend(self._compare_structures(baseline[key], current[key], current_path))
                else:
                    # 値の比較
                    diff = self._compare_values(baseline[key], current[key], current_path)
                    if diff:
                        differences.append(diff)
        
        # カレントにあってベースラインにないキー
        for key in current:
            current_path = f"{path}.{key}" if path else key
            
            if key not in baseline:
                differences.append({
                    "type": "extra_key",
                    "field": current_path,
                    "baseline": None,
                    "current": current[key],
                    "severity": "warning"
                })
        
        return differences
    
    def compare_snapshots(self, baseline_file: Path, current_file: Path) -> Dict[str, Any]:
        """スナップショットファイルの比較"""
        try:
            # ファイル読み込み
            with open(baseline_file, 'r', encoding='utf-8') as f:
                baseline_data = json.load(f)
            
            with open(current_file, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
            
            # 比較実行
            differences = self._compare_structures(baseline_data, current_data)
            
            # 結果サマリー
            critical_count = sum(1 for d in differences if d["severity"] == "critical")
            warning_count = sum(1 for d in differences if d["severity"] == "warning")
            info_count = sum(1 for d in differences if d["severity"] == "info")
            
            result = {
                "baseline_file": str(baseline_file),
                "current_file": str(current_file),
                "comparison_timestamp": datetime.now().isoformat(),
                "differences": differences,
                "summary": {
                    "total_differences": len(differences),
                    "critical": critical_count,
                    "warning": warning_count,
                    "info": info_count,
                    "passed": len(differences) == 0
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"スナップショット比較エラー: {e}")
            return {
                "baseline_file": str(baseline_file),
                "current_file": str(current_file),
                "error": str(e),
                "summary": {"passed": False}
            }
    
    def run_all_comparisons(self) -> Dict[str, Any]:
        """全スナップショット比較実行"""
        logger.info("スナップショット回帰テスト開始")
        
        baseline_dir = Path(self.test_config["output_settings"]["baseline_dir"])
        current_dir = Path(self.test_config["output_settings"]["current_dir"])
        
        all_results = {
            "test_run_info": {
                "timestamp": datetime.now().isoformat(),
                "baseline_dir": str(baseline_dir),
                "current_dir": str(current_dir)
            },
            "results_by_language": {},
            "overall_summary": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "critical_issues": 0,
                "warnings": 0
            }
        }
        
        # 言語別にテスト実行
        for language, test_cases in self.test_config["test_cases"].items():
            logger.info(f"言語 {language} のテスト開始")
            
            language_results = {
                "test_cases": {},
                "summary": {
                    "total": len(test_cases),
                    "passed": 0,
                    "failed": 0
                }
            }
            
            for test_case in test_cases:
                test_name = test_case["name"]
                
                baseline_file = baseline_dir / language / f"{test_name}_baseline.json"
                current_file = current_dir / language / f"{test_name}_current.json"
                
                if baseline_file.exists() and current_file.exists():
                    result = self.compare_snapshots(baseline_file, current_file)
                    language_results["test_cases"][test_name] = result
                    
                    # 統計更新
                    all_results["overall_summary"]["total_tests"] += 1
                    
                    if result["summary"]["passed"]:
                        language_results["summary"]["passed"] += 1
                        all_results["overall_summary"]["passed"] += 1
                    else:
                        language_results["summary"]["failed"] += 1
                        all_results["overall_summary"]["failed"] += 1
                        
                        # 重要度別カウント
                        all_results["overall_summary"]["critical_issues"] += result["summary"].get("critical", 0)
                        all_results["overall_summary"]["warnings"] += result["summary"].get("warning", 0)
                
                else:
                    logger.warning(f"スナップショットファイルが見つかりません: {test_name}")
                    language_results["test_cases"][test_name] = {
                        "error": "スナップショットファイルが見つかりません",
                        "summary": {"passed": False}
                    }
                    language_results["summary"]["failed"] += 1
                    all_results["overall_summary"]["failed"] += 1
            
            all_results["results_by_language"][language] = language_results
        
        # 結果保存
        self._save_comparison_results(all_results)
        
        logger.info("スナップショット回帰テスト完了")
        return all_results
    
    def _save_comparison_results(self, results: Dict[str, Any]):
        """比較結果の保存"""
        diff_dir = Path(self.test_config["output_settings"]["diff_dir"])
        diff_dir.mkdir(parents=True, exist_ok=True)
        
        # 詳細結果保存
        detailed_file = diff_dir / "detailed" / f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        detailed_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(detailed_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        # サマリー保存
        summary_file = diff_dir / "summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(results["overall_summary"], f, ensure_ascii=False, indent=2)
        
        logger.info(f"比較結果保存完了: {detailed_file}")


class TestSnapshotRegression:
    """スナップショット回帰テストクラス"""
    
    @pytest.fixture(scope="class")
    def comparator(self):
        """比較器のフィクスチャ"""
        return SnapshotComparator()
    
    def test_snapshot_regression_all(self, comparator):
        """全スナップショット回帰テスト"""
        results = comparator.run_all_comparisons()
        
        # テスト結果の検証
        overall_summary = results["overall_summary"]
        
        # 重要な回帰がないことを確認
        assert overall_summary["critical_issues"] == 0, f"重要な回帰が検出されました: {overall_summary['critical_issues']}件"
        
        # 警告レベルの問題が多すぎないことを確認
        max_warnings = 10  # 許容する警告数
        assert overall_summary["warnings"] <= max_warnings, f"警告が多すぎます: {overall_summary['warnings']}件 (最大{max_warnings}件)"
        
        # 少なくとも一部のテストが成功していることを確認
        assert overall_summary["passed"] > 0, "成功したテストがありません"
        
        # 成功率の確認
        if overall_summary["total_tests"] > 0:
            success_rate = overall_summary["passed"] / overall_summary["total_tests"]
            min_success_rate = 0.8  # 最低80%の成功率
            assert success_rate >= min_success_rate, f"成功率が低すぎます: {success_rate:.2%} (最低{min_success_rate:.2%})"
    
    @pytest.mark.parametrize("language", ["java", "python", "javascript", "typescript", "html", "markdown"])
    def test_snapshot_regression_by_language(self, comparator, language):
        """言語別スナップショット回帰テスト"""
        results = comparator.run_all_comparisons()
        
        if language not in results["results_by_language"]:
            pytest.skip(f"言語 {language} のテストデータがありません")
        
        language_results = results["results_by_language"][language]
        
        # 言語固有の検証
        for test_name, test_result in language_results["test_cases"].items():
            if "error" in test_result:
                pytest.fail(f"{language}/{test_name}: {test_result['error']}")
            
            # 重要な回帰がないことを確認
            critical_count = test_result["summary"].get("critical", 0)
            assert critical_count == 0, f"{language}/{test_name}: 重要な回帰が検出されました ({critical_count}件)"


def main():
    """スタンドアロン実行用メイン関数"""
    comparator = SnapshotComparator()
    results = comparator.run_all_comparisons()
    
    # 結果表示
    print("\n=== スナップショット回帰テスト結果 ===")
    print(f"総テスト数: {results['overall_summary']['total_tests']}")
    print(f"成功: {results['overall_summary']['passed']}")
    print(f"失敗: {results['overall_summary']['failed']}")
    print(f"重要な問題: {results['overall_summary']['critical_issues']}")
    print(f"警告: {results['overall_summary']['warnings']}")
    
    if results['overall_summary']['critical_issues'] > 0:
        print("\n重要な回帰が検出されました！")
        sys.exit(1)
    elif results['overall_summary']['failed'] > 0:
        print("\n一部のテストが失敗しました。")
        sys.exit(1)
    else:
        print("\n全てのテストが成功しました。")
        sys.exit(0)


if __name__ == "__main__":
    main()