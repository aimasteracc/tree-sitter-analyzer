from __future__ import annotations

from collections import OrderedDict
import threading
from typing import Any


class SharedCache:
    """
    Shared cache for MCP tools to reduce redundant operations.
    Implements thread-safe singleton pattern with LRU eviction.
    """

    _instance: "SharedCache | None" = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, max_size: int = 1000) -> "SharedCache":
        """Thread-safe singleton instantiation with configurable max size."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._max_size = max_size
                    instance._initialize()
                    cls._instance = instance
        return cls._instance

    def _initialize(self) -> None:
        """Initialize cache with OrderedDict for LRU tracking."""
        self._language_cache: OrderedDict[str, str] = OrderedDict()
        self._language_meta_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._security_cache: OrderedDict[str, tuple[bool, str]] = OrderedDict()
        self._metrics_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._resolved_paths: OrderedDict[str, str] = OrderedDict()
        self._access_lock = threading.Lock()

    def _make_key(self, kind: str, path: str, project_root: str | None) -> str:
        """
        Build a stable scoped cache key.

        Notes:
        - project_root is included to avoid cross-project cache pollution.
        - kind differentiates different caches sharing the same underlying dict key space.
        """
        pr = project_root or ""
        return f"{pr}::{kind}::{path}"

    def _evict_if_needed(self, cache: OrderedDict) -> None:
        """Evict oldest entries if cache is full."""
        while len(cache) >= self._max_size:
            cache.popitem(last=False)  # Remove oldest (FIFO for LRU)

    def get_language(
        self, file_path: str, project_root: str | None = None
    ) -> str | None:
        """Get language and mark as recently used."""
        with self._access_lock:
            key = self._make_key("language", file_path, project_root)
            if key in self._language_cache:
                self._language_cache.move_to_end(key)
                return self._language_cache[key]
            return None

    def set_language(
        self, file_path: str, language: str, project_root: str | None = None
    ) -> None:
        """Set language with LRU eviction."""
        with self._access_lock:
            key = self._make_key("language", file_path, project_root)
            if key in self._language_cache:
                del self._language_cache[key]
            self._evict_if_needed(self._language_cache)
            self._language_cache[key] = language

    def get_language_meta(
        self, abs_path: str, project_root: str | None = None
    ) -> dict[str, Any] | None:
        """Get language metadata and mark as recently used."""
        with self._access_lock:
            key = self._make_key("language_meta", abs_path, project_root)
            if key in self._language_meta_cache:
                self._language_meta_cache.move_to_end(key)
                return self._language_meta_cache[key]
            return None

    def set_language_meta(
        self, abs_path: str, meta: dict[str, Any], project_root: str | None = None
    ) -> None:
        """Set language metadata with LRU eviction."""
        with self._access_lock:
            key = self._make_key("language_meta", abs_path, project_root)
            if key in self._language_meta_cache:
                del self._language_meta_cache[key]
            self._evict_if_needed(self._language_meta_cache)
            self._language_meta_cache[key] = meta

    def get_security_validation(
        self, file_path: str, project_root: str | None = None
    ) -> tuple[bool, str] | None:
        """Get security validation and mark as recently used."""
        with self._access_lock:
            key = self._make_key("security", file_path, project_root)
            if key in self._security_cache:
                self._security_cache.move_to_end(key)
                return self._security_cache[key]
            return None

    def set_security_validation(
        self, file_path: str, result: tuple[bool, str], project_root: str | None = None
    ) -> None:
        """Set security validation with LRU eviction."""
        with self._access_lock:
            key = self._make_key("security", file_path, project_root)
            if key in self._security_cache:
                del self._security_cache[key]
            self._evict_if_needed(self._security_cache)
            self._security_cache[key] = result

    def get_metrics(
        self, file_path: str, project_root: str | None = None
    ) -> dict[str, Any] | None:
        """Get metrics and mark as recently used."""
        with self._access_lock:
            key = self._make_key("metrics", file_path, project_root)
            if key in self._metrics_cache:
                self._metrics_cache.move_to_end(key)
                return self._metrics_cache[key]
            return None

    def set_metrics(
        self, file_path: str, metrics: dict[str, Any], project_root: str | None = None
    ) -> None:
        """Set metrics with LRU eviction."""
        with self._access_lock:
            key = self._make_key("metrics", file_path, project_root)
            if key in self._metrics_cache:
                del self._metrics_cache[key]
            self._evict_if_needed(self._metrics_cache)
            self._metrics_cache[key] = metrics

    def get_resolved_path(
        self, original_path: str, project_root: str | None = None
    ) -> str | None:
        """Get resolved path and mark as recently used."""
        with self._access_lock:
            key = self._make_key("resolved_path", original_path, project_root)
            if key in self._resolved_paths:
                self._resolved_paths.move_to_end(key)
                return self._resolved_paths[key]
            return None

    def set_resolved_path(
        self, original_path: str, resolved_path: str, project_root: str | None = None
    ) -> None:
        """Set resolved path with LRU eviction."""
        with self._access_lock:
            key = self._make_key("resolved_path", original_path, project_root)
            if key in self._resolved_paths:
                del self._resolved_paths[key]
            self._evict_if_needed(self._resolved_paths)
            self._resolved_paths[key] = resolved_path

    def clear(self) -> None:
        """Clear all caches"""
        with self._access_lock:
            self._language_cache.clear()
            self._language_meta_cache.clear()
            self._security_cache.clear()
            self._metrics_cache.clear()
            self._resolved_paths.clear()


# Global instance access
def get_shared_cache() -> SharedCache:
    return SharedCache()
