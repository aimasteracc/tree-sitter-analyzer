#!/usr/bin/env python3
"""
Query module for tree_sitter_analyzer.core.

This module provides the QueryExecutor class which handles Tree-sitter
query execution in the new architecture.
"""

import logging
from typing import Any

from tree_sitter import Language, Node, Tree

from ..query_loader import get_query_loader
from ..utils.tree_sitter_compat import TreeSitterQueryCompat, get_node_text_safe
from ._query_execution import (
    execute_query_by_explicit_language,
    execute_query_by_name,
    execute_raw_query_string,
)
from ._query_results import (
    create_error_result,
    create_result_dict,
    process_captures,
    query_statistics,
)

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
        language: Language | None,
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
        return execute_query_by_name(
            self,
            tree,
            language,
            query_name,
            source_code,
            TreeSitterQueryCompat.safe_execute_query,
        )

    def execute_query_with_language_name(
        self,
        tree: Tree | None,
        language: Language | None,
        query_name: str,
        source_code: str,
        language_name: str,
    ) -> dict[str, Any]:
        """
        Execute a predefined query by name with explicit language name.

        Args:
            tree: Tree-sitter tree to query
            language: Tree-sitter language object
            query_name: Name of the predefined query
            source_code: Source code for context
            language_name: Name of the programming language

        Returns:
            Dictionary containing query results and metadata
        """
        return execute_query_by_explicit_language(
            self,
            tree,
            language,
            query_name,
            source_code,
            language_name,
            TreeSitterQueryCompat.safe_execute_query,
        )

    def execute_query_string(
        self,
        tree: Tree | None,
        language: Language | None,
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
        return execute_raw_query_string(
            self,
            tree,
            language,
            query_string,
            source_code,
            TreeSitterQueryCompat.safe_execute_query,
        )

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
        return process_captures(captures, source_code, self._create_result_dict)

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
        return create_result_dict(node, capture_name, source_code, get_node_text_safe)

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
        return create_error_result(error_message, query_name, **kwargs)

    # Public aliases used by companion module _query_execution.py
    create_error_result = _create_error_result

    @property
    def execution_stats(self) -> dict[str, Any]:
        """Return the live execution stats dict (mutable reference)."""
        return self._execution_stats

    @property
    def query_loader(self) -> Any:
        """Return the query loader instance."""
        return self._query_loader

    def process_captures(self, captures: Any, source_code: str) -> list[dict[str, Any]]:
        """Public alias for _process_captures used by companion helpers."""
        return self._process_captures(captures, source_code)

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
            return list(queries) if queries else []  # type: ignore[unreachable]
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

            from ..utils.tree_sitter_compat import create_query_safely

            return create_query_safely(lang_obj, query_string) is not None

        except Exception as e:
            logger.error(f"Query validation failed: {e}")
            return False

    def get_query_statistics(self) -> dict[str, Any]:
        """
        Get query execution statistics.

        Returns:
            Dictionary containing execution statistics
        """
        return query_statistics(self._execution_stats)

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
        "get_all_queries_for_language is deprecated and will be removed "
        "in a future version. Use the unified analysis engine instead.",
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
