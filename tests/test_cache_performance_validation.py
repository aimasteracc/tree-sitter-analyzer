#!/usr/bin/env python3
"""
Performance validation tests for Phase 2 cache implementation.

This module tests the actual performance improvements achieved by the caching system
using real search operations on the test directory.
"""

import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.utils.search_cache import clear_cache, configure_cache


class TestCachePerformanceValidation:
    """Test cache performance improvements with real search operations"""

    @pytest.fixture(scope="class")
    def test_directory(self):
        """Path to the test directory - using project examples directory"""
        project_root = Path(__file__).parent.parent
        return str(project_root / "examples")

    @pytest.fixture
    def tool_with_cache(self, test_directory):
        """Create a SearchContentTool with caching enabled"""
        clear_cache()  # Start with clean cache
        configure_cache(max_size=100, ttl_seconds=300)  # 5 minutes TTL for testing
        return SearchContentTool(project_root=test_directory, enable_cache=True)

    @pytest.fixture
    def tool_without_cache(self, test_directory):
        """Create a SearchContentTool with caching disabled"""
        return SearchContentTool(project_root=test_directory, enable_cache=False)

    @pytest.mark.asyncio
    async def test_cache_performance_improvement_real_search(
        self, tool_with_cache, test_directory
    ):
        """Test actual performance improvement with real search operations"""
        if not Path(test_directory).exists():
            pytest.skip(f"Test directory {test_directory} does not exist")

        # Test search arguments
        search_args = {
            "query": "class",
            "roots": [test_directory],
            "case": "smart",
            "include_globs": ["*.java", "*.xml"],
        }

        # First search - cache miss
        start_time = time.time()
        result1 = await tool_with_cache.execute(search_args)
        first_search_time = time.time() - start_time

        # Verify first search was successful
        assert result1.get("success", True)
        assert not result1.get("cache_hit", False)

        # Second search - cache hit
        start_time = time.time()
        result2 = await tool_with_cache.execute(search_args)
        second_search_time = time.time() - start_time

        # Verify second search was a cache hit
        assert result2.get("success", True)
        assert result2.get("cache_hit", False) is True

        # Verify results are identical (excluding cache_hit flag)
        result1_clean = {k: v for k, v in result1.items() if k != "cache_hit"}
        result2_clean = {k: v for k, v in result2.items() if k != "cache_hit"}
        assert result1_clean == result2_clean

        # Verify performance improvement
        performance_improvement = (
            (first_search_time - second_search_time) / first_search_time * 100
        )
        print(f"First search: {first_search_time:.3f}s")
        print(f"Second search: {second_search_time:.3f}s")
        print(f"Performance improvement: {performance_improvement:.1f}%")

        # Cache hit should be significantly faster (at least 50% improvement)
        assert (
            second_search_time < first_search_time * 0.5
        ), f"Cache hit should be at least 50% faster, got {performance_improvement:.1f}% improvement"

    @pytest.mark.asyncio
    async def test_cache_vs_no_cache_comparison(
        self, tool_with_cache, tool_without_cache, test_directory
    ):
        """Compare performance between cached and non-cached tools"""
        if not Path(test_directory).exists():
            pytest.skip(f"Test directory {test_directory} does not exist")

        search_args = {
            "query": "public",
            "roots": [test_directory],
            "case": "insensitive",
            "max_count": 50,
        }

        # Warm up the cache
        await tool_with_cache.execute(search_args)

        # Time multiple searches with cache
        cached_times = []
        for _ in range(3):
            start_time = time.time()
            result = await tool_with_cache.execute(search_args)
            cached_times.append(time.time() - start_time)
            assert result.get("cache_hit", False) is True

        # Time multiple searches without cache
        non_cached_times = []
        for _ in range(3):
            start_time = time.time()
            await tool_without_cache.execute(search_args)
            non_cached_times.append(time.time() - start_time)

        avg_cached_time = sum(cached_times) / len(cached_times)
        avg_non_cached_time = sum(non_cached_times) / len(non_cached_times)

        performance_improvement = (
            (avg_non_cached_time - avg_cached_time) / avg_non_cached_time * 100
        )

        print(f"Average cached search time: {avg_cached_time:.3f}s")
        print(f"Average non-cached search time: {avg_non_cached_time:.3f}s")
        print(f"Performance improvement: {performance_improvement:.1f}%")

        # Cached searches should be significantly faster
        assert (
            avg_cached_time < avg_non_cached_time * 0.3
        ), f"Cached searches should be at least 70% faster, got {performance_improvement:.1f}% improvement"

    @pytest.mark.asyncio
    async def test_cache_statistics_tracking(self, tool_with_cache, test_directory):
        """Test that cache statistics are properly tracked"""
        if not Path(test_directory).exists():
            pytest.skip(f"Test directory {test_directory} does not exist")

        # Clear cache and get initial stats
        clear_cache()
        initial_stats = tool_with_cache.cache.get_stats()
        assert initial_stats["hits"] == 0
        assert initial_stats["misses"] == 0

        search_args = {
            "query": "import",
            "roots": [test_directory],
            "include_globs": ["*.java"],
        }

        # First search - should be a miss
        await tool_with_cache.execute(search_args)
        stats_after_first = tool_with_cache.cache.get_stats()
        assert stats_after_first["misses"] == 1
        assert stats_after_first["hits"] == 0
        assert stats_after_first["hit_rate_percent"] == 0.0

        # Second search - should be a hit
        await tool_with_cache.execute(search_args)
        stats_after_second = tool_with_cache.cache.get_stats()
        assert stats_after_second["misses"] == 1
        assert stats_after_second["hits"] == 1
        assert stats_after_second["hit_rate_percent"] == 50.0

        # Third search - should be another hit
        await tool_with_cache.execute(search_args)
        stats_after_third = tool_with_cache.cache.get_stats()
        assert stats_after_third["misses"] == 1
        assert stats_after_third["hits"] == 2
        assert stats_after_third["hit_rate_percent"] == 66.67

    @pytest.mark.asyncio
    async def test_different_search_parameters_create_different_cache_keys(
        self, tool_with_cache, test_directory
    ):
        """Test that different search parameters create different cache entries"""
        if not Path(test_directory).exists():
            pytest.skip(f"Test directory {test_directory} does not exist")

        base_args = {
            "query": "class",
            "roots": [test_directory],
        }

        # Search with different parameters
        search_variants = [
            {**base_args, "case": "smart"},
            {**base_args, "case": "insensitive"},
            {**base_args, "include_globs": ["*.java"]},
            {**base_args, "include_globs": ["*.xml"]},
        ]

        # Each search should be a cache miss (different cache keys)
        for i, search_args in enumerate(search_variants):
            result = await tool_with_cache.execute(search_args)
            assert result.get("success", True)
            # Only the first search should definitely not be a cache hit
            if i == 0:
                assert not result.get("cache_hit", False)

        # Repeat the first search - should now be a cache hit
        result = await tool_with_cache.execute(search_variants[0])
        assert result.get("cache_hit", False) is True

    @pytest.mark.asyncio
    async def test_cache_memory_usage_efficiency(self, tool_with_cache, test_directory):
        """Test cache memory usage and LRU eviction"""
        if not Path(test_directory).exists():
            pytest.skip(f"Test directory {test_directory} does not exist")

        # Configure small cache for testing
        configure_cache(max_size=5, ttl_seconds=300)
        tool_small_cache = SearchContentTool(
            project_root=test_directory, enable_cache=True
        )

        # Perform more searches than cache size
        search_queries = [
            "class",
            "public",
            "private",
            "static",
            "void",
            "import",
            "package",
        ]

        for query in search_queries:
            search_args = {"query": query, "roots": [test_directory], "max_count": 10}
            await tool_small_cache.execute(search_args)

        # Cache should not exceed max size
        stats = tool_small_cache.cache.get_stats()
        assert stats["size"] <= 5

        # Some evictions should have occurred
        assert stats["evictions"] > 0

        print(f"Cache size: {stats['size']}")
        print(f"Evictions: {stats['evictions']}")
        print(f"Hit rate: {stats['hit_rate_percent']}%")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
