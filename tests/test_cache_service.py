#!/usr/bin/env python3
"""
Test Suite for Cache Service

Comprehensive tests for CacheService including:
- Unit tests
- Performance benchmarks
- Concurrency tests
- Edge case tests
"""

import asyncio
import time
import unittest
from unittest.mock import patch, MagicMock
from typing import Any
from datetime import datetime, timedelta

from tree_sitter_analyzer.core.cache_service import (
    CacheService,
    CacheEntry,
    CacheError,
    CacheKeyError,
    CacheFullError,
    create_cache_service,
    get_cache_service,
)


class TestCacheEntry(unittest.TestCase):
    """Unit tests for CacheEntry dataclass."""

    def test_cache_entry_creation(self):
        """Test cache entry creation with metadata."""
        entry = CacheEntry(
            value="test_value",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
            access_count=0,
        )

        self.assertEqual(entry.value, "test_value")
        self.assertEqual(entry.access_count, 0)
        self.assertIsNotNone(entry.created_at)
        self.assertIsNotNone(entry.expires_at)

    def test_cache_entry_expiration(self):
        """Test cache entry expiration check."""
        # Not expired entry
        entry = CacheEntry(
            value="test_value",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
            access_count=0,
        )
        self.assertFalse(entry.is_expired())

        # Expired entry
        expired_entry = CacheEntry(
            value="test_value",
            created_at=datetime.now() - timedelta(hours=2),
            expires_at=datetime.now() - timedelta(hours=1),
            access_count=0,
        )
        self.assertTrue(expired_entry.is_expired())

        # Entry without expiration
        no_expiration_entry = CacheEntry(
            value="test_value",
            created_at=datetime.now(),
            expires_at=None,
            access_count=0,
        )
        self.assertFalse(no_expiration_entry.is_expired())


class TestCacheServiceInit(unittest.TestCase):
    """Unit tests for CacheService initialization."""

    def test_cache_service_init_default(self):
        """Test cache service initialization with default parameters."""
        cache = CacheService()

        self.assertIsNotNone(cache)
        self.assertEqual(cache._maxsize, 100)
        self.assertEqual(cache._default_ttl, 3600)
        self.assertTrue(cache._cache_enabled)

    def test_cache_service_init_custom(self):
        """Test cache service initialization with custom parameters."""
        cache = CacheService(
            maxsize=200,
            ttl=7200,
            enable_threading=False,
        )

        self.assertEqual(cache._maxsize, 200)
        self.assertEqual(cache._default_ttl, 7200)
        self.assertFalse(cache._cache_enabled)


class TestCacheServiceBasicOps(unittest.IsolatedAsyncioTestCase):
    """Unit tests for basic cache operations."""

    async def asyncSetUp(self):
        """Set up test environment."""
        self.cache = create_cache_service(maxsize=10, ttl=60)
        await self.cache.clear()

    async def test_cache_set_and_get(self):
        """Test basic set and get operations."""
        await self.cache.set("key1", "value1")
        result = await self.cache.get("key1")

        self.assertEqual(result, "value1")
        self.assertEqual(len(await self.cache), 1)

    async def test_cache_get_miss(self):
        """Test cache miss scenario."""
        result = await self.cache.get("nonexistent_key")

        self.assertIsNone(result)
        self.assertEqual(len(await self.cache), 0)

    async def test_cache_update(self):
        """Test cache update operation."""
        await self.cache.set("key1", "value1")
        await self.cache.set("key1", "value2")

        result = await self.cache.get("key1")
        self.assertEqual(result, "value2")
        self.assertEqual(len(await self.cache), 1)

    async def test_cache_delete(self):
        """Test cache delete operation."""
        await self.cache.set("key1", "value1")
        deleted = await self.cache.delete("key1")

        self.assertTrue(deleted)
        self.assertIsNone(await self.cache.get("key1"))
        self.assertEqual(len(await self.cache), 0)

    async def test_cache_delete_nonexistent(self):
        """Test deleting nonexistent key."""
        deleted = await self.cache.delete("nonexistent_key")

        self.assertFalse(deleted)
        self.assertEqual(len(await self.cache), 0)

    async def test_cache_clear(self):
        """Test cache clear operation."""
        await self.cache.set("key1", "value1")
        await self.cache.set("key2", "value2")

        cleared = await self.cache.clear()

        self.assertTrue(cleared)
        self.assertEqual(len(await self.cache), 0)

    async def test_cache_size(self):
        """Test cache size method."""
        self.assertEqual(len(await self.cache), 0)

        await self.cache.set("key1", "value1")
        await self.cache.set("key2", "value2")

        self.assertEqual(len(await self.cache), 2)


class TestCacheServiceTTL(unittest.IsolatedAsyncioTestCase):
    """Unit tests for TTL (Time-To-Live) functionality."""

    async def asyncSetUp(self):
        """Set up test environment."""
        self.cache = create_cache_service(maxsize=10, ttl=1)  # 1 second TTL

    async def test_cache_ttl_expiration(self):
        """Test cache entry expiration after TTL."""
        # Set a value with 1 second TTL
        await self.cache.set("key1", "value1")

        # Should be available immediately
        result = await self.cache.get("key1")
        self.assertEqual(result, "value1")

        # Wait for TTL to expire
        await asyncio.sleep(1.1)  # Wait 1.1 seconds (plus small margin)

        # Should be expired now
        result = await self.cache.get("key1")
        self.assertIsNone(result)

    async def test_cache_ttl_override(self):
        """Test TTL override on set operation."""
        # Set entry with 5 second TTL
        await self.cache.set("key1", "value1", ttl=5)

        # Wait 2 seconds (should still be valid)
        await asyncio.sleep(2.1)

        result = await self.cache.get("key1")
        self.assertEqual(result, "value1")

        # Wait another 3 seconds (should be expired)
        await asyncio.sleep(3.1)

        result = await self.cache.get("key1")
        self.assertIsNone(result)


class TestCacheServiceLRU(unittest.IsolatedAsyncioTestCase):
    """Unit tests for LRU (Least Recently Used) eviction policy."""

    async def asyncSetUp(self):
        """Set up test environment."""
        self.cache = create_cache_service(maxsize=3, ttl=3600)  # 3 entries max

    async def test_cache_lru_eviction(self):
        """Test LRU eviction policy."""
        # Fill cache to capacity (3 entries)
        await self.cache.set("key1", "value1")
        await self.cache.set("key2", "value2")
        await self.cache.set("key3", "value3")

        self.assertEqual(len(await self.cache), 3)

        # Access key1 (most recently used)
        await self.cache.get("key1")

        # Access key2 (second most recently used)
        await self.cache.get("key2")

        # Add new entry (should evict key3 - least recently used)
        await self.cache.set("key4", "value4")

        self.assertEqual(len(await self.cache), 3)

        # key3 should be evicted
        result = await self.cache.get("key3")
        self.assertIsNone(result)

        # key1, key2, key4 should exist
        self.assertEqual(await self.cache.get("key1"), "value1")
        self.assertEqual(await self.cache.get("key2"), "value2")
        self.assertEqual(await self.cache.get("key4"), "value4")

    async def test_cache_lru_ordering(self):
        """Test LRU access ordering."""
        # Fill cache in order: key1, key2, key3
        await self.cache.set("key1", "value1")
        await self.cache.set("key2", "value2")
        await self.cache.set("key3", "value3")

        # Access key3 (make it most recently used)
        await self.cache.get("key3")

        # Access key2 (make it second most recently used)
        await self.cache.get("key2")

        # Add new entry (key4)
        await self.cache.set("key4", "value4")

        # key1 should be evicted (least recently used)
        result = await self.cache.get("key1")
        self.assertIsNone(result)

        # key3, key2, key4 should exist
        self.assertEqual(await self.cache.get("key2"), "value2")
        self.assertEqual(await self.cache.get("key3"), "value3")
        self.assertEqual(await self.cache.get("key4"), "value4")


class TestCacheServiceConcurrency(unittest.IsolatedAsyncioTestCase):
    """Unit tests for concurrent cache operations."""

    async def asyncSetUp(self):
        """Set up test environment."""
        self.cache = create_cache_service(maxsize=100, ttl=3600)
        await self.cache.clear()

    async def test_cache_concurrent_sets(self):
        """Test concurrent set operations."""
        # Create many tasks to set values concurrently
        tasks = [
            self.cache.set(f"key{i}", f"value{i}")
            for i in range(50)
        ]

        # Execute all tasks concurrently
        await asyncio.gather(*tasks)

        # Verify all entries were set
        for i in range(50):
            result = await self.cache.get(f"key{i}")
            self.assertEqual(result, f"value{i}")

        self.assertEqual(len(await self.cache), 50)

    async def test_cache_concurrent_gets(self):
        """Test concurrent get operations."""
        # Set up cache
        for i in range(50):
            await self.cache.set(f"key{i}", f"value{i}")

        # Create many tasks to get values concurrently
        tasks = [self.cache.get(f"key{i}") for i in range(50)]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)

        # Verify all results
        for i, result in enumerate(results):
            self.assertEqual(result, f"value{i}")

    async def test_cache_concurrent_updates(self):
        """Test concurrent update operations."""
        # Set initial value
        await self.cache.set("key1", "value1")

        # Create many tasks to update the same key
        tasks = [
            self.cache.set("key1", f"value{i}")
            for i in range(10)
        ]

        # Execute all tasks concurrently
        await asyncio.gather(*tasks)

        # Final value should be from the last task (race condition acceptable)
        result = await self.cache.get("key1")
        self.assertIn(result, [f"value{i}" for i in range(10)])


class TestCacheServicePerformance(unittest.IsolatedAsyncioTestCase):
    """Performance benchmarks for cache operations."""

    async def asyncSetUp(self):
        """Set up test environment."""
        self.cache = create_cache_service(maxsize=1000, ttl=3600)
        await self.cache.clear()

    async def test_cache_performance_set(self):
        """Benchmark cache set operations."""
        # Warm up cache
        for i in range(100):
            await self.cache.set(f"warmup{i}", f"warmup_value{i}")

        # Benchmark set operations
        start = time.perf_counter()
        for i in range(1000):
            await self.cache.set(f"key{i}", f"value{i}")
        end = time.perf_counter()

        elapsed = end - start
        ops_per_sec = 1000 / elapsed

        print(f"Cache set: {1000} ops in {elapsed:.3f}s ({ops_per_sec:.0f} ops/sec)")
        self.assertLess(elapsed, 10.0)  # Should complete within 10 seconds

    async def test_cache_performance_get(self):
        """Benchmark cache get operations."""
        # Fill cache
        for i in range(100):
            await self.cache.set(f"key{i}", f"value{i}")

        # Benchmark get operations
        start = time.perf_counter()
        for i in range(10000):
            await self.cache.get(f"key{i % 100}")
        end = time.perf_counter()

        elapsed = end - start
        ops_per_sec = 10000 / elapsed

        print(f"Cache get: {10000} ops in {elapsed:.3f}s ({ops_per_sec:.0f} ops/sec)")
        self.assertLess(elapsed, 5.0)  # Should complete within 5 seconds

    async def test_cache_performance_hit_rate(self):
        """Test cache hit rate."""
        # Set a value
        await self.cache.set("key1", "value1")

        # Benchmark get operations (should hit 100%)
        hits = 0
        misses = 0
        start = time.perf_counter()

        for i in range(10000):
            result = await self.cache.get("key1")
            if result is not None:
                hits += 1
            else:
                misses += 1

        end = time.perf_counter()
        elapsed = end - start

        hit_rate = hits / (hits + misses)

        print(f"Cache hit rate: {hit_rate:.2%} ({hits}/{misses}) in {elapsed:.3f}s")
        self.assertGreater(hit_rate, 0.95)  # Should have high hit rate

    async def test_cache_performance_miss_rate(self):
        """Test cache miss rate."""
        # Benchmark get operations (should miss 100%)
        misses = 0
        start = time.perf_counter()

        for i in range(1000):
            result = await self.cache.get(f"miss_key{i}")

            if result is None:
                misses += 1

        end = time.perf_counter()
        elapsed = end - start

        miss_rate = misses / 1000

        print(f"Cache miss rate: {miss_rate:.2%} ({misses}/1000) in {elapsed:.3f}s")
        self.assertGreaterEqual(miss_rate, 0.99)  # Should have near 100% miss rate


class TestCacheServiceEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Edge case tests for cache operations."""

    async def asyncSetUp(self):
        """Set up test environment."""
        self.cache = create_cache_service(maxsize=10, ttl=60)

    async def test_cache_key_validation(self):
        """Test cache key validation."""
        with self.assertRaises(CacheKeyError):
            await self.cache.get("")

        with self.assertRaises(CacheKeyError):
            await self.cache.set("", "value")

    async def test_cache_value_serialization(self):
        """Test cache value serialization."""
        # Test different value types
        await self.cache.set("string_value", "test")
        await self.cache.set("int_value", 42)
        await self.cache.set("list_value", [1, 2, 3])
        await self.cache.set("dict_value", {"key": "value"})

        self.assertEqual(await self.cache.get("string_value"), "test")
        self.assertEqual(await self.cache.get("int_value"), 42)
        self.assertEqual(await self.cache.get("list_value"), [1, 2, 3])
        self.assertEqual(await self.cache.get("dict_value"), {"key": "value"})

    async def test_cache_large_values(self):
        """Test caching of large values."""
        large_string = "x" * 100000  # 100KB string
        large_list = list(range(10000))  # Large list

        await self.cache.set("large_string", large_string)
        await self.cache.set("large_list", large_list)

        result_string = await self.cache.get("large_string")
        result_list = await self.cache.get("large_list")

        self.assertEqual(result_string, large_string)
        self.assertEqual(result_list, large_list)

    async def test_cache_full_cache_eviction(self):
        """Test behavior when cache is full."""
        # Set cache max size to 5
        cache = create_cache_service(maxsize=5, ttl=3600)
        await cache.clear()

        # Fill cache to capacity
        for i in range(5):
            await cache.set(f"key{i}", f"value{i}")

        # Try to add another entry (should fail or evict)
        try:
            await cache.set("key6", "value6")
        # Should either succeed (with eviction) or fail
        # For LRU cache, it should evict the least recently used entry
            pass
        except CacheFullError:
            self.fail("Cache should evict entry instead of failing")

        # Verify cache size is still 5
        self.assertEqual(len(await cache), 5)

        # Verify LRU eviction
        # Access key2, key3, key4, key5 (make them more recently used than key1)
        for i in range(2, 6):
            await cache.get(f"key{i}")

        # Add new entry (key6 should evict key1)
        await cache.set("key6", "value6")

        # key1 should be evicted
        result = await cache.get("key1")
        self.assertIsNone(result)

        # Other keys should exist
        for i in range(2, 7):
            result = await cache.get(f"key{i}")
            if i != 1:
                self.assertEqual(result, f"value{i}")


class TestCacheServiceStats(unittest.IsolatedAsyncioTestCase):
    """Unit tests for cache statistics."""

    async def asyncSetUp(self):
        """Set up test environment."""
        self.cache = create_cache_service(maxsize=10, ttl=60)
        await self.cache.clear()

    async def test_cache_stats_initial(self):
        """Test initial cache statistics."""
        stats = await self.cache.get_stats()

        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["misses"], 0)
        self.assertEqual(stats["size"], 0)
        self.assertEqual(stats["max_size"], 10)
        self.assertEqual(stats["hit_rate"], 0.0)
        self.assertEqual(stats["total_size"], 0)

    async def test_cache_stats_after_operations(self):
        """Test cache statistics after operations."""
        # Perform some operations
        await self.cache.set("key1", "value1")
        await self.cache.set("key2", "value2")
        await self.cache.get("key1")  # Hit
        await self.cache.get("key3")  # Miss

        stats = await self.cache.get_stats()

        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["size"], 2)
        self.assertGreater(stats["hit_rate"], 0.0)
        self.assertGreater(stats["total_size"], 0)

    async def test_cache_stats_after_clear(self):
        """Test cache statistics after clear."""
        # Fill cache
        await self.cache.set("key1", "value1")
        await self.cache.set("key2", "value2")
        await self.cache.set("key3", "value3")

        stats = await self.cache.get_stats()
        self.assertEqual(stats["size"], 3)

        # Clear cache
        await self.cache.clear()

        stats = await self.cache.get_stats()
        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["misses"], 0)
        self.assertEqual(stats["size"], 0)
        self.assertEqual(stats["total_size"], 0)


class TestCacheService(unittest.IsolatedAsyncioTestCase):
    """Integration tests for cache service."""

    async def asyncSetUp(self):
        """Set up test environment."""
        self.cache = create_cache_service(maxsize=100, ttl=60)
        await self.cache.clear()

    async def test_cache_service_get_and_set(self):
        """Test get and set operations."""
        await self.cache.set("key1", "value1")

        result = await self.cache.get("key1")
        self.assertEqual(result, "value1")

        stats = await self.cache.get_stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["size"], 1)

    async def test_cache_service_eviction(self):
        """Test cache eviction."""
        cache = create_cache_service(maxsize=3, ttl=60)
        await cache.clear()

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        self.assertEqual(len(await cache), 3)

        # Access key1 (most recently used)
        await cache.get("key1")

        # Access key2 (second most recently used)
        await cache.get("key2")

        # Add new entry (should evict key3)
        await cache.set("key4", "value4")

        self.assertEqual(len(await cache), 3)

        result = await cache.get("key3")
        self.assertIsNone(result)


def run_performance_benchmarks():
    """Run performance benchmarks for cache service."""
    print("\n" + "="*60)
    print("Cache Service Performance Benchmarks")
    print("="*60)

    async def run_benchmarks():
        """Run all performance benchmarks."""
        suite = unittest.TestLoader().loadTestsFromName(__name__, TestCacheServicePerformance)
        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)

    asyncio.run(run_benchmarks())


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2, exit=False)

    # Optionally run performance benchmarks
    import sys

    if "--benchmark" in sys.argv:
        print("\n" + "="*60)
        print("Running performance benchmarks...")
        print("="*60)
        asyncio.run(run_performance_benchmarks())
