"""Detailed class view helpers for the legacy table formatter."""

from __future__ import annotations

from typing import Any

from ._legacy_table_formatter_common import convert_visibility, extract_doc_summary


def append_detail_fields_section(
    lines: list[str],
    fields: list[dict[str, Any]],
    include_javadoc: bool,
) -> None:
    """Append the detailed class fields section."""
    if not fields:
        return

    lines.append("### Fields")
    lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
    lines.append("|------|------|-----|-----------|------|-----|")

    for field in fields:
        lines.append(format_detail_field_row(field, include_javadoc))
    lines.append("")


def format_detail_field_row(field: dict[str, Any], include_javadoc: bool) -> str:
    """Format a detailed class field row."""
    name_field = str(field.get("name", ""))
    type_field = str(field.get("type", ""))
    visibility = convert_visibility(str(field.get("visibility", "")))
    modifiers = ",".join(field.get("modifiers", []))
    line_num = field.get("line_range", {}).get("start", 0)
    doc = extract_doc_summary(str(field.get("javadoc", ""))) if include_javadoc else "-"

    return (
        f"| {name_field} | {type_field} | {visibility} | {modifiers} | "
        f"{line_num} | {doc} |"
    )


def detail_method_groups(
    methods: list[dict[str, Any]],
) -> list[tuple[list[dict[str, Any]], str]]:
    """Group detailed methods by legacy visibility order."""
    return [
        ([m for m in methods if m.get("visibility", "") == "public"], "Public Methods"),
        (
            [m for m in methods if m.get("visibility", "") == "protected"],
            "Protected Methods",
        ),
        (
            [m for m in methods if m.get("visibility", "") == "package"],
            "Package Methods",
        ),
        (
            [m for m in methods if m.get("visibility", "") == "private"],
            "Private Methods",
        ),
    ]


def append_detailed_methods_section(
    lines: list[str],
    title: str,
    methods: list[dict[str, Any]],
    format_method_row: Any,
    *,
    constructor: bool = False,
) -> None:
    """Append a detailed method section."""
    if not methods:
        return

    lines.append(f"### {title}")
    if constructor:
        lines.append("| Constructor | Signature | Vis | Lines | Cx | Doc |")
        lines.append("|-------------|-----------|-----|-------|----|----|")
    else:
        lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
        lines.append("|--------|-----------|-----|-------|----|----|")

    for method in methods:
        lines.append(format_method_row(method))
    lines.append("")
