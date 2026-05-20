"""Swift AST node helpers."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

VISIBILITY_MODIFIERS = {"open", "public", "internal", "fileprivate", "private"}
TYPE_DECLARATION_KINDS = {"actor", "class", "struct", "enum", "extension"}


def walk(root: tree_sitter.Node) -> list[tree_sitter.Node]:
    """Return root and descendants in source order."""
    stack = [root]
    nodes = []
    while stack:
        node = stack.pop()
        nodes.append(node)
        stack.extend(reversed(node.children))
    return nodes


def extract_matching_nodes(
    root: tree_sitter.Node,
    node_types: set[str],
    extractor: Callable[[tree_sitter.Node], Any | None],
) -> list[Any]:
    """Extract model elements for matching Swift AST node types."""
    elements = []
    for node in walk(root):
        if node.type not in node_types:
            continue
        element = extractor(node)
        if element:
            elements.append(element)
    return elements


def decode_node_text(node: tree_sitter.Node) -> str:
    """Decode a node's byte text safely."""
    source = node.text or b""
    if isinstance(source, bytes):
        return source.decode("utf-8", errors="replace")
    return str(source)


def modifier_words(node: tree_sitter.Node) -> list[str]:
    """Return Swift modifier tokens attached to a declaration."""
    modifiers = node.child_by_field_name("modifiers")
    if modifiers is None:
        modifiers = next(
            (child for child in node.children if child.type == "modifiers"),
            None,
        )
    if modifiers is None:
        return []
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*", decode_node_text(modifiers))


def class_type(node: tree_sitter.Node) -> str:
    """Return Swift type declaration kind."""
    if node.type == "protocol_declaration":
        return "protocol"
    declaration_kind = node.child_by_field_name("declaration_kind")
    if declaration_kind is not None:
        return declaration_kind.type
    for child in node.children:
        if child.type in TYPE_DECLARATION_KINDS:
            return child.type
    return "class"


def binding_kind(node: tree_sitter.Node, raw_text: str) -> str:
    """Return let/var binding kind for a Swift property."""
    for child in node.children:
        if child.type == "value_binding_pattern":
            return decode_node_text(child).strip()
    match = re.match(r"\s*(let|var)\b", raw_text)
    return match.group(1) if match else "var"


def visibility(modifiers: list[str]) -> str:
    """Return Swift visibility, defaulting to internal."""
    for modifier in modifiers:
        if modifier in VISIBILITY_MODIFIERS:
            return modifier
    return "internal"


def base_element_fields(
    node: tree_sitter.Node,
    raw_text: str,
    name: str,
) -> dict[str, Any]:
    """Return fields common to all extracted Swift elements."""
    return {
        "name": name,
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "raw_text": raw_text,
        "language": "swift",
    }


def named_child_text(
    extractor: Any,
    node: tree_sitter.Node,
    node_types: tuple[str, ...],
) -> str:
    """Return the first descendant text matching any node type."""
    return first_descendant_text(extractor, node, node_types) or fallback_name(node)


def first_descendant_text(
    extractor: Any,
    node: tree_sitter.Node,
    node_types: tuple[str, ...],
) -> str:
    """Return the first matching descendant text."""
    for descendant in walk(node):
        if descendant.type in node_types:
            return extractor.get_node_text(descendant)
    return ""


def type_name(extractor: Any, node: tree_sitter.Node) -> str:
    """Return the declared Swift type name."""
    name_node = node.child_by_field_name("name")
    node_types = ("type_identifier", "user_type", "simple_identifier", "identifier")
    if name_node is not None:
        return first_descendant_text(extractor, name_node, node_types)
    return named_child_text(extractor, node, ("type_identifier", "user_type"))


def variable_name(extractor: Any, node: tree_sitter.Node) -> str:
    """Return the declared Swift property name."""
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return first_descendant_text(
            extractor,
            name_node,
            ("simple_identifier", "identifier"),
        )
    return named_child_text(extractor, node, ("simple_identifier", "identifier"))


def type_annotation(extractor: Any, node: tree_sitter.Node) -> str | None:
    """Return a Swift type annotation without the leading colon."""
    for child in node.children:
        if child.type == "type_annotation":
            return extractor.get_node_text(child).lstrip(":").strip()
    return None


def inherited_types(raw_text: str) -> list[str]:
    """Return inherited class/protocol names from a Swift declaration header."""
    header = raw_text.split("{", 1)[0]
    if ":" not in header:
        return []
    inherited = header.split(":", 1)[1]
    return [item.strip() for item in inherited.split(",") if item.strip()]


def superclass(class_type_name: str, inherited: list[str]) -> str | None:
    """Return superclass for class declarations."""
    if class_type_name == "class" and inherited:
        return inherited[0]
    return None


def interfaces(inherited: list[str], superclass_name: str | None) -> list[str]:
    """Return protocol/interface names after removing superclass."""
    return inherited[1:] if superclass_name else inherited


def fallback_name(node: tree_sitter.Node) -> str:
    """Return a deterministic fallback name for anonymous Swift nodes."""
    return f"element_{node.start_point[0] + 1}_{node.start_point[1] + 1}"
