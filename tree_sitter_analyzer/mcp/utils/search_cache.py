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

    def _cleanup_expired(self) -> None:
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

    def get(self, cache_key: str) -> Any:
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

    def get_compatible_result(self, cache_key: str, requested_format: str) -> Any:
        """
        Get cached result and try to derive compatible formats.

        This enables smart cross-format caching where count results can be used
        to derive file lists without additional searches.

        Args:
            cache_key: The cache key
            requested_format: The format being requested ('file_list', 'summary', etc.)

        Returns:
            Compatible cached data if derivable, None otherwise
        """
        # First try direct cache hit - but only if the format matches
        direct_result = self.get(cache_key)
        if direct_result is not None:
            # Check if the cached result matches the requested format
            if self._is_format_compatible(direct_result, requested_format):
                return direct_result

        # Try to find compatible cached results for derivation
        # Look for count_only results that can derive file lists
        if requested_format in ["file_list", "summary", "files_only"]:
            # Look for a count_only version of the same search
            count_key = self._derive_count_key_from_cache_key(cache_key)
            if count_key and count_key != cache_key:
                count_result = self.get(count_key)
                if count_result and self._can_derive_file_list(count_result):
                    logger.debug(f"Deriving {requested_format} from cached count data")
                    return self._derive_file_list_result(count_result, requested_format)

        return None

    def _is_format_compatible(self, cached_result: Any, requested_format: str) -> bool:
        """
        Check if a cached result is compatible with the requested format.

        This prevents returning wrong format data (e.g., returning integer total
        when detailed results are requested).
        """
        if requested_format == "total_only":
            # total_only expects a simple integer
            return isinstance(cached_result, int)
        elif requested_format == "count_only":
            # count_only expects a dict with file_counts
            return isinstance(cached_result, dict) and (
                "file_counts" in cached_result or "count_only" in cached_result
            )
        elif requested_format in ["summary", "file_list", "files_only"]:
            # These formats expect dict results with specific structures
            return isinstance(cached_result, dict) and cached_result.get(
                "success", False
            )
        elif requested_format in ["normal", "group_by_file"]:
            # Normal format expects dict with matches, files, or results data
            return isinstance(cached_result, dict) and (
                "matches" in cached_result
                or "files" in cached_result
                or "results" in cached_result
            )
        else:
            # For unknown formats or test scenarios, allow dict results but not primitives
            # This maintains backward compatibility while preventing the integer bug
            return isinstance(cached_result, dict)

    def _derive_count_key_from_cache_key(self, cache_key: str) -> str | None:
        """Try to derive what the count_only cache key would be for this search."""
        # Simple heuristic: replace summary_only with count_only_matches
        if "summary_only" in cache_key:
            return cache_key.replace(
                "'summary_only': True", "'count_only_matches': True"
            )
        elif "count_only_matches" not in cache_key:
            # Add count_only_matches parameter
            return cache_key.replace("}", ", 'count_only_matches': True}")
        return None

    def _can_derive_file_list(self, count_result: dict[str, Any]) -> bool:
        """Check if a count result contains file count data that can derive file lists."""
        return (
            isinstance(count_result, dict)
            and "file_counts" in count_result
            and isinstance(count_result["file_counts"], dict)
        )

    def _derive_file_list_result(
        self, count_result: dict[str, Any], requested_format: str
    ) -> dict[str, Any]:
        """Derive file list result from count data."""
        try:
            from ..tools import fd_rg_utils  # Import here to avoid circular imports

            file_counts = count_result.get("file_counts", {})
            if requested_format == "summary":
                derived_result = fd_rg_utils.create_file_summary_from_count_data(
                    file_counts
                )
                derived_result["cache_derived"] = True  # Mark as derived from cache
                return derived_result
            elif requested_format in ["file_list", "files_only"]:
                file_list = fd_rg_utils.extract_file_list_from_count_data(file_counts)
                return {
                    "success": True,
                    "files": file_list,
                    "file_count": len(file_list),
                    "total_matches": file_counts.get("__total__", 0),
                    "cache_derived": True,  # Mark as derived from cache
                }
        except ImportError:
            logger.warning("Could not import fd_rg_utils for cache derivation")

        return count_result

    def set(self, cache_key: str, data: dict[str, Any] | Any) -> None:
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

    def clear(self) -> None:
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

    def create_cache_key(self, query: str, roots: list[str], **params: Any) -> str:
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


def configure_cache(max_size: int = 1000, ttl_seconds: int = 3600) -> None:
    """Configure the default search cache"""
    global _default_cache
    _default_cache = SearchCache(max_size, ttl_seconds)


def clear_cache() -> None:
    """Clear the default search cache"""
    cache = get_default_cache()
    cache.clear()
