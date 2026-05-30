"""Full table output for the TypeScript formatter."""

from typing import Any

from ._typescript_formatter_helpers import (
    doc_summary,
    field_type,
    format_method_row,
    format_typescript_modifiers,
    get_class_fields,
    get_class_methods,
    grouped_class_methods,
    line_range_text,
    trim_trailing_blank_lines,
    typescript_title,
)


def format_typescript_full_table(formatter: Any, data: dict[str, Any]) -> str:
    """Full table format for TypeScript."""
    lines: list[str] = [
        f"# {typescript_title(data, strip_declaration_suffix=True)}",
        "",
    ]

    classes = data.get("classes", [])
    methods = data.get("methods", []) or data.get("functions", [])
    fields = data.get("fields", []) or data.get("variables", [])

    _append_classes_overview(lines, classes, methods, fields)
    for class_info in classes:
        _append_class_section(formatter, lines, class_info, methods, fields)

    trim_trailing_blank_lines(lines)
    return "\n".join(lines)


def _append_classes_overview(
    lines: list[str],
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> None:
    if not classes:
        return

    lines.append("## Classes Overview")
    lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
    lines.append("|-------|------|------------|-------|---------|--------|")
    for class_info in classes:
        lines.append(_class_overview_row(class_info, methods, fields))
    lines.append("")


def _class_overview_row(
    class_info: dict[str, Any],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> str:
    line_range = class_info.get("line_range", {})
    class_methods = get_class_methods(methods, line_range)
    class_fields = get_class_fields(fields, line_range)
    return (
        f"| {str(class_info.get('name', 'Unknown'))} | "
        f"{_class_type(class_info)} | "
        f"{str(class_info.get('visibility', 'public'))} | "
        f"{line_range_text(line_range)} | {len(class_methods)} | "
        f"{len(class_fields)} |"
    )


def _append_class_section(
    formatter: Any,
    lines: list[str],
    class_info: dict[str, Any],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> None:
    class_name = str(class_info.get("name", "Unknown"))
    line_range = class_info.get("line_range", {})
    lines.append(f"## {class_name} ({line_range_text(line_range)})")

    class_methods = get_class_methods(methods, line_range)
    class_fields = get_class_fields(fields, line_range)
    _append_fields_section(formatter, lines, class_fields)
    _append_method_sections(formatter, lines, class_methods)


def _append_fields_section(
    formatter: Any, lines: list[str], class_fields: list[dict[str, Any]]
) -> None:
    if not class_fields:
        return

    lines.append("### Fields")
    lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
    lines.append("|------|------|-----|-----------|------|-----|")
    for field in class_fields:
        lines.append(_field_row(formatter, field))
    lines.append("")


def _field_row(formatter: Any, field: dict[str, Any]) -> str:
    visibility = formatter.convert_visibility(str(field.get("visibility", "public")))
    line_range = field.get("line_range", {})
    return (
        f"| {str(field.get('name', ''))} | {field_type(field)} | {visibility} | "
        f"{format_typescript_modifiers(field)} | {line_range.get('start', 0)} | "
        f"{doc_summary(formatter, field)} |"
    )


def _append_method_sections(
    formatter: Any, lines: list[str], class_methods: list[dict[str, Any]]
) -> None:
    grouped = grouped_class_methods(class_methods)
    _append_method_group(
        formatter, lines, "Constructors", "Constructor", grouped["constructors"]
    )
    _append_method_group(
        formatter, lines, "Public Methods", "Method", grouped["public"]
    )
    _append_method_group(
        formatter, lines, "Protected Methods", "Method", grouped["protected"]
    )
    _append_method_group(
        formatter, lines, "Private Methods", "Method", grouped["private"]
    )


def _append_method_group(
    formatter: Any,
    lines: list[str],
    title: str,
    label: str,
    methods: list[dict[str, Any]],
) -> None:
    if not methods:
        return

    lines.append(f"### {title}")
    lines.append(f"| {label} | Signature | Vis | Lines | Cx | Doc |")
    lines.append(
        "|-------------|-----------|-----|-------|----|----|"
        if label == "Constructor"
        else "|--------|-----------|-----|-------|----|----|"
    )
    for method in methods:
        lines.append(format_method_row(formatter, method))
    lines.append("")


def _class_type(class_info: dict[str, Any]) -> str:
    return str(class_info.get("class_type", "") or class_info.get("type", "class"))
