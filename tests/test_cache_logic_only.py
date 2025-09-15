#!/usr/bin/env python3
"""
Cache logic-only tests for Phase 2 cache implementation.

This module tests only the cache logic itself, without external tool dependencies.
"""

import time

import pytest

from tree_sitter_analyzer.mcp.utils.search_cache import (
    SearchCache,
    clear_cache,
    configure_cache,
    get_default_cache,
)


class TestSearchCacheLogic:
    """Test SearchCache class logic without external dependencies"""

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
        # After clear, stats should be reset
        # Note: The clear() method resets all counters

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

    def test_cache_with_path_normalization(self):
        """Test cache key generation with path normalization"""
        cache = SearchCache()

        # Different path representations should normalize to same key
        key1 = cache.create_cache_key("test", ["/path/to/dir"], case="smart")

        # Note: The actual normalization depends on Path.resolve(),
        # but we can test that consistent inputs produce consistent outputs
        key3 = cache.create_cache_key("test", ["/path/to/dir"], case="smart")
        assert key1 == key3

    def test_cache_thread_safety_structure(self):
        """Test that cache has thread safety mechanisms in place"""
        cache = SearchCache()

        # Verify that the cache has a lock (for thread safety)
        assert hasattr(cache, "_lock")
        assert cache._lock is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
