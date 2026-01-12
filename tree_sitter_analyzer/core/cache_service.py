#!/usr/bin/env python3
"""
Unified Cache Service - Common Cache System for CLI and MCP

このモジュールはメモリ効率の良いキャッシュシステムを提供します。
シンプルなLRUキャッシュを使用し、TTL（有効期限）をサポートします。

設計ノート:
以前の3階層キャッシュ（L1/L2/L3）は設計上の問題がありました：
- set()で同じエントリが全階層に保存されていた
- 「昇格」ロジックは意味がなかった（データは最初から全階層に存在）
- メモリが無駄に使用されていた

この実装では、シンプルな単層LRUキャッシュを使用します：
- メモリ効率が良い
- 動作が予測可能
- APIは後方互換性を維持
"""

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from cachetools import LRUCache

from ..utils import log_debug, log_info


@dataclass(frozen=True)
class CacheEntry:
    """
    キャッシュエントリ

    キャッシュされた値とメタデータを保持するデータクラス。

    Attributes:
        value: キャッシュされた値
        created_at: 作成タイムスタンプ
        expires_at: 有効期限
        access_count: アクセス回数
    """

    value: Any
    created_at: datetime
    expires_at: datetime | None = None
    access_count: int = 0

    def is_expired(self) -> bool:
        """
        有効期限チェック

        Returns:
            bool: 期限切れの場合True
        """
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at


class CacheService:
    """
    統合キャッシュサービス

    シンプルなLRUキャッシュを提供し、CLI/MCP間でキャッシュを共有します。
    TTL（有効期限）をサポートし、メモリ効率を最適化しています。

    Attributes:
        _cache: LRUキャッシュ
        _lock: スレッドセーフのためのロック
        _stats: キャッシュ統計
    """

    def __init__(
        self,
        l1_maxsize: int = 100,
        l2_maxsize: int = 1000,
        l3_maxsize: int = 10000,
        ttl_seconds: int = 3600,
    ) -> None:
        """
        初期化

        Args:
            l1_maxsize: 後方互換性のため保持（無視）
            l2_maxsize: 後方互換性のため保持（無視）
            l3_maxsize: キャッシュの最大サイズ
            ttl_seconds: デフォルトTTL（秒）

        注意: 単層キャッシュのため、l3_maxsize が実際のキャッシュサイズになります。
        """
        # 単一のLRUキャッシュを使用
        self._cache: LRUCache[str, CacheEntry] = LRUCache(maxsize=l3_maxsize)

        # スレッドセーフのためのロック
        self._lock = threading.RLock()

        # キャッシュ統計（後方互換性のため階層別統計を維持）
        self._stats = {
            "hits": 0,
            "misses": 0,
            "l1_hits": 0,  # 後方互換性のため保持
            "l2_hits": 0,  # 後方互換性のため保持
            "l3_hits": 0,  # 後方互換性のため保持
            "sets": 0,
            "evictions": 0,
        }

        # デフォルト設定
        self._default_ttl = ttl_seconds
        self._maxsize = l3_maxsize

        log_debug(f"CacheService initialized: maxsize={l3_maxsize}, TTL={ttl_seconds}s")

    async def get(self, key: str) -> Any | None:
        """
        キャッシュから値を取得

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
            entry = self._cache.get(key)
            if entry and not entry.is_expired():
                self._stats["hits"] += 1
                self._stats["l1_hits"] += 1  # 後方互換性
                log_debug(f"Cache hit: {key}")
                return entry.value

            # 期限切れエントリがある場合は削除
            if entry and entry.is_expired():
                del self._cache[key]

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

        # シリアライズ可能性チェック
        import pickle  # nosec B403

        try:
            pickle.dumps(value)
        except Exception as e:
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
            # キャッシュに設定
            self._cache[key] = entry
            self._stats["sets"] += 1
            log_debug(f"Cache set: {key} (TTL={ttl}s)")

    def clear(self) -> None:
        """
        全キャッシュをクリア
        """
        with self._lock:
            self._cache.clear()

            # 統計をリセット
            for stat_key in self._stats:
                self._stats[stat_key] = 0

            # Only log if not in quiet mode
            import logging

            if logging.getLogger("tree_sitter_analyzer").level <= logging.INFO:
                log_info("Cache cleared")

    def size(self) -> int:
        """
        キャッシュサイズを取得

        Returns:
            キャッシュ内のアイテム数
        """
        with self._lock:
            return len(self._cache)

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

            cache_size = len(self._cache)
            return {
                **self._stats,
                "hit_rate": hit_rate,
                "total_requests": total_requests,
                # 後方互換性のため、3つのサイズを報告（全て同じ値）
                "l1_size": cache_size,
                "l2_size": cache_size,
                "l3_size": cache_size,
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
        key_components = [
            file_path,
            language,
            str(sorted(options.items())),
        ]

        key_string = ":".join(key_components)
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
            keys_to_remove = [key for key in self._cache.keys() if pattern in key]

            for key in keys_to_remove:
                if key in self._cache:
                    del self._cache[key]
                    invalidated_count += 1

        log_info(
            f"Invalidated {invalidated_count} cache entries matching pattern: {pattern}"
        )
        return invalidated_count

    def __del__(self) -> None:
        """デストラクタ - リソースクリーンアップ"""
        try:
            import sys

            if sys.meta_path is not None:
                with self._lock:
                    self._cache.clear()
        except Exception:
            pass  # nosec
