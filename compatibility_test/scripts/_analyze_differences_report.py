"""Report rendering helpers for analyze_differences."""

from datetime import datetime
from pathlib import Path
from typing import Any


def build_report_path(
    project_root: Path,
    version_a: str,
    version_b: str,
    smart_compare: bool,
) -> Path:
    """Build the timestamped report path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = (
        "smart_comparison_report"
        if smart_compare
        else f"difference_analysis_{version_a}_vs_{version_b}"
    )
    return (
        project_root
        / "compatibility_test"
        / "reports"
        / f"{report_name}_{timestamp}.md"
    )


def build_analysis_report_lines(
    analysis_results: dict[str, Any],
    version_a: str,
    version_b: str,
    smart_compare: bool,
) -> list[str]:
    """Render the Markdown report lines."""
    report_title = (
        f"# {'スマート' if smart_compare else ''}"
        f"差分分析レポート: v{version_a} vs v{version_b}"
    )
    report_lines = _summary_lines(report_title, analysis_results, version_a, version_b)
    report_lines.extend(_missing_file_lines(analysis_results, version_a, version_b))
    report_lines.extend(["## ファイル別詳細分析", ""])
    report_lines.extend(_file_analysis_lines(analysis_results))
    return report_lines


def write_report(report_file: Path, report_lines: list[str]) -> str:
    """Write the report and return its string path."""
    report_content = "\n".join(report_lines)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(report_content, encoding="utf-8")
    print(f"📄 差分分析レポートを生成しました: {report_file}")
    return str(report_file)


def _summary_lines(
    report_title: str,
    analysis_results: dict[str, Any],
    version_a: str,
    version_b: str,
) -> list[str]:
    summary = analysis_results["summary"]
    return [
        report_title,
        "",
        f"- **分析実施日**: {analysis_results['analysis_date']}",
        f"- **分析対象**: v{version_a} → v{version_b}",
        "",
        "## 分析サマリー",
        "",
        "| 項目 | 値 |",
        "| :--- | :--- |",
        f"| 総ファイル数 | {summary['total_files']} |",
        f"| 一致ファイル | {summary['identical_files']} |",
        f"| 差分ファイル | {summary['different_files']} |",
        f"| 破壊的変更 | {summary['breaking_changes']} |",
        f"| 非破壊的変更 | {summary['non_breaking_changes']} |",
        f"| パフォーマンス変更 | {summary['performance_changes']} |",
        "",
    ]


def _missing_file_lines(
    analysis_results: dict[str, Any], version_a: str, version_b: str
) -> list[str]:
    missing = analysis_results.get("missing_files", {})
    if not missing.get("missing_in_a") and not missing.get("missing_in_b"):
        return []

    lines = ["## 欠落ファイル", ""]
    lines.extend(_one_missing_side_lines(missing.get("missing_in_b"), version_b))
    lines.extend(_one_missing_side_lines(missing.get("missing_in_a"), version_a))
    return lines


def _one_missing_side_lines(missing_files: list[str] | None, version: str) -> list[str]:
    if not missing_files:
        return []
    lines = [f"### v{version}で欠落:", ""]
    lines.extend(f"- {filename}" for filename in missing_files)
    lines.append("")
    return lines


def _file_analysis_lines(analysis_results: dict[str, Any]) -> list[str]:
    lines = []
    for filename, analysis in analysis_results.get("file_analysis", {}).items():
        lines.extend([f"### {filename}", ""])
        lines.extend(_single_analysis_lines(analysis))
        lines.append("")
    return lines


def _single_analysis_lines(analysis: dict[str, Any]) -> list[str]:
    analysis_type = analysis.get("type")
    if analysis_type == "identical":
        return ["✅ **完全一致**"]
    if analysis_type == "smart_json_comparison":
        return _smart_json_analysis_lines(analysis)
    if analysis_type == "json_comparison":
        return _json_comparison_lines(analysis)
    if analysis_type == "text_difference":
        return _text_difference_lines(analysis)
    return []


def _smart_json_analysis_lines(analysis: dict[str, Any]) -> list[str]:
    if analysis["is_identical_normalized"]:
        lines = [
            "- **Raw比較**: 差異あり",
            "- **正規化比較**: 一致",
            "- **最終判定**: 実質的に同一 ✅",
        ]
        if analysis["raw_diff"]:
            lines.extend(["\n**詳細分析:**"])
            ignored_diffs = analysis["raw_diff"].get("values_changed", {})
            lines.extend(
                f"- {key}: {values['old_value']} vs {values['new_value']}"
                for key, values in ignored_diffs.items()
            )
        return lines

    lines = [
        "- **Raw比較**: 差異あり",
        "- **正規化比較**: 差異あり",
        "- **最終判定**: 差分あり ❌",
    ]
    if analysis["normalized_diff"]:
        lines.extend(
            [
                "\n**正規化後の差分:**",
                f"```json\n{analysis['normalized_diff'].to_json(indent=2)}\n```",
            ]
        )
    return lines


def _json_comparison_lines(analysis: dict[str, Any]) -> list[str]:
    differences = analysis.get("differences", [])
    if not differences:
        return ["✅ **構造的差分なし**"]

    lines = [f"⚠️ **{len(differences)}件の差分を検出**", ""]
    for severity, title in [
        ("high", "#### 🚨 高重要度の変更:"),
        ("medium", "#### ⚠️ 中重要度の変更:"),
        ("low", "#### ℹ️ 低重要度の変更:"),
    ]:
        severity_lines = _severity_section_lines(differences, severity, title)
        if severity_lines:
            lines.extend(severity_lines)
    return lines


def _severity_section_lines(
    differences: list[dict[str, Any]], severity: str, title: str
) -> list[str]:
    severity_diffs = [diff for diff in differences if diff.get("severity") == severity]
    if not severity_diffs:
        return []

    lines = [title]
    for diff in severity_diffs:
        if diff["type"] == "performance_change":
            lines.append(_performance_diff_line(diff))
        else:
            lines.extend(_generic_diff_lines(diff, include_values=severity == "high"))
    lines.append("")
    return lines


def _generic_diff_lines(diff: dict[str, Any], include_values: bool) -> list[str]:
    lines = [f"- **{diff['type']}**: `{diff['path']}`"]
    if include_values and "old_value" in diff and "new_value" in diff:
        lines.append(f"  - 変更前: `{diff['old_value']}`")
        lines.append(f"  - 変更後: `{diff['new_value']}`")
    return lines


def _performance_diff_line(diff: dict[str, Any]) -> str:
    change_pct = diff.get("change_percent", 0)
    direction = "向上" if change_pct < 0 else "悪化"
    return f"- **パフォーマンス{direction}**: `{diff['path']}` ({change_pct:+.1f}%)"


def _text_difference_lines(analysis: dict[str, Any]) -> list[str]:
    added = analysis.get("added_lines", 0)
    removed = analysis.get("removed_lines", 0)
    return [f"📝 **テキスト差分**: +{added}行, -{removed}行"]
