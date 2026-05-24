"""Compact table helpers for the legacy table formatter."""

from __future__ import annotations

from typing import Any

from ._legacy_table_formatter_common import get_visibility_symbol


def compact_table_header(
    package_name: str,
    classes: list[dict[str, Any]],
) -> str:
    """Build the legacy compact-table header."""
    class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
    if package_name:
        return f"{package_name}.{class_name}"
    return str(class_name)


def append_compact_info_section(
    lines: list[str],
    package_name: str,
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> None:
    """Append compact-table info section."""
    lines.append("## Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    if package_name:
        lines.append(f"| Package | {package_name} |")
    lines.append(f"| Methods | {len(methods)} |")
    lines.append(f"| Fields | {len(fields)} |")
    lines.append("")


def append_compact_methods_section(
    lines: list[str],
    methods: list[dict[str, Any]],
    format_method_row: Any,
) -> None:
    """Append compact-table methods section."""
    lines.append("## Methods")
    lines.append("| Method | Sig | V | L | Cx | Doc |")
    lines.append("|--------|-----|---|---|----|----|")
    for method in methods:
        lines.append(format_method_row(method))
    lines.append("")


def append_compact_fields_section(
    lines: list[str],
    fields: list[dict[str, Any]],
    abbreviate_type: Any,
) -> None:
    """Append compact-table fields section."""
    lines.append("## Fields")
    lines.append("| Field | Type | V | L |")
    lines.append("|-------|------|---|---|")
    for field in fields:
        lines.append(format_compact_field_row(field, abbreviate_type))
    lines.append("")


def format_compact_field_row(field: dict[str, Any], abbreviate_type: Any) -> str:
    """Format a compact-table field row."""
    name = str(field.get("name", ""))
    field_type = abbreviate_type(str(field.get("type", "Object")))
    visibility = get_visibility_symbol(str(field.get("visibility", "private")))
    line_range = field.get("line_range", {})
    start = line_range.get("start", 0) if line_range else 0

    return f"| {name} | {field_type} | {visibility} | {start} |"
