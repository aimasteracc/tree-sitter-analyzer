"""Row helpers for Python formatter output."""

from typing import Any

_DOCSTRING_MISMATCH_WORDS = ("bark", "meow", "fetch", "purr")
_VISIBILITY_SYMBOLS = {
    "public": "🔓",
    "private": "🔒",
    "protected": "🔐",
    "magic": "✨",
}


def format_python_method_row(formatter: Any, method: dict[str, Any]) -> str:
    """Format a method table row for Python"""
    name = str(method.get("name", ""))
    signature = formatter.format_python_signature(method)
    visibility = _method_visibility(method, name)
    vis_symbol = formatter.get_python_visibility_symbol(visibility)
    lines_str = _method_lines(method)
    complexity = method.get("complexity_score", 0)
    doc = formatter.clean_csv_text(
        formatter.extract_doc_summary(str(method.get("docstring", "")))
    )
    decorators = method.get("modifiers", []) or method.get("decorators", [])
    decorator_str = formatter.format_decorators(decorators)
    async_indicator = "🔄" if method.get("is_async", False) else ""

    return f"| {name}{async_indicator} | {signature} | {vis_symbol} | {lines_str} | 5-6 | {complexity} | {decorator_str} | {doc} |"


def _method_visibility(method: dict[str, Any], name: str) -> str:
    if name.startswith("__") and name.endswith("__"):
        return "magic"
    if name.startswith("_"):
        return "private"
    return method.get("visibility", "public")


def _method_lines(method: dict[str, Any]) -> str:
    line_range = method.get("line_range") or {}
    if isinstance(line_range, dict) and line_range:
        return f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    return f"{method.get('start_line', 0)}-{method.get('end_line', 0)}"


def get_python_visibility_symbol(visibility: str) -> str:
    """Get Python visibility symbol"""
    return _VISIBILITY_SYMBOLS.get(visibility, "🔓")


def format_python_class_method_row(formatter: Any, method: dict[str, Any]) -> str:
    """Format a method table row for class-specific sections"""
    name = str(method.get("name", ""))
    signature = formatter.format_python_signature_compact(method)
    vis_symbol = _class_method_visibility_symbol(method, name)
    lines_str = _class_method_lines(method)
    complexity = method.get("complexity_score", 0)
    doc = _class_method_doc(formatter, method)
    modifier_str = _class_method_modifier(method)
    return f"| {name} | {signature}{modifier_str} | {vis_symbol} | {lines_str} | {complexity} | {doc} |"


def _class_method_visibility_symbol(method: dict[str, Any], name: str) -> str:
    visibility = _method_visibility(method, name)
    return "+" if visibility == "public" or visibility == "magic" else "-"


def _class_method_lines(method: dict[str, Any]) -> str:
    line_range = method.get("line_range") or {}
    if isinstance(line_range, dict):
        return f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    return "0-0"


def _class_method_doc(formatter: Any, method: dict[str, Any]) -> str:
    docstring = method.get("docstring", "")
    method_name = method.get("name", "")
    if not _has_docstring_text(docstring):
        return "-"

    docstring_text = str(docstring).strip()
    if method_name == "__init__" and _looks_like_other_method_doc(docstring_text):
        return "-"
    return formatter.extract_doc_summary(docstring_text)


def _has_docstring_text(docstring: Any) -> bool:
    return bool(
        docstring and str(docstring).strip() and str(docstring).strip() != "None"
    )


def _looks_like_other_method_doc(docstring_text: str) -> bool:
    return any(word in docstring_text.lower() for word in _DOCSTRING_MISMATCH_WORDS)


def _class_method_modifier(method: dict[str, Any]) -> str:
    modifiers = ["static"] if method.get("is_static", False) else []
    return f" [{', '.join(modifiers)}]" if modifiers else ""
