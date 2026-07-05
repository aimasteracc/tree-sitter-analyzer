"""Variable extraction helpers for the JavaScript extractor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from ...models import Variable
from ...utils import log_debug

if TYPE_CHECKING:
    import tree_sitter


TextExtractor: TypeAlias = Callable[["tree_sitter.Node"], str]
JsdocExtractor: TypeAlias = Callable[[int], str | None]
TypeInferer: TypeAlias = Callable[[str | None], str]

_VALUE_NODE_TYPES = {
    "string",
    "number",
    "true",
    "false",
    "null",
    "object",
    "array",
    "function_expression",
    "arrow_function",
    "call_expression",
    "member_expression",
    "template_literal",
}


_DESTRUCTURING_PATTERN_TYPES = {"object_pattern", "array_pattern"}


@dataclass
class _VariableParts:
    name: str | None = None
    value: str | None = None
    is_destructuring: bool = False


def parse_variable_declarator(
    node: tree_sitter.Node,
    kind: str,
    start_line: int,
    end_line: int,
    get_node_text: TextExtractor,
    infer_type: TypeInferer,
    extract_jsdoc: JsdocExtractor,
) -> Variable | None:
    """Parse an individual JavaScript variable declarator.

    Destructuring declarations (``const { a } = obj``, ``const [x] = arr``)
    are skipped entirely — they bind names via patterns rather than declaring a
    single named variable, and the RHS identifier (``obj``, ``arr``) must not
    be reported as a phantom variable name.
    """
    try:
        parts = _parse_variable_parts(node, get_node_text)
        if parts.is_destructuring:
            return None
        if not parts.name or _has_arrow_function_child(node):
            return None

        return Variable(
            name=parts.name,
            start_line=start_line,
            end_line=end_line,
            raw_text=_variable_raw_text(node, get_node_text),
            language="javascript",
            variable_type=infer_type(parts.value),
            is_static=False,
            is_constant=(kind == "const"),
            docstring=extract_jsdoc(start_line),
            initializer=parts.value,
        )
    except Exception as e:
        log_debug(f"Failed to parse variable declarator: {e}")
        return None


def infer_type_from_value(value: str | None) -> str:
    """Infer JavaScript type from a literal-ish value."""
    if not value:
        return "unknown"

    value = value.strip()
    if value.startswith(('"', "'", "`")):
        return "string"
    if value in {"true", "false"}:
        return "boolean"
    if value == "null":
        return "null"
    if value == "undefined":
        return "undefined"
    if value.startswith("[") and value.endswith("]"):
        return "array"
    if value.startswith("{") and value.endswith("}"):
        return "object"
    if value.replace(".", "").replace("-", "").isdigit():
        return "number"
    if "function" in value or "=>" in value:
        return "function"
    return "unknown"


def _parse_variable_parts(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> _VariableParts:
    parts = _VariableParts()
    for child in node.children:
        _apply_variable_child(parts, child, get_node_text)

    if not parts.value and len(node.children) >= 3:
        parts.value = _value_after_assignment(node, get_node_text)

    return parts


def _apply_variable_child(
    parts: _VariableParts,
    child: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> None:
    if child.type in _DESTRUCTURING_PATTERN_TYPES:
        # Mark as destructuring so the RHS identifier is not used as the name.
        parts.is_destructuring = True
    elif child.type == "identifier" and not parts.is_destructuring:
        # Only treat a bare identifier as the declared name when no destructuring
        # pattern has been seen yet.  After a pattern like `{ a, b }` or `[x]`,
        # any subsequent identifier is the RHS source, not the declared name.
        parts.name = get_node_text(child)
    elif child.type == "=" and child.next_sibling:
        parts.value = get_node_text(child.next_sibling)
    elif child.type in _VALUE_NODE_TYPES:
        parts.value = get_node_text(child)


def _value_after_assignment(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> str | None:
    for index, child in enumerate(node.children):
        if child.type == "=" and index + 1 < len(node.children):
            value_node = node.children[index + 1]
            if value_node.type == "arrow_function":
                return None
            return get_node_text(value_node)
    return None


def _has_arrow_function_child(node: tree_sitter.Node) -> bool:
    return any(child.type == "arrow_function" for child in node.children)


def _variable_raw_text(node: tree_sitter.Node, get_node_text: TextExtractor) -> str:
    raw_text = get_node_text(node)
    parent = node.parent
    if parent and parent.type in {"lexical_declaration", "variable_declaration"}:
        parent_text = get_node_text(parent)
        if parent_text and len(parent_text) > len(raw_text) and raw_text in parent_text:
            return parent_text
    return raw_text
