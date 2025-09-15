#!/usr/bin/env python3
"""
Tests for the search cache functionality in Phase 2.

This module tests the basic caching features integrated into the search_content tool.
"""

import time
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.utils.search_cache import (
    SearchCache,
    clear_cache,
    configure_cache,
    get_default_cache,
)


class TestSearchCache:
    """Test cases for the SearchCache class"""

    def test_cache_initialization(self):
        """Test cache initialization with default and custom parameters"""
        # Test default initialization
        cache = SearchCache()
        assert cache.max_size == 1000
        assert cache.ttl_seconds == 3600

        # Test custom initialization
        cache = SearchCache(max_size=500, ttl_seconds=1800)
        assert cache.max_size == 500
        assert cache.ttl_seconds == 1800

    def test_cache_key_creation(self):
        """Test cache key creation for consistent caching"""
        cache = SearchCache()

        # Test basic key creation
        key1 = cache.create_cache_key("test query", ["./src"], case="smart")
        key2 = cache.create_cache_key("test query", ["./src"], case="smart")
        assert key1 == key2

        # Test different parameters create different keys
        key3 = cache.create_cache_key("test query", ["./src"], case="insensitive")
        assert key1 != key3

        # Test different roots create different keys
        key4 = cache.create_cache_key("test query", ["./lib"], case="smart")
        assert key1 != key4

    def test_cache_set_and_get(self):
        """Test basic cache set and get operations"""
        cache = SearchCache()

        test_data = {"results": ["match1", "match2"], "count": 2}
        cache_key = "test_key"

        # Test cache miss
        assert cache.get(cache_key) is None

        # Test cache set and hit
        cache.set(cache_key, test_data)
        retrieved = cache.get(cache_key)
        assert retrieved == test_data

    def test_cache_ttl_expiration(self):
        """Test cache TTL (time-to-live) functionality"""
        cache = SearchCache(ttl_seconds=1)  # 1 second TTL

        test_data = {"results": ["match1"], "count": 1}
        cache_key = "test_key"

        # Set data and verify immediate retrieval
        cache.set(cache_key, test_data)
        assert cache.get(cache_key) == test_data

        # Wait for expiration
        time.sleep(1.1)
        assert cache.get(cache_key) is None

    def test_cache_lru_eviction(self):
        """Test LRU (Least Recently Used) eviction"""
        cache = SearchCache(max_size=2)  # Small cache for testing

        # Fill cache to capacity
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})

        # Access key1 to make it more recently used
        cache.get("key1")

        # Add third item, should evict key2 (least recently used)
        cache.set("key3", {"data": "value3"})

        assert cache.get("key1") is not None  # Should still be there
        assert cache.get("key2") is None  # Should be evicted
        assert cache.get("key3") is not None  # Should be there

    def test_cache_stats(self):
        """Test cache statistics tracking"""
        cache = SearchCache()

        # Initial stats
        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        # Add some data and check stats
        cache.set("key1", {"data": "value1"})
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss

        stats = cache.get_stats()
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == 50.0

    def test_cache_clear(self):
        """Test cache clearing functionality"""
        cache = SearchCache()

        # Add some data
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})

        assert cache.get_stats()["size"] == 2

        # Clear cache
        cache.clear()

        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_global_cache_functions(self):
        """Test global cache management functions"""
        # Test default cache
        default_cache = get_default_cache()
        assert isinstance(default_cache, SearchCache)

        # Test configuration
        configure_cache(max_size=500, ttl_seconds=1800)
        new_cache = get_default_cache()
        assert new_cache.max_size == 500
        assert new_cache.ttl_seconds == 1800

        # Test clear
        new_cache.set("test", {"data": "test"})
        assert new_cache.get_stats()["size"] == 1
        clear_cache()
        assert new_cache.get_stats()["size"] == 0


class TestSearchContentToolWithCache:
    """Test cases for SearchContentTool with caching enabled"""

    @pytest.fixture
    def tool_with_cache(self):
        """Create a SearchContentTool with caching enabled"""
        return SearchContentTool(enable_cache=True)

    @pytest.fixture
    def tool_without_cache(self):
        """Create a SearchContentTool with caching disabled"""
        return SearchContentTool(enable_cache=False)

    def test_tool_initialization_with_cache(self, tool_with_cache):
        """Test tool initialization with cache enabled"""
        assert tool_with_cache.cache is not None
        assert isinstance(tool_with_cache.cache, SearchCache)

    def test_tool_initialization_without_cache(self, tool_without_cache):
        """Test tool initialization with cache disabled"""
        assert tool_without_cache.cache is None

    @pytest.mark.asyncio
    async def test_cache_hit_scenario(self, tool_with_cache):
        """Test cache hit scenario in search_content tool"""
        # Mock the ripgrep execution to avoid actual file system operations
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Create proper ripgrep JSON output format
            mock_output = b'{"type":"match","data":{"path":{"text":"test.txt"},"lines":{"text":"test content"},"line_number":1}}\n'
            mock_run.return_value = (0, mock_output, b"")

            # Mock path validation
            with patch.object(tool_with_cache, "_validate_roots", return_value=["."]):
                # First call - cache miss
                arguments = {"query": "test", "roots": ["."]}

                result1 = await tool_with_cache.execute(arguments)
                assert "cache_hit" not in result1 or not result1.get("cache_hit", False)

                # Second call - should be cache hit
                result2 = await tool_with_cache.execute(arguments)
                assert result2.get("cache_hit", False) is True

                # Verify ripgrep was only called once
                assert mock_run.call_count == 1

    def test_cache_key_consistency(self, tool_with_cache):
        """Test that cache keys are generated consistently"""
        arguments1 = {"query": "test", "roots": ["./src"], "case": "smart"}

        arguments2 = {"query": "test", "roots": ["./src"], "case": "smart"}

        key1 = tool_with_cache.cache.create_cache_key(**arguments1)
        key2 = tool_with_cache.cache.create_cache_key(**arguments2)

        assert key1 == key2


class TestCachePerformance:
    """Performance-related tests for the cache system"""

    def test_cache_performance_improvement(self):
        """Test that cache provides performance improvement"""
        cache = SearchCache()

        # Simulate expensive operation
        def expensive_operation():
            time.sleep(0.1)  # 100ms delay
            return {"results": ["result1", "result2"], "count": 2}

        cache_key = "performance_test"

        # First call - cache miss (expensive)
        start_time = time.time()
        result = expensive_operation()
        cache.set(cache_key, result)
        first_call_time = time.time() - start_time

        # Second call - cache hit (fast)
        start_time = time.time()
        cached_result = cache.get(cache_key)
        second_call_time = time.time() - start_time

        # Verify cache hit is significantly faster
        assert cached_result == result
        assert second_call_time < first_call_time * 0.1  # At least 10x faster

    def test_cache_memory_efficiency(self):
        """Test cache memory management"""
        cache = SearchCache(max_size=100)

        # Add many entries
        for i in range(150):  # More than max_size
            cache.set(f"key_{i}", {"data": f"value_{i}"})

        # Should not exceed max_size
        assert cache.get_stats()["size"] <= 100

        # Most recent entries should still be available
        assert cache.get("key_149") is not None
        assert cache.get("key_148") is not None


if __name__ == "__main__":
    pytest.main([__file__])
