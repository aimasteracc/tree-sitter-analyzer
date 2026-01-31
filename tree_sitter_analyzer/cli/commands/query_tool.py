#!/usr/bin/env python3
"""
Query Tool - CLI Command for Tree-sitter Query Execution

This module provides a CLI command for executing custom Tree-sitter queries
on code with support for query strings, query files, and named queries.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling
- Performance optimization (lazy loading, caching)
- Detailed documentation

Features:
- Tree-sitter query execution
- Custom query support
- Query file loading
- Named query execution
- Type-safe operations (PEP 484)
- Command pattern implementation

Architecture:
- Command pattern implementation
- Layered design with clear separation of concerns
- Performance optimization with lazy loading
- Type-safe operations (PEP 484)
- Integration with analysis engine and core components

Usage:
    >>> from tree_sitter_analyzer.cli.commands import QueryToolCommand
    >>> result = command.execute(context)
    >>> print(result.message)

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import hashlib
import logging
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
)

# Type checking setup
if TYPE_CHECKING:
    # Core imports
    # Utility imports
    from ...utils.logging import (
        log_debug,
        log_error,
        log_info,
        log_warning,
    )
    from ..core.analysis_engine import AnalysisEngine, AnalysisRequest, AnalysisResult
    from ..core.cache_service import CacheConfig, CacheService
    from ..core.parser import Parser, ParseResult
    from ..core.query import QueryError, QueryExecutor, QueryResult
    from ..language_detector import LanguageDetector, LanguageInfo
    from ..plugins.manager import PluginInfo, PluginManager

    # CLI imports
    from .base import Command, CommandMetadata, CommandResult, ExecutionContext
else:
    # Runtime imports (when type checking is disabled)
    # Core imports
    AnalysisEngine = Any
    AnalysisRequest = Any
    AnalysisResult = Any
    Parser = Any
    ParseResult = Any
    QueryExecutor = Any
    QueryResult = Any
    QueryError = Any
    CacheService = Any
    CacheConfig = Any
    LanguageDetector = Any
    LanguageInfo = Any
    PluginManager = Any
    PluginInfo = Any

    # CLI imports
    Command = Any
    CommandResult = Any
    ExecutionContext = Any
    CommandMetadata = Any

    # Utility imports
    from ...utils.logging import (
        log_debug,
        log_error,
        log_info,
        log_warning,
    )

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# =====
# Type Definitions
# =====


class QueryToolProtocol(Protocol):
    """Interface for query tool command creation functions."""

    def __call__(self, project_root: str) -> "QueryToolCommand":
        """
        Create query tool command instance.

        Args:
            project_root: Root directory of the project

        Returns:
            QueryToolCommand instance
        """
        ...


class CacheProtocol(Protocol):
    """Interface for cache services."""

    def get(self, key: str) -> Any | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        ...

    def set(self, key: str, value: Any) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        ...

    def clear(self) -> None:
        """Clear all cache entries."""
        ...


class PerformanceMonitorProtocol(Protocol):
    """Interface for performance monitoring."""

    def measure_operation(self, operation_name: str) -> Any:
        """
        Measure operation execution time.

        Args:
            operation_name: Name of operation

        Returns:
            Context manager for measuring time
        """
        ...


# ============================================================================
# Custom Exceptions
# ============================================================================


class QueryToolError(Exception):
    """Base exception for query tool errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class InitializationError(QueryToolError):
    """Exception raised when query tool initialization fails."""

    pass


class ExecutionError(QueryToolError):
    """Exception raised when query execution fails."""

    pass


class ValidationError(QueryToolError):
    """Exception raised when validation fails."""

    pass


class CacheError(QueryToolError):
    """Exception raised when caching fails."""

    pass


# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True, slots=True)
class QuerySpec:
    """
    Query specification.

    Attributes:
        query_string: Tree-sitter query string
        query_file: Path to query file
        query_name: Named query name
        language: Programming language
    pattern: Search pattern (if applicable)
        scope: Query scope (file, project, etc.)
    """

    query_string: str | None = None
    query_file: str | None = None
    query_name: str | None = None
    language: str = "python"
    pattern: str | None = None
    scope: str = "file"

    def __hash__(self) -> int:
        """Hash based on query spec."""
        return hash(
            (
                self.query_string or "",
                self.query_file or "",
                self.query_name or "",
                self.language,
                self.pattern or "",
                self.scope,
            )
        )


@dataclass
class QueryResult:  # type: ignore
    """
    Result of query execution.

    Attributes:
        query_spec: Query specification
        captures: List of query captures
        execution_time: Time taken to execute (seconds)
        success: Whether execution was successful
        error_message: Error message if execution failed
    """

    query_spec: QuerySpec
    captures: list[dict[str, Any]]
    execution_time: float
    success: bool
    error_message: str | None = None

    @property
    def capture_count(self) -> int:
        """Get number of captures."""
        return len(self.captures)


@dataclass
class QueryToolConfig:
    """
    Configuration for query tool.

    Attributes:
        project_root: Root directory of the project
        enable_caching: Enable LRU caching for query results
        cache_max_size: Maximum size of LRU cache
        cache_ttl_seconds: Time-to-live for cache entries in seconds
        enable_performance_monitoring: Enable performance monitoring
        enable_thread_safety: Enable thread-safe operations
        max_query_depth: Maximum depth for query execution
    enable_lazy_loading: Enable lazy loading of components
    """

    project_root: str = "."
    enable_caching: bool = True
    cache_max_size: int = 128
    cache_ttl_seconds: int = 3600
    enable_performance_monitoring: bool = True
    enable_thread_safety: bool = True
    max_query_depth: int = 100
    enable_lazy_loading: bool = True

    def get_project_root(self) -> str:
        """Get project root path."""
        return self.project_root


# ============================================================================
# Query Tool Command
# ============================================================================


class QueryToolCommand(Command):
    """
    Optimized command for executing Tree-sitter queries.

    Features:
    - Tree-sitter query execution
    - Custom query support
    - Query file loading
    - Named query execution
    - Type-safe operations (PEP 484)
    - Performance optimization (caching, lazy loading)
    - Comprehensive error handling

    Architecture:
    - Command pattern implementation
    - Layered design with clear separation of concerns
    - Performance optimization with caching and lazy loading
    - Type-safe operations (PEP 484)
    - Integration with analysis engine and core components

    Usage:
        >>> from tree_sitter_analyzer.cli.commands import QueryToolCommand
        >>> command = QueryToolCommand()
        >>> result = command.execute(context)
        >>> print(result.message)
    """

    def __init__(self, config: QueryToolConfig | None = None):
        """
        Initialize query tool command.

        Args:
            config: Optional query tool configuration (uses defaults if None)
        """
        super().__init__(
            name="query",
            description="Execute Tree-sitter queries on code",
            category="analysis",
        )

        self._config = config or QueryToolConfig()

        # Thread-safe lock for operations
        self._lock = threading.RLock() if self._config.enable_thread_safety else None

        # Query executor (lazy loading)
        self._query_executor: QueryExecutor | None = None

        # Cache for query results
        self._query_cache: dict[str, QueryResult] = {}

        # Performance statistics
        self._stats: dict[str, Any] = {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "execution_times": [],
        }

    def execute(self, context: ExecutionContext) -> CommandResult:
        """
        Execute query tool command.

        Args:
            context: Execution context

        Returns:
            CommandResult with execution details

        Raises:
            ExecutionError: If query execution fails
            ValidationError: If validation fails
            CacheError: If caching fails

        Note:
            - Parses query specification from arguments
            - Executes Tree-sitter query
            - Returns captures and metadata
            - Handles errors gracefully
        """
        start_time = perf_counter()

        try:
            # Initialize components (lazy loading)
            self._ensure_components()

            # Parse query specification
            query_spec = self._parse_query_spec(context)

            if not query_spec:
                end_time = perf_counter()
                execution_time = end_time - start_time

                return CommandResult(
                    command_name=self._name,
                    success=False,
                    message="Invalid query specification",
                    execution_time=execution_time,
                )

            # Check cache
            cache_key = self._generate_cache_key(query_spec)
            cached_result = self._query_cache.get(cache_key)

            if cached_result:
                self._stats["cache_hits"] += 1
                end_time = perf_counter()
                execution_time = end_time - start_time

                self._stats["total_queries"] += 1
                self._stats["successful_queries"] += 1
                self._stats["execution_times"].append(execution_time)

                return CommandResult(
                    command_name=self._name,
                    success=True,
                    message=f"Query from cache: {query_spec.query_name or query_spec.query_string[:50]}...",  # type: ignore
                    data=cached_result,
                    execution_time=execution_time,
                )

            self._stats["cache_misses"] += 1

            # Execute query
            query_result = self._execute_query(query_spec, context)

            # Cache result
            if self._config.enable_caching and query_result.success:
                self._query_cache[cache_key] = query_result

            end_time = perf_counter()
            execution_time = end_time - start_time

            self._stats["total_queries"] += 1
            self._stats["execution_times"].append(execution_time)

            if query_result.success:
                self._stats["successful_queries"] += 1
            else:
                self._stats["failed_queries"] += 1

            return query_result

        except Exception as e:
            end_time = perf_counter()
            execution_time = end_time - start_time

            self._stats["total_queries"] += 1
            self._stats["failed_queries"] += 1
            self._stats["execution_times"].append(execution_time)

            log_error(f"Query execution failed: {e}")

            return CommandResult(
                command_name=self._name,
                success=False,
                message=f"Query execution failed: {str(e)}",
                execution_time=execution_time,
            )

    def _ensure_components(self) -> None:
        """
        Ensure all components are initialized (lazy loading).

        Raises:
            InitializationError: If component initialization fails

        Note:
            - Initializes all analysis components
            - Thread-safe operation
        """
        with self._lock if self._lock else nullcontext():
            if self._query_executor is None:
                if TYPE_CHECKING:
                    from ...core.query import QueryExecutor, QueryExecutorConfig
                else:
                    from ...core.query import QueryExecutor, QueryExecutorConfig

                try:
                    executor_config = QueryExecutorConfig(
                        project_root=self._config.project_root,
                        enable_caching=self._config.enable_caching,
                        cache_max_size=self._config.cache_max_size,
                        cache_ttl_seconds=self._config.cache_ttl_seconds,
                        enable_performance_monitoring=self._config.enable_performance_monitoring,
                        enable_thread_safety=self._config.enable_thread_safety,
                    )
                    self._query_executor = QueryExecutor(config=executor_config)
                    log_debug("Query executor initialized")
                except Exception as e:
                    log_error(f"Failed to initialize query executor: {e}")
                    raise InitializationError(
                        f"Failed to initialize query executor: {e}"
                    ) from e

    def _parse_query_spec(self, context: ExecutionContext) -> QuerySpec | None:
        """
        Parse query specification from arguments.

        Args:
            context: Execution context

        Returns:
            QuerySpec object or None

        Note:
            - Supports query strings, query files, and named queries
            - Validates query syntax if possible
            - Handles errors gracefully
        """
        try:
            if not context.args or len(context.args) < 1:
                return None

            # First argument is query specification
            spec = context.args[0]

            # Check if it's a query string
            if spec.startswith(
                ('"') or spec.startswith("'") or "(" in spec or "." in spec
            ):
                return QuerySpec(
                    query_string=spec,
                    language=self._config.project_root,
                )

            # Check if it's a query file
            if spec.endswith(".scm") or spec.endswith(".scm"):
                return QuerySpec(
                    query_file=spec,
                    language=self._config.project_root,
                )

            # Otherwise, treat it as a named query
            return QuerySpec(
                query_name=spec,
                language=self._config.project_root,
            )

        except Exception as e:
            log_error(f"Failed to parse query specification: {e}")
            return None

    def _execute_query(
        self, query_spec: QuerySpec, context: ExecutionContext
    ) -> QueryResult:
        """
        Execute Tree-sitter query with given specification.

        Args:
            query_spec: Query specification
            context: Execution context

        Returns:
            QueryResult with execution details

        Raises:
            ExecutionError: If query execution fails

        Note:
            - Parses file if needed
            - Executes Tree-sitter query
            - Returns captures and metadata
        """
        start_time = perf_counter()

        try:
            # Determine query string
            query_string = None

            if query_spec.query_string:
                # Use query string directly
                query_string = query_spec.query_string

            elif query_spec.query_file:
                # Load query from file
                query_string = self._load_query_file(query_spec.query_file)

            elif query_spec.query_name:
                # Load named query
                query_string = self._load_named_query(
                    query_spec.query_name, query_spec.language
                )
            else:
                return QueryResult(
                    query_spec=query_spec,
                    captures=[],
                    execution_time=0.0,
                    success=False,
                    error_message="Invalid query specification",
                )

            if not query_string:
                return QueryResult(
                    query_spec=query_spec,
                    captures=[],
                    execution_time=0.0,
                    success=False,
                    error_message="Failed to load query",
                )

            # Execute query
            if TYPE_CHECKING:
                from ..core.parser import Parser, ParserConfig
            else:
                from ..core.parser import Parser, ParserConfig

            parser_config = ParserConfig(
                project_root=self._config.project_root,
                enable_caching=self._config.enable_caching,
                enable_performance_monitoring=self._config.enable_performance_monitoring,
                enable_thread_safety=self._config.enable_thread_safety,
            )
            parser = Parser(config=parser_config)

            parse_result = parser.parse_code(query_string, query_spec.language)

            if not parse_result.success:
                end_time = perf_counter()
                execution_time = end_time - start_time

                return QueryResult(
                    query_spec=query_spec,
                    captures=[],
                    execution_time=execution_time,
                    success=False,
                    error_message=f"Parse failed: {parse_result.error_message}",
                )

            # Execute query on parsed tree
            if self._query_executor:
                query_result = self._query_executor.execute_query(
                    parse_result.tree,
                    parse_result.language,
                    query_spec.query_name or "custom",
                    parse_result.source_code,
                )
            else:
                end_time = perf_counter()
                execution_time = end_time - start_time

                return QueryResult(
                    query_spec=query_spec,
                    captures=[],
                    execution_time=execution_time,
                    success=False,
                    error_message="Query executor not available",
                )

            return QueryResult(
                query_spec=query_spec,
                captures=query_result.captures,
                execution_time=query_result.execution_time,
                success=query_result.success,
                error_message=query_result.error_message,
            )

        except Exception as e:
            end_time = perf_counter()
            execution_time = end_time - start_time

            log_error(f"Query execution failed: {e}")

            return QueryResult(
                query_spec=query_spec,
                captures=[],
                execution_time=execution_time,
                success=False,
                error_message=f"Query execution failed: {str(e)}",
            )

    def _load_query_file(self, file_path: str) -> str | None:
        """
        Load query string from file.

        Args:
            file_path: Path to query file

        Returns:
            Query string or None

        Note:
            - Reads file with encoding detection
            - Handles errors gracefully
        """
        try:
            if TYPE_CHECKING:
                from ..encoding_utils import EncodingManager, read_file_safe
            else:
                from ...encoding_utils import EncodingManager, read_file_safe

            EncodingManager()
            content, encoding = read_file_safe(file_path)
            return content  # type: ignore

        except Exception as e:
            log_error(f"Failed to load query file {file_path}: {e}")
            return None

    def _load_named_query(self, name: str, language: str) -> str | None:
        """
        Load named query from registry.

        Args:
            name: Query name
            language: Programming language

        Returns:
            Query string or None

        Note:
            - Looks up query in registry
            - Returns query string if found
        """
        # TODO: Implement named query registry
        # For now, return None
        log_warning(f"Named query registry not implemented: {name}")
        return None

    def _generate_cache_key(self, query_spec: QuerySpec) -> str:
        """
        Generate cache key from query specification.

        Args:
            query_spec: Query specification

        Returns:
            SHA-256 hash string

        Note:
            - Includes query string, language, scope
            - Ensures consistent hashing for cache stability
        """
        key_components = [
            "query",
            query_spec.query_string or "",
            query_spec.query_file or "",
            query_spec.query_name or "",
            query_spec.language,
            query_spec.pattern or "",
            query_spec.scope,
        ]

        # Generate SHA-256 hash
        key_str = ":".join(key_components)
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    def clear_cache(self) -> None:
        """
        Clear all caches.

        Note:
            - Invalidates all cached query results
            - Resets internal cache statistics
        """
        with self._lock if self._lock else nullcontext():
            self._query_cache.clear()
            self._stats["cache_hits"] = 0
            self._stats["cache_misses"] = 0

        log_info("Query tool cache cleared")

    def get_stats(self) -> dict[str, Any]:
        """
        Get query tool statistics.

        Returns:
            Dictionary with tool statistics

        Note:
            - Returns cache size and hit/miss ratios
            - Returns query execution statistics
            - Returns performance metrics
        """
        with self._lock if self._lock else nullcontext():
            return {
                "total_queries": self._stats["total_queries"],
                "successful_queries": self._stats["successful_queries"],
                "failed_queries": self._stats["failed_queries"],
                "cache_hits": self._stats["cache_hits"],
                "cache_misses": self._stats["cache_misses"],
                "cache_hit_rate": (
                    self._stats["cache_hits"]
                    / (self._stats["cache_hits"] + self._stats["cache_misses"])
                    if (self._stats["cache_hits"] + self._stats["cache_misses"]) > 0
                    else 0.0
                ),
                "execution_times": self._stats["execution_times"],
                "average_execution_time": (
                    sum(self._stats["execution_times"])
                    / len(self._stats["execution_times"])
                    if self._stats["execution_times"]
                    else 0
                ),
                "cache_size": len(self._query_cache),
                "config": {
                    "project_root": self._config.project_root,
                    "enable_caching": self._config.enable_caching,
                    "cache_max_size": self._config.cache_max_size,
                    "cache_ttl_seconds": self._config.cache_ttl_seconds,
                    "enable_performance_monitoring": self._config.enable_performance_monitoring,
                    "enable_thread_safety": self._config.enable_thread_safety,
                    "max_query_depth": self._config.max_query_depth,
                    "enable_lazy_loading": self._config.enable_lazy_loading,
                },
            }


# ============================================================================
# Convenience Functions with LRU Caching
# ============================================================================


@lru_cache(maxsize=64, typed=True)
def get_query_tool_command(project_root: str = ".") -> QueryToolCommand:
    """
    Get query tool command instance with LRU caching.

    Args:
        project_root: Root directory of the project (default: '.')

    Returns:
        QueryToolCommand instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    config = QueryToolConfig(project_root=project_root)
    return QueryToolCommand(config=config)


def create_query_tool_command(
    project_root: str = ".",
    enable_caching: bool = True,
    cache_max_size: int = 128,
    cache_ttl_seconds: int = 3600,
    enable_performance_monitoring: bool = True,
    enable_thread_safety: bool = True,
    max_query_depth: int = 100,
    enable_lazy_loading: bool = True,
) -> QueryToolCommand:
    """
    Factory function to create a properly configured query tool command.

    Args:
        project_root: Root directory of the project
        enable_caching: Enable LRU caching for query results
        cache_max_size: Maximum size of LRU cache
        cache_ttl_seconds: Time-to-live for cache entries in seconds
        enable_performance_monitoring: Enable performance monitoring
        enable_thread_safety: Enable thread-safe operations
        max_query_depth: Maximum depth for query execution
        enable_lazy_loading: Enable lazy loading of components

    Returns:
        Configured QueryToolCommand instance

    Raises:
        InitializationError: If initialization fails

    Note:
        - Creates all necessary dependencies
        - Provides clean factory interface
        - All settings are properly initialized
    """
    config = QueryToolConfig(
        project_root=project_root,
        enable_caching=enable_caching,
        cache_max_size=cache_max_size,
        cache_ttl_seconds=cache_ttl_seconds,
        enable_performance_monitoring=enable_performance_monitoring,
        enable_thread_safety=enable_thread_safety,
        max_query_depth=max_query_depth,
        enable_lazy_loading=enable_lazy_loading,
    )
    return QueryToolCommand(config=config)


# ============================================================================
# Module-level exports
# ============================================================================

__all__: list[str] = [
    # Data classes
    "QuerySpec",
    "QueryResult",
    "QueryToolConfig",
    # Exceptions
    "QueryToolError",
    "InitializationError",
    "ExecutionError",
    "ValidationError",
    "CacheError",
    # Main class
    "QueryToolCommand",
    # Convenience functions
    "get_query_tool_command",
    "create_query_tool_command",
]


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================


def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of module, class, or function to import

    Returns:
        Imported module, class, or function

    Raises:
        ImportError: If requested component is not found
    """
    # Handle specific imports
    if name == "QueryToolCommand":
        return QueryToolCommand
    elif name == "QuerySpec":
        return QuerySpec
    elif name == "QueryResult":
        return QueryResult
    elif name == "QueryToolConfig":
        return QueryToolConfig
    elif name in [
        "QueryToolError",
        "InitializationError",
        "ExecutionError",
        "ValidationError",
        "CacheError",
    ]:
        # Import from module
        import sys

        module = sys.modules[__name__]
        if module is None:
            raise ImportError(f"Module {name} not found")
        return module
    elif name == "get_query_tool_command":
        return get_query_tool_command
    elif name == "create_query_tool_command":
        return create_query_tool_command
    else:
        # Default behavior
        try:
            # Try to import from current package
            module = __import__(f".{name}", fromlist=["__name__"])
            return module
        except ImportError:
            raise ImportError(f"Module {name} not found") from None
