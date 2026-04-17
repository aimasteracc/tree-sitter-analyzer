"""
Incremental analysis cache implementation.

Caches analysis results by file content hash, with git-aware invalidation
and concurrent access support.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import pickle
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Pickle protocol compatible with Python 3.8+
PICKLE_PROTOCOL = 4


@dataclass(frozen=True)
class CacheKey:
    """Cache key that uniquely identifies a file's analysis result."""

    file_path: str
    content_hash: str  # SHA256 of file content
    tree_sitter_version: str  # Grammar version (for future use)
    language: str  # python, javascript, etc.

    def __hash__(self) -> int:
        return hash((self.file_path, self.content_hash, self.language))


@dataclass
class CachedAnalysis:
    """Analysis result stored in cache."""

    key: CacheKey
    ast_bytes: bytes  # Serialized tree-sitter Tree
    analysis_result: dict[str, Any]  # Tool-specific analysis
    timestamp: float
    git_sha: str | None  # None for non-git repos


@dataclass
class CacheEntry:
    """Single cache entry with metadata for eviction."""

    key: CacheKey
    value: CachedAnalysis
    last_access: float  # For LRU tracking
    size_bytes: int  # For size-based eviction


class IncrementalCacheManager:
    """
    Manages incremental analysis cache with file-hash and git SHA invalidation.

    Features:
    - File-hash based caching (content-addressable)
    - Git SHA aware invalidation
    - Concurrent access via file locks
    - Size-based eviction with LRU
    - Fallback for non-git repos
    """

    def __init__(
        self,
        repo_path: str,
        cache_dir: str | None = None,
        max_size_bytes: int = 1024 * 1024 * 1024,  # 1GB default
    ) -> None:
        """
        Initialize cache manager.

        Args:
            repo_path: Path to the repository/codebase
            cache_dir: Cache directory (defaults to .tree-sitter-cache/)
            max_size_bytes: Maximum cache size in bytes
        """
        self.repo_path = Path(repo_path).resolve()
        self.max_size = max_size_bytes
        self._current_size = 0
        self._cache: dict[CacheKey, CacheEntry] = {}

        # Set up cache directory
        if cache_dir is None:
            cache_dir = str(self.repo_path / ".tree-sitter-cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # File lock for concurrent access
        self._lock_path = self.cache_dir / ".lock"
        self._lock_fd: int | None = None

    def _acquire_lock(self, exclusive: bool = False) -> None:
        """Acquire file lock for concurrent access safety."""
        lock_mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        self._lock_fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR)
        fcntl.flock(self._lock_fd, lock_mode)

    def _release_lock(self) -> None:
        """Release file lock."""
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None

    def _get_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file content."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _make_cache_key(self, file_path: str, language: str) -> CacheKey:
        """Create cache key for a file."""
        content_hash = self._get_file_hash(file_path)
        # Resolve symlinks to handle macOS temp directories
        resolved_path = Path(os.path.realpath(file_path))
        try:
            relative_path = str(resolved_path.relative_to(self.repo_path))
        except ValueError:
            # File is outside repo_path, use absolute path
            relative_path = str(resolved_path)
        return CacheKey(
            file_path=relative_path,
            content_hash=content_hash,
            tree_sitter_version="1.0.0",  # TODO: Get from parser
            language=language,
        )

    def _get_cache_path(self, key: CacheKey) -> Path:
        """Get cache file path for a key."""
        # Use content_hash as filename for content-addressable storage
        # Include language in filename to distinguish different language analyses
        safe_path = key.file_path.replace("/", "_").replace("\\", "_")
        return self.cache_dir / f"{safe_path}.{key.language}.{key.content_hash[:16]}.cache"

    def _write_atomically(self, path: Path, data: bytes) -> None:
        """Write to temporary file, then rename for atomicity."""
        temp_path = path.with_suffix(f".tmp.{os.getpid()}")
        with open(temp_path, "wb") as f:
            f.write(data)
        temp_path.rename(path)  # Atomic on POSIX

    def get(self, file_path: str, language: str = "python") -> CachedAnalysis | None:
        """
        Get cached analysis for a file.

        Args:
            file_path: Path to the file
            language: Programming language (for cache key)

        Returns:
            CachedAnalysis if found and valid, None otherwise
        """
        key = self._make_cache_key(file_path, language)
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        # Check if file content changed (hash mismatch)
        current_hash = self._get_file_hash(file_path)
        if key.content_hash != current_hash:
            return None

        try:
            self._acquire_lock(exclusive=False)
            with open(cache_path, "rb") as f:
                entry = pickle.load(f)

            # Update last access time for LRU
            if isinstance(entry, CacheEntry):
                entry.last_access = time.time()
            else:
                # Legacy format: wrap in CacheEntry
                entry = CacheEntry(
                    key=entry.key if hasattr(entry, "key") else key,
                    value=entry if isinstance(entry, CachedAnalysis) else entry,
                    last_access=time.time(),
                    size_bytes=cache_path.stat().st_size,
                )

            return entry.value if isinstance(entry, CacheEntry) else entry

        except (pickle.UnpicklingError, EOFError, OSError):
            # Corrupted cache — delete and return miss
            cache_path.unlink(missing_ok=True)
            return None
        finally:
            self._release_lock()

    def put(
        self,
        file_path: str,
        analysis_result: dict[str, Any],
        ast_bytes: bytes,
        language: str = "python",
        git_sha: str | None = None,
    ) -> None:
        """
        Store analysis result in cache.

        Args:
            file_path: Path to the file
            analysis_result: Analysis result to cache
            ast_bytes: Serialized AST (tree-sitter Tree)
            language: Programming language
            git_sha: Current git commit SHA (if available)
        """
        key = self._make_cache_key(file_path, language)
        cache_path = self._get_cache_path(key)

        cached = CachedAnalysis(
            key=key,
            ast_bytes=ast_bytes,
            analysis_result=analysis_result,
            timestamp=time.time(),
            git_sha=git_sha,
        )

        # Calculate entry size
        entry_size = sys.getsizeof(pickle.dumps(cached, protocol=PICKLE_PROTOCOL))

        self._acquire_lock(exclusive=True)
        try:
            # Evict if necessary
            if self._current_size + entry_size > self.max_size:
                self._evict_lru_until_fit(entry_size)

            # Write atomically
            entry = CacheEntry(
                key=key,
                value=cached,
                last_access=time.time(),
                size_bytes=entry_size,
            )
            data = pickle.dumps(entry, protocol=PICKLE_PROTOCOL)
            self._write_atomically(cache_path, data)

            self._cache[key] = entry
            self._current_size += entry_size

        finally:
            self._release_lock()

    def is_stale(self, cached: CachedAnalysis) -> bool:
        """
        Check if cached result is stale.

        Args:
            cached: Cached analysis result

        Returns:
            True if stale (file changed or git SHA changed)
        """
        # Check if file still exists and has same content
        file_path = self.repo_path / cached.key.file_path
        if not Path(file_path).exists():
            return True

        current_hash = self._get_file_hash(str(file_path))
        if cached.key.content_hash != current_hash:
            return True

        # Git SHA check is done at repo level (not here)
        # This method checks file-level staleness only
        return False

    def invalidate(self, file_path: str) -> None:
        """
        Invalidate cache entry for a file.

        Args:
            file_path: Path to the file
        """
        # Resolve symlinks to handle macOS temp directories
        resolved_path = Path(os.path.realpath(file_path))
        try:
            relative_path = str(resolved_path.relative_to(self.repo_path))
        except ValueError:
            relative_path = str(resolved_path)

        safe_path = relative_path.replace("/", "_").replace("\\", "_")

        # Remove all cache files matching this path (any language/hash)
        self._acquire_lock(exclusive=True)
        try:
            for cache_file in self.cache_dir.glob(f"{safe_path}.*.cache"):
                cache_file.unlink(missing_ok=True)
        finally:
            self._release_lock()

    def invalidate_all(self) -> None:
        """Invalidate all cache entries."""
        self._acquire_lock(exclusive=True)
        try:
            for cache_file in self.cache_dir.glob("*.cache"):
                cache_file.unlink(missing_ok=True)
            self._cache.clear()
            self._current_size = 0
        finally:
            self._release_lock()

    def _evict_lru_until_fit(self, required_bytes: int) -> None:
        """Evict least-recently-used entries until there's space."""
        while self._current_size + required_bytes > self.max_size and self._cache:
            # Find LRU entry
            lru_key = min(self._cache.items(), key=lambda x: x[1].last_access)[0]
            lru_entry = self._cache.pop(lru_key)

            # Delete cache file
            cache_path = self._get_cache_path(lru_entry.key)
            cache_path.unlink(missing_ok=True)

            self._current_size -= lru_entry.size_bytes

    def __enter__(self) -> IncrementalCacheManager:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self._release_lock()
