"""Helper functions for QueryService internals."""

import logging
from typing import Any

logger = logging.getLogger("tree_sitter_analyzer.core.query_service")


class PluginQueryNode:
    """Small node shim for plugin elements returned without tree-sitter nodes."""

    def __init__(self, element: Any, query_key: str | None) -> None:
        self.type = getattr(element, "element_type", query_key or "unknown")
        self.start_point = (getattr(element, "start_line", 1) - 1, 0)
        self.end_point = (getattr(element, "end_line", 1) - 1, 0)
        self.text = getattr(element, "raw_text", "").encode("utf-8")


def _element_to_capture(element: Any, query_key: str | None) -> tuple[Any, str] | None:
    if not (hasattr(element, "start_line") and hasattr(element, "end_line")):
        return None
    return PluginQueryNode(element, query_key), query_key or "element"


def plugin_strategy_captures(
    plugin: Any, query_key: str | None, source_code: str
) -> list[tuple[Any, str]] | None:
    try:
        elements = plugin.execute_query_strategy(source_code, query_key or "function")
    except Exception as e:
        logger.debug(f"Plugin query strategy failed: {e}")
        return None

    captures = []
    for element in elements or []:
        capture = _element_to_capture(element, query_key)
        if capture is not None:
            captures.append(capture)
    return captures


def _walk_for_plugin_categories(
    node: Any, node_types: list[str], query_key: str, captures: list[tuple[Any, str]]
) -> None:
    if node.type in node_types:
        captures.append((node, query_key))

    for child in node.children:
        _walk_for_plugin_categories(child, node_types, query_key, captures)


def plugin_category_captures(
    plugin: Any, root_node: Any, query_key: str | None
) -> list[tuple[Any, str]] | None:
    try:
        element_categories = plugin.get_element_categories()
    except Exception as e:
        logger.debug(f"Plugin element categories failed: {e}")
        return None

    if not element_categories or not query_key or query_key not in element_categories:
        return None

    captures: list[tuple[Any, str]] = []
    _walk_for_plugin_categories(
        root_node, element_categories[query_key], query_key, captures
    )
    return captures


def _node_matches_query(node_type: str, query_key: str | None) -> bool:
    return (
        query_key in ("function", "functions")
        and "function" in node_type
        or query_key in ("class", "classes")
        and "class" in node_type
        or query_key in ("method", "methods")
        and "method" in node_type
        or query_key in ("variable", "variables")
        and "variable" in node_type
        or query_key in ("import", "imports")
        and "import" in node_type
        or query_key in ("header", "headers")
        and "heading" in node_type
    )


def fallback_query_captures(
    root_node: Any, query_key: str | None
) -> list[tuple[Any, str]]:
    captures: list[tuple[Any, str]] = []

    def walk_tree_basic(node: Any) -> None:
        node_type = getattr(node, "type", "")
        if not isinstance(node_type, str):
            node_type = str(node_type)

        if _node_matches_query(node_type, query_key):
            captures.append((node, query_key or "element"))

        for child in getattr(node, "children", []):
            walk_tree_basic(child)

    walk_tree_basic(root_node)
    return captures
