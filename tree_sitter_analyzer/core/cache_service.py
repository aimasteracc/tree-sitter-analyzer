#!/usr/bin/env python3
"""
Unified Cache Service - Common Cache System for CLI and MCP

This module provides a memory-efficient hierarchical cache system.
Achieves optimal performance with a 3-tier structure: L1 (fast), L2 (medium-term), L3 (long-term).

Roo Code compliance:
- Type hints: Required for all functions
- MCP logging: Log output at each step
- docstring: Google Style docstring
- Performance-focused: Optimization of memory efficiency and access speed
"""

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from cachetools import LRUCache, TTLCache

from ..utils import log_debug, log_error, log_info


@dataclass(frozen=True)
class CacheEntry:
    """
    Cache Entry

    Data class that holds cached values and metadata.

    Attributes:
        value: Cached value
        created_at: Creation timestamp
        expires_at: Expiration time
        access_count: Access count
    """

    value: Any
    created_at: datetime
    expires_at: datetime | None = None
    access_count: int = 0

    def is_expired(self) -> bool:
        """
        Expiration check

        Returns:
            bool: True if expired
        """
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at


class CacheService:
    """
    Unified Cache Service

    Provides hierarchical cache system and shares cache between CLI and MCP.
    3-tier structure optimized for memory efficiency and access speed.

    Attributes:
        _l1_cache: L1 cache (for fast access)
        _l2_cache: L2 cache (for medium-term storage)
        _l3_cache: L3 cache (for long-term storage)
        _lock: Lock for thread safety
        _stats: Cache statistics
    """

    def __init__(
        self,
        l1_maxsize: int = 100,
        l2_maxsize: int = 1000,
        l3_maxsize: int = 10000,
        ttl_seconds: int = 3600,
    ) -> None:
        """
        Initialization

        Args:
            l1_maxsize: Maximum size of L1 cache
            l2_maxsize: Maximum size of L2 cache
            l3_maxsize: Maximum size of L3 cache
            ttl_seconds: Default TTL (seconds)
        """
        # Initialize hierarchical cache
        self._l1_cache: LRUCache[str, CacheEntry] = LRUCache(maxsize=l1_maxsize)
        self._l2_cache: TTLCache[str, CacheEntry] = TTLCache(
            maxsize=l2_maxsize, ttl=ttl_seconds
        )
        self._l3_cache: LRUCache[str, CacheEntry] = LRUCache(maxsize=l3_maxsize)

        # Lock for thread safety
        self._lock = threading.RLock()

        # Cache statistics
        self._stats = {
            "hits": 0,
            "misses": 0,
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_hits": 0,
            "sets": 0,
            "evictions": 0,
        }

        # デフォルト設定
        self._default_ttl = ttl_seconds

        log_debug(
            f"CacheService initialized: L1={l1_maxsize}, L2={l2_maxsize}, "
            f"L3={l3_maxsize}, TTL={ttl_seconds}s"
        )

    async def get(self, key: str) -> Any | None:
        """
        キャッシュから値を取得

        階層キャッシュを順番にチェックし、見つかった場合は
        上位キャッシュに昇格させる。

        Args:
            key: キャッシュキー

        Returns:
            キャッシュされた値、見つからない場合はNone

        Raises:
            ValueError: 無効なキーの場合
        """
        if not key or key is None:
            raise ValueError("Cache key cannot be empty or None")

        with self._lock:
            # L1キャッシュをチェック
            entry = self._l1_cache.get(key)
            if entry and not entry.is_expired():
                self._stats["hits"] += 1
                self._stats["l1_hits"] += 1
                log_debug(f"Cache L1 hit: {key}")
                return entry.value

            # L2キャッシュをチェック
            entry = self._l2_cache.get(key)
            if entry and not entry.is_expired():
                self._stats["hits"] += 1
                self._stats["l2_hits"] += 1
                # L1に昇格
                self._l1_cache[key] = entry
                log_debug(f"Cache L2 hit: {key} (promoted to L1)")
                return entry.value

            # L3キャッシュをチェック
            entry = self._l3_cache.get(key)
            if entry and not entry.is_expired():
                self._stats["hits"] += 1
                self._stats["l3_hits"] += 1
                # L2とL1に昇格
                self._l2_cache[key] = entry
                self._l1_cache[key] = entry
                log_debug(f"Cache L3 hit: {key} (promoted to L1/L2)")
                return entry.value

            # キャッシュミス
            self._stats["misses"] += 1
            log_debug(f"Cache miss: {key}")
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """
        キャッシュに値を設定

        Args:
            key: キャッシュキー
            value: キャッシュする値
            ttl_seconds: TTL（秒）、Noneの場合はデフォルト値

        Raises:
            ValueError: 無効なキーの場合
            TypeError: シリアライズできない値の場合
        """
        if not key or key is None:
            raise ValueError("Cache key cannot be empty or None")

        # シリアライズ可能性チェック（安全のため標準の pickle を最小限に使用）
        import pickle  # nosec B403

        try:
            pickle.dumps(value)
        except Exception as e:
            # 具体的なエラー型に依存せず、直感的な TypeError に正規化
            raise TypeError(f"Value is not serializable: {e}") from e

        ttl = ttl_seconds or self._default_ttl
        expires_at = datetime.now() + timedelta(seconds=ttl)

        entry = CacheEntry(
            value=value,
            created_at=datetime.now(),
            expires_at=expires_at,
            access_count=0,
        )

        with self._lock:
            # 全階層に設定
            self._l1_cache[key] = entry
            self._l2_cache[key] = entry
            self._l3_cache[key] = entry

            self._stats["sets"] += 1
            log_debug(f"Cache set: {key} (TTL={ttl}s)")

    def clear(self) -> None:
        """
        全キャッシュをクリア
        """
        with self._lock:
            self._l1_cache.clear()
            self._l2_cache.clear()
            self._l3_cache.clear()

            # 統計をリセット
            for key in self._stats:
                self._stats[key] = 0

            log_info("All caches cleared")

    def size(self) -> int:
        """
        キャッシュサイズを取得

        Returns:
            L1キャッシュのサイズ（最も頻繁にアクセスされるアイテム数）
        """
        with self._lock:
            return len(self._l1_cache)

    def get_stats(self) -> dict[str, Any]:
        """
        キャッシュ統計を取得

        Returns:
            統計情報辞書
        """
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests if total_requests > 0 else 0.0
            )

            return {
                **self._stats,
                "hit_rate": hit_rate,
                "total_requests": total_requests,
                "l1_size": len(self._l1_cache),
                "l2_size": len(self._l2_cache),
                "l3_size": len(self._l3_cache),
            }

    def generate_cache_key(
        self, file_path: str, language: str, options: dict[str, Any]
    ) -> str:
        """
        キャッシュキーを生成

        Args:
            file_path: ファイルパス
            language: プログラミング言語
            options: 解析オプション

        Returns:
            ハッシュ化されたキャッシュキー
        """
        # 一意なキーを生成するための文字列を構築
        key_components = [
            file_path,
            language,
            str(sorted(options.items())),  # 辞書を安定した文字列に変換
        ]

        key_string = ":".join(key_components)

        # SHA256でハッシュ化
        return hashlib.sha256(key_string.encode("utf-8")).hexdigest()

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        パターンに一致するキーを無効化

        Args:
            pattern: 無効化するキーのパターン

        Returns:
            無効化されたキー数
        """
        invalidated_count = 0

        with self._lock:
            # 各階層からパターンに一致するキーを削除
            for cache in [self._l1_cache, self._l2_cache, self._l3_cache]:
                keys_to_remove = [key for key in cache.keys() if pattern in key]

                for key in keys_to_remove:
                    if key in cache:
                        del cache[key]
                        invalidated_count += 1

        log_info(
            f"Invalidated {invalidated_count} cache entries matching pattern: {pattern}"
        )
        return invalidated_count

    def __del__(self) -> None:
        """デストラクタ - リソースクリーンアップ"""
        try:
            self.clear()
            log_debug("CacheService destroyed and cleaned up")
        except Exception as e:
            log_error(f"Error during CacheService cleanup: {e}")
