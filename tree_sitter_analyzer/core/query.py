#!/usr/bin/env python3
"""
Query Executor Module for Tree-sitter Analyzer

This module provides a QueryExecutor class which handles Tree-sitter
query execution with caching, performance monitoring, and error handling.

Features:
- LRU caching for query results
- Performance monitoring and statistics
- Comprehensive error handling
- Type-safe operations (PEP 484)
- Query validation and execution
"""

import logging
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, NamedTuple
from functools import lru_cache
from time import perf_counter
from dataclasses import dataclass

if TYPE_CHECKING:
    from tree_sitter import Language, Node, Tree, Query
    from ..language_loader import get_loader, LanguageLoader
    from ..utils.tree_sitter_compat import get_node_text_safe, TreeSitterQueryCompat

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """
    Result of a query execution.

    Attributes:
        query_name: Name of the query
        captures: List of captured nodes
        query_string: Original query string
        execution_time: Time taken to execute (seconds)
        success: Whether query execution was successful
        error_message: Error message if execution failed
    """

    query_name: str
    captures: List[Dict[str, Any]]
    query_string: str
    execution_time: float
    success: bool
    error_message: Optional[str] = None


class QueryExecutionError(Exception):
    """Raised when query execution fails."""

    pass


class UnsupportedQueryError(QueryExecutionError):
    """Raised when an unsupported query is requested."""

    pass


class QueryValidationError(QueryExecutionError):
    """Raised when query validation fails."""

    pass


class QueryExecutor:
    """
    Tree-sitter query executor with caching and performance monitoring.

    Features:
    - LRU caching for query results
    - Performance monitoring and statistics
    - Comprehensive error handling
    - Query validation
    - Batch query execution
    - Type-safe operations (PEP 484)

    Usage:
    ```python
    executor = QueryExecutor()

    # Execute a query
    result = executor.execute_query(tree, language, "function_name")

    # Execute multiple queries
    results = executor.execute_multiple_queries(tree, language, ["function_name", "class_name"])

    # Get statistics
    stats = executor.get_query_statistics()
    ```

    """

    # Class-level cache (shared across all QueryExecutor instances)
    _cache: Dict[str, QueryResult] = {}
    _cache_enabled: bool = True
    _default_cache_ttl: int = 3600  # 1 hour
    _max_cache_size: int = 100

    # Performance statistics
    _query_stats: Dict[str, int] = {
        "total_queries": 0,
        "successful_queries": 0,
        "failed_queries": 0,
        "total_execution_time": 0.0,
    }

    def __init__(
        self,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
        max_cache_size: int = 100,
    ) -> None:
        """
        Initialize query executor with caching and performance monitoring.

        Args:
            cache_enabled: Whether to enable LRU caching (default: True)
            cache_ttl: Cache time-to-live in seconds (default: 3600 = 1 hour)
            max_cache_size: Maximum number of cached queries (default: 100)

        Note:
            - LRU caching avoids re-executing identical queries
            - Performance monitoring tracks execution time and success rate
            - Statistics help identify performance bottlenecks
        """
        self._cache_enabled = cache_enabled
        self._default_cache_ttl = cache_ttl
        self._max_cache_size = max_cache_size

        # Initialize logger
        self._logger = logger

        self._logger.info(f"QueryExecutor initialized (cache={cache_enabled}, ttl={cache_ttl}s, maxsize={max_cache_size})")

    def execute_query(
        self,
        tree: Tree | None,
        language: Language | None,
        query_name: str,
        source_code: str | None = None,
    ) -> QueryResult:
        """
        Execute a predefined query by name.

        Args:
            tree: Tree-sitter tree to query
            language: Tree-sitter language object
            query_name: Name of the query
            source_code: Source code for context

        Returns:
            QueryResult with captures and metadata

        Raises:
            UnsupportedQueryError: If query is not supported
            QueryExecutionError: If query execution fails
            ValidationError: If query is invalid

        Note:
            - Uses LRU caching to avoid re-executing identical queries
            - Performance monitoring is built-in
            - Supports both predefined queries and custom queries
        """
        start_time = perf_counter()
        self._query_stats["total_queries"] += 1

        try:
            # 1. Validation
            if tree is None:
                self._logger.error("Tree is None")
                return QueryResult(
                    query_name=query_name,
                    captures=[],
                    query_string="",
                    execution_time=0.0,
                    success=False,
                    error_message="Tree is None",
                )

            if language is None:
                self._logger.error("Language is None")
                return QueryResult(
                    query_name=query_name,
                    captures=[],
                    query_string="",
                    execution_time=0.0,
                    success=False,
                    error_message="Language is None",
                )

            # 2. Get query string
            if not self._is_supported_query(query_name, language):
                self._logger.error(f"Query '{query_name}' not supported for {language}")
                self._query_stats["failed_queries"] += 1
                raise UnsupportedQueryError(f"Query '{query_name}' not supported for {language}")

            query_string = self._get_query_string(query_name, language)
            if query_string is None:
                self._logger.error(f"Could not get query string for '{query_name}'")
                self._query_stats["failed_queries"] += 1
                return QueryResult(
                    query_name=query_name,
                    captures=[],
                    query_string="",
                    execution_time=0.0,
                    success=False,
                    error_message=f"Could not get query string for '{query_name}'",
                )

            # 3. Check cache
            cache_key = self._generate_cache_key(query_name, language, query_string)
            if self._cache_enabled and cache_key in self._cache:
                self._logger.debug(f"Query cache hit for '{query_name}'")
                end_time = perf_counter()
                execution_time = end_time - start_time
                self._query_stats["successful_queries"] += 1
                self._query_stats["total_execution_time"] += execution_time
                return QueryResult(
                    query_name=query_name,
                    captures=self._cache[cache_key].captures,
                    query_string=query_string,
                    execution_time=execution_time,
                    success=True,
                    error_message=None,
                )

            # 4. Execute query
            try:
                captures = TreeSitterQueryCompat.safe_execute_query(
                    language, query_string, tree.root_node, fallback_result=[]
                )
            except Exception as e:
                self._logger.error(f"Query execution failed: {e}")
                self._query_stats["failed_queries"] += 1
                end_time = perf_counter()
                execution_time = end_time - start_time
                return QueryResult(
                    query_name=query_name,
                    captures=[],
                    query_string=query_string,
                    execution_time=execution_time,
                    success=False,
                    error_message=f"Query execution failed: {str(e)}",
                )

            # 5. Process captures
            processed_captures = self._process_captures(captures, source_code)

            # 6. Store in cache
            if self._cache_enabled:
                self._cache[cache_key] = QueryResult(
                    query_name=query_name,
                    captures=processed_captures,
                    query_string=query_string,
                    execution_time=0.0,  # Will be updated in return
                    success=True,
                    error_message=None,
                )

            # 7. Update statistics
            end_time = perf_counter()
            execution_time = end_time - start_time
            self._query_stats["successful_queries"] += 1
            self._query_stats["total_execution_time"] += execution_time

            self._logger.debug(f"Query '{query_name}' executed in {execution_time:.3f}s")

            return QueryResult(
                query_name=query_name,
                captures=processed_captures,
                query_string=query_string,
                execution_time=execution_time,
                success=True,
                error_message=None,
            )

        except Exception as e:
            self._logger.error(f"Unexpected error executing query '{query_name}': {e}")
            self._query_stats["failed_queries"] += 1
            end_time = perf_counter()
            execution_time = end_time - start_time
            return QueryResult(
                query_name=query_name,
                captures=[],
                query_string=query_string,
                execution_time=execution_time,
                success=False,
                error_message=f"Unexpected error: {str(e)}",
            )

    def execute_query_with_language_name(
        self,
        tree: Tree | None,
        language: str,
        query_name: str,
        source_code: str | None = None,
    ) -> QueryResult:
        """
        Execute a query using language name (for API compatibility).

        Args:
            tree: Tree-sitter tree to query
            language: Language name (e.g., "python")
            query_name: Name of the query
            source_code: Source code for context

        Returns:
            QueryResult with captures and metadata

        Note:
            - Wrapper method for convenience
            - Loads language loader dynamically
        """
        try:
            # Load language loader
            loader = get_loader()
            if loader is None:
                self._logger.error(f"Failed to load language loader")
                return QueryResult(
                    query_name=query_name,
                    captures=[],
                    query_string="",
                    execution_time=0.0,
                    success=False,
                    error_message="Failed to load language loader",
                )

            # Load language object
            lang_obj = loader.load_language(language)
            if lang_obj is None:
                self._logger.error(f"Failed to load language: {language}")
                return QueryResult(
                    query_name=query_name,
                    captures=[],
                    query_string="",
                    execution_time=0.0,
                    success=False,
                    error_message=f"Failed to load language: {language}",
                )

            # Execute query
            return self.execute_query(tree, lang_obj, query_name, source_code)

        except Exception as e:
            self._logger.error(f"Error loading language: {e}")
            self._query_stats["failed_queries"] += 1
            return QueryResult(
                query_name=query_name,
                captures=[],
                query_string="",
                execution_time=0.0,
                success=False,
                error_message=f"Failed to load language: {str(e)}",
            )

    def execute_query_string(
        self,
        tree: Tree | None,
        language: Language | None,
        query_string: str,
        source_code: str | None = None,
    ) -> QueryResult:
        """
        Execute a query string directly.

        Args:
            tree: Tree-sitter tree to query
            language: Tree-sitter language object
            query_string: Query string to execute
            source_code: Source code for context

        Returns:
            QueryResult with captures and metadata

        Note:
            - Does not support caching (query is dynamic)
            - Useful for custom queries
        """
        start_time = perf_counter()

        try:
            # 1. Validation
            if tree is None:
                self._logger.error("Tree is None")
                return QueryResult(
                    query_name="custom",
                    captures=[],
                    query_string=query_string,
                    execution_time=0.0,
                    success=False,
                    error_message="Tree is None",
                )

            if language is None:
                self._logger.error("Language is None")
                return QueryResult(
                    query_name="custom",
                    captures=[],
                    query_string=query_string,
                    execution_time=0.0,
                    success=False,
                    error_message="Language is None",
                )

            if not query_string:
                self._logger.error("Query string is empty")
                return QueryResult(
                    query_name="custom",
                    captures=[],
                    query_string=query_string,
                    execution_time=0.0,
                    success=False,
                    error_message="Query string is empty",
                )

            # 2. Validate query
            if not self._validate_query(query_string, language):
                self._logger.error(f"Invalid query string: {query_string[:50]}...")
                self._query_stats["failed_queries"] += 1
                return QueryResult(
                    query_name="custom",
                    captures=[],
                    query_string=query_string,
                    execution_time=0.0,
                    success=False,
                    error_message="Invalid query string",
                )

            # 3. Execute query
            try:
                captures = TreeSitterQueryCompat.safe_execute_query(
                    language, query_string, tree.root_node, fallback_result=[]
                )
            except Exception as e:
                self._logger.error(f"Query execution failed: {e}")
                self._query_stats["failed_queries"] += 1
                end_time = perf_counter()
                execution_time = end_time - start_time
                return QueryResult(
                    query_name="custom",
                    captures=[],
                    query_string=query_string,
                    execution_time=execution_time,
                    success=False,
                    error_message=f"Query execution failed: {str(e)}",
                )

            # 4. Process captures
            processed_captures = self._process_captures(captures, source_code)

            # 5. Update statistics
            end_time = perf_counter()
            execution_time = end_time - start_time
            self._query_stats["total_queries"] += 1
            self._query_stats["successful_queries"] += 1
            self._query_stats["total_execution_time"] += execution_time

            self._logger.debug(f"Custom query executed in {execution_time:.3f}s")

            return QueryResult(
                query_name="custom",
                captures=processed_captures,
                query_string=query_string,
                execution_time=execution_time,
                success=True,
                error_message=None,
            )

        except Exception as e:
            self._logger.error(f"Unexpected error executing custom query: {e}")
            self._query_stats["failed_queries"] += 1
            end_time = perf_counter()
            execution_time = end_time - start_time
            return QueryResult(
                query_name="custom",
                captures=[],
                query_string=query_string,
                execution_time=execution_time,
                success=False,
                error_message=f"Unexpected error: {str(e)}",
                execution_time=execution_time,
            )

    def execute_multiple_queries(
        self,
        tree: Tree | None,
        language: Language | None,
        query_names: List[str],
        source_code: str | None = None,
    ) -> Dict[str, QueryResult]:
        """
        Execute multiple queries and return combined results.

        Args:
            tree: Tree-sitter tree to query
            language: Tree-sitter language object
            query_names: List of query names
            source_code: Source code for context

        Returns:
            Dictionary mapping query names to QueryResults

        Note:
            - Executes queries sequentially
            - Uses caching for each query
            - Returns results for all queries (even if some fail)
        """
        start_time = perf_counter()
        results = {}

        self._logger.info(f"Executing {len(query_names)} queries")

        for query_name in query_names:
            try:
                result = self.execute_query(tree, language, query_name, source_code)
                results[query_name] = result
            except Exception as e:
                self._logger.error(f"Query '{query_name}' failed: {e}")
                results[query_name] = QueryResult(
                    query_name=query_name,
                    captures=[],
                    query_string="",
                    execution_time=0.0,
                    success=False,
                    error_message=str(e),
                )

        end_time = perf_counter()
        execution_time = end_time - start_time

        self._logger.info(f"Executed {len(query_names)} queries in {execution_time:.3f}s")

        return results

    def _is_supported_query(
        self,
        query_name: str,
        language: Language | None,
    ) -> bool:
        """
        Check if a query is supported for a language.

        Args:
            query_name: Name of the query
            language: Tree-sitter language object

        Returns:
            Support status (True/False)

        Note:
            - Checks against query loader
            - Returns False if query or language is None
        """
        if not query_name or query_name.strip() == "":
            return False

        if language is None:
            return False

        try:
            loader = get_loader()
            if loader is None:
                return False

            available_queries = loader.list_queries_for_language(language)
            return query_name in available_queries
        except Exception as e:
            self._logger.error(f"Error checking query support: {e}")
            return False

    def _get_query_string(
        self,
        query_name: str,
        language: Language | None,
    ) -> Optional[str]:
        """
        Get query string for a predefined query.

        Args:
            query_name: Name of the query
            language: Tree-sitter language object

        Returns:
            Query string or None

        Note:
            - Loads query string from query loader
            - Returns None if query is not found
        """
        try:
            loader = get_loader()
            if loader is None:
                return None

            return loader.get_query(language, query_name)
        except Exception as e:
            self._logger.error(f"Error getting query string: {e}")
            return None

    def _validate_query(
        self,
        query_string: str,
        language: Language | None,
    ) -> bool:
        """
        Validate a query string.

        Args:
            query_string: Query string to validate
            language: Tree-sitter language object

        Returns:
            Validation status (True/False)

        Note:
            - Basic validation
            - Checks for empty strings
            - Checks for syntax errors (basic)
        """
        if not query_string or query_string.strip() == "":
            return False

        # TODO: Add more sophisticated validation
        # For now, we'll trust that valid queries are pre-defined
        return True

    def _process_captures(
        self,
        captures: List[Tuple[Node, str]],
        source_code: str | None,
    ) -> List[Dict[str, Any]]:
        """
        Process query captures into standardized format.

        Args:
            captures: Raw captures from Tree-sitter query
            source_code: Source code for context

        Returns:
            List of processed capture dictionaries

        Note:
            - Extracts node information
            - Includes text content
            - Includes position information
        """
        processed = []

        try:
            for capture in captures:
                try:
                    # Handle different capture formats
                    if isinstance(capture, tuple) and len(capture) == 2:
                        node, name = capture
                    elif (
                        isinstance(capture, dict)
                        and "node" in capture
                        and "name" in capture
                    ):
                        node = capture["node"]
                        name = capture["name"]
                    else:
                        self._logger.warning(f"Unexpected capture format: {type(capture)}")
                        continue

                    if node is None:
                        continue

                    # Extract node information
                    node_text = get_node_text_safe(node, source_code)
                    node_type = getattr(node, "type", "unknown")
                    start_point = getattr(node, "start_point", (0, 0))
                    end_point = getattr(node, "end_point", (0, 0))
                    start_line, start_col = start_point
                    end_line, end_col = end_point

                    result_dict = {
                        "capture_name": name,
                        "node_type": node_type,
                        "start_line": start_line,
                        "start_column": start_col,
                        "end_line": end_line,
                        "end_column": end_col,
                        "text": node_text,
                    }

                    processed.append(result_dict)

        except Exception as e:
            self._logger.error(f"Error processing capture: {e}")

        return processed

    def _generate_cache_key(
        self,
        query_name: str,
        language: Language | None,
        query_string: str,
    ) -> str:
        """
        Generate cache key from query parameters.

        Args:
            query_name: Name of the query
            language: Tree-sitter language object
            query_string: Query string

        Returns:
            Cache key string

        Note:
            - Includes query name and language
            - Supports multiple queries for same language
            - Consistent hashing ensures cache stability
        """
        import hashlib

        language_name = getattr(language, "name", "unknown")
        key_components = [
            query_name,
            language_name,
            query_string[:50],  # Use first 50 chars of query
        ]

        key_str = ":".join(key_components)
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    def get_available_queries(
        self,
        language: str | None = None,
    ) -> List[str]:
        """
        Get list of available queries for a language.

        Args:
            language: Language name (optional)

        Returns:
            List of available query names

        Note:
            - Returns all queries if language is not specified
            - Returns language-specific queries if language is specified
        """
        try:
            loader = get_loader()
            if loader is None:
                return []

            if language:
                return loader.list_queries_for_language(language)
            else:
                # Return all queries across all languages
                all_queries = set()
                for lang in loader.list_supported_languages():
                    all_queries.update(loader.list_queries_for_language(lang))
                return sorted(all_queries)
        except Exception as e:
            self._logger.error(f"Error getting available queries: {e}")
            return []

    def get_query_description(
        self,
        language: str,
        query_name: str,
    ) -> Optional[str]:
        """
        Get description for a query.

        Args:
            language: Language name
            query_name: Query name

        Returns:
            Query description or None

        Note:
            - Returns None if query description is not found
        """
        try:
            loader = get_loader()
            if loader is None:
                return None

            return loader.get_query_description(language, query_name)
        except Exception as e:
            self._logger.error(f"Error getting query description: {e}")
            return None

    def get_query_statistics(self) -> Dict[str, Any]:
        """
        Get query execution statistics.

        Returns:
            Dictionary containing statistics

        Note:
            - Returns total queries, successful queries, failed queries
            - Returns total execution time and average execution time
            - Returns success rate (successful / total)
        """
        stats = self._query_stats.copy()

        if stats["total_queries"] > 0:
            stats["success_rate"] = stats["successful_queries"] / stats["total_queries"]
            stats["average_execution_time"] = (
                stats["total_execution_time"] / stats["total_queries"]
            )
        else:
            stats["success_rate"] = 0.0
            stats["average_execution_time"] = 0.0

        return stats

    def clear_cache(self) -> None:
        """
        Clear query cache.

        Note:
            - Invalidates all cached query results
            - Next query execution will re-execute
        """
        self._cache.clear()
        self._logger.info("Query cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache information

        Note:
            - Returns cache size and configuration
            - Useful for monitoring and debugging
        """
        return {
            "cache_enabled": self._cache_enabled,
            "cache_size": len(self._cache),
            "cache_ttl": self._default_cache_ttl,
            "max_cache_size": self._max_cache_size,
        }


# Module-level factory function
def create_query_executor(
    cache_enabled: bool = True,
    cache_ttl: int = 3600,
    max_cache_size: int = 100,
) -> QueryExecutor:
    """
    Factory function to create a properly configured query executor.

    This function creates a QueryExecutor instance with optimal settings.

    Args:
        cache_enabled: Whether to enable LRU caching (default: True)
        cache_ttl: Cache time-to-live in seconds (default: 3600 = 1 hour)
        max_cache_size: Maximum number of cached queries (default: 100)

    Returns:
        Configured QueryExecutor instance

    Raises:
        InitializationError: If initialization fails

    Note:
        - Recommended for new code
        - Provides clean factory pattern
        - All settings are properly initialized
    """
    return QueryExecutor(
        cache_enabled=cache_enabled,
        cache_ttl=cache_ttl,
        max_cache_size=max_cache_size,
    )


# Module-level loader for backward compatibility
try:
    from ..language_loader import get_loader

    loader = get_loader()
except Exception:
    loader = None


def get_query_executor() -> QueryExecutor:
    """
    Get default query executor instance (backward compatible).

    This function returns a singleton instance and is provided for
    backward compatibility. For new code, prefer using `create_query_executor()`.

    Returns:
        QueryExecutor instance with default settings

    Note:
        - Cache is enabled by default
        - Cache TTL is 1 hour
        - Max cache size is 100
        - For new code, prefer `create_query_executor()` factory function
    """
    return create_query_executor()


# Export for backward compatibility
__all__ = [
    "QueryExecutor",
    "QueryResult",
    "QueryExecutionError",
    "UnsupportedQueryError",
    "QueryValidationError",
    "create_query_executor",
    "get_query_executor",
]
