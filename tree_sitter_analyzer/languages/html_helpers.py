"""HTML attribute, classification, and utility helpers — extracted from html_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..models import MarkupElement
from ..utils import log_debug


def extract_node_text(node: Any, source_code: str) -> str:
    """Extract text content from a tree-sitter node."""
    try:
        if hasattr(node, "start_byte") and hasattr(node, "end_byte"):
            source_bytes = source_code.encode("utf-8")
            node_bytes = source_bytes[node.start_byte : node.end_byte]
            return node_bytes.decode("utf-8", errors="replace")
        return ""
    except Exception as e:
        log_debug(f"Failed to extract node text: {e}")
        return ""


# Parse input into structured data: parse_attribute
def parse_attribute(
    attr_node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str, str]:
    """Parse individual attribute node."""
    try:
        attr_name, attr_value = _parse_attribute_children(attr_node, get_node_text)
        if attr_name:
            return attr_name, attr_value

        return _parse_attribute_text(get_node_text(attr_node))
    except Exception:
        return "", ""


def classify_element(
    tag_name: str,
    element_categories: dict[str, list[str]],
) -> str:
    """Classify HTML element based on tag name."""
    tag_name_lower = tag_name.lower()
    for category, tags in element_categories.items():
        if tag_name_lower in tags:
            return category
    return "unknown"


# Extract elements from AST: extract_html_tag_name
def extract_html_tag_name(node: Any, get_node_text: Callable[..., str]) -> str:
    """Extract tag name from HTML element node."""
    try:
        tag_name = _extract_tag_name_from_children(node, get_node_text)
        if tag_name:
            return tag_name

        return _extract_tag_name_from_text(get_node_text(node))
    except Exception:
        return "unknown"


# Extract elements from AST: extract_html_attributes
def extract_html_attributes(
    node: Any, get_node_text: Callable[..., str]
) -> dict[str, str]:
    """Extract attributes from HTML element node."""
    attributes: dict[str, str] = {}
    try:
        for attr_node in _iter_attribute_nodes(node):
            attr_name, attr_value = parse_attribute(attr_node, get_node_text)
            if attr_name:
                attributes[attr_name] = attr_value
    except Exception as e:
        log_debug(f"Failed to extract attributes: {e}")
    return attributes


def create_markup_element(
    node: Any,
    get_node_text: Callable[..., str],
    element_categories: dict[str, list[str]],
    parent: MarkupElement | None,
) -> MarkupElement | None:
    """Create MarkupElement from tree-sitter node."""
    try:
        tag_name = extract_html_tag_name(node, get_node_text)
        if not tag_name:
            return None

        attributes = extract_html_attributes(node, get_node_text)
        element_class = classify_element(tag_name, element_categories)
        raw_text = get_node_text(node)

        element = MarkupElement(
            name=tag_name,
            start_line=node.start_point[0] + 1 if hasattr(node, "start_point") else 0,
            end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
            raw_text=raw_text,
            language="html",
            tag_name=tag_name,
            attributes=attributes,
            parent=parent,
            children=[],
            element_class=element_class,
        )

        if parent:
            parent.children.append(element)

        return element
    except Exception as e:
        log_debug(f"Failed to create MarkupElement: {e}")
        return None


def _iter_typed_children(node: Any) -> list[Any]:
    if not hasattr(node, "children"):
        return []
    return [child for child in node.children if hasattr(child, "type")]


def _parse_attribute_children(
    attr_node: Any, get_node_text: Callable[..., str]
) -> tuple[str, str]:
    attr_name = ""
    attr_value = ""

    for child in _iter_typed_children(attr_node):
        if child.type == "attribute_name":
            attr_name = get_node_text(child).strip()
        elif child.type == "quoted_attribute_value":
            attr_value = get_node_text(child).strip().strip('"').strip("'")
        elif child.type == "attribute_value":
            attr_value = get_node_text(child).strip()

    return attr_name, attr_value


def _parse_attribute_text(attr_text: str) -> tuple[str, str]:
    if "=" not in attr_text:
        return attr_text.strip(), ""

    name, value = attr_text.split("=", 1)
    return name.strip(), value.strip().strip('"').strip("'")


def _extract_tag_name_from_children(
    node: Any, get_node_text: Callable[..., str]
) -> str:
    for child in _iter_typed_children(node):
        if child.type == "tag_name":
            return get_node_text(child).strip()

        if child.type in ("start_tag", "self_closing_tag"):
            tag_name = _extract_tag_name_from_children(child, get_node_text)
            if tag_name:
                return tag_name

    return ""


def _extract_tag_name_from_text(node_text: str) -> str:
    if not node_text.startswith("<"):
        return "unknown"

    tag_part = node_text.split(">")[0].split()[0]
    return tag_part.lstrip("<").rstrip(">")


def _iter_attribute_nodes(node: Any) -> list[Any]:
    attribute_nodes = []

    for child in _iter_typed_children(node):
        if child.type == "attribute":
            attribute_nodes.append(child)
        elif child.type in ("start_tag", "self_closing_tag"):
            attribute_nodes.extend(
                grandchild
                for grandchild in _iter_typed_children(child)
                if grandchild.type == "attribute"
            )

    return attribute_nodes
