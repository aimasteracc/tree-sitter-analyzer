"""CSV output for the TypeScript formatter."""

from typing import Any

from ._typescript_formatter_helpers import (
    create_csv_signature,
    doc_summary,
    field_type,
    line_range_text,
)


def format_typescript_csv(formatter: Any, data: dict[str, Any]) -> str:
    """CSV format for TypeScript."""
    lines = ["Type,Name,Signature,Visibility,Lines,Complexity,Doc"]
    _append_fields(
        formatter, lines, data.get("fields", []) or data.get("variables", [])
    )
    _append_methods(
        formatter, lines, data.get("methods", []) or data.get("functions", [])
    )
    lines.append("")
    return "\n".join(lines)


def _append_fields(
    formatter: Any, lines: list[str], fields: list[dict[str, Any]]
) -> None:
    for field in fields:
        name = str(field.get("name", ""))
        type_text = field_type(field)
        signature = f"{name}:{type_text}" if type_text else name
        visibility = str(field.get("visibility", "public"))
        line_range = field.get("line_range", {})
        doc = doc_summary(formatter, field)
        lines.append(
            f"Field,{name},{signature},{visibility},{line_range_text(line_range)},,{doc}"
        )


def _append_methods(
    formatter: Any, lines: list[str], methods: list[dict[str, Any]]
) -> None:
    for method in methods:
        signature = _escaped_signature(create_csv_signature(method))
        method_type = "Constructor" if method.get("is_constructor", False) else "Method"
        line_range = method.get("line_range", {})
        lines.append(
            f"{method_type},{str(method.get('name', ''))},{signature},"
            f"{str(method.get('visibility', 'public'))},{line_range_text(line_range)},"
            f"{method.get('complexity_score', 0)},{doc_summary(formatter, method)}"
        )


def _escaped_signature(signature: str) -> str:
    if "," in signature:
        return f'"{signature}"'
    return signature
