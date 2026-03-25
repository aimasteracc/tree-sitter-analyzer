#!/usr/bin/env python3
"""
SearchCache 单元测试

Tests for the SearchCache class used by MCP tools.
Includes basic logic tests and format compatibility bug fix tests.
"""

import time
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.utils.search_cache import (
    SearchCache,
    clear_cache,
    configure_cache,
    get_default_cache,
)


class TestSearchCacheInit:
    """SearchCache 初始化测试"""

    @pytest.fixture(autouse=True)
    def clear_cache_between_tests(self):
        """Clear cache before each test to avoid interference"""
        clear_cache()
        yield
        clear_cache()

    def test_cache_initialization(self):
        """Test SearchCache initialization"""
        cache = SearchCache(max_size=50, ttl_seconds=600)
        assert cache.max_size == 50
        assert cache.ttl_seconds == 600
        assert len(cache.cache) == 0

        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["max_size"] == 50
        assert stats["ttl_seconds"] == 600
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats.get("hit_rate", 0) == 0


class TestSearchCacheBasicOperations:
    """SearchCache 基本操作测试"""

    @pytest.fixture(autouse=True)
    def clear_cache_between_tests(self):
        """Clear cache before each test to avoid interference"""
        clear_cache()
        yield
        clear_cache()

    def test_cache_basic_operations(self):
        """Test basic cache set/get operations"""
        cache = SearchCache(max_size=10, ttl_seconds=300)

        # Test cache miss
        result = cache.get("nonexistent_key")
        assert result is None

        # Test cache set and get
        test_data = {"results": ["file1.py", "file2.py"], "count": 2}
        cache.set("test_key", test_data)

        retrieved = cache.get("test_key")
        assert retrieved == test_data

        # Check stats
        stats = cache.get_stats()
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_cache_key_generation(self):
        """Test cache key generation"""
        cache = SearchCache()

        # Test basic key generation
        key1 = cache.create_cache_key("test", ["/path1"], case="smart", max_count=10)
        key2 = cache.create_cache_key("test", ["/path1"], case="smart", max_count=10)
        assert key1 == key2  # Same parameters should generate same key

        # Test different parameters generate different keys
        key3 = cache.create_cache_key(
            "test", ["/path1"], case="insensitive", max_count=10
        )
        assert key1 != key3

        key4 = cache.create_cache_key(
            "different", ["/path1"], case="smart", max_count=10
        )
        assert key1 != key4

    def test_cache_with_path_normalization(self):
        """Test cache key generation with path normalization"""
        cache = SearchCache()

        # Different path representations should normalize to same key
        key1 = cache.create_cache_key("test", ["/path/to/dir"], case="smart")

        # Note: The actual normalization depends on Path.resolve(),
        # but we can test that consistent inputs produce consistent outputs
        key3 = cache.create_cache_key("test", ["/path/to/dir"], case="smart")
        assert key1 == key3


class TestSearchCacheTTL:
    """SearchCache TTL 过期测试"""

    @pytest.fixture(autouse=True)
    def clear_cache_between_tests(self):
        """Clear cache before each test to avoid interference"""
        clear_cache()
        yield
        clear_cache()

    def test_cache_ttl_expiration(self):
        """Test TTL-based cache expiration"""
        cache = SearchCache(max_size=10, ttl_seconds=1)  # 1 second TTL

        test_data = {"results": ["file1.py"], "count": 1}
        cache.set("test_key", test_data)

        # Should be available immediately
        result = cache.get("test_key")
        assert result == test_data

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        result = cache.get("test_key")
        assert result is None


class TestSearchCacheLRU:
    """SearchCache LRU 驱逐测试"""

    @pytest.fixture(autouse=True)
    def clear_cache_between_tests(self):
        """Clear cache before each test to avoid interference"""
        clear_cache()
        yield
        clear_cache()

    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full"""
        cache = SearchCache(
            max_size=2, ttl_seconds=3600
        )  # 1 hour TTL to avoid expiration issues

        # Fill cache to capacity
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})

        # Small delay to ensure different timestamps
        time.sleep(0.01)

        # Access key1 to make it more recently used
        result1 = cache.get("key1")
        assert result1 is not None  # Ensure the get was successful

        # Small delay to ensure different timestamps
        time.sleep(0.01)

        # Add third item - should evict key2 (least recently used)
        cache.set("key3", {"data": "value3"})

        # key1 should still be there (more recently accessed)
        assert cache.get("key1") is not None
        # key2 should be evicted (least recently used)
        assert cache.get("key2") is None
        # key3 should be there (just added)
        assert cache.get("key3") is not None

        stats = cache.get_stats()
        assert stats["evictions"] >= 1


class TestSearchCacheClear:
    """SearchCache 清除测试"""

    @pytest.fixture(autouse=True)
    def clear_cache_between_tests(self):
        """Clear cache before each test to avoid interference"""
        clear_cache()
        yield
        clear_cache()

    def test_cache_clear(self):
        """Test cache clearing functionality"""
        cache = SearchCache()

        # Add some data
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})
        cache.get("key1")  # Generate a hit

        # Verify data is there
        assert cache.get("key1") is not None
        assert cache.get("key2") is not None

        # Clear cache
        cache.clear()

        # Verify cache is empty
        assert cache.get("key1") is None
        assert cache.get("key2") is None

        stats = cache.get_stats()
        assert stats["size"] == 0


class TestSearchCacheStatistics:
    """SearchCache 统计测试"""

    @pytest.fixture(autouse=True)
    def clear_cache_between_tests(self):
        """Clear cache before each test to avoid interference"""
        clear_cache()
        yield
        clear_cache()

    def test_cache_statistics_accuracy(self):
        """Test cache statistics are accurately tracked"""
        cache = SearchCache(max_size=5, ttl_seconds=300)

        # Generate some cache activity
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})

        # Generate hits and misses
        cache.get("key1")  # hit
        cache.get("key2")  # hit
        cache.get("nonexistent")  # miss
        cache.get("key1")  # hit again

        stats = cache.get_stats()
        assert stats["hits"] == 3
        assert stats["misses"] == 1
        expected_hit_rate = round(3 / 4 * 100, 2)  # Should match cache's rounding
        assert stats.get("hit_rate_percent", 0) == expected_hit_rate
        assert stats["size"] == 2


class TestSearchCacheGlobalFunctions:
    """SearchCache 全局函数测试"""

    @pytest.fixture(autouse=True)
    def clear_cache_between_tests(self):
        """Clear cache before each test to avoid interference"""
        clear_cache()
        yield
        clear_cache()

    def test_global_cache_functions(self):
        """Test global cache configuration functions"""
        # Test default cache
        default_cache = get_default_cache()
        assert isinstance(default_cache, SearchCache)

        # Test cache configuration
        configure_cache(max_size=200, ttl_seconds=1800)
        configured_cache = get_default_cache()
        assert configured_cache.max_size == 200
        assert configured_cache.ttl_seconds == 1800

        # Test global clear
        configured_cache.set("test", {"data": "value"})
        assert configured_cache.get("test") is not None

        clear_cache()
        assert configured_cache.get("test") is None


class TestSearchCacheThreadSafety:
    """SearchCache 线程安全测试"""

    @pytest.fixture(autouse=True)
    def clear_cache_between_tests(self):
        """Clear cache before each test to avoid interference"""
        clear_cache()
        yield
        clear_cache()

    def test_cache_thread_safety_structure(self):
        """Test that cache has thread safety mechanisms in place"""
        cache = SearchCache()

        # Verify that the cache has a lock (for thread safety)
        assert hasattr(cache, "_lock")
        assert cache._lock is not None


class TestSearchCacheFormatCompatibility:
    """SearchCache 格式兼容性测试 (bug fix tests)"""

    @pytest.fixture(autouse=True)
    def clear_cache_between_tests(self):
        """Clear cache before each test to avoid interference"""
        clear_cache()
        yield
        clear_cache()

    def test_total_only_should_not_return_for_detailed_request(self):
        """
        Test that cached total_only results (integers) are not returned
        when detailed results are requested.
        """
        cache = SearchCache()

        # Simulate the bug scenario:
        # 1. total_only query caches an integer result
        total_only_key = "query:test_total_only:True"
        cache.set(total_only_key, 3)  # Cache integer result

        # 2. User requests detailed results with same query
        detailed_key = "query:test_summary_only:True"  # Different format key

        # 3. get_compatible_result should NOT return the integer for detailed request
        result = cache.get_compatible_result(detailed_key, "summary")

        # Should return None (not compatible) instead of the integer 3
        assert (
            result is None
        ), "Should not return integer result for summary format request"

    def test_format_compatibility_validation(self):
        """Test the _is_format_compatible method with various scenarios."""
        cache = SearchCache()

        # Test total_only format compatibility
        assert cache._is_format_compatible(3, "total_only") is True
        assert cache._is_format_compatible({"matches": []}, "total_only") is False

        # Test count_only format compatibility
        count_result = {"file_counts": {"file1.java": 2}, "success": True}
        assert cache._is_format_compatible(count_result, "count_only") is True
        assert cache._is_format_compatible(3, "count_only") is False

        # Test summary format compatibility
        summary_result = {"success": True, "files": [], "total_matches": 0}
        assert cache._is_format_compatible(summary_result, "summary") is True
        assert cache._is_format_compatible(3, "summary") is False

        # Test normal format compatibility
        normal_result = {"matches": [{"file": "test.java", "line": 1}]}
        assert cache._is_format_compatible(normal_result, "normal") is True
        assert cache._is_format_compatible(3, "normal") is False

    def test_correct_format_cache_hit(self):
        """Test that correctly formatted cached results are returned."""
        cache = SearchCache()

        # Cache a summary result
        summary_key = "query:test_summary_only:True"
        summary_result = {
            "success": True,
            "files": [{"file": "test.java", "match_count": 2}],
            "total_matches": 2,
        }
        cache.set(summary_key, summary_result)

        # Request summary format - should get cache hit
        result = cache.get_compatible_result(summary_key, "summary")
        assert result is not None
        assert result == summary_result

    def test_cross_format_derivation_still_works(self):
        """Test that cross-format derivation still works after the fix."""
        cache = SearchCache()

        # Mock the derivation methods
        with (
            patch.object(cache, "_derive_count_key_from_cache_key") as mock_derive_key,
            patch.object(cache, "_can_derive_file_list") as mock_can_derive,
            patch.object(cache, "_derive_file_list_result") as mock_derive_result,
        ):
            # Setup mocks
            count_key = "query:test_count_only_matches:True"
            mock_derive_key.return_value = count_key
            mock_can_derive.return_value = True

            expected_derived = {
                "success": True,
                "files": ["test.java"],
                "cache_derived": True,
            }
            mock_derive_result.return_value = expected_derived

            # Cache a count result
            count_result = {
                "file_counts": {"test.java": 2},
                "success": True,
                "count_only": True,
            }
            cache.set(count_key, count_result)

            # Request file_list format - should derive from count data
            file_list_key = "query:test_file_list:True"
            result = cache.get_compatible_result(file_list_key, "file_list")

            # Should get derived result
            assert result == expected_derived
            mock_derive_result.assert_called_once_with(count_result, "file_list")

    def test_bug_reproduction_scenario(self):
        """
        Reproduce the exact bug scenario from the roo_task document.

        User sequence:
        1. total_only: true -> returns 3
        2. Request detailed results -> should NOT return 3, should return proper format
        """
        cache = SearchCache()

        # Step 1: User makes total_only request
        total_only_key = cache.create_cache_key(
            query="insert.*TEST_PATTERN_ABC|TEST_PATTERN_ABC.*insert",
            roots=["."],
            case="insensitive",
            include_globs=["*.java"],
            total_only=True,
        )
        cache.set(total_only_key, 3)  # Cache the integer result

        # Step 2: User requests detailed results (same query, different format)
        detailed_key = cache.create_cache_key(
            query="insert.*TEST_PATTERN_ABC|TEST_PATTERN_ABC.*insert",
            roots=["."],
            case="insensitive",
            include_globs=["*.java"],
            context_before=5,
            context_after=5,
        )

        # Step 3: get_compatible_result should NOT return the integer 3
        result = cache.get_compatible_result(detailed_key, "normal")

        # The bug was: this returned 3 instead of None
        # After fix: should return None (no compatible cached result)
        assert result is None, f"Expected None, but got {result}. Bug not fixed!"

    def test_unknown_format_prevents_primitive_return(self):
        """Test that unknown formats prevent primitive data return (the main bug)."""
        cache = SearchCache()

        # Cache a primitive result (the bug scenario)
        cache.set("test_key", 42)  # Integer result

        result = cache.get_compatible_result("test_key", "unknown_format")
        assert (
            result is None
        ), "Unknown formats should not return primitive data (prevents bug)"

        # But dict results are allowed for unknown formats (backward compatibility)
        cache.set("test_key2", {"some": "data"})
        result2 = cache.get_compatible_result("test_key2", "unknown_format")
        assert result2 is not None, "Dict results should be allowed for unknown formats"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
