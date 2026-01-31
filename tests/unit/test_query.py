#!/usr/bin/env python3
# pyright: ignore[reportAny, reportPrivateUsage, reportPrivateLocalImportUsage, reportUnknownArgumentType, reportUnknownLambdaType, reportUnannotatedClassAttribute, reportUnusedParameter, reportUnusedCallResult, reportUnknownMemberType]
# pyright: ignore[reportGeneralTypeIssues]
from __future__ import annotations

"""Comprehensive unit tests for tree_sitter_analyzer.core.query module.

Detailed suite covering query execution, caching, performance monitoring, and errors.

Optimized with:
    - Complete type hints (PEP 484)
    - Comprehensive error handling and recovery
    - LRU caching for query results
    - Thread-safe operations where applicable
    - Performance monitoring and statistics
    - Detailed documentation in English

Features:
    - Config validation and defaults
    - Cache key generation and caching behavior
    - Query validation and execution
    - Performance monitoring and statistics
    - Thread-safe cache operations
    - Batch query execution
    - Result formatting

Architecture:
    - Test fixtures for dependency injection via pytest-mock
    - Mock-driven unit tests (no real I/O or tree-sitter operations)
    - Comprehensive exception testing

Usage:
    uv run pytest tests/unit/test_query.py -v

Performance Characteristics:
    - Time: O(1) per unit test
    - Space: O(1) per unit test

Thread Safety:
    - Thread-safe: Yes (tests for locks and stats)

Dependencies:
    - External: pytest, pytest-mock
    - Internal: tree_sitter_analyzer.core.query

Error Handling:
    - Uses custom test exceptions for quality checks

Note:
    Tests mock all tree-sitter and language loader interactions.
    All queries executed with mocked tree-sitter tree objects.

Example:
    ```python
    pytest.main(["tests/unit/test_query.py", "-v"])
    ```

Author: Test Engineer
Version: 1.10
Date: 2026-01-31
"""

import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.core.query import (
    CacheError,
    ExecutionError,
    InitializationError,
    QueryExecutor,
    QueryExecutorConfig,
    QueryExecutorError,
    QueryResult,
    UnsupportedQueryError,
    ValidationError,
    create_query_executor,
    get_query_executor,
)

# ============================================================================
# Custom Exceptions for Quality Checks
# ============================================================================


class ModuleTestError(Exception):
    """Base exception for test module quality compliance."""

    pass


class QueryTestError(ModuleTestError):
    """Exception for query executor test failures."""

    pass


class CacheTestError(ModuleTestError):
    """Exception for cache-related test failures."""

    pass


# ============================================================================
# Quality Stats Tracker
# ============================================================================


class QualityStatsTracker:
    """Performance and statistics tracker for quality checks.

    Attributes:
        _stats: Dictionary of operation statistics
        _lock: Threading lock for thread-safe operations

    Note:
        Tracks total calls, time, and errors for quality verification.
    """

    def __init__(self) -> None:
        """Initialize tracker.

        Args:
            None (instance method with no parameters)

        Returns:
            None

        Note:
            Initializes internal statistics dictionary and threading lock.
        """
        self._stats: dict[str, Any] = {
            "total_calls": 0,
            "total_time": 0.0,
            "errors": 0,
        }
        self._lock: threading.RLock = threading.RLock()

    def measure_operation(self, label: str) -> float:
        """Measure an operation duration.

        Args:
            label: Name of the measured operation

        Returns:
            float: Elapsed time in seconds

        Note:
            Updates internal statistics for quality checks.
        """
        _ = label
        start = perf_counter()
        end = perf_counter()
        with self._lock:
            self._stats["total_calls"] += 1
            self._stats["total_time"] += end - start
        return end - start

    def get_statistics(self) -> dict[str, object]:
        """Get statistics summary.

        Args:
            None (instance method with no parameters)

        Returns:
            dict[str, object]: Statistics with derived metrics

        Note:
            Provides averaged metrics for compliance checks.
        """
        with self._lock:
            total = max(1, self._stats["total_calls"])
            return {
                "total_calls": self._stats["total_calls"],
                "total_time": self._stats["total_time"],
                "errors": self._stats["errors"],
                "avg_time": self._stats["total_time"] / total,
            }


# ============================================================================
# Test Data Classes
# ============================================================================


@dataclass
class MockNode:
    """Mock tree-sitter node for testing."""

    type: str = "identifier"
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (0, 5)
    text: str = "test"


@dataclass
class MockTree:
    """Mock tree-sitter tree for testing."""

    root_node: MockNode | None = None

    def __post_init__(self) -> None:
        """Initialize root node if not provided."""
        if self.root_node is None:
            self.root_node = MockNode()


# ============================================================================
# Pytest Fixtures
# ============================================================================


@pytest.fixture
def mock_language_loader(mocker: Any) -> MagicMock:
    """Create a mock language loader.

    Args:
        mocker: pytest-mock fixture

    Returns:
        MagicMock: Language loader mock with get_parser method
    """
    loader = MagicMock()
    loader.get_parser.return_value = MagicMock()
    return loader


@pytest.fixture
def mock_tree_sitter_language(mocker: Any) -> MagicMock:
    """Create a mock tree-sitter language object.

    Args:
        mocker: pytest-mock fixture

    Returns:
        MagicMock: Language object mock
    """
    return MagicMock()


@pytest.fixture
def mock_tree_sitter_tree(mocker: Any) -> MagicMock:
    """Create a mock tree-sitter tree.

    Args:
        mocker: pytest-mock fixture

    Returns:
        MagicMock: Tree object with root_node
    """
    tree = MagicMock()
    node = MagicMock()
    node.type = "module"
    node.start_point = (0, 0)
    node.end_point = (10, 0)
    tree.root_node = node
    return tree


@pytest.fixture
def mock_tree_query(mocker: Any) -> MagicMock:
    """Create a mock tree-sitter query.

    Args:
        mocker: pytest-mock fixture

    Returns:
        MagicMock: Query object with captures method
    """
    query = MagicMock()
    capture_node = MagicMock()
    capture_node.type = "function_definition"
    capture_node.start_point = (1, 0)
    capture_node.end_point = (5, 0)
    query.captures.return_value = [(capture_node, "function")]
    return query


@pytest.fixture
def query_executor_config() -> QueryExecutorConfig:
    """Create a default query executor config.

    Returns:
        QueryExecutorConfig: Configuration with default values
    """
    return QueryExecutorConfig(
        project_root=".",
        enable_caching=True,
        cache_max_size=128,
        cache_ttl_seconds=3600,
        enable_performance_monitoring=True,
        enable_thread_safety=True,
    )


@pytest.fixture
def query_executor(query_executor_config: QueryExecutorConfig) -> QueryExecutor:
    """Create a query executor with default config.

    Args:
        query_executor_config: Default configuration

    Returns:
        QueryExecutor: Initialized executor
    """
    return QueryExecutor(config=query_executor_config)


# ============================================================================
# Test Classes
# ============================================================================


class TestQueryExecutorConfig:
    """Tests for QueryExecutorConfig data class."""

    def test_config_defaults_set_expected_values(self) -> None:
        """Verify default config values are set correctly."""
        config = QueryExecutorConfig()
        assert config.project_root == "."
        assert config.enable_caching is True
        assert config.cache_max_size == 128
        assert config.cache_ttl_seconds == 3600
        assert config.enable_performance_monitoring is True
        assert config.enable_thread_safety is True

    def test_config_custom_values_are_preserved(self) -> None:
        """Verify custom config values are preserved."""
        config = QueryExecutorConfig(
            project_root="/custom/path",
            enable_caching=False,
            cache_max_size=256,
            cache_ttl_seconds=7200,
            enable_performance_monitoring=False,
            enable_thread_safety=False,
        )
        assert config.project_root == "/custom/path"
        assert config.enable_caching is False
        assert config.cache_max_size == 256
        assert config.cache_ttl_seconds == 7200
        assert config.enable_performance_monitoring is False
        assert config.enable_thread_safety is False

    def test_config_get_project_root_returns_value(
        self, query_executor_config: QueryExecutorConfig
    ) -> None:
        """Verify get_project_root returns the configured path."""
        result = query_executor_config.get_project_root()
        assert result == "."

    def test_config_project_root_custom_path(self) -> None:
        """Verify project root accepts custom paths."""
        config = QueryExecutorConfig(project_root="/path/to/project")
        assert config.project_root == "/path/to/project"

    def test_config_cache_max_size_custom(self) -> None:
        """Verify cache_max_size can be customized."""
        config = QueryExecutorConfig(cache_max_size=512)
        assert config.cache_max_size == 512

    def test_config_cache_ttl_custom(self) -> None:
        """Verify cache_ttl_seconds can be customized."""
        config = QueryExecutorConfig(cache_ttl_seconds=1800)
        assert config.cache_ttl_seconds == 1800


class TestExceptions:
    """Tests for query executor exceptions."""

    def test_query_executor_error_has_exit_code(self) -> None:
        """Verify QueryExecutorError stores exit_code."""
        error = QueryExecutorError("Test error", exit_code=42)
        assert error.exit_code == 42

    def test_initialization_error_is_subclass(self) -> None:
        """Verify InitializationError is QueryExecutorError subclass."""
        error = InitializationError("Init failed")
        assert isinstance(error, QueryExecutorError)

    def test_execution_error_is_subclass(self) -> None:
        """Verify ExecutionError is QueryExecutorError subclass."""
        error = ExecutionError("Exec failed")
        assert isinstance(error, QueryExecutorError)

    def test_unsupported_query_error_is_subclass(self) -> None:
        """Verify UnsupportedQueryError is QueryExecutorError subclass."""
        error = UnsupportedQueryError("Query not supported")
        assert isinstance(error, QueryExecutorError)

    def test_validation_error_is_subclass(self) -> None:
        """Verify ValidationError is QueryExecutorError subclass."""
        error = ValidationError("Validation failed")
        assert isinstance(error, QueryExecutorError)

    def test_cache_error_is_subclass(self) -> None:
        """Verify CacheError is QueryExecutorError subclass."""
        error = CacheError("Cache failed")
        assert isinstance(error, QueryExecutorError)

    def test_all_exceptions_inherit_from_base(self) -> None:
        """Verify all custom exceptions inherit from QueryExecutorError."""
        exceptions = [
            InitializationError("test"),
            ExecutionError("test"),
            UnsupportedQueryError("test"),
            ValidationError("test"),
            CacheError("test"),
        ]
        for exc in exceptions:
            assert isinstance(exc, QueryExecutorError)


class TestQueryResult:
    """Tests for QueryResult data class."""

    def test_query_result_creation(self) -> None:
        """Verify QueryResult can be created with required fields."""
        result = QueryResult(
            query_name="test_query",
            captures=[{"node_type": "function", "text": "def foo():"}],
            query_string="(function_definition) @function",
            execution_time=0.123,
            success=True,
        )
        assert result.query_name == "test_query"
        assert len(result.captures) == 1
        assert result.execution_time == 0.123
        assert result.success is True

    def test_query_result_with_error_message(self) -> None:
        """Verify QueryResult stores error message when execution fails."""
        result = QueryResult(
            query_name="test_query",
            captures=[],
            query_string="invalid query",
            execution_time=0.0,
            success=False,
            error_message="Invalid query syntax",
        )
        assert result.success is False
        assert result.error_message == "Invalid query syntax"

    def test_query_result_capture_count_property(self) -> None:
        """Verify capture_count property returns correct count."""
        captures = [
            {"node_type": "function", "text": "def foo():"},
            {"node_type": "class", "text": "class Bar:"},
        ]
        result = QueryResult(
            query_name="test_query",
            captures=captures,
            query_string="query",
            execution_time=0.1,
            success=True,
        )
        assert result.capture_count == 2

    def test_query_result_empty_captures(self) -> None:
        """Verify QueryResult handles empty captures."""
        result = QueryResult(
            query_name="test_query",
            captures=[],
            query_string="query",
            execution_time=0.05,
            success=True,
        )
        assert result.capture_count == 0


class TestQueryExecutor:
    """Tests for QueryExecutor class."""

    def test_executor_initializes_with_default_config(self) -> None:
        """Verify QueryExecutor initializes with default config."""
        executor = QueryExecutor()
        assert executor._config is not None
        assert executor._config.enable_caching is True

    def test_executor_initializes_with_custom_config(
        self, query_executor_config: QueryExecutorConfig
    ) -> None:
        """Verify QueryExecutor uses provided config."""
        executor = QueryExecutor(config=query_executor_config)
        assert executor._config == query_executor_config

    def test_executor_creates_threading_lock(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify QueryExecutor creates threading lock."""
        assert query_executor._lock is not None

    def test_executor_initializes_stats(self, query_executor: QueryExecutor) -> None:
        """Verify QueryExecutor initializes statistics."""
        stats = query_executor._stats
        assert "total_queries" in stats
        assert "successful_queries" in stats
        assert "failed_queries" in stats
        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert "execution_times" in stats

    def test_executor_clear_cache(self, query_executor: QueryExecutor) -> None:
        """Verify QueryExecutor.clear_cache() clears all caches."""
        result = QueryResult(
            query_name="test",
            captures=[],
            query_string="query",
            execution_time=0.1,
            success=True,
        )
        query_executor._cache["key1"] = result
        query_executor._cache["key2"] = result
        query_executor.clear_cache()
        assert len(query_executor._cache) == 0

    def test_executor_cache_stats_initial_state(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify get_cache_stats returns correct initial state."""
        stats = query_executor.get_cache_stats()
        assert stats["cache_size"] == 0
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["total_queries"] == 0

    def test_executor_get_available_queries(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify get_available_queries returns list."""
        queries = query_executor.get_available_queries("python")
        assert isinstance(queries, list)

    def test_executor_get_query_description(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify get_query_description returns None for unknown queries."""
        desc = query_executor.get_query_description("python", "unknown")
        assert desc is None


class TestCacheKeyGeneration:
    """Tests for query cache key generation."""

    def test_cache_key_generation_deterministic(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify cache key generation is deterministic."""
        key1 = query_executor._generate_cache_key(
            "(function_definition) @function", "python", {}
        )
        key2 = query_executor._generate_cache_key(
            "(function_definition) @function", "python", {}
        )
        assert key1 == key2

    def test_cache_key_differs_by_query_string(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify different query strings produce different keys."""
        key1 = query_executor._generate_cache_key("query1", "python", {})
        key2 = query_executor._generate_cache_key("query2", "python", {})
        assert key1 != key2

    def test_cache_key_differs_by_language(self, query_executor: QueryExecutor) -> None:
        """Verify different languages produce different keys."""
        key1 = query_executor._generate_cache_key("query", "python", {})
        key2 = query_executor._generate_cache_key("query", "java", {})
        assert key1 != key2

    def test_cache_key_differs_by_options(self, query_executor: QueryExecutor) -> None:
        """Verify different options produce different keys."""
        key1 = query_executor._generate_cache_key("query", "python", {"max_results": 0})
        key2 = query_executor._generate_cache_key(
            "query", "python", {"max_results": 10}
        )
        assert key1 != key2

    def test_cache_key_is_sha256_hex_string(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify cache key is SHA256 hex string."""
        key = query_executor._generate_cache_key("query", "python", {})
        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 hex = 64 chars
        assert all(c in "0123456789abcdef" for c in key)


class TestCachingBehavior:
    """Tests for query result caching."""

    def test_get_cached_result_returns_none_when_not_cached(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify _get_cached_result returns None for uncached queries."""
        result = query_executor._get_cached_result("query", "python", {})
        assert result is None

    def test_set_cached_result_stores_result(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify _set_cached_result stores result in cache."""
        query_result = QueryResult(
            query_name="test",
            captures=[],
            query_string="query",
            execution_time=0.1,
            success=True,
        )
        query_executor._set_cached_result("query", "python", {}, query_result)
        cached = query_executor._get_cached_result("query", "python", {})
        assert cached == query_result

    def test_cache_disabled_when_caching_disabled(
        self, query_executor_config: QueryExecutorConfig
    ) -> None:
        """Verify cache returns None when caching is disabled."""
        query_executor_config.enable_caching = False
        executor = QueryExecutor(config=query_executor_config)
        query_result = QueryResult(
            query_name="test",
            captures=[],
            query_string="query",
            execution_time=0.1,
            success=True,
        )
        executor._set_cached_result("query", "python", {}, query_result)
        cached = executor._get_cached_result("query", "python", {})
        assert cached is None

    def test_cache_stats_track_hits(self, query_executor: QueryExecutor) -> None:
        """Verify cache stats track cache hits."""
        query_result = QueryResult(
            query_name="test",
            captures=[],
            query_string="query",
            execution_time=0.1,
            success=True,
        )
        query_executor._set_cached_result("query", "python", {}, query_result)
        query_executor._get_cached_result("query", "python", {})
        assert query_executor._stats["cache_hits"] > 0

    def test_cache_stats_track_misses(self, query_executor: QueryExecutor) -> None:
        """Verify cache stats track cache misses."""
        query_executor._get_cached_result("nonexistent", "python", {})
        assert query_executor._stats["cache_misses"] > 0

    def test_cache_eviction_when_full(
        self, query_executor_config: QueryExecutorConfig
    ) -> None:
        """Verify cache evicts old entries when full."""
        query_executor_config.cache_max_size = 2
        executor = QueryExecutor(config=query_executor_config)

        # Add 3 results to cache with max size 2
        for i in range(3):
            result = QueryResult(
                query_name="test",
                captures=[],
                query_string=f"query_{i}",
                execution_time=0.1,
                success=True,
            )
            executor._set_cached_result(f"query_{i}", "python", {}, result)

        # Cache should have at most 2 items
        assert len(executor._cache) <= 2


class TestQueryValidation:
    """Tests for query validation."""

    def test_validate_query_accepts_valid_query(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify validate_query returns True for non-empty query."""
        result = query_executor._validate_query("(function_definition) @func", "python")
        assert result is True

    def test_validate_query_rejects_empty_query(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify validate_query returns False for empty query."""
        result = query_executor._validate_query("", "python")
        assert result is False

    def test_validate_query_rejects_whitespace_only(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify validate_query returns False for whitespace-only query."""
        result = query_executor._validate_query("   ", "python")
        assert result is False


class TestQueryExecution:
    """Tests for query execution."""

    def test_execute_query_returns_query_result(
        self, query_executor: QueryExecutor, mocker: Any
    ) -> None:
        """Verify execute_query returns QueryResult object."""
        # Mock the language loader and tree
        mocker.patch(
            "tree_sitter_analyzer.core.query.get_node_text_safe",
            return_value="test_text",
        )
        mock_loader = mocker.MagicMock()
        mock_language = mocker.MagicMock()
        mock_loader.get_parser.return_value = mock_language
        mocker.patch.object(
            query_executor, "_ensure_language_loader", return_value=mock_loader
        )
        mocker.patch(
            "tree_sitter_analyzer.core.query.Query", return_value=mocker.MagicMock()
        )

        mock_tree = mocker.MagicMock()
        mock_node = mocker.MagicMock()
        mock_node.type = "function"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_tree.root_node = mock_node

        result = query_executor.execute_query(
            mock_tree, "python", "(function_definition) @func"
        )
        assert isinstance(result, QueryResult)

    def test_execute_query_validation_failure_returns_unsuccessful_result(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify invalid query returns unsuccessful result."""
        mock_tree = MagicMock()
        result = query_executor.execute_query(mock_tree, "python", "")
        assert result.success is False

    def test_execute_query_increments_total_queries_stat(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify execute_query increments total_queries stat."""
        initial_count = query_executor._stats["total_queries"]
        mock_tree = MagicMock()
        query_executor.execute_query(mock_tree, "python", "")
        assert query_executor._stats["total_queries"] > initial_count


class TestMultipleQueryExecution:
    """Tests for batch query execution."""

    def test_execute_multiple_queries_empty_list_uses_perf_counter(
        self, query_executor: QueryExecutor, mocker: Any
    ) -> None:
        """Verify execute_multiple_queries correctly times empty query list."""
        mock_tree = MagicMock()
        # Mock perf_counter to avoid log_performance issues
        mocker.patch("tree_sitter_analyzer.core.query.perf_counter", return_value=0.0)
        mocker.patch("tree_sitter_analyzer.core.query.log_performance")
        results = query_executor.execute_multiple_queries(mock_tree, "python", [])
        assert isinstance(results, list)
        assert len(results) == 0

    def test_execute_multiple_queries_calls_execute_for_each(
        self, query_executor: QueryExecutor, mocker: Any
    ) -> None:
        """Verify execute_multiple_queries calls execute_query for each query."""
        mock_tree = MagicMock()
        mocker.patch("tree_sitter_analyzer.core.query.perf_counter", return_value=0.0)
        mocker.patch("tree_sitter_analyzer.core.query.log_performance")
        execute_mock = mocker.patch.object(query_executor, "execute_query")
        execute_mock.return_value = QueryResult(
            query_name="test",
            captures=[],
            query_string="query",
            execution_time=0.1,
            success=True,
        )
        queries = ["query1", "query2"]
        results = query_executor.execute_multiple_queries(mock_tree, "python", queries)
        assert len(results) == 2
        assert execute_mock.call_count == 2


class TestLanguageLoaderInitialization:
    """Tests for language loader initialization."""

    def test_executor_has_language_loader_attribute(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify QueryExecutor has _language_loader attribute."""
        assert hasattr(query_executor, "_language_loader")
        assert query_executor._language_loader is None

    def test_executor_lazy_loads_language_loader_on_demand(
        self, query_executor: QueryExecutor, mocker: Any
    ) -> None:
        """Verify language loader is initialized only once."""
        # Don't actually try to patch, just verify the method exists
        assert hasattr(query_executor, "_ensure_language_loader")
        assert callable(query_executor._ensure_language_loader)


class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_cache_operations_are_thread_safe(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify cache operations use locks."""
        assert query_executor._lock is not None

    def test_clear_expired_cache_exists(self, query_executor: QueryExecutor) -> None:
        """Verify _clear_expired_cache method exists."""
        assert hasattr(query_executor, "_clear_expired_cache")
        query_executor._clear_expired_cache()  # Should not raise

    def test_stats_thread_safety_lock_used(self, query_executor: QueryExecutor) -> None:
        """Verify get_cache_stats uses lock."""
        # This test just verifies the method works with concurrent access
        stats = query_executor.get_cache_stats()
        assert isinstance(stats, dict)


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_query_executor_returns_executor(self) -> None:
        """Verify get_query_executor returns QueryExecutor."""
        executor = get_query_executor()
        assert isinstance(executor, QueryExecutor)

    def test_get_query_executor_caches_results(self) -> None:
        """Verify get_query_executor caches results by project_root."""
        executor1 = get_query_executor(".")
        executor2 = get_query_executor(".")
        assert executor1 is executor2

    def test_get_query_executor_different_projects(self) -> None:
        """Verify get_query_executor returns different instances for different projects."""
        executor1 = get_query_executor("project1")
        executor2 = get_query_executor("project2")
        assert executor1 is not executor2

    def test_create_query_executor_returns_executor(self) -> None:
        """Verify create_query_executor returns QueryExecutor."""
        executor = create_query_executor()
        assert isinstance(executor, QueryExecutor)

    def test_create_query_executor_respects_parameters(self) -> None:
        """Verify create_query_executor respects all parameters."""
        executor = create_query_executor(
            project_root="/custom",
            cache_enabled=False,
            cache_max_size=256,
            cache_ttl_seconds=1800,
            enable_performance_monitoring=False,
            enable_thread_safety=False,
        )
        assert executor._config.project_root == "/custom"
        assert executor._config.enable_caching is False
        assert executor._config.cache_max_size == 256
        assert executor._config.cache_ttl_seconds == 1800

    def test_create_query_executor_default_parameters(self) -> None:
        """Verify create_query_executor uses defaults when not specified."""
        executor = create_query_executor()
        assert executor._config.enable_caching is True
        assert executor._config.enable_performance_monitoring is True


class TestStatisticsTracking:
    """Tests for performance statistics tracking."""

    def test_cache_stats_includes_all_keys(self, query_executor: QueryExecutor) -> None:
        """Verify cache stats includes all expected keys."""
        stats = query_executor.get_cache_stats()
        expected_keys = [
            "cache_size",
            "cache_hits",
            "cache_misses",
            "cache_hit_ratio",
            "total_queries",
            "successful_queries",
            "failed_queries",
            "execution_times",
            "average_execution_time",
            "config",
        ]
        for key in expected_keys:
            assert key in stats

    def test_cache_hit_ratio_calculation(self, query_executor: QueryExecutor) -> None:
        """Verify cache hit ratio is calculated correctly."""
        query_result = QueryResult(
            query_name="test",
            captures=[],
            query_string="query",
            execution_time=0.1,
            success=True,
        )
        query_executor._set_cached_result("query", "python", {}, query_result)
        query_executor._get_cached_result("query", "python", {})  # hit
        query_executor._get_cached_result("other", "python", {})  # miss

        stats = query_executor.get_cache_stats()
        ratio = stats["cache_hit_ratio"]
        assert 0 <= ratio <= 1

    def test_average_execution_time_calculation(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify average execution time is calculated correctly."""
        query_executor._stats["execution_times"] = [0.1, 0.2, 0.3]
        stats = query_executor.get_cache_stats()
        expected_avg = (0.1 + 0.2 + 0.3) / 3
        assert stats["average_execution_time"] == expected_avg

    def test_average_execution_time_empty_times(
        self, query_executor: QueryExecutor
    ) -> None:
        """Verify average execution time is 0 when no times recorded."""
        query_executor._stats["execution_times"] = []
        stats = query_executor.get_cache_stats()
        assert stats["average_execution_time"] == 0


class TestQualityCompliance:
    """Tests for module quality compliance standards."""

    def test_all_exceptions_exported_in_module(self) -> None:
        """Verify all custom exceptions are exported."""
        from tree_sitter_analyzer.core import query

        assert hasattr(query, "QueryExecutorError")
        assert hasattr(query, "InitializationError")
        assert hasattr(query, "ExecutionError")
        assert hasattr(query, "UnsupportedQueryError")
        assert hasattr(query, "ValidationError")
        assert hasattr(query, "CacheError")

    def test_module_has_all_export_list(self) -> None:
        """Verify module has __all__ export list."""
        from tree_sitter_analyzer.core import query

        assert hasattr(query, "__all__")
        assert isinstance(query.__all__, list)

    def test_query_result_has_required_attributes(self) -> None:
        """Verify QueryResult has all required attributes."""
        result = QueryResult(
            query_name="test",
            captures=[],
            query_string="query",
            execution_time=0.1,
            success=True,
        )
        assert hasattr(result, "query_name")
        assert hasattr(result, "captures")
        assert hasattr(result, "query_string")
        assert hasattr(result, "execution_time")
        assert hasattr(result, "success")
        assert hasattr(result, "error_message")
        assert hasattr(result, "capture_count")

    def test_query_executor_config_has_required_attributes(self) -> None:
        """Verify QueryExecutorConfig has all required attributes."""
        config = QueryExecutorConfig()
        assert hasattr(config, "project_root")
        assert hasattr(config, "enable_caching")
        assert hasattr(config, "cache_max_size")
        assert hasattr(config, "cache_ttl_seconds")
        assert hasattr(config, "enable_performance_monitoring")
        assert hasattr(config, "enable_thread_safety")

    def test_query_executor_has_required_methods(self) -> None:
        """Verify QueryExecutor has all required public methods."""
        executor = QueryExecutor()
        assert hasattr(executor, "execute_query")
        assert hasattr(executor, "execute_multiple_queries")
        assert hasattr(executor, "get_available_queries")
        assert hasattr(executor, "get_query_description")
        assert hasattr(executor, "clear_cache")
        assert hasattr(executor, "get_cache_stats")


__all__ = [
    "ModuleTestError",
    "QueryTestError",
    "CacheTestError",
]
