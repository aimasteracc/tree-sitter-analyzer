#!/usr/bin/env python3
"""
統一キャッシュサービス - CLI・MCP共通キャッシュシステム

このモジュールは、メモリ効率的な階層キャッシュシステムを提供します。
L1（高速）、L2（中期）、L3（長期）の3層構造で最適なパフォーマンスを実現。

Roo Code規約準拠:
- 型ヒント: 全関数に型ヒント必須
- MCPログ: 各ステップでログ出力
- docstring: Google Style docstring
- パフォーマンス重視: メモリ効率とアクセス速度の最適化
"""

import asyncio
import hashlib
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union
from cachetools import LRUCache, TTLCache

from ..utils import log_debug, log_info, log_warning, log_error


@dataclass(frozen=True)
class CacheEntry:
    """
    キャッシュエントリ
    
    キャッシュされた値とメタデータを保持するデータクラス。
    
    Attributes:
        value: キャッシュされた値
        created_at: 作成日時
        expires_at: 有効期限
        access_count: アクセス回数
    """
    value: Any
    created_at: datetime
    expires_at: Optional[datetime] = None
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
    統一キャッシュサービス
    
    階層化キャッシュシステムを提供し、CLI・MCP間でキャッシュを共有。
    メモリ効率とアクセス速度を最適化した3層構造。
    
    Attributes:
        _l1_cache: L1キャッシュ（高速アクセス用）
        _l2_cache: L2キャッシュ（中期保存用）
        _l3_cache: L3キャッシュ（長期保存用）
        _lock: スレッドセーフ用ロック
        _stats: キャッシュ統計情報
    """
    
    def __init__(
        self,
        l1_maxsize: int = 100,
        l2_maxsize: int = 1000,
        l3_maxsize: int = 10000,
        ttl_seconds: int = 3600
    ) -> None:
        """
        初期化
        
        Args:
            l1_maxsize: L1キャッシュの最大サイズ
            l2_maxsize: L2キャッシュの最大サイズ
            l3_maxsize: L3キャッシュの最大サイズ
            ttl_seconds: デフォルトTTL（秒）
        """
        # 階層化キャッシュの初期化
        self._l1_cache: LRUCache[str, CacheEntry] = LRUCache(maxsize=l1_maxsize)
        self._l2_cache: TTLCache[str, CacheEntry] = TTLCache(
            maxsize=l2_maxsize, 
            ttl=ttl_seconds
        )
        self._l3_cache: LRUCache[str, CacheEntry] = LRUCache(maxsize=l3_maxsize)
        
        # スレッドセーフ用ロック
        self._lock = threading.RLock()
        
        # キャッシュ統計
        self._stats = {
            "hits": 0,
            "misses": 0,
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_hits": 0,
            "sets": 0,
            "evictions": 0
        }
        
        # デフォルト設定
        self._default_ttl = ttl_seconds
        
        log_info(
            f"CacheService initialized: L1={l1_maxsize}, L2={l2_maxsize}, "
            f"L3={l3_maxsize}, TTL={ttl_seconds}s"
        )
    
    async def get(self, key: str) -> Optional[Any]:
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
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl_seconds: Optional[int] = None
    ) -> None:
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
        try:
            import pickle
            pickle.dumps(value)
        except (pickle.PicklingError, TypeError) as e:
            raise TypeError(f"Value is not serializable: {e}")
        
        ttl = ttl_seconds or self._default_ttl
        expires_at = datetime.now() + timedelta(seconds=ttl)
        
        entry = CacheEntry(
            value=value,
            created_at=datetime.now(),
            expires_at=expires_at,
            access_count=0
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
    
    def get_stats(self) -> Dict[str, Any]:
        """
        キャッシュ統計を取得
        
        Returns:
            統計情報辞書
        """
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests 
                if total_requests > 0 else 0.0
            )
            
            return {
                **self._stats,
                "hit_rate": hit_rate,
                "total_requests": total_requests,
                "l1_size": len(self._l1_cache),
                "l2_size": len(self._l2_cache),
                "l3_size": len(self._l3_cache)
            }
    
    def generate_cache_key(
        self, 
        file_path: str, 
        language: str, 
        options: Dict[str, Any]
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
            str(sorted(options.items()))  # 辞書を安定した文字列に変換
        ]
        
        key_string = ":".join(key_components)
        
        # SHA256でハッシュ化
        return hashlib.sha256(key_string.encode('utf-8')).hexdigest()
    
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
                keys_to_remove = [
                    key for key in cache.keys() 
                    if pattern in key
                ]
                
                for key in keys_to_remove:
                    if key in cache:
                        del cache[key]
                        invalidated_count += 1
        
        log_info(f"Invalidated {invalidated_count} cache entries matching pattern: {pattern}")
        return invalidated_count
    
    def __del__(self) -> None:
        """デストラクタ - リソースクリーンアップ"""
        try:
            self.clear()
            log_debug("CacheService destroyed and cleaned up")
        except Exception as e:
            log_error(f"Error during CacheService cleanup: {e}")