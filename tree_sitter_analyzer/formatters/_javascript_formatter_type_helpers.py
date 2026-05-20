"""Pure type helpers for the JavaScript formatter."""

from typing import Any

METHOD_FUNCTION_FLAGS = (
    ("is_constructor", "constructor"),
    ("is_getter", "getter"),
    ("is_setter", "setter"),
    ("is_static", "static method"),
)

METHOD_TYPE_FLAGS = (
    ("is_constructor", "constructor"),
    ("is_getter", "getter"),
    ("is_setter", "setter"),
    ("is_static", "static"),
    ("is_async", "async"),
)

EXPORT_TYPE_FLAGS = (
    ("is_default", "default"),
    ("is_named", "named"),
    ("is_all", "all"),
)

VARIABLE_KINDS = ("const", "let", "var")


def method_function_type(func: dict[str, Any]) -> str:
    """Return the full function type for a class method."""
    return _first_truthy_flag(func, METHOD_FUNCTION_FLAGS, default="method")


def method_type(method: dict[str, Any]) -> str:
    """Return the method type label."""
    return _first_truthy_flag(method, METHOD_TYPE_FLAGS, default="method")


def is_method(func: dict[str, Any]) -> bool:
    """Return whether a function mapping describes a class method."""
    return func.get("is_method", False) or func.get("class_name") is not None


def method_class(method: dict[str, Any]) -> str:
    """Return the class name for a method mapping."""
    return str(method.get("class_name", "Unknown"))


def infer_js_type(value: Any) -> str:
    """Infer JavaScript type from a literal-like value."""
    if value is None:
        return "undefined"

    value_str = str(value).strip()
    literal_type = _literal_js_type(value_str)
    if literal_type:
        return literal_type

    if _is_function_like(value_str):
        return "function"
    if value_str.startswith("class"):
        return "class"
    if value_str.replace(".", "").replace("-", "").isdigit():
        return "number"
    return "unknown"


def variable_kind(var: dict[str, Any]) -> str:
    """Return the JavaScript declaration kind for a variable mapping."""
    if var.get("is_constant", False):
        return "const"

    raw_text = str(var.get("raw_text", "")).strip()
    return _variable_kind_from_text(raw_text)


def export_type(export: Any) -> str:
    """Return the export type label."""
    if not isinstance(export, dict):
        return "unknown"
    return _first_truthy_flag(export, EXPORT_TYPE_FLAGS, default="unknown")


def _first_truthy_flag(
    data: dict[str, Any], flags: tuple[tuple[str, str], ...], *, default: str
) -> str:
    for flag, label in flags:
        if data.get(flag, False):
            return label
    return default


def _literal_js_type(value_str: str) -> str | None:
    if value_str in {"undefined", "null"}:
        return value_str
    if value_str in {"NaN", "Infinity", "-Infinity"}:
        return "number"
    if value_str.startswith(('"', "'", "`")):
        return "string"
    if value_str in {"true", "false"}:
        return "boolean"
    if value_str.startswith("[") and value_str.endswith("]"):
        return "array"
    if value_str.startswith("{") and value_str.endswith("}"):
        return "object"
    return None


def _is_function_like(value_str: str) -> bool:
    return (
        value_str.startswith("function")
        or value_str.startswith("async function")
        or value_str.startswith("new Function")
        or "=>" in value_str
    )


def _variable_kind_from_text(raw_text: str) -> str:
    for kind in VARIABLE_KINDS:
        if raw_text.startswith(kind):
            return kind
    return "unknown"
