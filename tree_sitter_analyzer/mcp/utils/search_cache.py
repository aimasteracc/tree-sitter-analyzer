#!/usr/bin/env python3
"""
Search Cache Module for MCP Tools

Provides basic caching functionality for search results to improve performance
by avoiding repeated expensive search operations.

This is a simplified version focusing on core caching features for Phase 2.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SearchCache:
    """Thread-safe in-memory search result cache with TTL and LRU eviction"""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """
        Initialize the search cache.

        Args:
            max_size: Maximum number of cached entries
            ttl_seconds: Time-to-live for cached entries in seconds (default: 1 hour)
        """
        self.cache: dict[str, dict[str, Any]] = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._access_times: dict[str, float] = {}  # Track access times for LRU

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _is_expired(self, timestamp: float) -> bool:
        """Check if a cache entry is expired"""
        return time.time() - timestamp > self.ttl_seconds

    def _cleanup_expired(self):
        """Remove expired entries (should be called with lock held)"""
        current_time = time.time()
        expired_keys = [
            key
            for key, entry in self.cache.items()
            if current_time - entry["timestamp"] > self.ttl_seconds
        ]
        for key in expired_keys:
            del self.cache[key]
            if key in self._access_times:
                del self._access_times[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    def get(self, cache_key: str) -> dict[str, Any] | None:
        """
        Get cached result if valid.

        Args:
            cache_key: The cache key to look up

        Returns:
            Cached data if found and valid, None otherwise
        """
        with self._lock:
            if cache_key in self.cache:
                entry = self.cache[cache_key]
                if not self._is_expired(entry["timestamp"]):
                    # Update access time for LRU
                    self._access_times[cache_key] = time.time()
                    self._hits += 1
                    logger.debug(f"Cache hit for key: {cache_key[:50]}...")
                    return entry["data"]
                else:
                    # Remove expired entry
                    del self.cache[cache_key]
                    if cache_key in self._access_times:
                        del self._access_times[cache_key]

            self._misses += 1
            return None

    def set(self, cache_key: str, data: dict[str, Any]):
        """
        Set cached result.

        Args:
            cache_key: The cache key
            data: The data to cache
        """
        with self._lock:
            self._cleanup_expired()

            # If cache is full and this is a new key, remove LRU entry
            if len(self.cache) >= self.max_size and cache_key not in self.cache:
                # Remove least recently used entry
                if self._access_times:
                    lru_key = min(
                        self._access_times.keys(),
                        key=lambda k: self._access_times.get(k, 0),
                    )
                    del self.cache[lru_key]
                    del self._access_times[lru_key]
                    self._evictions += 1
                    logger.debug(f"Cache full, removed LRU entry: {lru_key[:50]}...")

            current_time = time.time()
            self.cache[cache_key] = {"data": data, "timestamp": current_time}
            self._access_times[cache_key] = current_time
            logger.debug(f"Cached result for key: {cache_key[:50]}...")

    def clear(self):
        """Clear all cached results"""
        with self._lock:
            self.cache.clear()
            self._access_times.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
        logger.info("Search cache cleared")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_percent": round(hit_rate, 2),
                "evictions": self._evictions,
                "expired_entries": len(
                    [
                        key
                        for key, entry in self.cache.items()
                        if self._is_expired(entry["timestamp"])
                    ]
                ),
            }

    def create_cache_key(self, query: str, roots: list[str], **params) -> str:
        """
        Create a deterministic cache key for search parameters.

        Args:
            query: Search query
            roots: List of root directories
            **params: Additional search parameters

        Returns:
            Cache key string
        """
        # Normalize query
        normalized_query = query.strip().lower()

        # Normalize roots - resolve paths and sort for consistency
        normalized_roots = []
        for r in roots:
            try:
                resolved = str(Path(r).resolve())
                normalized_roots.append(resolved)
            except Exception:
                # If path resolution fails, use original
                normalized_roots.append(r)
        normalized_roots.sort()

        # Only include parameters that affect search results
        relevant_params = {
            "case": params.get("case", "smart"),
            "include_globs": (
                sorted(params.get("include_globs", []))
                if params.get("include_globs")
                else []
            ),
            "exclude_globs": (
                sorted(params.get("exclude_globs", []))
                if params.get("exclude_globs")
                else []
            ),
            "no_ignore": params.get("no_ignore", False),
            "hidden": params.get("hidden", False),
            "fixed_strings": params.get("fixed_strings", False),
            "word": params.get("word", False),
            "multiline": params.get("multiline", False),
            "max_filesize": params.get("max_filesize", ""),
        }

        # Create deterministic key
        key_parts = [
            normalized_query,
            str(normalized_roots),
            str(sorted(relevant_params.items())),
        ]
        return "|".join(key_parts)


# Global cache instance for easy access
_default_cache = None


def get_default_cache() -> SearchCache:
    """Get the default search cache instance"""
    global _default_cache
    if _default_cache is None:
        _default_cache = SearchCache()
    return _default_cache


def configure_cache(max_size: int = 1000, ttl_seconds: int = 3600):
    """Configure the default search cache"""
    global _default_cache
    _default_cache = SearchCache(max_size, ttl_seconds)


def clear_cache():
    """Clear the default search cache"""
    cache = get_default_cache()
    cache.clear()
