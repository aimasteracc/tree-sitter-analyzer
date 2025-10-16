#!/usr/bin/env python3
"""
Tree-sitter API Utilities

This module provides utilities for tree-sitter query execution using the modern API.
Supports tree-sitter 0.20+ with query.matches() method only.
"""

import logging
from typing import Any

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
        try:
            import tree_sitter

            query = tree_sitter.Query(language, query_string)

            # Try newest API first (tree-sitter 0.25+) with QueryCursor
            if hasattr(tree_sitter, "QueryCursor"):
                logger.debug("Using newest tree-sitter API (QueryCursor)")
                return TreeSitterQueryCompat._execute_newest_api(query, root_node)
            # Try modern API (tree-sitter 0.20+)
            elif hasattr(query, "matches"):
                logger.debug("Using modern tree-sitter API (matches)")
                return TreeSitterQueryCompat._execute_modern_api(query, root_node)
            # Fall back to legacy API (tree-sitter < 0.20)
            elif hasattr(query, "captures"):
                logger.debug("Using legacy tree-sitter API (captures)")
                return TreeSitterQueryCompat._execute_legacy_api(query, root_node)
            # Try very old API with different method signature
            else:
                logger.debug("Using very old tree-sitter API (direct query)")
                return TreeSitterQueryCompat._execute_old_api(query, root_node)

        except Exception as e:
            logger.error(f"Tree-sitter query execution failed: {e}")
            # Return empty result instead of raising to prevent complete failure
            logger.debug("Returning empty result due to query execution failure")
            return []

    @staticmethod
    def _execute_newest_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
        """Execute query using newest API (tree-sitter 0.25+) with QueryCursor"""
        captures = []
        try:
            import tree_sitter

            cursor = tree_sitter.QueryCursor(query)

            # Execute query and get matches
            matches = cursor.matches(root_node)
            # matches is a list of tuples: (pattern_index, captures_dict)
            for _pattern_index, captures_dict in matches:
                # captures_dict is {capture_name: [node1, node2, ...]}
                for capture_name, nodes in captures_dict.items():
                    for node in nodes:
                        captures.append((node, capture_name))

        except Exception as e:
            logger.error(f"Newest API execution failed: {e}")
            # Don't raise, just return empty result

        return captures

    @staticmethod
    def _execute_modern_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
        """Execute query using modern API (tree-sitter 0.20+)"""
        captures = []
        try:
            matches = query.matches(root_node)
            for match in matches:
                for capture in match.captures:
                    capture_name = query.capture_names[capture.index]
                    captures.append((capture.node, capture_name))
        except Exception as e:
            logger.error(f"Modern API execution failed: {e}")
            raise
        return captures

    @staticmethod
    def _execute_legacy_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
        """Execute query using legacy API (tree-sitter < 0.20)"""
        captures = []
        try:
            # Use the legacy captures method
            query_captures = query.captures(root_node)
            for node, capture_name in query_captures:
                captures.append((node, capture_name))
        except Exception as e:
            logger.error(f"Legacy API execution failed: {e}")
            raise
        return captures

    @staticmethod
    def _execute_old_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
        """Execute query using very old API (tree-sitter < 0.19)"""
        captures = []
        try:
            # Try different old API patterns
            if callable(query):
                # Some very old versions had callable queries
                query_result = query(root_node)
                if isinstance(query_result, list):
                    for item in query_result:
                        if isinstance(item, tuple) and len(item) >= 2:
                            captures.append((item[0], str(item[1])))
                        elif hasattr(item, "node") and hasattr(item, "name"):
                            captures.append((item.node, item.name))
            else:
                # If no known API is available, return empty result
                logger.warning(
                    "No compatible tree-sitter query API found, returning empty result"
                )

        except Exception as e:
            logger.error(f"Old API execution failed: {e}")
            # Don't raise, just return empty result

        return captures

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
        # Try byte-based extraction first
        if hasattr(node, "start_byte") and hasattr(node, "end_byte"):
            start_byte = node.start_byte
            end_byte = node.end_byte
            source_bytes = source_code.encode(encoding)
            if start_byte <= end_byte <= len(source_bytes):
                return source_bytes[start_byte:end_byte].decode(
                    encoding, errors="replace"
                )

        # Fall back to node.text if available
        if hasattr(node, "text") and node.text:
            if isinstance(node.text, bytes):
                return node.text.decode(encoding, errors="replace")
            else:
                return str(node.text)

        # Fall back to point-based extraction
        if hasattr(node, "start_point") and hasattr(node, "end_point"):
            start_point = node.start_point
            end_point = node.end_point
            lines = source_code.split("\n")

            if start_point[0] < len(lines) and end_point[0] < len(lines):
                if start_point[0] == end_point[0]:
                    # Single line
                    line = lines[start_point[0]]
                    start_col = max(0, min(start_point[1], len(line)))
                    end_col = max(start_col, min(end_point[1], len(line)))
                    return line[start_col:end_col]
                else:
                    # Multiple lines
                    result_lines = []
                    for i in range(start_point[0], min(end_point[0] + 1, len(lines))):
                        line = lines[i]
                        if i == start_point[0]:
                            start_col = max(0, min(start_point[1], len(line)))
                            result_lines.append(line[start_col:])
                        elif i == end_point[0]:
                            end_col = max(0, min(end_point[1], len(line)))
                            result_lines.append(line[:end_col])
                        else:
                            result_lines.append(line)
                    return "\n".join(result_lines)

        return ""

    except Exception as e:
        logger.debug(f"Node text extraction failed: {e}")
        return ""


def log_api_info():
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
