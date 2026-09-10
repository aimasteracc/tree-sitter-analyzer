"""Shared Kotlin AST helpers used by declaration extractors."""

from collections.abc import Callable
from typing import Any

from ..models import Import
from ..utils import log_error

_KOTLIN_DECISION_TYPES: frozenset[str] = frozenset(
    {
        "if_expression",
        "when_expression",
        "for_statement",
        "while_statement",
        "do_while_statement",
        "catch_block",
    }
)
_KOTLIN_LOGIC_OP_TOKENS: frozenset[str] = frozenset({"&&", "||"})


def _kotlin_import_parts(
    node: Any,
    get_node_text: Callable[..., str],
    raw_text: str,
) -> tuple[str, bool, str | None] | None:
    qualified: str | None = None
    is_wildcard = False
    alias: str | None = None
    saw_as = False
    for child in node.children:
        if child.type == "qualified_identifier":
            qualified = get_node_text(child)
        elif child.type == "*":
            is_wildcard = True
        elif child.type == "as":
            saw_as = True
        elif child.type == "identifier" and saw_as:
            alias = get_node_text(child)

    if qualified is not None:
        return qualified + (".*" if is_wildcard else ""), is_wildcard, alias
    parts = raw_text.split()
    if len(parts) < 2:
        return None
    name = parts[1].rstrip(";")
    return name, name.endswith(".*"), alias


def extract_import(node: Any, get_node_text: Callable[..., str]) -> Import | None:
    """Extract a Kotlin import from AST children with a text fallback."""
    try:
        raw_text = get_node_text(node)
        parts = _kotlin_import_parts(node, get_node_text, raw_text)
        if parts is None:
            return None
        name, is_wildcard, alias = parts
        return Import(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            language="kotlin",
            import_statement=raw_text,
            module_name=name,
            is_wildcard=is_wildcard,
            alias=alias,
        )
    except Exception as exc:
        log_error(f"Error extracting Kotlin import: {exc}")
        return None


def determine_visibility(modifiers_text: str) -> str:
    """Determine visibility from Kotlin modifiers text."""
    if "private" in modifiers_text:
        return "private"
    if "protected" in modifiers_text:
        return "protected"
    if "internal" in modifiers_text:
        return "internal"
    return "public"


def _kotlin_parameter_pair(
    parameter_node: Any, get_node_text: Callable[..., str]
) -> tuple[str, str]:
    """Return the first name and type found in a Kotlin parameter node."""
    param_name = ""
    param_type = ""
    for child in parameter_node.children:
        if child.type in ("simple_identifier", "identifier") and not param_name:
            param_name = get_node_text(child)
        elif "type" in child.type or child.type == "user_type":
            param_type = get_node_text(child)
    return param_name, param_type


def _parameter_text(
    node: Any,
    modifier: str,
    get_node_text: Callable[..., str],
) -> str | None:
    name, param_type = _kotlin_parameter_pair(node, get_node_text)
    if not name:
        return None
    value = f"{name}: {param_type or 'Any'}"
    return f"{modifier} {value}" if modifier else value


def extract_kotlin_parameters(
    node: Any, get_node_text: Callable[..., str]
) -> list[str]:
    """Extract ordered Kotlin parameters, including a preceding modifier."""
    params_node = next(
        (child for child in node.children if child.type == "function_value_parameters"),
        None,
    )
    if params_node is None:
        return []

    parameters: list[str] = []
    pending_modifier = ""
    for child in params_node.children:
        if child.type == "parameter_modifiers":
            pending_modifier = get_node_text(child)
            continue
        if child.type != "parameter":
            pending_modifier = ""
            continue
        value = _parameter_text(child, pending_modifier, get_node_text)
        if value is not None:
            parameters.append(value)
        pending_modifier = ""
    return parameters


def _kotlin_extension_receiver(
    node: Any, get_node_text: Callable[..., str]
) -> str | None:
    """Return the receiver in ``fun Type.name()``, including nullable types."""
    children = list(node.children)
    for index, child in enumerate(children):
        if child.type == "function_value_parameters":
            break
        if child.type not in ("user_type", "nullable_type"):
            continue
        if index + 1 < len(children) and children[index + 1].type == ".":
            return get_node_text(child)
    return None


def _declaration_name(node: Any) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        name_node = next(
            (child for child in node.children if child.type == "identifier"),
            None,
        )
    if name_node is None:
        return None
    try:
        return str(name_node.text.decode("utf-8", errors="replace"))
    except (AttributeError, UnicodeDecodeError):
        return str(name_node.text)


def _kotlin_owning_type(node: Any) -> tuple[str | None, bool]:
    """Return the nearest named class/object and companion-object status."""
    parent = node.parent
    in_companion = False
    for _ in range(256):
        if parent is None or parent.type == "source_file":
            return None, False
        if parent.type in ("function_declaration", "object_literal"):
            return None, False
        if parent.type == "companion_object":
            in_companion = True
        elif parent.type in ("class_declaration", "object_declaration"):
            name = _declaration_name(parent)
            return (name, in_companion) if name is not None else (None, False)
        parent = parent.parent
    return None, False


def _kotlin_expression_body_type(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Infer pinned literal types and report unknown expression bodies honestly."""
    body = next(
        (child for child in node.children if child.type == "function_body"),
        None,
    )
    if body is None or body.child_count == 0 or body.children[0].type != "=":
        return None
    if body.child_count < 2:
        return ""
    expression = body.children[1]
    if expression.type in ("string_literal", "multiline_string_literal"):
        return "String"
    if expression.type == "float_literal":
        return "Double"
    if expression.type == "number_literal":
        return "Int" if get_node_text(expression).isdigit() else ""
    if expression.type in ("boolean_literal", "identifier"):
        return "Boolean" if get_node_text(expression) in ("true", "false") else ""
    return ""


def _safe_children(node: Any) -> list[Any]:
    """Return a concrete child list, or an empty list for malformed nodes."""
    try:
        children = getattr(node, "children", None)
        return [] if children is None else list(children)
    except (TypeError, AttributeError):
        return []


def calculate_kotlin_complexity(node: Any) -> int:
    """Return one plus Kotlin decision nodes and boolean operator leaves."""
    decisions = 0
    stack = [node]
    while stack:
        current = stack.pop()
        children = _safe_children(current)
        is_leaf = not children
        node_type = getattr(current, "type", None)
        if not is_leaf and node_type in _KOTLIN_DECISION_TYPES:
            decisions += 1
        elif is_leaf and node_type in _KOTLIN_LOGIC_OP_TOKENS:
            decisions += 1
        stack.extend(children)
    return 1 + decisions
