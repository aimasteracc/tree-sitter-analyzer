"""Batch analysis helpers for analyze_differences."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

FileAnalyzer = Callable[[Path, Path], dict[str, Any]]


def generate_normalized_outputs(analyzer: Any) -> None:
    """Generate normalized files when requested."""
    if not analyzer.generate_normalized:
        return

    print(f"  ...正規化ファイルを出力中: v{analyzer.version_a}-normalized")
    analyzer.json_comparator.generate_normalized_files(
        analyzer.version_a_dir, analyzer.version_a_normalized_dir
    )
    print(f"  ...正規化ファイルを出力中: v{analyzer.version_b}-normalized")
    analyzer.json_comparator.generate_normalized_files(
        analyzer.version_b_dir, analyzer.version_b_normalized_dir
    )
    print("  ✅ 正規化ファイルの生成が完了しました。")


def validate_version_dirs(analyzer: Any) -> bool:
    """Validate that both version result directories exist."""
    if not analyzer.version_a_dir.exists():
        print(
            f"❌ v{analyzer.version_a} の結果ディレクトリが見つかりません: "
            f"{analyzer.version_a_dir}"
        )
        return False

    if not analyzer.version_b_dir.exists():
        print(
            f"❌ v{analyzer.version_b} の結果ディレクトリが見つかりません: "
            f"{analyzer.version_b_dir}"
        )
        return False

    return True


def build_initial_results(analyzer: Any, common_files: set[str]) -> dict[str, Any]:
    """Build the analysis result envelope."""
    files_a = set(analyzer.version_a_files)
    files_b = set(analyzer.version_b_files)
    return {
        "analysis_date": datetime.now().isoformat(),
        "version_a": analyzer.version_a,
        "version_b": analyzer.version_b,
        "file_analysis": {},
        "summary": {
            "total_files": len(common_files),
            "identical_files": 0,
            "different_files": 0,
            "breaking_changes": 0,
            "non_breaking_changes": 0,
            "performance_changes": 0,
        },
        "missing_files": {
            "missing_in_b": list(files_a - files_b),
            "missing_in_a": list(files_b - files_a),
        },
    }


def analyze_common_files(
    analyzer: Any,
    common_files: set[str],
    analyze_json: FileAnalyzer,
    analyze_text: FileAnalyzer,
) -> dict[str, Any]:
    """Analyze every common output file and update summary counts."""
    results = build_initial_results(analyzer, common_files)

    for filename in sorted(common_files):
        print(f"  📄 分析中: {filename}")
        analysis = _analyze_one_file(analyzer, filename, analyze_json, analyze_text)
        results["file_analysis"][filename] = analysis
        update_summary(results["summary"], analysis)

    return results


def update_summary(summary: dict[str, int], analysis: dict[str, Any]) -> None:
    """Update aggregate counters for one file analysis."""
    if _is_identical_analysis(analysis):
        summary["identical_files"] += 1
        return

    summary["different_files"] += 1
    _update_change_severity_counts(summary, analysis)
    _update_performance_change_count(summary, analysis)


def _analyze_one_file(
    analyzer: Any,
    filename: str,
    analyze_json: FileAnalyzer,
    analyze_text: FileAnalyzer,
) -> dict[str, Any]:
    file_a = analyzer.version_a_files[filename]
    file_b = analyzer.version_b_files[filename]
    if filename.endswith(".json"):
        return analyze_json(file_a, file_b)
    return analyze_text(file_a, file_b)


def _is_identical_analysis(analysis: dict[str, Any]) -> bool:
    return analysis.get("type") == "identical" or analysis.get(
        "is_identical_normalized"
    )


def _update_change_severity_counts(
    summary: dict[str, int], analysis: dict[str, Any]
) -> None:
    if analysis.get("severity") == "high":
        summary["breaking_changes"] += 1
    elif analysis.get("severity") in ["medium", "low"]:
        summary["non_breaking_changes"] += 1


def _update_performance_change_count(
    summary: dict[str, int], analysis: dict[str, Any]
) -> None:
    if analysis.get("type") == "json_comparison":
        summary["performance_changes"] += sum(
            1
            for diff in analysis.get("differences", [])
            if diff.get("type") == "performance_change"
        )
    elif analysis.get("type") == "smart_json_comparison":
        if not analysis.get("is_identical_raw") and analysis.get(
            "is_identical_normalized"
        ):
            summary["performance_changes"] += 1
