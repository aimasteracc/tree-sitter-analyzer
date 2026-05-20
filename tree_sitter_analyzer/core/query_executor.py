"""Query execution helpers — extracted from query_service.py."""

import logging
from typing import Any

from ..query_loader import query_loader
from ..utils.tree_sitter_compat import TreeSitterQueryCompat

logger = logging.getLogger(__name__)


def resolve_query_string(
    language: str,
    query_key: str | None,
    query_string: str | None,
) -> str:
    """Resolve query_key or query_string into a concrete query string.

    Raises ValueError if neither/both are provided, or key not found.
    """
    if not query_key and not query_string:
        raise ValueError("Must provide either query_key or query_string")

    if query_key and query_string:
        raise ValueError("Cannot provide both query_key and query_string")

    if query_key:
        resolved = query_loader.get_query(language, query_key)
        if not resolved:
            raise ValueError(f"Query '{query_key}' not found for language '{language}'")
        return resolved

    return query_string or ""


def execute_ts_query(
    tree: Any,
    language_obj: Any,
    query_string: str,
    root_node: Any,
    fallback_fn: Any,
    query_key: str | None,
    language: str,
    content: str,
) -> list[tuple[Any, str]]:
    """Execute a tree-sitter query with plugin fallback."""
    try:
        captures = TreeSitterQueryCompat.safe_execute_query(
            language_obj, query_string, root_node, fallback_result=[]
        )
        if not captures:
            captures = fallback_fn(root_node, query_key, language, content)
    except Exception as e:
        logger.debug(f"Tree-sitter query execution failed, using plugin fallback: {e}")
        captures = fallback_fn(root_node, query_key, language, content)

    return captures if isinstance(captures, list) else []


def process_captures(
    captures: list[tuple[Any, str]],
    content: str,
    create_result_fn: Any,
) -> list[dict[str, Any]]:
    """Convert capture tuples into result dicts."""
    results: list[dict[str, Any]] = []
    for capture in captures:
        if isinstance(capture, tuple) and len(capture) == 2:
            node, name = capture
            results.append(create_result_fn(node, name, content))
    return results
