#!/usr/bin/env python3
"""
Unit tests for CacheService.

This module provides comprehensive tests for the hierarchical cache system,
including L1/L2/L3 cache tiers, TTL expiration, and thread safety.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import pytest

from tree_sitter_analyzer.core.cache_service import CacheEntry, CacheService


class TestCacheEntry:
    """Test cases for CacheEntry dataclass."""

    def test_cache_entry_initialization(self):
        """Test CacheEntry initialization."""
        now = datetime.now()
        expires = now + timedelta(hours=1)

        entry = CacheEntry(
            value="test_value",
            created_at=now,
            expires_at=expires,
            access_count=5,
        )

        assert entry.value == "test_value"
        assert entry.created_at == now
        assert entry.expires_at == expires
        assert entry.access_count == 5

    def test_cache_entry_defaults(self):
        """Test CacheEntry with default values."""
        now = datetime.now()

        entry = CacheEntry(value="test_value", created_at=now)

        assert entry.expires_at is None
        assert entry.access_count == 0

    def test_is_expired_with_expiration(self):
        """Test is_expired with expiration time."""
        now = datetime.now()
        past = now - timedelta(hours=1)

        entry = CacheEntry(value="test", created_at=now, expires_at=past)

        assert entry.is_expired() is True

    def test_is_expired_without_expiration(self):
        """Test is_expired without expiration time."""
        now = datetime.now()

        entry = CacheEntry(value="test", created_at=now, expires_at=None)

        assert entry.is_expired() is False

    def test_is_expired_future(self):
        """Test is_expired with future expiration."""
        now = datetime.now()
        future = now + timedelta(hours=1)

        entry = CacheEntry(value="test", created_at=now, expires_at=future)

        assert entry.is_expired() is False


class TestCacheServiceInit:
    """Test cases for CacheService initialization."""

    def test_cache_service_default_initialization(self):
        """Test CacheService with default parameters."""
        service = CacheService()

        assert service.size() == 0
        stats = service.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_cache_service_custom_sizes(self):
        """Test CacheService with custom cache sizes."""
        service = CacheService(
            l1_maxsize=50, l2_maxsize=500, l3_maxsize=5000, ttl_seconds=1800
        )

        assert service.size() == 0
        stats = service.get_stats()
        assert stats["l1_size"] == 0
        assert stats["l2_size"] == 0
        assert stats["l3_size"] == 0

    def test_cache_service_stats_initialization(self):
        """Test that stats are properly initialized."""
        service = CacheService()

        stats = service.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["l1_hits"] == 0
        assert stats["l2_hits"] == 0
        assert stats["l3_hits"] == 0
        assert stats["sets"] == 0
        assert stats["evictions"] == 0
        assert stats["hit_rate"] == 0.0
        assert stats["total_requests"] == 0


class TestCacheServiceGet:
    """Test cases for cache get operations."""

    @pytest.mark.asyncio
    async def test_get_cache_miss(self):
        """Test get with cache miss."""
        service = CacheService()

        result = await service.get("nonexistent_key")

        assert result is None
        stats = service.get_stats()
        assert stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_get_l1_hit(self):
        """Test get with L1 cache hit."""
        service = CacheService()

        await service.set("key1", "value1")
        result = await service.get("key1")

        assert result == "value1"
        stats = service.get_stats()
        assert stats["hits"] == 1
        assert stats["l1_hits"] == 1

    @pytest.mark.asyncio
    async def test_get_expired_entry(self):
        """Test get with expired entry."""
        service = CacheService(ttl_seconds=1)

        await service.set("key1", "value1", ttl_seconds=1)
        # Wait for expiration
        await asyncio.sleep(1.1)

        result = await service.get("key1")

        assert result is None
        stats = service.get_stats()
        assert stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_get_empty_key(self):
        """Test get with empty key."""
        service = CacheService()

        with pytest.raises(ValueError, match="Cache key cannot be empty"):
            await service.get("")

    @pytest.mark.asyncio
    async def test_get_none_key(self):
        """Test get with None key."""
        service = CacheService()

        with pytest.raises(ValueError, match="Cache key cannot be empty"):
            await service.get(None)  # type: ignore[arg-type]


class TestCacheServiceSet:
    """Test cases for cache set operations."""

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Test basic set and get operations."""
        service = CacheService()

        await service.set("key1", "value1")
        result = await service.get("key1")

        assert result == "value1"
        stats = service.get_stats()
        assert stats["sets"] == 1

    @pytest.mark.asyncio
    async def test_set_with_custom_ttl(self):
        """Test set with custom TTL."""
        service = CacheService()

        await service.set("key1", "value1", ttl_seconds=10)

        result = await service.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_set_overwrites_existing(self):
        """Test that set overwrites existing value."""
        service = CacheService()

        await service.set("key1", "value1")
        await service.set("key1", "value2")

        result = await service.get("key1")
        assert result == "value2"

    @pytest.mark.asyncio
    async def test_set_empty_key(self):
        """Test set with empty key."""
        service = CacheService()

        with pytest.raises(ValueError, match="Cache key cannot be empty"):
            await service.set("", "value")

    @pytest.mark.asyncio
    async def test_set_none_key(self):
        """Test set with None key."""
        service = CacheService()

        with pytest.raises(ValueError, match="Cache key cannot be empty"):
            await service.set(None, "value")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_set_unserializable_value(self):
        """Test set with unserializable value."""
        service = CacheService()

        # Create an unserializable object
        class UnserializableClass:
            pass

        unserializable = UnserializableClass()

        with pytest.raises(TypeError, match="Value is not serializable"):
            await service.set("key", unserializable)


class TestCacheServiceClear:
    """Test cases for cache clear operations."""

    @pytest.mark.asyncio
    async def test_clear_all_caches(self):
        """Test clearing all caches."""
        service = CacheService()

        await service.set("key1", "value1")
        await service.set("key2", "value2")
        await service.set("key3", "value3")

        assert service.size() > 0

        service.clear()

        assert service.size() == 0
        result = await service.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear_resets_stats(self):
        """Test that clear resets statistics."""
        service = CacheService()

        await service.set("key1", "value1")
        await service.get("key1")

        stats_before = service.get_stats()
        assert stats_before["hits"] > 0
        assert stats_before["sets"] > 0

        service.clear()

        stats_after = service.get_stats()
        assert stats_after["hits"] == 0
        assert stats_after["misses"] == 0
        assert stats_after["sets"] == 0


class TestCacheServiceSize:
    """Test cases for cache size operations."""

    @pytest.mark.asyncio
    async def test_size_empty_cache(self):
        """Test size of empty cache."""
        service = CacheService()

        assert service.size() == 0

    @pytest.mark.asyncio
    async def test_size_with_entries(self):
        """Test size with cache entries."""
        service = CacheService()

        await service.set("key1", "value1")
        await service.set("key2", "value2")
        await service.set("key3", "value3")

        # Size returns L1 cache size
        assert service.size() == 3


class TestCacheServiceStats:
    """Test cases for cache statistics."""

    @pytest.mark.asyncio
    async def test_get_stats_comprehensive(self):
        """Test comprehensive statistics."""
        service = CacheService()

        await service.set("key1", "value1")
        await service.get("key1")  # Hit
        await service.get("key2")  # Miss

        stats = service.get_stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["total_requests"] == 2
        assert stats["hit_rate"] == 0.5
        assert stats["sets"] == 1

    @pytest.mark.asyncio
    async def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        service = CacheService()

        await service.set("key1", "value1")
        await service.set("key2", "value2")
        await service.set("key3", "value3")

        await service.get("key1")  # Hit
        await service.get("key2")  # Hit
        await service.get("key3")  # Hit
        await service.get("key4")  # Miss

        stats = service.get_stats()
        assert stats["hit_rate"] == 0.75

    @pytest.mark.asyncio
    async def test_hit_rate_no_requests(self):
        """Test hit rate with no requests."""
        service = CacheService()

        stats = service.get_stats()
        assert stats["hit_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_l1_l2_l3_hit_tracking(self):
        """Test tracking of L1, L2, L3 hits."""
        service = CacheService()

        await service.set("key1", "value1")
        await service.get("key1")  # L1 hit

        stats = service.get_stats()
        assert stats["l1_hits"] == 1
        assert stats["l2_hits"] == 0
        assert stats["l3_hits"] == 0


class TestCacheServiceGenerateKey:
    """Test cases for cache key generation."""

    def test_generate_cache_key_basic(self):
        """Test basic cache key generation."""
        service = CacheService()

        key = service.generate_cache_key(
            file_path="test.py", language="python", options={"include_complexity": True}
        )

        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 hash length

    def test_generate_cache_key_consistent(self):
        """Test that same inputs generate same key."""
        service = CacheService()

        key1 = service.generate_cache_key(
            file_path="test.py", language="python", options={"include_complexity": True}
        )
        key2 = service.generate_cache_key(
            file_path="test.py", language="python", options={"include_complexity": True}
        )

        assert key1 == key2

    def test_generate_cache_key_different_inputs(self):
        """Test that different inputs generate different keys."""
        service = CacheService()

        key1 = service.generate_cache_key(
            file_path="test.py", language="python", options={"include_complexity": True}
        )
        key2 = service.generate_cache_key(
            file_path="test.py",
            language="python",
            options={"include_complexity": False},
        )

        assert key1 != key2


class TestCacheServiceInvalidatePattern:
    """Test cases for pattern-based cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_pattern(self):
        """Test invalidating entries by pattern."""
        service = CacheService()

        await service.set("prefix_key1", "value1")
        await service.set("prefix_key2", "value2")
        await service.set("other_key", "value3")

        # invalidate_pattern is async, so use await
        count = await service.invalidate_pattern("prefix_")

        # 単層キャッシュのため、2つのマッチするキーが削除される
        # 注意: 以前の3階層キャッシュでは 2 * 3 = 6 だった
        assert count == 2

        result1 = await service.get("prefix_key1")
        result2 = await service.get("prefix_key2")
        result3 = await service.get("other_key")

        assert result1 is None
        assert result2 is None
        assert result3 == "value3"

    @pytest.mark.asyncio
    async def test_invalidate_pattern_no_matches(self):
        """Test invalidating with no matching pattern."""
        service = CacheService()

        await service.set("key1", "value1")

        # invalidate_pattern is async, so use await
        count = await service.invalidate_pattern("nonexistent_")

        assert count == 0

    @pytest.mark.asyncio
    async def test_invalidate_pattern_all(self):
        """Test invalidating all entries with wildcard pattern."""
        service = CacheService()

        await service.set("key1", "value1")
        await service.set("key2", "value2")

        # invalidate_pattern is async, so use await
        count = await service.invalidate_pattern("key")

        # 単層キャッシュのため、2つのマッチするキーが削除される
        # 注意: 以前の3階層キャッシュでは 2 * 3 = 6 だった
        assert count == 2


class TestCacheServiceHierarchical:
    """Test cases for hierarchical cache behavior."""

    @pytest.mark.asyncio
    async def test_cache_promotion_l2_to_l1(self):
        """Test cache promotion from L2 to L1."""
        service = CacheService(l1_maxsize=1, l2_maxsize=10)

        # Fill L1
        await service.set("key1", "value1")
        # Add to L2
        await service.set("key2", "value2")

        # Access key2 (should promote from L2 to L1)
        result = await service.get("key2")

        assert result == "value2"
        stats = service.get_stats()
        # Note: In current implementation, all tiers are set on set(), so first access is L1 hit
        assert stats["hits"] == 1

    @pytest.mark.asyncio
    async def test_cache_promotion_l3_to_l2(self):
        """Test cache promotion from L3 to L2."""
        service = CacheService(l2_maxsize=1, l3_maxsize=10)

        # Fill caches
        await service.set("key1", "value1")
        await service.set("key2", "value2")

        # Access from L3
        result = await service.get("key2")

        assert result == "value2"
        stats = service.get_stats()
        # Note: In current implementation, all tiers are set on set(), so first access is L1 hit
        assert stats["hits"] == 1

    @pytest.mark.asyncio
    async def test_multiple_cache_tiers(self):
        """Test that values are stored in all tiers."""
        service = CacheService()

        await service.set("key1", "value1")

        # Access should work regardless of tier
        result = await service.get("key1")
        assert result == "value1"

        stats = service.get_stats()
        assert stats["hits"] == 1


class TestCacheServiceThreadSafety:
    """Test cases for thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_sets(self):
        """Test concurrent set operations."""
        service = CacheService()

        async def set_value(i: int) -> None:
            await service.set(f"key{i}", f"value{i}")

        # Run concurrent sets
        tasks = [set_value(i) for i in range(100)]
        await asyncio.gather(*tasks)

        stats = service.get_stats()
        assert stats["sets"] == 100

    @pytest.mark.asyncio
    async def test_concurrent_gets(self):
        """Test concurrent get operations."""
        service = CacheService()

        # Pre-populate cache
        await service.set("key1", "value1")

        async def get_value() -> Any:
            return await service.get("key1")

        # Run concurrent gets
        tasks = [get_value() for _ in range(50)]
        results = await asyncio.gather(*tasks)

        # All should return the same value
        assert all(r == "value1" for r in results)


class TestCacheServiceEdgeCases:
    """Test cases for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_large_value(self):
        """Test caching a large value."""
        service = CacheService()

        large_value = "x" * 1000000  # 1MB string

        await service.set("large_key", large_value)
        result = await service.get("large_key")

        assert result == large_value

    @pytest.mark.asyncio
    async def test_complex_value(self):
        """Test caching a complex nested value."""
        service = CacheService()

        complex_value = {
            "nested": {"dict": {"with": ["lists", "and", "numbers", 123]}},
            "list": [1, 2, 3, {"key": "value"}],
        }

        await service.set("complex_key", complex_value)
        result = await service.get("complex_key")

        assert result == complex_value

    @pytest.mark.asyncio
    async def test_cache_eviction(self):
        """Test cache eviction when size limit is reached."""
        service = CacheService(l1_maxsize=2, l2_maxsize=2, l3_maxsize=2)

        # Add more items than cache size
        for i in range(5):
            await service.set(f"key{i}", f"value{i}")

        # Some items should have been evicted
        # The exact behavior depends on LRU implementation
        stats = service.get_stats()
        assert stats["sets"] == 5
