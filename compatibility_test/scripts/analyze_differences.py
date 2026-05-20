#!/usr/bin/env python3
"""
tree-sitter-analyzer 出力差分分析スクリプト

使用方法:
    python compatibility_test/scripts/analyze_differences.py --version-a 1.9.2 --version-b 1.9.3
"""

from pathlib import Path
from typing import Any

from compatibility_test.scripts._analyze_differences_analysis import (
    analyze_common_files,
    generate_normalized_outputs,
    validate_version_dirs,
)
from compatibility_test.scripts._analyze_differences_json import (
    analyze_text_difference,
    compare_json_structure,
    compare_performance_metrics,
    determine_field_severity,
    determine_severity,
    load_json_pair,
)
from compatibility_test.scripts._analyze_differences_report import (
    build_analysis_report_lines,
    build_report_path,
    write_report,
)
from compatibility_test.scripts._analyze_differences_setup import (
    build_argument_parser,
    configure_smart_comparison,
    initial_analysis_results,
    run_analysis_cli,
)


class DifferenceAnalyzer:
    def __init__(
        self,
        version_a: str,
        version_b: str,
        project_root: str = None,
        config_path: str = None,
        smart_compare: bool = False,
        generate_normalized: bool = False,
    ):
        self.version_a = version_a
        self.version_b = version_b
        self.project_root = (
            Path(project_root) if project_root else Path(__file__).parent.parent.parent
        )
        self.smart_compare = smart_compare
        self.generate_normalized = generate_normalized

        self.results_dir = self.project_root / "compatibility_test" / "results"
        self.version_a_dir = self.results_dir / f"v{version_a}"
        self.version_b_dir = self.results_dir / f"v{version_b}"

        configure_smart_comparison(self, config_path)
        self.analysis_results = initial_analysis_results()

    def analyze_json_differences(self, file_a: Path, file_b: Path) -> dict[str, Any]:
        """JSONファイルの構造的差分を分析"""
        if self.smart_compare:
            report = self.json_comparator.compare_with_report(file_a, file_b)

            severity = "none"
            if not report["is_identical_normalized"]:
                severity = "high"  # 正規化後に差分があれば破壊的変更とみなす
            elif not report["is_identical_raw"]:
                severity = "low"  # 正規化後に一致すれば非破壊的変更

            return {
                "type": "smart_json_comparison",
                "raw_diff": report["raw_diff"],
                "normalized_diff": report["normalized_diff"],
                "is_identical_raw": report["is_identical_raw"],
                "is_identical_normalized": report["is_identical_normalized"],
                "severity": severity,
            }

        loaded = load_json_pair(file_a, file_b)
        if isinstance(loaded, dict) and loaded.get("type") in {
            "json_parse_error",
            "file_read_error",
        }:
            return loaded
        data_a, data_b = loaded

        differences = []

        # 構造的差分を検出
        structural_diffs = compare_json_structure(
            data_a, data_b, "", determine_field_severity
        )
        differences.extend(structural_diffs)

        # パフォーマンスメトリクスの変化を検出
        perf_diffs = compare_performance_metrics(data_a, data_b)
        differences.extend(perf_diffs)

        return {
            "type": "json_comparison",
            "differences": differences,
            "severity": determine_severity(differences),
        }

    def analyze_text_differences(self, file_a: Path, file_b: Path) -> dict[str, Any]:
        """テキストファイルの差分を分析"""
        return analyze_text_difference(file_a, file_b, self.version_a, self.version_b)

    def analyze_all_differences(self) -> dict[str, Any]:
        """全ての差分を分析"""
        print(f"🔍 v{self.version_a} と v{self.version_b} の差分を分析中...")
        generate_normalized_outputs(self)

        if not validate_version_dirs(self):
            return {}

        self.version_a_files = {
            file.name: file for file in self.version_a_dir.iterdir() if file.is_file()
        }
        self.version_b_files = {
            file.name: file for file in self.version_b_dir.iterdir() if file.is_file()
        }
        common_files = set(self.version_a_files) & set(self.version_b_files)

        return analyze_common_files(
            self,
            common_files,
            self.analyze_json_differences,
            self.analyze_text_differences,
        )

    def generate_analysis_report(self, analysis_results: dict[str, Any]) -> str:
        """分析レポートを生成"""
        report_file = build_report_path(
            self.project_root, self.version_a, self.version_b, self.smart_compare
        )
        report_lines = build_analysis_report_lines(
            analysis_results, self.version_a, self.version_b, self.smart_compare
        )
        return write_report(report_file, report_lines)


def main():
    """メイン実行関数"""
    parser = build_argument_parser()
    args = parser.parse_args()
    run_analysis_cli(args, DifferenceAnalyzer)


if __name__ == "__main__":
    main()
