"""Shared AST traversal utilities for language plugins.

These thin helpers wrap common tree-sitter node operations so plugins
do not duplicate the same boilerplate traversal code.
"""

from __future__ import annotations

from typing import Any, Generator


def iter_children_of_type(node: Any, *node_types: str) -> Generator[Any, None, None]:
    """Yield direct children of *node* whose type is in *node_types*.

    Args:
        node: A tree-sitter Node (or compatible mock).
        *node_types: One or more node type strings to match.

    Yields:
        Direct child nodes whose ``.type`` is in *node_types*.
    """
    for child in getattr(node, "children", []):
        if child.type in node_types:
            yield child


def find_first_child(node: Any, *node_types: str) -> Any | None:
    """Return the first direct child of *node* whose type is in *node_types*.

    Returns None if no matching child exists.
    """
    for child in getattr(node, "children", []):
        if child.type in node_types:
            return child
    return None


def collect_named_nodes(root: Any, *node_types: str) -> list[Any]:
    """Walk the subtree rooted at *root* and return all nodes whose type is in
    *node_types*, in DFS pre-order.

    Uses an explicit stack to avoid RecursionError on deeply nested trees.
    """
    results: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in node_types:
            results.append(node)
        # Push children in reverse so left-to-right DFS order is preserved
        children = getattr(node, "children", [])
        for child in reversed(list(children)):
            stack.append(child)
    return results


def node_text(node: Any, source_bytes: bytes) -> str:
    """Extract the source text for *node* using UTF-8 byte offsets.

    Prefers ``node.text`` (bytes) when available — tree-sitter's canonical
    source-of-truth. Falls back to slicing *source_bytes* by
    ``start_byte`` / ``end_byte``.

    Args:
        node: A tree-sitter Node.
        source_bytes: The full source file as UTF-8-encoded bytes.

    Returns:
        The node's source text as a string, or "" on any error.
    """
    if node is None:
        return ""
    text_attr = getattr(node, "text", None)
    if isinstance(text_attr, bytes):
        try:
            return text_attr.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return ""
    if isinstance(text_attr, str):
        return text_attr
    try:
        start = node.start_byte
        end = node.end_byte
        return source_bytes[start:end].decode("utf-8", errors="replace")
    except (AttributeError, IndexError, TypeError):
        return ""


def node_range(node: Any) -> tuple[int, int]:
    """Return the (start_line, end_line) of *node* as 1-indexed integers.

    ``node.start_point`` and ``node.end_point`` are 0-indexed (row, col)
    tuples in tree-sitter; this helper converts to 1-indexed line numbers
    for use in CodeElement metadata.

    Returns:
        (start_line, end_line) — both 1-indexed. Returns (0, 0) on error.
    """
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        return (start_line, end_line)
    except (AttributeError, IndexError, TypeError):
        return (0, 0)
