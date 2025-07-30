#!/usr/bin/env python3
"""
Tests for core.cache_service

Roo Code規約準拠:
- TDD: テスト先行実装
- 型ヒント: 全関数に型ヒント必須
- MCPログ: 各ステップでログ出力
- docstring: Google Style docstring
- カバレッジ: 80%以上目標
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
import time
# Mock functionality now provided by pytest-mock
from typing import Dict, Any, Optional

# テスト対象のインポート
from tree_sitter_analyzer.core.cache_service import CacheService, CacheEntry


@pytest.fixture
def cache_service():
    """キャッシュサービスのフィクスチャ"""
    service = CacheService()
    yield service
    service.clear()


@pytest.mark.unit
def test_initialization():
    """初期化テスト"""
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
    """キャッシュ設定・取得テスト"""
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
    """キャッシュミステスト"""
    # Arrange
    non_existent_key = "non_existent_key"
    
    # Act
    result = await cache_service.get(non_existent_key)
    
    # Assert
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_expiration():
    """キャッシュ有効期限テスト"""
    # Arrange
    cache_service = CacheService(ttl_seconds=1)  # 1秒で期限切れ
    key = "expiring_key"
    value = "expiring_value"
    
    # Act
    await cache_service.set(key, value)
    immediate_result = await cache_service.get(key)
    
    # 2秒待機
    await asyncio.sleep(2)
    expired_result = await cache_service.get(key)
    
    # Assert
    assert immediate_result == value
    assert expired_result is None


@pytest.mark.unit
def test_cache_size_limit():
    """キャッシュサイズ制限テスト"""
    # Arrange
    max_size = 3
    cache_service = CacheService(l1_maxsize=max_size)
    
    # Act
    for i in range(max_size + 2):  # 制限を超えて追加
        asyncio.run(cache_service.set(f"key_{i}", f"value_{i}"))
    
    # Assert
    assert cache_service.size() <= max_size


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_clear(cache_service):
    """キャッシュクリアテスト"""
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
    """階層キャッシュL1ヒットテスト"""
    # Arrange
    key = "l1_test_key"
    value = "l1_test_value"
    
    # Act
    await cache_service.set(key, value)
    
    # L1キャッシュから取得されることを確認
    mock_l2_get = mocker.patch.object(cache_service._l2_cache, 'get')
    result = await cache_service.get(key)
    
    # Assert
    assert result == value
    mock_l2_get.assert_not_called()  # L2は呼ばれない


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hierarchical_cache_l2_hit(cache_service):
    """階層キャッシュL2ヒットテスト"""
    # Arrange
    key = "l2_test_key"
    value = "l2_test_value"
    
    # L1をクリアしてL2のみに保存
    await cache_service.set(key, value)
    cache_service._l1_cache.clear()
    
    # Act
    result = await cache_service.get(key)
    
    # Assert
    assert result == value
    # L1に昇格されていることを確認
    l1_entry = cache_service._l1_cache.get(key)
    assert l1_entry is not None
    assert l1_entry.value == value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_access(cache_service):
    """並行アクセステスト"""
    # Arrange
    num_operations = 100
    
    async def set_operation(i: int) -> None:
        await cache_service.set(f"key_{i}", f"value_{i}")
    
    async def get_operation(i: int) -> Optional[str]:
        return await cache_service.get(f"key_{i}")
    
    # Act
    # 並行でset操作を実行
    await asyncio.gather(*[set_operation(i) for i in range(num_operations)])
    
    # 並行でget操作を実行
    results = await asyncio.gather(*[get_operation(i) for i in range(num_operations)])
    
    # Assert
    for i, result in enumerate(results):
        assert result == f"value_{i}"


@pytest.mark.unit
def test_cache_key_generation(cache_service):
    """キャッシュキー生成テスト"""
    # Arrange
    file_path = "/path/to/test.java"
    language = "java"
    options = {"include_complexity": True}
    
    # Act
    key1 = cache_service.generate_cache_key(file_path, language, options)
    key2 = cache_service.generate_cache_key(file_path, language, options)
    key3 = cache_service.generate_cache_key(file_path, "python", options)
    
    # Assert
    assert key1 == key2  # 同じ入力なら同じキー
    assert key1 != key3  # 異なる入力なら異なるキー
    assert isinstance(key1, str)
    assert len(key1) > 0


@pytest.mark.unit
def test_cache_stats(cache_service):
    """キャッシュ統計テスト"""
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
    """キャッシュエントリ作成テスト"""
    # Arrange
    from datetime import datetime, timedelta
    value = {"test": "data"}
    created_at = datetime.now()
    expires_at = created_at + timedelta(seconds=300)
    
    # Act
    entry = CacheEntry(
        value=value,
        created_at=created_at,
        expires_at=expires_at
    )
    
    # Assert
    assert entry.value == value
    assert entry.created_at == created_at
    assert entry.expires_at == expires_at


@pytest.mark.unit
def test_cache_entry_expiration_check():
    """キャッシュエントリ有効期限チェックテスト"""
    # Arrange
    from datetime import datetime, timedelta
    value = "test_value"
    created_at = datetime.now()
    expires_at = created_at + timedelta(seconds=1)
    
    entry = CacheEntry(
        value=value,
        created_at=created_at,
        expires_at=expires_at
    )
    
    # Act & Assert
    assert not entry.is_expired()  # 作成直後は有効
    
    # 2秒待機
    time.sleep(2)
    assert entry.is_expired()  # 期限切れ


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_key_handling():
    """無効なキーの処理テスト"""
    # Arrange
    cache_service = CacheService()
    
    # Act & Assert
    with pytest.raises(ValueError):
        await cache_service.set("", "value")  # 空文字キー
    
    with pytest.raises(ValueError):
        await cache_service.set(None, "value")  # Noneキー


@pytest.mark.unit
@pytest.mark.asyncio
async def test_serialization_error_handling():
    """シリアライゼーションエラーハンドリングテスト"""
    # Arrange
    cache_service = CacheService()
    non_serializable_value = lambda x: x  # 関数は通常シリアライズできない
    
    # Act & Assert
    with pytest.raises(AttributeError):
        await cache_service.set("key", non_serializable_value)