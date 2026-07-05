"""Compact table helpers for the legacy table formatter."""

from __future__ import annotations

from typing import Any

from .common import get_visibility_symbol


def compact_table_header(
    package_name: str,
    classes: list[dict[str, Any]],
    file_path: str = "",
) -> str:
    """Build the legacy compact-table header.

    When *classes* is empty (e.g. Bash, Go scripts without class constructs)
    fall back to the filename stem derived from *file_path* instead of the
    placeholder string ``"Unknown"`` that confused agents.  When *file_path*
    is also absent the header is simply empty, which is still better than
    mis-labelling every class-less file as "Unknown".
    """
    if classes:
        class_name = str(classes[0].get("name", "Unknown"))
    else:
        # No class: derive a sensible header from the file name.
        if file_path:
            basename = file_path.replace("\\", "/").split("/")[-1]
            # Strip the extension (only the last dot-segment).
            class_name = basename.rsplit(".", 1)[0] if "." in basename else basename
        else:
            class_name = ""

    if package_name and class_name:
        return f"{package_name}.{class_name}"
    if class_name:
        return class_name
    if package_name:
        return package_name
    return ""


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
