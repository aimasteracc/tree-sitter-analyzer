#!/usr/bin/env python3
"""Comprehensive unit tests for cache_service module."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tree_sitter_analyzer.core.cache_service import (
    CacheConfig,
    CacheEntry,
    CacheFullError,
    CacheKeyError,
    CacheService,
    CacheServiceError,
    CacheStats,
    CacheTimeoutError,
    CacheValueError,
    InitializationError,
    create_cache_service,
    get_cache_service,
)


@pytest.fixture
def cache_service() -> CacheService:
    return CacheService(config=CacheConfig())


class TestCacheConfig:
    def test_config_defaults(self) -> None:
        config = CacheConfig()
        assert config.max_size == 128
        assert config.ttl_seconds == 3600

    def test_config_custom_values(self) -> None:
        config = CacheConfig(max_size=64, ttl_seconds=600)
        assert config.max_size == 64
        assert config.ttl_seconds == 600

    def test_config_getters(self) -> None:
        config = CacheConfig(max_size=64)
        assert config.get_max_size() == 64


class TestCacheEntry:
    def test_entry_creation(self) -> None:
        now = datetime.now()
        entry = CacheEntry(
            value="test", created_at=now, expires_at=now + timedelta(hours=1)
        )
        assert entry.value == "test"
        assert entry.access_count == 0

    def test_entry_not_expired_when_future(self) -> None:
        now = datetime.now()
        entry = CacheEntry(
            value="test", created_at=now, expires_at=now + timedelta(hours=1)
        )
        assert not entry.is_expired

    def test_entry_expired_when_past(self) -> None:
        now = datetime.now()
        entry = CacheEntry(
            value="test", created_at=now, expires_at=now - timedelta(seconds=5)
        )
        assert entry.is_expired

    def test_entry_never_expires_with_none(self) -> None:
        now = datetime.now()
        entry = CacheEntry(value="test", created_at=now, expires_at=None)
        assert not entry.is_expired


class TestCacheStats:
    def test_stats_creation(self) -> None:
        stats = CacheStats(
            total_entries=100,
            total_hits=75,
            total_misses=25,
            total_evictions=5,
            hit_rate=0.75,
            total_size=1000,
            average_size=10.0,
            uptime=100.0,
        )
        assert stats.total_entries == 100
        assert stats.total_hits == 75


class TestCacheServiceExceptions:
    def test_exceptions_exist(self) -> None:
        exceptions = [
            CacheServiceError,
            InitializationError,
            CacheFullError,
            CacheKeyError,
            CacheValueError,
            CacheTimeoutError,
        ]
        for exc_class in exceptions:
            assert issubclass(exc_class, Exception)


class TestCacheServiceInit:
    def test_service_with_config(self) -> None:
        config = CacheConfig(max_size=32)
        service = CacheService(config=config)
        assert service._config.max_size == 32

    def test_service_with_none_uses_defaults(self) -> None:
        service = CacheService(config=None)
        assert service._config.max_size == 128

    def test_service_initializes_stats(self, cache_service: CacheService) -> None:
        assert "total_gets" in cache_service._stats
        assert cache_service._stats["total_gets"] == 0

    def test_service_empty_cache(self, cache_service: CacheService) -> None:
        assert len(cache_service._cache) == 0


class TestCacheGet:
    def test_get_existing_key(self, cache_service: CacheService) -> None:
        cache_service.set("key1", "value1")
        assert cache_service.get("key1") == "value1"

    def test_get_missing_with_default(self, cache_service: CacheService) -> None:
        result = cache_service.get("missing", default="default")
        assert result == "default"

    def test_get_missing_without_default(self, cache_service: CacheService) -> None:
        assert cache_service.get("missing") is None

    def test_get_increments_hit(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        before = cache_service._stats["total_hits"]
        cache_service.get("k1")
        assert cache_service._stats["total_hits"] == before + 1

    def test_get_increments_miss(self, cache_service: CacheService) -> None:
        before = cache_service._stats["total_misses"]
        cache_service.get("missing")
        assert cache_service._stats["total_misses"] == before + 1


class TestCacheSet:
    def test_set_stores_value(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        assert cache_service.get("k1") == "v1"

    def test_set_increments_counter(self, cache_service: CacheService) -> None:
        before = cache_service._stats["total_sets"]
        cache_service.set("k1", "v1")
        assert cache_service._stats["total_sets"] == before + 1

    def test_set_overwrites_key(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        cache_service.set("k1", "v2")
        assert cache_service.get("k1") == "v2"

    def test_set_multiple_keys(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        cache_service.set("k2", "v2")
        assert cache_service.get("k1") == "v1"
        assert cache_service.get("k2") == "v2"


class TestCacheClear:
    def test_clear_removes_entries(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        cache_service.set("k2", "v2")
        cache_service.clear()
        assert cache_service.get("k1") is None

    def test_clear_empties_cache(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        cache_service.clear()
        assert len(cache_service._cache) == 0


class TestCacheEviction:
    def test_evict_removes_entry(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        cache_service._evict_entry("k1", reason="test")
        assert cache_service.get("k1") is None

    def test_evict_increments_counter(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        before = cache_service._stats["total_evictions"]
        cache_service._evict_entry("k1", reason="test")
        assert cache_service._stats["total_evictions"] == before + 1


class TestCacheStatistics:
    def test_get_stats_returns_object(self, cache_service: CacheService) -> None:
        stats = cache_service.get_stats()
        assert isinstance(stats, CacheStats)

    def test_stats_track_entries(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        stats = cache_service.get_stats()
        assert stats.total_entries >= 1

    def test_stats_track_hits_misses(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        cache_service.get("k1")
        cache_service.get("k2")
        stats = cache_service.get_stats()
        assert stats.total_hits >= 1
        assert stats.total_misses >= 1


class TestCacheDelete:
    def test_delete_removes_entry(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        cache_service.delete("k1")
        assert cache_service.get("k1") is None

    def test_delete_returns_bool(self, cache_service: CacheService) -> None:
        cache_service.set("k1", "v1")
        result = cache_service.delete("k1")
        assert isinstance(result, bool)


class TestModuleExports:
    def test_get_cache_service(self) -> None:
        service = get_cache_service()
        assert isinstance(service, CacheService)

    def test_create_cache_service(self) -> None:
        service = create_cache_service(project_root=".")
        assert isinstance(service, CacheService)
