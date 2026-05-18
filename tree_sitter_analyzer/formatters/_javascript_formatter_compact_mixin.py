"""Compact table rendering for the JavaScript formatter."""

from typing import Any

from ._javascript_formatter_full_mixin import (
    _list_or_empty,
    _title,
    _trim_trailing_blank_lines,
)


class JavaScriptTableFormatterCompactMixin:
    """Compact-format rendering helpers."""

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for JavaScript - matches golden master format"""
        lines: list[str] = []
        methods = _list_or_empty(data.get("methods", []))

        lines.append(f"# {_title(data, _list_or_empty(data.get('classes', [])))}")
        lines.append("")
        _append_info_section(lines, methods)
        _append_methods_section(lines, methods, self._create_compact_signature)

        _trim_trailing_blank_lines(lines)
        return "\n".join(lines)

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature for JavaScript"""
        params = method.get("parameters", [])
        if not params or isinstance(params, str):
            return "():unknown"

        param_types = []
        for param in params:
            if isinstance(param, dict):
                param_types.append(param.get("type", "Any"))
            else:
                param_types.append("Any")

        params_str = ",".join(param_types)
        return_type = method.get("return_type", "unknown")
        return f"({params_str}):{return_type}"


def _append_info_section(lines: list[str], methods: list[dict[str, Any]]) -> None:
    lines.append("## Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append("| Package |  |")
    lines.append(f"| Methods | {len(methods)} |")
    lines.append("| Fields | 0 |")
    lines.append("")


def _append_methods_section(
    lines: list[str],
    methods: list[dict[str, Any]],
    signature_builder: Any,
) -> None:
    if not methods:
        return

    lines.append("## Methods")
    lines.append("| Method | Sig | V | L | Cx | Doc |")
    lines.append("|--------|-----|---|---|----|----|")
    for method in methods:
        lines.append(_compact_method_row(method, signature_builder))


def _compact_method_row(method: dict[str, Any], signature_builder: Any) -> str:
    name = str(method.get("name", ""))
    signature = signature_builder(method)
    line_range = method.get("line_range", {})
    lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    complexity = method.get("complexity_score", 1)
    return f"| {name} | {signature} | + | {lines_str} | {complexity} | - |"
