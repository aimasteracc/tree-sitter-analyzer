#!/usr/bin/env python3
"""
Tree-sitter API Utilities

This module provides utilities for tree-sitter query execution using the modern API.
Supports tree-sitter 0.20+ with query.matches() method only.
"""

import logging
from typing import Any

from ._tree_sitter_compat_helpers import (
    execute_legacy_api,
    execute_modern_api,
    execute_newest_api,
    execute_old_api,
    execute_query_compat,
    get_node_text_compat,
)

logger = logging.getLogger(__name__)


class TreeSitterQueryCompat:
    """
    Tree-sitter query execution wrapper for modern API.

    Uses only the modern tree-sitter API (query.matches()).
    """

    @staticmethod
    def execute_query(
        language: Any, query_string: str, root_node: Any
    ) -> list[tuple[Any, str]]:
        """
        Execute a tree-sitter query using the modern API.

        Args:
            language: Tree-sitter language object
            query_string: Query string to execute
            root_node: Root node to query against

        Returns:
            List of (node, capture_name) tuples

        Raises:
            Exception: If query execution fails
        """
        return execute_query_compat(language, query_string, root_node)

    @staticmethod
    def _execute_newest_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
        """Execute query using newest API (tree-sitter 0.25+) with QueryCursor"""
        return execute_newest_api(query, root_node)

    @staticmethod
    def _execute_modern_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
        """Execute query using modern API (tree-sitter 0.20+)"""
        return execute_modern_api(query, root_node)

    @staticmethod
    def _execute_legacy_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
        """Execute query using legacy API (tree-sitter < 0.20)"""
        return execute_legacy_api(query, root_node)

    @staticmethod
    def _execute_old_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
        """Execute query using very old API (tree-sitter < 0.19)"""
        return execute_old_api(query, root_node)

    @staticmethod
    def safe_execute_query(
        language: Any,
        query_string: str,
        root_node: Any,
        fallback_result: list[tuple[Any, str]] | None = None,
    ) -> list[tuple[Any, str]]:
        """
        Safely execute a query with fallback handling.

        Args:
            language: Tree-sitter language object
            query_string: Query string to execute
            root_node: Root node to query against
            fallback_result: Result to return if query fails

        Returns:
            List of (node, capture_name) tuples or fallback_result
        """
        try:
            return TreeSitterQueryCompat.execute_query(
                language, query_string, root_node
            )
        except Exception as e:
            logger.debug(f"Query execution failed, using fallback: {e}")
            return fallback_result or []


def create_query_safely(language: Any, query_string: str) -> Any | None:
    """
    Safely create a tree-sitter query object.

    Args:
        language: Tree-sitter language object
        query_string: Query string

    Returns:
        Query object or None if creation fails
    """
    try:
        import tree_sitter

        return tree_sitter.Query(language, query_string)
    except Exception as e:
        logger.debug(f"Query creation failed: {e}")
        return None


def get_node_text_safe(node: Any, source_code: str, encoding: str = "utf-8") -> str:
    """
    Safely extract text from a tree-sitter node.

    Args:
        node: Tree-sitter node
        source_code: Source code string
        encoding: Text encoding

    Returns:
        Node text or empty string if extraction fails
    """
    try:
        return get_node_text_compat(node, source_code, encoding)
    except Exception as e:
        logger.debug(f"Node text extraction failed: {e}")
        return ""


def log_api_info() -> None:
    """Log information about available tree-sitter APIs."""
    try:
        import tree_sitter

        logger.debug("Tree-sitter library available")

        # Check available APIs
        try:
            # Create a dummy query to test available methods
            # We can't actually test without a language, so just check the class

            # We can't actually test without a language, so just check the class
            query_class = tree_sitter.Query
            has_matches = "matches" in dir(query_class)
            has_captures = "captures" in dir(query_class)

            if has_matches:
                logger.debug("Tree-sitter modern API (matches) available")
            elif has_captures:
                logger.debug("Tree-sitter legacy API (captures) available")
            else:
                logger.warning("No compatible tree-sitter API found")

        except Exception as e:
            logger.debug(f"API detection failed: {e}")

    except ImportError:
        logger.debug("Tree-sitter library not available")


def count_nodes_iterative(root_node: Any) -> int:
    """
    Count total number of nodes in a tree using iterative traversal.
    Prevents recursion limit issues for very large ASTs.

    Args:
        root_node: The root node of the tree or sub-tree

    Returns:
        Total number of nodes
    """
    if root_node is None:
        return 0

    count = 0
    stack = [root_node]

    while stack:
        node = stack.pop()
        count += 1

        # Add real tree-sitter child lists to the stack. Mock objects can synthesize
        # async attributes here, which creates unawaited coroutine warnings.
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
    return count
