"""Variable extraction helpers for the TypeScript extractor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from ...models import Variable
from ...utils import log_debug

if TYPE_CHECKING:
    import tree_sitter


TextExtractor: TypeAlias = Callable[["tree_sitter.Node"], str]
TsdocExtractor: TypeAlias = Callable[[int], str | None]
TypeInferer: TypeAlias = Callable[[str | None], str]


@dataclass
class _PropertyParts:
    name: str | None = None
    type_name: str | None = None
    value: str | None = None
    is_static: bool = False
    visibility: str = "public"


@dataclass
class _VariableParts:
    name: str | None = None
    type_name: str | None = None
    value: str | None = None


def extract_property(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> Variable | None:
    """Extract class property definition."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        parts = _parse_property_parts(node, get_node_text)

        if not parts.name:
            return None

        return Variable(
            name=parts.name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            variable_type=parts.type_name or "any",
            initializer=parts.value,
            is_static=parts.is_static,
            is_constant=False,
            visibility=parts.visibility,
        )
    except Exception as e:
        log_debug(f"Failed to extract property info: {e}")
        return None


def parse_variable_declarator(
    node: tree_sitter.Node,
    kind: str,
    start_line: int,
    end_line: int,
    get_node_text: TextExtractor,
    infer_type_from_value: TypeInferer,
    extract_tsdoc: TsdocExtractor,
) -> Variable | None:
    """Parse an individual variable declarator with TypeScript type annotations."""
    try:
        parts = _parse_variable_parts(node, get_node_text)
        if not parts.name or _has_arrow_function_child(node):
            return None

        return Variable(
            name=parts.name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            variable_type=parts.type_name or infer_type_from_value(parts.value),
            is_static=False,
            is_constant=(kind == "const"),
            docstring=extract_tsdoc(start_line),
            initializer=parts.value,
            visibility="public",
        )
    except Exception as e:
        log_debug(f"Failed to parse variable declarator: {e}")
        return None


def _parse_property_parts(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> _PropertyParts:
    parts = _PropertyParts()

    if hasattr(node, "children") and node.children:
        for child in node.children:
            if hasattr(child, "type"):
                _apply_property_child(parts, child, get_node_text)

    node_text = get_node_text(node)
    parts.is_static = "static" in node_text
    parts.visibility = _visibility_from_text(node_text)
    return parts


def _apply_property_child(
    parts: _PropertyParts,
    child: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> None:
    if child.type == "property_identifier":
        parts.name = get_node_text(child)
    elif child.type == "type_annotation":
        parts.type_name = get_node_text(child).lstrip(": ")
    elif child.type in ["string", "number", "true", "false", "null"]:
        parts.value = get_node_text(child)


def _parse_variable_parts(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> _VariableParts:
    parts = _VariableParts()

    for child in node.children:
        if child.type == "identifier":
            parts.name = get_node_text(child)
        elif child.type == "type_annotation":
            parts.type_name = get_node_text(child).lstrip(": ")
        elif child.type == "=" and child.next_sibling:
            parts.value = get_node_text(child.next_sibling)

    return parts


def _has_arrow_function_child(node: tree_sitter.Node) -> bool:
    return any(child.type == "arrow_function" for child in node.children)


def _visibility_from_text(node_text: str) -> str:
    if "private" in node_text:
        return "private"
    if "protected" in node_text:
        return "protected"
    return "public"
