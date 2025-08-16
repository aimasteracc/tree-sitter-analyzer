#!/usr/bin/env python3
"""
Query Service

Unified query service for both CLI and MCP interfaces to avoid code duplication.
Provides core tree-sitter query functionality including predefined and custom queries.
"""

import logging
from typing import Any

from ..encoding_utils import read_file_safe
from ..query_loader import query_loader
from .parser import Parser
from .query_filter import QueryFilter

logger = logging.getLogger(__name__)


class QueryService:
    """Unified query service providing tree-sitter query functionality"""

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the query service"""
        self.project_root = project_root
        self.parser = Parser()
        self.filter = QueryFilter()

    async def execute_query(
        self,
        file_path: str,
        language: str,
        query_key: str | None = None,
        query_string: str | None = None,
        filter_expression: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """
        Execute a query

        Args:
            file_path: Path to the file to analyze
            language: Programming language
            query_key: Predefined query key (e.g., 'methods', 'class')
            query_string: Custom query string (e.g., '(method_declaration) @method')
            filter_expression: Filter expression (e.g., 'name=main', 'name=~get*,public=true')

        Returns:
            List of query results, each containing capture_name, node_type, start_line, end_line, content

        Raises:
            ValueError: If neither query_key nor query_string is provided
            FileNotFoundError: If file doesn't exist
            Exception: If query execution fails
        """
        if not query_key and not query_string:
            raise ValueError("Must provide either query_key or query_string")

        if query_key and query_string:
            raise ValueError("Cannot provide both query_key and query_string")

        try:
            # Read file content
            content, encoding = read_file_safe(file_path)

            # Parse file
            parse_result = self.parser.parse_code(content, language, file_path)
            if not parse_result or not parse_result.tree:
                raise Exception("Failed to parse file")

            tree = parse_result.tree
            language_obj = tree.language if hasattr(tree, "language") else None
            if not language_obj:
                raise Exception(f"Language object not available for {language}")

            # Get query string
            if query_key:
                query_string = query_loader.get_query(language, query_key)
                if not query_string:
                    raise ValueError(
                        f"Query '{query_key}' not found for language '{language}'"
                    )

            # Execute tree-sitter query
            ts_query = language_obj.query(query_string)
            captures = ts_query.captures(tree.root_node)

            # Process capture results
            results = []
            if isinstance(captures, dict):
                # New tree-sitter API returns dictionary
                for capture_name, nodes in captures.items():
                    for node in nodes:
                        results.append(self._create_result_dict(node, capture_name))
            else:
                # Old tree-sitter API returns list of tuples
                for capture in captures:
                    if isinstance(capture, tuple) and len(capture) == 2:
                        node, name = capture
                        results.append(self._create_result_dict(node, name))

            # Apply filters
            if filter_expression and results:
                results = self.filter.filter_results(results, filter_expression)

            return results

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    def _create_result_dict(self, node: Any, capture_name: str) -> dict[str, Any]:
        """
        Create result dictionary from tree-sitter node

        Args:
            node: tree-sitter node
            capture_name: capture name

        Returns:
            Result dictionary
        """
        return {
            "capture_name": capture_name,
            "node_type": node.type if hasattr(node, "type") else "unknown",
            "start_line": (
                node.start_point[0] + 1 if hasattr(node, "start_point") else 0
            ),
            "end_line": node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
            "content": (
                node.text.decode("utf-8", errors="replace")
                if hasattr(node, "text") and node.text
                else ""
            ),
        }

    def get_available_queries(self, language: str) -> list[str]:
        """
        Get available query keys for specified language

        Args:
            language: Programming language

        Returns:
            List of available query keys
        """
        return query_loader.list_queries(language)

    def get_query_description(self, language: str, query_key: str) -> str | None:
        """
        Get description for query key

        Args:
            language: Programming language
            query_key: Query key

        Returns:
            Query description, or None if not found
        """
        try:
            return query_loader.get_query_description(language, query_key)
        except Exception:
            return None
