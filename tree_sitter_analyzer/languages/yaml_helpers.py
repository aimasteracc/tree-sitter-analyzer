"""YAML mapping, sequence, and utility helpers — extracted from yaml_plugin.py."""

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


def calculate_nesting_level(node: Any) -> int:
    """Calculate AST-based logical nesting level."""
    level = 0
    current = node.parent
    while current is not None:
        if current.type in (
            "block_mapping",
            "block_sequence",
            "flow_mapping",
            "flow_sequence",
        ):
            level += 1
        current = getattr(current, "parent", None)
        if current is None:
            break
    return level


def get_document_index(node: Any) -> int:
    """Get document index for a node."""
    current = node
    while current is not None:
        if current.type == "document":
            index = 0
            sibling = current.prev_sibling
            while sibling is not None:
                if sibling.type == "document":
                    index += 1
                sibling = sibling.prev_sibling
            return index
        current = getattr(current, "parent", None)
        if current is None:
            break
    return 0


def traverse_nodes(node: Any) -> list[Any]:
    """Traverse all nodes in the tree."""
    nodes = [node]
    for child in node.children:
        nodes.extend(traverse_nodes(child))
    return nodes


def is_number(text: str) -> bool:
    """Check if text represents a number."""
    try:
        float(text)
        return True
    except ValueError:
        return False


def extract_value_info(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str | None, str | None, int | None]:
    """Extract value information from a node.

    Returns:
        Tuple of (value, value_type, child_count)
    """
    if node is None:
        return None, None, None

    node_type = node.type
    text = get_node_text(node).strip()

    if node_type in ("plain_scalar", "double_quote_scalar", "single_quote_scalar"):
        if text.lower() in ("true", "false", "yes", "no", "on", "off"):
            return text, "boolean", None
        elif text.lower() in ("null", "~", ""):
            return text if text else None, "null", None
        elif is_number(text):
            return text, "number", None
        else:
            return text, "string", None
    elif node_type == "block_scalar":
        return text, "string", None
    elif node_type in ("block_mapping", "flow_mapping"):
        child_count = len(
            [c for c in node.children if c.type in ("block_mapping_pair", "flow_pair")]
        )
        return None, "mapping", child_count
    elif node_type in ("block_sequence", "flow_sequence"):
        child_count = len(
            [c for c in node.children if c.type in ("block_sequence_item",)]
            or node.children
        )
        return None, "sequence", child_count
    elif node_type == "alias":
        alias_name = text.lstrip("*")
        return f"*{alias_name}", "alias", None

    return text, "unknown", None


def _drill_to_scalar(node: Any, get_node_text: Callable[..., str]) -> str | None:
    """Drill down through flow_node/block_node wrappers to get scalar text."""
    current = node
    while current and current.type in ("flow_node", "block_node") and current.children:
        current = current.children[0]
    if current:
        return get_node_text(current).strip()
    return None


def extract_mapping_key_and_value(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str | None, str | None, str | None, int | None, str | None]:
    """Extract key, value, value_type, child_count, and anchor from a mapping pair node.

    Returns:
        Tuple of (key, value, value_type, child_count, anchor_name)
    """
    key = None
    value = None
    value_type = None
    child_count = None
    anchor_name = None

    key_node = None
    value_node = None
    found_colon = False

    for child in node.children:
        if child.type == ":":
            found_colon = True
        elif child.type in ("flow_node", "block_node"):
            if not found_colon:
                key_node = child
            else:
                value_node = child
                for subchild in child.children:
                    if subchild.type == "anchor":
                        anchor_text = get_node_text(subchild)
                        anchor_name = anchor_text.lstrip("&").strip()
        elif child.type == "key":
            if child.children:
                key_node = child.children[0]
            else:
                key_node = child
        elif child.type == "value":
            if child.children:
                value_node = child.children[0]
            else:
                value_node = child
            for subchild in child.children:
                if subchild.type == "anchor":
                    anchor_text = get_node_text(subchild)
                    anchor_name = anchor_text.lstrip("&").strip()
        elif child.type == "anchor":
            anchor_text = get_node_text(child)
            anchor_name = anchor_text.lstrip("&").strip()

    if key_node is not None:
        key = _drill_to_scalar(key_node, get_node_text)

    if value_node is not None:
        scalar = _drill_to_scalar(value_node, get_node_text)
        if scalar:
            value, value_type, child_count = extract_value_info(
                _find_inner_node(value_node), get_node_text
            )
        else:
            value, value_type, child_count = extract_value_info(
                _find_inner_node(value_node), get_node_text
            )

    return key, value, value_type, child_count, anchor_name


def _find_inner_node(node: Any) -> Any:
    """Find the inner content node by drilling through wrappers."""
    current = node
    while current and current.type in ("flow_node", "block_node") and current.children:
        current = current.children[0]
    return current


def extract_sequence_key(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Try to find the key for a sequence by checking parent mapping."""
    key = None
    parent = node.parent
    while parent is not None:
        if parent.type in ("block_mapping_pair", "flow_pair"):
            for child in parent.children:
                if child.type in ("flow_node", "block_node"):
                    found_colon = False
                    for sibling in parent.children:
                        if sibling.type == ":":
                            found_colon = True
                            break
                    if (
                        not found_colon
                        or child.start_byte < parent.children[1].start_byte
                    ):
                        key = _drill_to_scalar(child, get_node_text)
                        break
            break
        parent = getattr(parent, "parent", None)
    return key
