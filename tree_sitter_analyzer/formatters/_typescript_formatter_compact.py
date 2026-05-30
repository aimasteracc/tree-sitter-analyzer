"""Compact table output for the TypeScript formatter."""

from typing import Any

from ._typescript_formatter_helpers import (
    create_compact_signature,
    doc_summary,
    line_range_text,
    trim_trailing_blank_lines,
    typescript_title,
)


def format_typescript_compact_table(formatter: Any, data: dict[str, Any]) -> str:
    """Compact table format for TypeScript."""
    methods = data.get("methods", []) or data.get("functions", [])
    fields = data.get("fields", []) or data.get("variables", [])
    lines = [f"# {typescript_title(data, strip_declaration_suffix=False)}", ""]

    _append_info(lines, data, methods, fields)
    _append_methods(formatter, lines, methods)
    trim_trailing_blank_lines(lines)
    return "\n".join(lines)


def _append_info(
    lines: list[str],
    data: dict[str, Any],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> None:
    package_name = (data.get("package") or {}).get("name", "")
    lines.append("## Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Package | {package_name} |")
    lines.append(f"| Methods | {len(methods)} |")
    lines.append(f"| Fields | {len(fields)} |")
    lines.append("")


def _append_methods(
    formatter: Any, lines: list[str], methods: list[dict[str, Any]]
) -> None:
    if not methods:
        return

    lines.append("## Methods")
    lines.append("| Method | Sig | V | L | Cx | Doc |")
    lines.append("|--------|-----|---|---|----|----|")
    for method in methods:
        lines.append(_method_row(formatter, method))
    lines.append("")


def _method_row(formatter: Any, method: dict[str, Any]) -> str:
    visibility = formatter.convert_visibility(str(method.get("visibility", "public")))
    line_range = method.get("line_range", {})
    return (
        f"| {str(method.get('name', ''))} | {create_compact_signature(method)} | "
        f"{visibility} | {line_range_text(line_range)} | "
        f"{method.get('complexity_score', 0)} | {doc_summary(formatter, method)} |"
    )
