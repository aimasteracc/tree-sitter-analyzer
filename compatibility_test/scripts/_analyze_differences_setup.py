"""Setup and CLI helpers for analyze_differences."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from compatibility_test.utils.smart_json_comparator import SmartJsonComparator


def configure_smart_comparison(analyzer: Any, config_path: str | None) -> None:
    """Configure optional smart JSON comparison paths and comparator."""
    if not analyzer.smart_compare and not analyzer.generate_normalized:
        return

    analyzer.config_path = (
        Path(config_path)
        if config_path
        else analyzer.project_root
        / "compatibility_test"
        / "config"
        / "comparison_config.json"
    )
    if not analyzer.config_path.exists():
        raise FileNotFoundError(
            f"比較設定ファイルが見つかりません: {analyzer.config_path}"
        )

    analyzer.json_comparator = SmartJsonComparator(analyzer.config_path)
    if analyzer.generate_normalized:
        analyzer.version_a_normalized_dir = (
            analyzer.results_dir / f"v{analyzer.version_a}-normalized"
        )
        analyzer.version_b_normalized_dir = (
            analyzer.results_dir / f"v{analyzer.version_b}-normalized"
        )


def initial_analysis_results() -> dict[str, list[Any]]:
    """Return the legacy analysis-results buckets."""
    return {
        "breaking_changes": [],
        "non_breaking_changes": [],
        "bugs_or_unintended": [],
        "identical_outputs": [],
        "performance_changes": [],
    }


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="tree-sitter-analyzer 出力差分分析")
    parser.add_argument(
        "--version-a", required=True, help="比較元バージョン (例: 1.9.2)"
    )
    parser.add_argument(
        "--version-b", required=True, help="比較先バージョン (例: 1.9.3)"
    )
    parser.add_argument(
        "--project-root", help="プロジェクトルートパス (デフォルト: 自動検出)"
    )
    parser.add_argument("--output-json", help="分析結果をJSONファイルに出力")
    parser.add_argument(
        "--smart-compare", action="store_true", help="スマート比較モードを有効化"
    )
    parser.add_argument(
        "--generate-normalized",
        action="store_true",
        help="正規化されたJSONファイルを出力",
    )
    parser.add_argument("--config", help="比較設定ファイルのパス")
    return parser


def run_analysis_cli(args: argparse.Namespace, analyzer_factory: Any) -> None:
    """Run the CLI flow for parsed arguments."""
    analyzer = analyzer_factory(
        version_a=args.version_a,
        version_b=args.version_b,
        project_root=args.project_root,
        config_path=args.config,
        smart_compare=args.smart_compare,
        generate_normalized=args.generate_normalized,
    )

    try:
        analysis_results = analyzer.analyze_all_differences()
        if not analysis_results:
            print("❌ 分析に失敗しました")
            sys.exit(1)

        report_file = analyzer.generate_analysis_report(analysis_results)
        write_optional_json_output(args.output_json, analysis_results)
        print_completion_summary(analysis_results["summary"], report_file)
    except Exception as exc:
        print(f"❌ 分析エラー: {exc}")
        sys.exit(1)


def write_optional_json_output(
    output_json: str | None, analysis_results: dict[str, Any]
) -> None:
    """Write optional JSON output requested by the CLI."""
    if not output_json:
        return

    json_file = Path(output_json)
    json_file.write_text(
        json.dumps(analysis_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"📄 JSON結果を保存しました: {json_file}")


def print_completion_summary(summary: dict[str, int], report_file: str) -> None:
    """Print the CLI completion summary."""
    print("\n" + "=" * 60)
    print("🎉 差分分析完了!")
    print(f"📊 総ファイル数: {summary['total_files']}")
    print(f"📊 一致: {summary['identical_files']}, 差分: {summary['different_files']}")
    print(
        f"📊 破壊的変更: {summary['breaking_changes']}, "
        f"非破壊的変更: {summary['non_breaking_changes']}"
    )
    print(f"📋 詳細レポート: {report_file}")
