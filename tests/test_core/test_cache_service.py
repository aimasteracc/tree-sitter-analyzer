#!/usr/bin/env python3
"""
Tests for core.cache_service

Roo Code compliance:
- TDD: Test-driven development
- Type hints: Required for all functions
- MCP logging: Log output at each step
- docstring: Google Style docstring
- Coverage: Target 80%+
"""

import asyncio
import time

# Mock functionality now provided by pytest-mock
import pytest

# Import test targets
from tree_sitter_analyzer.core.cache_service import CacheEntry, CacheService


@pytest.fixture
def cache_service():
    """Cache service fixture"""
    service = CacheService()
    yield service
    service.clear()


@pytest.mark.unit
def test_initialization():
    """Initialization test"""
    # Arrange & Act
    cache_service = CacheService()

    # Assert
    assert cache_service is not None
    assert cache_service.size() == 0
    assert cache_service._l1_cache is not None
    assert cache_service._l2_cache is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_set_and_get(cache_service):
    """Cache set and get test"""
    # Arrange
    key = "test_key"
    value = {"test": "data", "number": 42}

    # Act
    await cache_service.set(key, value)
    result = await cache_service.get(key)

    # Assert
    assert result == value


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_miss(cache_service):
    """Cache miss test"""
    # Arrange
    non_existent_key = "non_existent_key"

    # Act
    result = await cache_service.get(non_existent_key)

    # Assert
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_expiration():
    """Cache expiration test"""
    # Arrange
    cache_service = CacheService(ttl_seconds=1)  # Expires in 1 second
    key = "expiring_key"
    value = "expiring_value"

    # Act
    await cache_service.set(key, value)
    immediate_result = await cache_service.get(key)

    # Wait 2 seconds
    await asyncio.sleep(2)
    expired_result = await cache_service.get(key)

    # Assert
    assert immediate_result == value
    assert expired_result is None


@pytest.mark.unit
def test_cache_size_limit():
    """Cache size limit test"""
    # Arrange
    max_size = 3
    cache_service = CacheService(l1_maxsize=max_size)

    # Act
    for i in range(max_size + 2):  # Add beyond limit
        asyncio.run(cache_service.set(f"key_{i}", f"value_{i}"))

    # Assert
    assert cache_service.size() <= max_size


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_clear(cache_service):
    """Cache clear test"""
    # Arrange
    await cache_service.set("key1", "value1")
    await cache_service.set("key2", "value2")

    # Act
    cache_service.clear()

    # Assert
    assert cache_service.size() == 0
    result1 = await cache_service.get("key1")
    result2 = await cache_service.get("key2")
    assert result1 is None
    assert result2 is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hierarchical_cache_l1_hit(cache_service, mocker):
    """Hierarchical cache L1 hit test"""
    # Arrange
    key = "l1_test_key"
    value = "l1_test_value"

    # Act
    await cache_service.set(key, value)

    # Verify retrieval from L1 cache
    mock_l2_get = mocker.patch.object(cache_service._l2_cache, "get")
    result = await cache_service.get(key)

    # Assert
    assert result == value
    mock_l2_get.assert_not_called()  # L2 is not called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hierarchical_cache_l2_hit(cache_service):
    """Hierarchical cache L2 hit test"""
    # Arrange
    key = "l2_test_key"
    value = "l2_test_value"

    # Clear L1 and store only in L2
    await cache_service.set(key, value)
    cache_service._l1_cache.clear()

    # Act
    result = await cache_service.get(key)

    # Assert
    assert result == value
    # Verify promotion to L1
    l1_entry = cache_service._l1_cache.get(key)
    assert l1_entry is not None
    assert l1_entry.value == value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_access(cache_service):
    """Concurrent access test"""
    # Arrange
    num_operations = 100

    async def set_operation(i: int) -> None:
        await cache_service.set(f"key_{i}", f"value_{i}")

    async def get_operation(i: int) -> str | None:
        return await cache_service.get(f"key_{i}")

    # Act
    # Execute set operations concurrently
    await asyncio.gather(*[set_operation(i) for i in range(num_operations)])

    # Execute get operations concurrently
    results = await asyncio.gather(*[get_operation(i) for i in range(num_operations)])

    # Assert
    for i, result in enumerate(results):
        assert result == f"value_{i}"


@pytest.mark.unit
def test_cache_key_generation(cache_service):
    """Cache key generation test"""
    # Arrange
    file_path = "/path/to/test.java"
    language = "java"
    options = {"include_complexity": True}

    # Act
    key1 = cache_service.generate_cache_key(file_path, language, options)
    key2 = cache_service.generate_cache_key(file_path, language, options)
    key3 = cache_service.generate_cache_key(file_path, "python", options)

    # Assert
    assert key1 == key2  # Same input produces same key
    assert key1 != key3  # Different input produces different key
    assert isinstance(key1, str)
    assert len(key1) > 0


@pytest.mark.unit
def test_cache_stats(cache_service):
    """Cache statistics test"""
    # Arrange & Act
    stats = cache_service.get_stats()

    # Assert
    assert "hits" in stats
    assert "misses" in stats
    assert "hit_rate" in stats
    assert "total_requests" in stats
    assert stats["hits"] == 0
    assert stats["misses"] == 0


@pytest.mark.unit
def test_cache_entry_creation():
    """Cache entry creation test"""
    # Arrange
    from datetime import datetime, timedelta

    value = {"test": "data"}
    created_at = datetime.now()
    expires_at = created_at + timedelta(seconds=300)

    # Act
    entry = CacheEntry(value=value, created_at=created_at, expires_at=expires_at)

    # Assert
    assert entry.value == value
    assert entry.created_at == created_at
    assert entry.expires_at == expires_at


@pytest.mark.unit
def test_cache_entry_expiration_check():
    """Cache entry expiration check test"""
    # Arrange
    from datetime import datetime, timedelta

    value = "test_value"
    created_at = datetime.now()
    expires_at = created_at + timedelta(seconds=1)

    entry = CacheEntry(value=value, created_at=created_at, expires_at=expires_at)

    # Act & Assert
    assert not entry.is_expired()  # Valid immediately after creation

    # Wait 2 seconds
    time.sleep(2)
    assert entry.is_expired()  # Expired


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_key_handling():
    """Invalid key handling test"""
    # Arrange
    cache_service = CacheService()

    # Act & Assert
    with pytest.raises(ValueError):
        await cache_service.set("", "value")  # Empty string key

    with pytest.raises(ValueError):
        await cache_service.set(None, "value")  # None key


@pytest.mark.unit
@pytest.mark.asyncio
async def test_serialization_error_handling():
    """Serialization error handling test"""
    # Arrange
    cache_service = CacheService()

    def non_serializable_value(x):
        """Functions are typically not serializable"""
        return x

    # Act & Assert
    with pytest.raises(TypeError):
        await cache_service.set("key", non_serializable_value)
