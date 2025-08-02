#!/usr/bin/env python3
"""
Query module for tree_sitter_analyzer.core.

This module provides the QueryExecutor class which handles Tree-sitter
query execution in the new architecture.
"""

import logging
import time
from typing import Any

from tree_sitter import Language, Node, Tree

from ..query_loader import get_query_loader

# Configure logging
logger = logging.getLogger(__name__)


class QueryExecutor:
    """
    Tree-sitter query executor for the new architecture.

    This class provides a unified interface for executing Tree-sitter queries
    with proper error handling and result processing.
    """

    def __init__(self) -> None:
        """Initialize the QueryExecutor."""
        self._query_loader = get_query_loader()
        self._execution_stats: dict[str, Any] = {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "total_execution_time": 0.0,
        }
        logger.info("QueryExecutor initialized successfully")

    def execute_query(
        self,
        tree: Tree | None,
        language: Language,
        query_name: str,
        source_code: str,
    ) -> dict[str, Any]:
        """
        Execute a predefined query by name.

        Args:
            tree: Tree-sitter tree to query
            language: Tree-sitter language object
            query_name: Name of the predefined query
            source_code: Source code for context

        Returns:
            Dictionary containing query results and metadata
        """
        start_time = time.time()
        self._execution_stats["total_queries"] += 1

        try:
            # Validate inputs
            if tree is None:
                return self._create_error_result("Tree is None", query_name=query_name)

            if language is None:
                return self._create_error_result(  # type: ignore[unreachable]
                    "Language is None", query_name=query_name
                )

            # Get the query string
            language_name = language.name if hasattr(language, "name") else "unknown"
            query_string = self._query_loader.get_query(language_name, query_name)
            if query_string is None:
                return self._create_error_result(
                    f"Query '{query_name}' not found", query_name=query_name
                )

            # Create and execute the query
            try:
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                # Process captures
                try:
                    processed_captures = self._process_captures(captures, source_code)
                except Exception as e:
                    logger.error(f"Error processing captures for {query_name}: {e}")
                    return self._create_error_result(
                        f"Capture processing failed: {str(e)}", query_name=query_name
                    )

                self._execution_stats["successful_queries"] += 1
                execution_time = time.time() - start_time
                self._execution_stats["total_execution_time"] += execution_time

                return {
                    "captures": processed_captures,
                    "query_name": query_name,
                    "query_string": query_string,
                    "execution_time": execution_time,
                    "success": True,
                }

            except Exception as e:
                logger.error(f"Error executing query '{query_name}': {e}")
                return self._create_error_result(
                    f"Query execution failed: {str(e)}", query_name=query_name
                )

        except Exception as e:
            logger.error(f"Unexpected error in execute_query: {e}")
            self._execution_stats["failed_queries"] += 1
            return self._create_error_result(
                f"Unexpected error: {str(e)}", query_name=query_name
            )

    def execute_query_string(
        self,
        tree: Tree | None,
        language: Language,
        query_string: str,
        source_code: str,
    ) -> dict[str, Any]:
        """
        Execute a query string directly.

        Args:
            tree: Tree-sitter tree to query
            language: Tree-sitter language object
            query_string: Query string to execute
            source_code: Source code for context

        Returns:
            Dictionary containing query results and metadata
        """
        start_time = time.time()
        self._execution_stats["total_queries"] += 1

        try:
            # Validate inputs
            if tree is None:
                return self._create_error_result("Tree is None")

            if language is None:
                return self._create_error_result("Language is None")  # type: ignore[unreachable]

            # Create and execute the query
            try:
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                # Process captures
                try:
                    processed_captures = self._process_captures(captures, source_code)
                except Exception as e:
                    logger.error(f"Error processing captures: {e}")
                    return self._create_error_result(
                        f"Capture processing failed: {str(e)}"
                    )

                self._execution_stats["successful_queries"] += 1
                execution_time = time.time() - start_time
                self._execution_stats["total_execution_time"] += execution_time

                return {
                    "captures": processed_captures,
                    "query_string": query_string,
                    "execution_time": execution_time,
                    "success": True,
                }

            except Exception as e:
                logger.error(f"Error executing query string: {e}")
                return self._create_error_result(
                    f"Query execution failed: {str(e)}", query_string=query_string
                )

        except Exception as e:
            logger.error(f"Unexpected error in execute_query_string: {e}")
            self._execution_stats["failed_queries"] += 1
            return self._create_error_result(f"Unexpected error: {str(e)}")

    def execute_multiple_queries(
        self, tree: Tree, language: Language, query_names: list[str], source_code: str
    ) -> dict[str, dict[str, Any]]:
        """
        Execute multiple queries and return combined results.

        Args:
            tree: Tree-sitter tree to query
            language: Tree-sitter language object
            query_names: List of query names to execute
            source_code: Source code for context

        Returns:
            Dictionary mapping query names to their results
        """
        results = {}

        for query_name in query_names:
            result = self.execute_query(tree, language, query_name, source_code)
            results[query_name] = result

        return results

    def _process_captures(
        self, captures: Any, source_code: str
    ) -> list[dict[str, Any]]:
        """
        Process query captures into standardized format.

        Args:
            captures: Raw captures from Tree-sitter query
            source_code: Source code for context

        Returns:
            List of processed capture dictionaries
        """
        processed = []

        try:
            for capture in captures:
                try:
                    # Handle both dictionary and tuple formats
                    if isinstance(capture, dict):
                        # New Tree-sitter API format
                        node = capture.get("node")
                        name = capture.get("name", "unknown")
                    elif isinstance(capture, tuple) and len(capture) == 2:
                        # Old Tree-sitter API format
                        node, name = capture
                    else:
                        logger.warning(f"Unexpected capture format: {type(capture)}")
                        continue

                    if node is None:
                        continue

                    result_dict = self._create_result_dict(node, name, source_code)
                    processed.append(result_dict)

                except Exception as e:
                    logger.error(f"Error processing capture: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in _process_captures: {e}")

        return processed

    def _create_result_dict(
        self, node: Node, capture_name: str, source_code: str
    ) -> dict[str, Any]:
        """
        Create a result dictionary from a Tree-sitter node.

        Args:
            node: Tree-sitter node
            capture_name: Name of the capture
            source_code: Source code for context

        Returns:
            Dictionary containing node information
        """
        try:
            # Extract node text
            node_text = ""
            if hasattr(node, "text") and node.text:
                try:
                    node_text = node.text.decode("utf-8", errors="replace")
                except Exception:
                    node_text = str(node.text)

            return {
                "capture_name": capture_name,
                "node_type": getattr(node, "type", "unknown"),
                "start_point": getattr(node, "start_point", (0, 0)),
                "end_point": getattr(node, "end_point", (0, 0)),
                "start_byte": getattr(node, "start_byte", 0),
                "end_byte": getattr(node, "end_byte", 0),
                "text": node_text,
                "line_number": getattr(node, "start_point", (0, 0))[0] + 1,
                "column_number": getattr(node, "start_point", (0, 0))[1],
            }

        except Exception as e:
            logger.error(f"Error creating result dict: {e}")
            return {"capture_name": capture_name, "node_type": "error", "error": str(e)}

    def _create_error_result(
        self, error_message: str, query_name: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """
        Create an error result dictionary.

        Args:
            error_message: Error message
            query_name: Optional query name
            **kwargs: Additional fields to include in the error result

        Returns:
            Error result dictionary
        """
        result = {"captures": [], "error": error_message, "success": False}

        if query_name:
            result["query_name"] = query_name

        result.update(kwargs)
        return result

    def get_available_queries(self, language: str) -> list[str]:
        """
        Get available queries for a language.

        Args:
            language: Programming language name

        Returns:
            List of available query names
        """
        try:
            queries = self._query_loader.get_all_queries_for_language(language)
            if isinstance(queries, dict):
                return list(queries.keys())
            # Handle other iterable types
            try:  # type: ignore[unreachable]
                return list(queries) if queries else []
            except (TypeError, ValueError):
                return []
        except Exception as e:
            logger.error(f"Error getting available queries for {language}: {e}")
            return []

    def get_query_description(self, language: str, query_name: str) -> str | None:
        """
        Get description for a specific query.

        Args:
            language: Programming language name
            query_name: Name of the query

        Returns:
            Query description or None if not found
        """
        try:
            return self._query_loader.get_query_description(language, query_name)
        except Exception as e:
            logger.error(f"Error getting query description: {e}")
            return None

    def validate_query(self, language: str, query_string: str) -> bool:
        """
        Validate a query string for a specific language.

        Args:
            language: Programming language name
            query_string: Query string to validate

        Returns:
            True if query is valid, False otherwise
        """
        try:
            # This would require loading the language and attempting to create the query
            # For now, we'll do basic validation
            from ..language_loader import get_loader

            loader = get_loader()

            lang_obj = loader.load_language(language)
            if lang_obj is None:
                return False

            # Try to create the query
            lang_obj.query(query_string)
            return True

        except Exception as e:
            logger.error(f"Query validation failed: {e}")
            return False

    def get_query_statistics(self) -> dict[str, Any]:
        """
        Get query execution statistics.

        Returns:
            Dictionary containing execution statistics
        """
        stats = self._execution_stats.copy()

        if stats["total_queries"] > 0:
            stats["success_rate"] = stats["successful_queries"] / stats["total_queries"]
            stats["average_execution_time"] = (
                stats["total_execution_time"] / stats["total_queries"]
            )
        else:
            stats["success_rate"] = 0.0
            stats["average_execution_time"] = 0.0

        return stats

    def reset_statistics(self) -> None:
        """Reset query execution statistics."""
        self._execution_stats = {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "total_execution_time": 0.0,
        }


# Module-level convenience functions for backward compatibility
def get_available_queries(language: str | None = None) -> list[str]:
    """
    Get available queries for a language (module-level function).

    Args:
        language: Programming language name (optional)

    Returns:
        List of available query names
    """
    try:
        loader = get_query_loader()
        if language:
            return loader.list_queries_for_language(language)

        # If no language, return a list of all query names across supported languages
        all_queries = set()
        for lang in loader.list_supported_languages():
            all_queries.update(loader.list_queries_for_language(lang))
        return sorted(all_queries)

    except Exception as e:
        logger.error(f"Error getting available queries: {e}")
        return []


def get_query_description(language: str, query_name: str) -> str | None:
    """
    Get description for a specific query (module-level function).

    Args:
        language: Programming language name
        query_name: Name of the query

    Returns:
        Query description or None if not found
    """
    try:
        from ..query_loader import get_query_loader

        loader = get_query_loader()
        return loader.get_query_description(language, query_name)
    except Exception as e:
        logger.error(f"Error getting query description: {e}")
        return None


# Module-level attributes for backward compatibility
try:
    from ..query_loader import get_query_loader

    query_loader = get_query_loader()
except Exception:
    query_loader = None  # type: ignore


def get_all_queries_for_language(language: str) -> list[str]:
    """
    Get all available queries for a specific language.

    Args:
        language: Programming language name

    Returns:
        List of available query names for the language

    .. deprecated:: 0.2.1
        This function is deprecated and will be removed in a future version.
        Use the unified analysis engine instead.
    """
    import warnings

    warnings.warn(
        "get_all_queries_for_language is deprecated and will be removed in a future version. "
        "Use the unified analysis engine instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return []


# Update module-level attributes for backward compatibility
try:
    from ..language_loader import get_loader

    loader = get_loader()
except Exception:
    loader = None  # type: ignore
