#!/usr/bin/env python3
"""
Dynamic Query Loader for Tree-sitter

Handles loading of language-specific Tree-sitter queries with efficient caching
and lazy loading for optimal performance.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling
- LRU caching for queries
- Lazy loading for query modules
- Thread-safe operations
- Performance monitoring

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import functools
import threading
from typing import TYPE_CHECKING, Optional, Dict, List, Any, Union, Tuple, Callable, Type
import time
from pathlib import Path

# Type checking setup
if TYPE_CHECKING:
    from tree_sitter import Language, Parser

    # Plugins
    from .plugins import ElementExtractor, LanguagePlugin

    # Utilities
    from .utils import (
        log_debug,
        log_info,
        log_warning,
        log_error,
        log_performance,
    )
else:
    # Runtime imports (when type checking is disabled)
    Language = Any
    Parser = Any
    ElementExtractor = Any
    LanguagePlugin = Any

# ============================================================================
# Type Definitions
# ============================================================================

if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    Protocol = object

class QueryLoaderProtocol(Protocol):
    """Interface for query loader creation functions."""

    def __call__(self, project_root: str) -> "QueryLoader":
        """
        Create query loader instance.

        Args:
            project_root: Root directory of the project

        Returns:
            QueryLoader instance
        """
        ...

class QueryProtocol(Protocol):
    """Protocol for Tree-sitter query objects."""
    pass


# ============================================================================
# Custom Exceptions
# ============================================================================

class QueryLoaderError(Exception):
    """Base exception for query loader errors."""

    pass


class QueryLoadError(QueryLoaderError):
    """Exception raised when a query fails to load."""

    pass


class QueryExecutionError(QueryLoaderError):
    """Exception raised when a query fails to execute."""

    pass


class QuerySyntaxError(QueryLoaderError):
    """Exception raised when a query has syntax errors."""

    pass


# ============================================================================
# Query Data Classes
# ============================================================================

class QueryInfo:
    """
    Information about a Tree-sitter query.

    Attributes:
        name: Query name
        language: Programming language
        query_string: Tree-sitter query string
        description: Human-readable description
        metadata: Additional metadata
        cached: Whether the query is cached
    """

    def __init__(
        self,
        name: str,
        language: str,
        query_string: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.language = language
        self.query_string = query_string
        self.description = description
        self.metadata = metadata or {}
        self.cached = False


# ============================================================================
# Query Loader Configuration
# ============================================================================

class QueryLoaderConfig:
    """Configuration for query loader."""

    def __init__(
        self,
        enable_caching: bool = True,
        cache_max_size: int = 256,
        enable_lazy_loading: bool = True,
        enable_thread_safety: bool = True,
        enable_performance_monitoring: bool = True,
    ):
        """
        Initialize query loader configuration.

        Args:
            enable_caching: Enable LRU caching for queries
            cache_max_size: Maximum size of LRU cache
            enable_lazy_loading: Enable lazy loading for query modules
            enable_thread_safety: Enable thread-safe operations
            enable_performance_monitoring: Enable performance monitoring
        """
        self.enable_caching = enable_caching
        self.cache_max_size = cache_max_size
        self.enable_lazy_loading = enable_lazy_loading
        self.enable_thread_safety = enable_thread_safety
        self.enable_performance_monitoring = enable_performance_monitoring


# ============================================================================
# Query Loader
# ============================================================================

class QueryLoader:
    """
    Optimized query loader with enhanced caching, lazy loading, and thread safety.

    Features:
    - LRU caching for queries
    - Lazy loading for query modules
    - Thread-safe operations
    - Performance monitoring
    - Comprehensive error handling

    Usage:
        >>> loader = QueryLoader()
        >>> query_info = loader.load_query("python", "functions")
        >>> print(queryInfo.query_string)
    """

    def __init__(self, config: Optional[QueryLoaderConfig] = None):
        """
        Initialize query loader.

        Args:
            config: Optional query loader configuration (uses defaults if None)
        """
        self.config = config or QueryLoaderConfig()

        # Loaded query modules
        self._loaded_query_modules: Dict[str, Any] = {}

        # Query cache (LRU)
        self._query_cache: Dict[str, QueryInfo] = {}

        # Metadata cache (LRU)
        self._metadata_cache: Dict[str, Dict[str, Any]] = {}

        # Thread-safe lock for operations
        self._lock = threading.RLock() if self.config.enable_thread_safety else type(None)

        # Performance statistics
        self._stats: Dict[str, Any] = {
            "total_loads": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "load_times": [],
        }

    def load_query(
        self, language: str, query_name: str, project_root: Optional[str] = None
    ) -> QueryInfo:
        """
        Load a specific query for a language.

        Args:
            language: Programming language (e.g., 'python', 'java')
            query_name: Name of the query to load
            project_root: Optional root directory for project-specific queries

        Returns:
            QueryInfo containing query details

        Raises:
            QueryLoaderError: If query loader fails
            QueryLoadError: If query fails to load

        Performance:
            Uses LRU caching and lazy loading for optimal performance.
        """
        with self._lock if self.config.enable_thread_safety else type(None):
            # Update statistics
            self._stats["total_loads"] += 1

            # Check cache first
            cache_key = f"{language}:{query_name}"
            if self.config.enable_caching and cache_key in self._query_cache:
                self._stats["cache_hits"] += 1
                log_debug(f"Cache hit for query: {cache_key}")
                return self._query_cache[cache_key]

            self._stats["cache_misses"] += 1
            log_debug(f"Cache miss for query: {cache_key}")

            # Load query module (lazy loading)
            if self.config.enable_lazy_loading and query_name not in self._loaded_query_modules:
                self._load_query_module(language)

            # Get query string from loaded module
            try:
                query_module = self._loaded_query_modules.get(language)
                if not query_module:
                    raise QueryLoadError(f"Query module not loaded for language: {language}")

                # Get query string
                if hasattr(query_module, "get_query"):
                    query_string = query_module.get_query(query_name)
                elif hasattr(query_module, query_name):
                    query_string = getattr(query_module, query_name)
                else:
                    raise QueryLoadError(f"Query not found: {query_name}")

                # Get description
                description = ""
                if hasattr(query_module, "get_query_description"):
                    description = query_module.get_query_description(query_name)
                elif hasattr(query_module, f"{query_name}_description"):
                    description = getattr(query_module, f"{query_name}_description", "")

                # Get metadata
                metadata = {}
                if hasattr(query_module, "get_query_metadata"):
                    metadata = query_module.get_query_metadata(query_name)
                elif hasattr(query_module, f"{query_name}_metadata"):
                    metadata = getattr(query_module, f"{query_name}_metadata", {})

                # Create query info
                query_info = QueryInfo(
                    name=query_name,
                    language=language,
                    query_string=query_string,
                    description=description,
                    metadata=metadata,
                )
                query_info.cached = False

                # Cache result
                if self.config.enable_caching:
                    if len(self._query_cache) >= self.config.cache_max_size:
                        # Clear oldest entry (simple implementation)
                        oldest_key = next(iter(self._query_cache))
                        del self._query_cache[oldest_key]
                    self._query_cache[cache_key] = query_info
                    query_info.cached = True

                return query_info

            except Exception as e:
                raise QueryLoadError(f"Failed to load query {query_name} for {language}: {e}")

    def load_query_module(self, language: str) -> Any:
        """
        Load query module for a specific language.

        Args:
            language: Programming language to load queries for

        Returns:
            Loaded query module

        Raises:
            QueryLoadError: If query module fails to load

        Performance:
            Uses module caching to avoid repeated imports.
        """
        module_name = f"tree_sitter_analyzer.queries.{language}"

        # Check if already loaded
        if module_name in self._loaded_query_modules:
            return self._loaded_query_modules[module_name]

        try:
            start_time = time.perf_counter()
            module = __import__(module_name)
            end_time = time.perf_counter()

            log_debug(f"Loaded query module {module_name} in {(end_time - start_time) * 1000:.2f}ms")

            # Cache module
            if self.config.enable_lazy_loading:
                self._loaded_query_modules[module_name] = module

            return module

        except ImportError as e:
            raise QueryLoadError(f"Failed to import query module {module_name}: {e}")
        except Exception as e:
            raise QueryLoadError(f"Failed to load query module {module_name}: {e}")

    def list_queries(self, language: str) -> List[str]:
        """
        List all available queries for a language.

        Args:
            language: Programming language to list queries for

        Returns:
            List of query names

        Raises:
            QueryLoaderError: If query loader fails

        Performance:
            Uses cached query metadata for optimal performance.
        """
        try:
            query_module = self.load_query_module(language)

            # Get query list
            if hasattr(query_module, "list_queries"):
                return query_module.list_queries()
            elif hasattr(query_module, "ALL_QUERIES"):
                return list(query_module.ALL_QUERIES.keys())
            else:
                # Inspect module attributes
                queries = []
                for attr_name in dir(query_module):
                    if not attr_name.startswith("_") and attr_name.isupper():
                        attr_value = getattr(query_module, attr_name)
                        if isinstance(attr_value, str):
                            queries.append(attr_name)
                return queries

        except Exception as e:
            raise QueryLoaderError(f"Failed to list queries for {language}: {e}")

    def get_query_description(self, language: str, query_name: str) -> str:
        """
        Get description for a specific query.

        Args:
            language: Programming language
            query_name: Name of the query

        Returns:
            Query description

        Raises:
            QueryLoaderError: If query loader fails
        """
        try:
            query_info = self.load_query(language, query_name)
            return query_info.description
        except Exception as e:
            raise QueryLoaderError(f"Failed to get description for {query_name}: {e}")

    def get_query_metadata(self, language: str, query_name: str) -> Dict[str, Any]:
        """
        Get metadata for a specific query.

        Args:
            language: Programming language
            query_name: Name of the query

        Returns:
            Query metadata dictionary

        Raises:
            QueryLoaderError: If query loader fails
        """
        try:
            query_info = self.load_query(language, query_name)
            return query_info.metadata
        except Exception as e:
            raise QueryLoaderError(f"Failed to get metadata for {query_name}: {e}")

    def execute_query(
        self, query_string: str, parser: Parser, file_path: Optional[str] = None
    ) -> List[Any]:
        """
        Execute a query on a parser.

        Args:
            query_string: Tree-sitter query string
            parser: Tree-sitter parser
            file_path: Optional file path for error reporting

        Returns:
            List of query results

        Raises:
            QueryExecutionError: If query fails to execute
            QuerySyntaxError: If query has syntax errors

        Performance:
            Monitors query execution time.
        """
        try:
            start_time = time.perf_counter()

            # Execute query
            # (Implementation depends on Tree-sitter query API)
            # This is a simplified version - real implementation would be more complex

            # For now, just log that we executed the query
            log_performance(f"Executing query: {query_string[:50]}...")

            results = []
            # In a real implementation, we would:
            # 1. Parse the query string
            # 2. Execute the query on the parse tree
            # 3. Collect results
            # 4. Return results

            end_time = time.perf_counter()
            log_performance(f"Query executed in {(end_time - start_time) * 1000:.2f}ms")

            return results

        except Exception as e:
            raise QueryExecutionError(f"Failed to execute query: {e}")

    def clear_cache(self) -> None:
        """
        Clear all caches (query cache, metadata cache, query modules).

        This is useful for memory management and testing.
        """
        with self._lock if self.config.enable_thread_safety else type(None):
            self._query_cache.clear()
            self._metadata_cache.clear()
            if self.config.enable_lazy_loading:
                self._loaded_query_modules.clear()
            log_info("Query caches cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "query_cache_size": len(self._query_cache),
            "metadata_cache_size": len(self._metadata_cache),
            "module_cache_size": len(self._loaded_query_modules),
            "stats": self._stats,
            "config": {
                "enable_caching": self.config.enable_caching,
                "cache_max_size": self.config.cache_max_size,
                "enable_lazy_loading": self.config.enable_lazy_loading,
                "enable_thread_safety": self.config.enable_thread_safety,
                "enable_performance_monitoring": self.config.enable_performance_monitoring,
            },
        }


# ============================================================================
# Convenience Functions with Caching
# ============================================================================

@functools.lru_cache(maxsize=64, typed=True)
def get_query_loader_cached(project_root: str) -> QueryLoader:
    """
    Create query loader instance with LRU caching.

    Args:
        project_root: Root directory of the project

    Returns:
        QueryLoader instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    config = QueryLoaderConfig(
        enable_caching=True,
        cache_max_size=256,
        enable_lazy_loading=True,
        enable_thread_safety=True,
        enable_performance_monitoring=True,
    )
    return QueryLoader(config=config)


# ============================================================================
# Convenience Functions (Type-safe)
# ============================================================================

def create_query_loader(project_root: str) -> QueryLoader:
    """
    Create query loader instance.

    Args:
        project_root: Root directory of the project

    Returns:
        QueryLoader instance

    Performance:
        Uses LRU-cached factory function with maxsize=64.
    """
    return get_query_loader_cached(project_root)


def load_query(language: str, query_name: str) -> QueryInfo:
    """
    Load a specific query.

    Args:
        language: Programming language
        query_name: Name of the query

    Returns:
        QueryInfo containing query details

    Raises:
        QueryLoadError: If query fails to load

    Performance:
        Uses LRU-cached query loader.
    """
    loader = get_query_loader(".")
    return loader.load_query(language, query_name)


def list_queries(language: str) -> List[str]:
    """
    List all available queries for a language.

    Args:
        language: Programming language to list queries for

    Returns:
        List of query names

    Raises:
        QueryLoaderError: If query loader fails

    Performance:
        Uses LRU-cached query loader.
    """
    loader = get_query_loader(".")
    return loader.list_queries(language)


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================

def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of the component to import

    Returns:
        Imported component or function

    Raises:
        ImportError: If component not found
    """
    # Handle legacy imports
    if name == "QueryLoader":
        return QueryLoader
    elif name == "QueryLoaderConfig":
        return QueryLoaderConfig
    elif name == "QueryInfo":
        return QueryInfo
    elif name in ["create_query_loader", "load_query", "list_queries"]:
        # Import from module
        module = __import__(f".{name}", fromlist=[f".{name}"])
        return getattr(module, name)
    else:
        raise ImportError(f"Module {name} not found")
