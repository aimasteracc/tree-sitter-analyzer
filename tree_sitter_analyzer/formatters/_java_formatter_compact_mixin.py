"""Compact table rendering for the Java formatter."""

from typing import Any

from ._java_formatter_full_mixin import (
    _java_title,
    _trim_trailing_blank_lines,
)


class JavaTableFormatterCompactMixin:
    """Compact-format and compact signature helpers."""

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Java"""
        lines: list[str] = []
        package_name = (data.get("package") or {}).get("name", "")
        classes = data.get("classes", [])
        stats = data.get("statistics") or {}

        lines.append(f"# {_java_title(self, data, package_name, classes)}")
        lines.append("")
        _append_info(lines, package_name, stats)
        _append_methods(lines, data.get("methods", []), self)

        _trim_trailing_blank_lines(lines)
        return "\n".join(lines)

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature for Java"""
        params = method.get("parameters", [])
        param_types = [
            shorten_type(
                param.get("type", "O") if isinstance(param, dict) else str(param)
            )
            for param in params
        ]
        params_str = ",".join(param_types)
        return_type = shorten_type(method.get("return_type", "void"))

        return f"({params_str}):{return_type}"

    # Public alias for companion module
    create_compact_signature = _create_compact_signature


_TYPE_MAPPING = {
    "String": "S",
    "int": "i",
    "long": "l",
    "double": "d",
    "boolean": "b",
    "void": "void",
    "Object": "O",
    "Exception": "E",
    "SQLException": "SE",
    "IllegalArgumentException": "IAE",
    "RuntimeException": "RE",
}


def _append_info(lines: list[str], package_name: str, stats: dict[str, Any]) -> None:
    lines.append("## Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    if package_name:
        lines.append(f"| Package | {package_name} |")
    lines.append(f"| Methods | {stats.get('method_count', 0)} |")
    lines.append(f"| Fields | {stats.get('field_count', 0)} |")
    lines.append("")


def _append_methods(
    lines: list[str], methods: list[dict[str, Any]], formatter: Any
) -> None:
    if not methods:
        return

    lines.append("## Methods")
    lines.append("| Method | Sig | V | L | Cx | Doc |")
    lines.append("|--------|-----|---|---|----|----|")
    for method in methods:
        lines.append(_compact_method_row(method, formatter))
    lines.append("")


def _compact_method_row(method: dict[str, Any], formatter: Any) -> str:
    name = str(method.get("name", ""))
    signature = formatter.create_compact_signature(method)
    visibility = formatter.convert_visibility(str(method.get("visibility", "")))
    line_range = method.get("line_range", {})
    lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    complexity = method.get("complexity_score", 1)
    doc = formatter.clean_csv_text(
        formatter.extract_doc_summary(str(method.get("javadoc", "")))
    )

    return (
        f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"
    )


def _shorten_array_type(type_name: str) -> str:
    base_type = type_name.replace("[]", "")
    if base_type:
        return str(_TYPE_MAPPING.get(base_type, base_type[0].upper()) + "[]")
    return "O[]"


def shorten_type(type_name: Any) -> str:
    """Shorten type name for Java tables."""
    if type_name is None:
        return "O"

    if not isinstance(type_name, str):
        type_name = str(type_name)

    if "Map<" in type_name:
        return str(
            type_name.replace("Map<", "M<")
            .replace("String", "S")
            .replace("Object", "O")
        )

    if "List<" in type_name:
        return str(type_name.replace("List<", "L<").replace("String", "S"))

    if "[]" in type_name:
        return _shorten_array_type(type_name)

    return str(_TYPE_MAPPING.get(type_name, type_name))


JavaTableFormatterCompactMixin._shorten_type = staticmethod(shorten_type)  # type: ignore[attr-defined]  # noqa: SLF001
