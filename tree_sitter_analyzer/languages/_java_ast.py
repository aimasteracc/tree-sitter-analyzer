"""Java AST utility helpers for signatures, modifiers, and complexity."""

import re
from collections.abc import Callable
from typing import Any

from ._complexity_logical import is_executable_logical_operator

_MODIFIER_KEYWORDS = frozenset(
    {
        "public",
        "private",
        "protected",
        "static",
        "final",
        "abstract",
        "synchronized",
        "volatile",
        "transient",
    }
)

_RETURN_TYPE_NODES = frozenset(
    {
        "type_identifier",
        "void_type",
        "primitive_type",
        "integral_type",
        "boolean_type",
        "floating_point_type",
        "array_type",
        "generic_type",
    }
)

_FIELD_TYPE_NODES = frozenset(
    {
        "type_identifier",
        "primitive_type",
        "integral_type",
        "generic_type",
        "boolean_type",
        "floating_point_type",
        "array_type",
    }
)

# tree-sitter-java node names (verified against the grammar): the switch is
# "switch_expression" (covers statement and expression forms), the ternary is
# "ternary_expression", and the do-while is "do_statement". Earlier this set
# used "switch_statement"/"conditional_expression" — node types the grammar
# never emits — so Java silently dropped every switch / ternary / do-while.
_JAVA_DECISION_NODES = frozenset(
    {
        "if_statement",
        "while_statement",
        "for_statement",
        "enhanced_for_statement",
        "do_statement",
        "switch_expression",
        "catch_clause",
        "ternary_expression",
    }
)

# Short-circuit boolean operators each add a decision point, matching the
# Go/Rust/Swift convention. Counted only as logical operators (operands of a
# binary_expression) that drive executable control flow, for consistency with
# the C/C++ walkers. A "&&"/"||" in an annotation argument (a compile-time
# constant) is not a runtime branch and must not inflate complexity.
_JAVA_LOGICAL_OPERATORS = frozenset({"&&", "||"})
_JAVA_NON_EXECUTABLE_ANCHORS = frozenset(
    {"element_value_pair", "annotation_argument_list"}
)


def extract_modifiers(node: Any, get_node_text: Callable[..., str]) -> list[str]:
    """Extract modifiers from a declaration node."""
    modifiers: list[str] = []
    for child in node.children:
        if child.type != "modifiers":
            continue
        modifiers.extend(_extract_modifier_tokens(child, get_node_text))
    return modifiers


def parse_method_signature(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str, str, list[str], list[str], list[str]] | None:
    """Parse method signature into (name, return_type, parameters, modifiers, throws)."""
    try:
        method_name = _first_child_text(node, {"identifier"}, get_node_text)
        if not method_name:
            return None

        return_type = _first_child_text(node, _RETURN_TYPE_NODES, get_node_text)
        modifiers = extract_modifiers(node, get_node_text)
        return (
            method_name,
            return_type or "void",
            _extract_formal_parameters(node, get_node_text),
            modifiers,
            _extract_throws(node, get_node_text),
        )
    except Exception:
        return None


def parse_field_declaration(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str, list[str], list[str]] | None:
    """Parse field declaration into (type, variable_names, modifiers)."""
    try:
        field_type = _first_child_text(node, _FIELD_TYPE_NODES, get_node_text)
        if not field_type:
            return None

        variable_names = _extract_variable_names(node, get_node_text)
        if not variable_names:
            return None

        modifiers = extract_modifiers(node, get_node_text)
        return field_type, variable_names, modifiers
    except Exception:
        return None


def calculate_complexity(node: Any) -> int:
    """Calculate cyclomatic complexity."""
    return 1 + _count_decision_nodes(node)


def _extract_modifier_tokens(
    modifiers_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    modifiers: list[str] = []
    for mod_child in modifiers_node.children:
        modifier = _modifier_token(mod_child, get_node_text)
        if modifier:
            modifiers.append(modifier)
    return modifiers


def _modifier_token(node: Any, get_node_text: Callable[..., str]) -> str | None:
    if node.type in _MODIFIER_KEYWORDS:
        return str(node.type)
    if node.type == "marker_annotation":
        return None
    mod_text = get_node_text(node)
    return mod_text if mod_text in _MODIFIER_KEYWORDS else None


def _first_child_text(
    node: Any,
    child_types: frozenset[str] | set[str],
    get_node_text: Callable[..., str],
) -> str | None:
    for child in node.children:
        if child.type in child_types:
            return get_node_text(child)
    return None


def _extract_formal_parameters(
    node: Any, get_node_text: Callable[..., str]
) -> list[str]:
    parameters: list[str] = []
    for child in node.children:
        if child.type == "formal_parameters":
            parameters.extend(_formal_parameter_texts(child, get_node_text))
    return parameters


def _formal_parameter_texts(
    parameters_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    return [
        get_node_text(param)
        for param in parameters_node.children
        if param.type == "formal_parameter"
    ]


def _extract_throws(node: Any, get_node_text: Callable[..., str]) -> list[str]:
    throws: list[str] = []
    for child in node.children:
        if child.type == "throws":
            throws.extend(re.findall(r"\b[A-Z]\w*Exception\b", get_node_text(child)))
    return throws


def _extract_variable_names(node: Any, get_node_text: Callable[..., str]) -> list[str]:
    variable_names: list[str] = []
    for child in node.children:
        if child.type == "variable_declarator":
            variable_names.extend(_variable_declarator_names(child, get_node_text))
    return variable_names


def _variable_declarator_names(
    declarator_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    return [
        get_node_text(grandchild)
        for grandchild in declarator_node.children
        if grandchild.type == "identifier"
    ]


def _count_decision_nodes(node: Any) -> int:
    count = 0
    stack = [node]
    while stack:
        current = stack.pop()
        current_type = getattr(current, "type", None)
        if current_type in _JAVA_DECISION_NODES:
            count += 1
        elif current_type in _JAVA_LOGICAL_OPERATORS:
            if is_executable_logical_operator(current, _JAVA_NON_EXECUTABLE_ANCHORS):
                count += 1
        stack.extend(_safe_children(current))
    return count


def _safe_children(node: Any) -> list[Any]:
    try:
        return list(node.children) if hasattr(node, "children") else []
    except (TypeError, AttributeError):
        return []
