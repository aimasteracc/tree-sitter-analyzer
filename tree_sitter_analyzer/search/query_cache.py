"""
Query cache with git SHA-based invalidation.

Caches query results and invalidates when git HEAD moves,
ensuring stale results are discarded after code changes.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_CACHE_DIR = Path(".cache/tree-sitter-analyzer/queries")
DEFAULT_MAX_SIZE = 1000


@dataclass(frozen=True)
class CacheKey:
    """Cache key combining query hash and git SHA."""

    query_hash: str
    git_sha: str

    @classmethod
    def from_query(cls, query: str, project_root: Path | None = None) -> CacheKey:
        """Create cache key from query string and current git SHA."""
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        git_sha = get_git_sha(project_root)
        return cls(query_hash=query_hash, git_sha=git_sha)


@dataclass(frozen=True)
class CacheEntry:
    """Cached query result with metadata."""

    key: CacheKey
    result: dict[str, Any]
    tool_used: str
    timestamp: float
    execution_time_ms: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "key": {
                "query_hash": self.key.query_hash,
                "git_sha": self.key.git_sha,
            },
            "result": self.result,
            "tool_used": self.tool_used,
            "timestamp": self.timestamp,
            "execution_time_ms": self.execution_time_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """Create from dictionary."""
        key_data = data["key"]
        key = CacheKey(
            query_hash=key_data["query_hash"],
            git_sha=key_data["git_sha"],
        )
        return cls(
            key=key,
            result=data["result"],
            tool_used=data["tool_used"],
            timestamp=data["timestamp"],
            execution_time_ms=data["execution_time_ms"],
        )


@dataclass
class CacheStats:
    """Cache statistics."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    invalidations: int = 0

    @property
    def total_requests(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests


def get_git_sha(project_root: Path | None = None) -> str:
    """Get current git HEAD SHA.

    Returns 'unknown' if not in a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, TimeoutError):
        return "unknown"


class QueryCache:
    """Query result cache with git SHA-based invalidation.

    Cache entries are automatically invalidated when git HEAD moves,
    ensuring results are always fresh with respect to current code.
    """

    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        max_size: int = DEFAULT_MAX_SIZE,
        project_root: Path | None = None,
    ) -> None:
        """Initialize query cache.

        Args:
            cache_dir: Directory to store cache files
            max_size: Maximum number of cache entries (LRU eviction)
            project_root: Git repository root (for SHA detection)
        """
        self.cache_dir = cache_dir
        self.max_size = max_size
        self.project_root = project_root

        self._cache: dict[str, CacheEntry] = {}
        self._access_order: list[str] = []  # For LRU
        self._stats = CacheStats()

        self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from disk."""
        cache_file = self.cache_dir / "cache.json"
        if not cache_file.exists():
            return

        try:
            data = json.loads(cache_file.read_text())
            current_sha = get_git_sha(self.project_root)

            for entry_data in data.get("entries", []):
                entry = CacheEntry.from_dict(entry_data)
                # Skip entries from different git commits
                if entry.key.git_sha != current_sha:
                    self._stats.invalidations += 1
                    continue

                self._cache[entry.key.query_hash] = entry
                self._access_order.append(entry.key.query_hash)

            # Enforce max size after loading
            while len(self._cache) > self.max_size:
                self._evict_oldest()

        except (OSError, json.JSONDecodeError, KeyError):
            # Corrupt cache file - start fresh
            self._cache.clear()
            self._access_order.clear()

    def _save_cache(self) -> None:
        """Save cache to disk."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self.cache_dir / "cache.json"

        data = {
            "entries": [entry.to_dict() for entry in self._cache.values()],
            "stats": {
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "evictions": self._stats.evictions,
                "invalidations": self._stats.invalidations,
            },
        }

        cache_file.write_text(json.dumps(data, indent=2))

    def _evict_oldest(self) -> None:
        """Evict oldest cache entry (LRU)."""
        if not self._access_order:
            return

        oldest_key = self._access_order.pop(0)
        if oldest_key in self._cache:
            del self._cache[oldest_key]
            self._stats.evictions += 1

    def _record_access(self, key: CacheKey) -> None:
        """Record cache access for LRU tracking."""
        query_hash = key.query_hash
        if query_hash in self._access_order:
            self._access_order.remove(query_hash)
        self._access_order.append(query_hash)

    def get(self, query: str) -> CacheEntry | None:
        """Get cached result for query.

        Returns None if:
        - Query not in cache
        - Cache entry is from different git commit (auto-invalidated)
        """
        key = CacheKey.from_query(query, self.project_root)
        entry = self._cache.get(key.query_hash)

        if entry is None:
            self._stats.misses += 1
            return None

        # Check if git SHA matches (invalidation)
        if entry.key.git_sha != key.git_sha:
            del self._cache[key.query_hash]
            try:
                self._access_order.remove(key.query_hash)
            except ValueError:
                pass
            self._stats.invalidations += 1
            self._stats.misses += 1
            return None

        self._stats.hits += 1
        self._record_access(key)
        return entry

    def put(
        self,
        query: str,
        result: dict[str, Any],
        tool_used: str,
        execution_time_ms: int,
    ) -> CacheEntry:
        """Cache result for query.

        Enforces max size via LRU eviction if necessary.
        """
        import time

        key = CacheKey.from_query(query, self.project_root)
        entry = CacheEntry(
            key=key,
            result=result,
            tool_used=tool_used,
            timestamp=time.time(),
            execution_time_ms=execution_time_ms,
        )

        self._cache[key.query_hash] = entry
        self._record_access(key)

        # Evict if over size limit
        while len(self._cache) > self.max_size:
            self._evict_oldest()

        # Auto-save after write
        self._save_cache()

        return entry

    def invalidate_all(self) -> None:
        """Invalidate all cache entries."""
        count = len(self._cache)
        self._cache.clear()
        self._access_order.clear()
        self._stats.invalidations += count
        self._save_cache()

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    def clear(self) -> None:
        """Clear cache and delete cache file."""
        self._cache.clear()
        self._access_order.clear()
        cache_file = self.cache_dir / "cache.json"
        if cache_file.exists():
            cache_file.unlink()

    def optimize_for_fast_path(
        self,
        query: str,
        tool_name: str,
        threshold: int = 3,
    ) -> bool:
        """Check if query should be promoted to fast path.

        Returns True if query has been consistently resolved by the same tool.

        Args:
            query: The query string
            tool_name: Name of the tool that resolved the query
            threshold: Minimum cache hits for promotion (default: 3)
        """
        # This is a simple heuristic - future versions can analyze
        # query patterns to generate regex rules for the classifier
        key = CacheKey.from_query(query, self.project_root)
        entry = self._cache.get(key.query_hash)

        if entry is None:
            return False

        # Promote if same tool used consistently
        # (In a real implementation, we'd track multiple hits)
        return entry.tool_used == tool_name
