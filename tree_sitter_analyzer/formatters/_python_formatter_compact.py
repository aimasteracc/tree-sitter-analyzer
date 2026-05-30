"""Compact table output for the Python formatter."""

from typing import Any

from .._legacy_table_formatter_common import (
    trim_trailing_blank_lines as _trim_trailing_blank_lines,
)


def format_python_compact_table(formatter: Any, data: dict[str, Any]) -> str:
    """Compact table format for Python"""
    lines: list[str] = []
    module_name = _module_name(data.get("file_path", "Unknown"))
    classes = data.get("classes", [])

    _append_title(lines, classes, module_name)
    _append_info(lines, data, classes)
    _append_classes(lines, classes)
    _append_methods(lines, formatter, data.get("methods", []))
    _trim_trailing_blank_lines(lines)

    return "\n".join(lines)


def _module_name(file_path: Any) -> str:
    file_name = str(file_path).split("/")[-1].split("\\")[-1]
    return file_name.replace(".py", "").replace(".pyw", "").replace(".pyi", "")


def _append_title(
    lines: list[str], classes: list[dict[str, Any]], module_name: str
) -> None:
    if len(classes) == 1:
        class_name = classes[0].get("name", module_name)
        lines.append(f"# {class_name}")
    else:
        lines.append(f"# Module: {module_name}")
    lines.append("")


def _append_info(
    lines: list[str], data: dict[str, Any], classes: list[dict[str, Any]]
) -> None:
    stats = data.get("statistics") or {}
    lines.append("## Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Classes | {len(classes)} |")
    lines.append(f"| Methods | {stats.get('method_count', 0)} |")
    lines.append(f"| Fields | {stats.get('field_count', 0)} |")
    lines.append("")


def _append_classes(lines: list[str], classes: list[dict[str, Any]]) -> None:
    if not classes:
        return

    lines.append("## Classes")
    lines.append("| Class | Type | Lines |")
    lines.append("|-------|------|-------|")
    for class_info in classes:
        if class_info is None:
            continue
        lines.append(_compact_class_row(class_info))
    lines.append("")


def _compact_class_row(class_info: dict[str, Any]) -> str:
    name = str(class_info.get("name", "Unknown"))
    class_type = str(class_info.get("type", "class"))
    line_range = class_info.get("line_range") or {}
    lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    return f"| {name} | {class_type} | {lines_str} |"


def _append_methods(
    lines: list[str], formatter: Any, methods: list[dict[str, Any]]
) -> None:
    if not methods:
        return

    lines.append("## Methods")
    lines.append("| Method | Sig | V | L | Cx | Doc |")
    lines.append("|--------|-----|---|---|----|----|")
    for method in methods:
        lines.append(_compact_method_row(formatter, method))
    lines.append("")


def _compact_method_row(formatter: Any, method: dict[str, Any]) -> str:
    name = str(method.get("name", ""))
    signature = formatter.create_compact_signature(method)
    visibility = formatter.convert_visibility(str(method.get("visibility", "")))
    line_range = method.get("line_range") or {}
    lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    complexity = method.get("complexity_score", 0)
    doc = formatter.clean_csv_text(
        formatter.extract_doc_summary(str(method.get("javadoc", "")))
    )
    return (
        f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"
    )
