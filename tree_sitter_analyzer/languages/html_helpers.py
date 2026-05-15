"""HTML attribute, classification, and utility helpers — extracted from html_plugin.py."""

from collections.abc import Callable
from typing import Any

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


def parse_attribute(
    attr_node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str, str]:
    """Parse individual attribute node."""
    try:
        attr_name = ""
        attr_value = ""

        if hasattr(attr_node, "children"):
            for child in attr_node.children:
                if hasattr(child, "type"):
                    if child.type == "attribute_name":
                        attr_name = get_node_text(child).strip()
                    elif child.type == "quoted_attribute_value":
                        attr_value = get_node_text(child).strip().strip('"').strip("'")
                    elif child.type == "attribute_value":
                        attr_value = get_node_text(child).strip()

        if not attr_name:
            attr_text = get_node_text(attr_node)
            if "=" in attr_text:
                name, value = attr_text.split("=", 1)
                attr_name = name.strip()
                attr_value = value.strip().strip('"').strip("'")
            else:
                attr_name = attr_text.strip()
                attr_value = ""

        return attr_name, attr_value
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
