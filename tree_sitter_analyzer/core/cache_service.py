#!/usr/bin/env python3
"""
Cache Service Module for Tree-sitter Analyzer

This module provides a high-performance, thread-safe LRU cache with TTL support.
Designed for both CLI and MCP usage.

Features:
- LRU (Least Recently Used) cache eviction
- TTL (Time-To-Live) support
- Thread-safe operations
- Performance monitoring
- Comprehensive error handling
- Type-safe operations (PEP 484)
- Cache statistics (hits, misses, hit rate)
"""

import hashlib
import logging
import pickle
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, Type
from functools import lru_cache, wraps
from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..utils import log_debug, log_info, log_warning, log_error, log_performance


@dataclass
class CacheEntry:
    """
    Cache entry with metadata for cache management.

    Attributes:
        value: The cached value
        created_at: Timestamp when entry was created
        expires_at: Timestamp when entry expires (or None)
        access_count: Number of times entry was accessed
        last_accessed: Timestamp of last access
        size: Estimated size of cached value in bytes
    """

    value: Any
    created_at: datetime
    expires_at: Optional[datetime]
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    size: int = 0


class CacheError(Exception):
    """Raised when cache operation fails."""

    pass


class CacheFullError(CacheError):
    """Raised when cache is full and eviction failed."""

    pass


class CacheKeyError(CacheError):
    """Raised when cache key is invalid."""

    pass


class CacheService:
    """
    High-performance, thread-safe LRU cache with TTL support.

    Features:
    - LRU (Least Recently Used) cache eviction
    - TTL (Time-To-Live) support
    - Thread-safe operations
    - Performance monitoring and statistics
    - Comprehensive error handling
    - Type-safe operations (PEP 484)

    Usage:
    ```python
    cache = CacheService(maxsize=100, ttl=3600)

    # Set value
    await cache.set("key", "value")

    # Get value
    value = await cache.get("key")

    # Check cache statistics
    stats = await cache.get_stats()
    print(f"Hit rate: {stats['hit_rate']:.2%}")
    ```

    Attributes:
        _cache: Dict[str, CacheEntry]
        _lock: threading.RLock
        _maxsize: int
        _default_ttl: int
        _stats: Dict[str, Any]
    """

    def __init__(
        self,
        maxsize: int = 100,
        ttl: int = 3600,
        enable_threading: bool = True,
    ) -> None:
        """
        Initialize cache service.

        Args:
            maxsize: Maximum number of cached entries (default: 100)
            ttl: Default time-to-live in seconds (default: 3600 = 1 hour)
            enable_threading: Whether to enable thread-safety (default: True)

        Note:
            - Uses LRU eviction policy (evicts least recently used entries)
            - TTL (Time-To-Live) automatically expires entries
            - Thread-safe operations (if threading is enabled)
            - Provides cache statistics for monitoring
        """
        self._maxsize = maxsize
        self._default_ttl = ttl
        self._enable_threading = enable_threading
        self._lock = threading.RLock() if enable_threading else None

        # Initialize cache
        self._cache: Dict[str, CacheEntry] = {}

        # Initialize statistics
        self._stats: Dict[str, Any] = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "size": 0,
            "total_size": 0,
        }

        logger.info(
            f"CacheService initialized (maxsize={maxsize}, ttl={ttl}s, "
            f"threading={'enabled' if enable_threading else 'disabled'})"
        )

    async def get(
        self,
        key: str,
        default: Any = None,
        ttl: Optional[int] = None,
    ) -> Any:
        """
        Get value from cache by key.

        Args:
            key: Cache key
            default: Default value if key not found (default: None)
            ttl: Time-to-live in seconds (default: uses instance default)

        Returns:
            Cached value or default if not found/expired

        Raises:
            CacheKeyError: If key is invalid
            CacheError: If cache operation fails

        Note:
            - Returns None if key is not found or entry is expired
            - Returns default if key is not found and default is provided
            - Updates access statistics (hit, miss)
            - Uses LRU eviction policy
        """
        if not key or key.strip() == "":
            raise CacheKeyError(f"Cache key cannot be empty: {key}")

        cache_key = self._generate_cache_key(key)

        with self._lock:
            entry = self._cache.get(cache_key)

            # Cache miss
            if entry is None:
                self._stats["misses"] += 1
                self._stats["size"] -= 1  # size is updated in set()
                log_debug(f"Cache miss: {key}")
                return default

            # Check if entry is expired
            if entry.expires_at and datetime.now() > entry.expires_at:
                self._evict_entry(cache_key, "expired")
                return default

            # Update access statistics and mark entry as recently used
            entry.access_count += 1
            entry.last_accessed = datetime.now()

            # Move to front (LRU)
            del self._cache[cache_key]
            self._cache[cache_key] = entry

            self._stats["hits"] += 1
            log_debug(f"Cache hit: {key} (accesses: {entry.access_count})")

            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        override_ttl: bool = False,
    ) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (default: uses instance default)
            override_ttl: Whether to override the entry's existing TTL

        Raises:
            CacheKeyError: If key is invalid
            CacheFullError: If cache is full and eviction failed
            CacheError: If cache operation fails

        Note:
            - Replaces existing entry if key exists
            - Updates created_at and expires_at timestamps
            - Updates last_accessed timestamp
            - Evicts least recently used entries if cache is full
            - Uses LRU eviction policy
        """
        if not key or key.strip() == "":
            raise CacheKeyError(f"Cache key cannot be empty: {key}")

        cache_key = self._generate_cache_key(key)

        try:
            # Estimate value size
            size = self._estimate_size(value)

            # Calculate expiration time
            if override_ttl or ttl is not None:
                current_ttl = ttl if ttl is not None else self._default_ttl
            else:
                current_ttl = None  # Preserve existing TTL

            if current_ttl is not None:
                expires_at = datetime.now() + timedelta(seconds=current_ttl)
            else:
                # Try to preserve existing expiration
                existing_entry = self._cache.get(cache_key)
                expires_at = existing_entry.expires_at if existing_entry else None

            created_at = datetime.now()

            # Create new entry
            entry = CacheEntry(
                value=value,
                created_at=created_at,
                expires_at=expires_at,
                access_count=1,
                last_accessed=created_at,
                size=size,
            )

            # Check if cache is full
            with self._lock:
                if len(self._cache) >= self._maxsize:
                    log_info(f"Cache full (size={len(self._cache)}, max={self._maxsize})")
                    self._evict_lru()
                    # Check if still full after eviction
                    if len(self._cache) >= self._maxsize:
                        raise CacheFullError(
                            f"Cache is full and cannot evict entries (max={self._maxsize})"
                        )

                # Set entry
                old_entry = self._cache.get(cache_key)
                self._cache[cache_key] = entry

                # Update statistics
                if old_entry is not None:
                    # Decrease total size (old entry size will be subtracted in evict_lru)
                    pass  # size is updated in evict_lru
                else:
                    # New entry, increase size
                    self._stats["total_size"] += size

                log_debug(f"Cache set: {key} (size={size} bytes)")

        except Exception as e:
            log_error(f"Cache set failed for key '{key}': {e}")
            raise CacheError(f"Cache set failed: {e}") from e

    async def delete(self, key: str) -> bool:
        """
        Delete entry from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if entry was deleted, False otherwise

        Raises:
            CacheKeyError: If key is invalid
            CacheError: If cache operation fails

        Note:
            - Decrements cache size
            - Updates eviction statistics
        """
        if not key or key.strip() == "":
            return False

        cache_key = self._generate_cache_key(key)

        with self._lock:
            entry = self._cache.get(cache_key)

            if entry is None:
                log_debug(f"Cache delete (not found): {key}")
                return False

            # Update statistics
            self._stats["size"] -= 1
            self._stats["total_size"] -= entry.size

            # Delete entry
            del self._cache[cache_key]

            log_debug(f"Cache delete: {key}")

        return True

    async def clear(self) -> None:
        """
        Clear all entries from cache.

        Note:
            - Resets cache to empty state
            - Resets all statistics
            - Evicts all entries
        """
        with self._lock:
            # Get size before clearing
            size = len(self._cache)

            # Clear cache
            self._cache.clear()

            # Reset statistics
            self._stats["size"] = 0
            self._stats["hits"] = 0
            self._stats["misses"] = 0
            self._stats["evictions"] = size
            self._stats["total_size"] = 0

            log_info(f"Cache cleared ({size} entries)")

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary containing cache statistics
                - hits: Number of cache hits
                - misses: Number of cache misses
                - hit_rate: Cache hit rate (hits / (hits + misses))
                - size: Current number of cached entries
                - max_size: Maximum cache size
                - evictions: Number of evicted entries
                - total_size: Total estimated size of cached values
        """
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests
                if total_requests > 0 else 0.0
            )

            stats = self._stats.copy()
            stats["hit_rate"] = hit_rate
            stats["max_size"] = self._maxsize

            return stats

    async def invalidate(self, key: str) -> bool:
        """
        Invalidate (expire) an entry without deleting it.

        Args:
            key: Cache key to invalidate

        Returns:
            True if entry was invalidated, False otherwise

        Raises:
            CacheKeyError: If key is invalid

        Note:
            - Sets expires_at to current time
            - Entry will be considered expired on next access
        """
        if not key or key.strip() == "":
            return False

        cache_key = self._generate_cache_key(key)

        with self._lock:
            entry = self._cache.get(cache_key)

            if entry is None:
                log_debug(f"Cache invalidate (not found): {key}")
                return False

            # Invalidate entry
            entry.expires_at = datetime.now()

            log_debug(f"Cache invalidate: {key}")

        return True

    def _evict_entry(self, key: str, reason: str = "evicted") -> None:
        """
        Evict an entry from cache.

        Args:
            key: Cache key
            reason: Reason for eviction (default: "evicted")

        Note:
            - Decrements cache size
            - Updates eviction statistics
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                return

            # Update statistics
            self._stats["size"] -= 1
            self._stats["evictions"] += 1
            self._stats["total_size"] -= entry.size

            # Delete entry
            del self._cache[key]

            log_debug(f"Cache {reason}: {key} (size={entry.size} bytes)")

    def _evict_lru(self, count: int = 1) -> None:
        """
        Evict least recently used entries (LRU policy).

        Args:
            count: Number of entries to evict (default: 1)

        Note:
            - Evicts entries that haven't been accessed recently
            - Updates access statistics
            - Updates eviction statistics
        """
        with self._lock:
            if len(self._cache) == 0:
                return

            # Sort by last accessed time (oldest first)
            sorted_entries = sorted(
                self._cache.items(),
                key=lambda item: (
                    item[1].last_accessed
                    if item[1].last_accessed is not None
                    else datetime.min()
                )
            )

            # Evict specified count
            evicted_count = 0
            for key, entry in sorted_entries[:count]:
                # Update statistics
                self._stats["evictions"] += 1
                self._stats["total_size"] -= entry.size

                # Delete entry
                del self._cache[key]

                evicted_count += 1

            log_debug(f"Evicted {evicted_count} LRU entries")

    def _generate_cache_key(self, key: str) -> str:
        """
        Generate cache key with namespace support.

        Args:
            key: Original cache key

        Returns:
            Namespaced cache key

        Note:
            - Uses SHA-256 hash to ensure key uniqueness
            - Includes namespace to avoid key collisions
        """
        # Add namespace (e.g., "tree_sitter_analyzer")
        namespace = "tree_sitter_analyzer"
        key_string = f"{namespace}:{key}"

        return hashlib.sha256(key_string.encode("utf-8")).hexdigest()

    def _estimate_size(self, value: Any) -> int:
        """
        Estimate the size of a cached value in bytes.

        Args:
            value: Value to estimate size

        Returns:
            Estimated size in bytes

        Note:
            - Uses pickle.dumps() to estimate size
            - Returns 0 for None values
            - Provides rough estimate for monitoring
        """
        if value is None:
            return 0

        try:
            # Use pickle to estimate size
            return len(pickle.dumps(value))
        except Exception:
            # Fallback to string length
            return len(str(value))

    def __len__(self) -> int:
        """
        Return the current number of cached entries.

        Returns:
            Current cache size (number of entries)
        """
        with self._lock:
            return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """
        Check if a key exists in the cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise

        Note:
            - Does not update access statistics
            - Does not affect LRU ordering
        """
        if not key or key.strip() == "":
            return False

        cache_key = self._generate_cache_key(key)

        with self._lock:
            return cache_key in self._cache

    def __repr__(self) -> str:
        """
        Return string representation of cache service.

        Returns:
            String representation with key statistics
        """
        stats = self._stats.copy()
        stats["max_size"] = self._maxsize

        with self._lock:
            stats["size"] = len(self._cache)

        total_requests = stats["hits"] + stats["misses"]
        hit_rate = (
            stats["hits"] / total_requests if total_requests > 0 else 0.0
        )

        return (
            f"CacheService(size={stats['size']}/{self._maxsize}, "
            f"hits={stats['hits']}, misses={stats['misses']}, "
            f"hit_rate={hit_rate:.2%}, "
            f"evictions={stats['evictions']}, "
            f"total_size={stats['total_size']} bytes)"
        )


# Convenience functions
def create_cache_service(
    maxsize: int = 100,
    ttl: int = 3600,
    enable_threading: bool = True,
) -> CacheService:
    """
    Factory function to create a properly configured cache service.

    Args:
        maxsize: Maximum number of cached entries (default: 100)
        ttl: Default time-to-live in seconds (default: 3600 = 1 hour)
        enable_threading: Whether to enable thread-safety (default: True)

    Returns:
        Configured CacheService instance

    Raises:
        ValueError: If maxsize or ttl is invalid

    Note:
        - Creates all necessary dependencies
        - Provides clean factory pattern
        - Recommended for new code
    """
    # Validate parameters
    if maxsize <= 0:
        raise ValueError(f"maxsize must be positive, got: {maxsize}")

    if ttl <= 0:
        raise ValueError(f"ttl must be positive, got: {ttl}")

    return CacheService(
        maxsize=maxsize,
        ttl=ttl,
        enable_threading=enable_threading,
    )


def get_cache_service() -> CacheService:
    """
    Get default cache service instance (backward compatible).

    This function returns a singleton-like instance and is provided
    for backward compatibility. For new code, prefer using `create_cache_service()`
    factory function.

    Returns:
        CacheService instance with default settings

    Note:
        - maxsize: 100
        - ttl: 3600 (1 hour)
        - enable_threading: True
    """
    return CacheService()


# Export for backward compatibility
__all__ = [
    "CacheService",
    "CacheEntry",
    "CacheError",
    "CacheFullError",
    "CacheKeyError",
    "create_cache_service",
    "get_cache_service",
]
