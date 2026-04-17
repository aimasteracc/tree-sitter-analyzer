"""
Query Cache Module

Provides intelligent caching with git SHA-based invalidation and adaptive
pattern learning. Cache entries are invalidated when the git repository state
changes (e.g., new commits, branch changes).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

# Set up logging
logger = setup_logger(__name__)


@dataclass
class CacheEntry:
    """A cache entry storing query results with metadata."""

    query: str
    results: list[dict[str, Any]]
    handler: str
    timestamp: str
    git_sha: str
    hit_count: int = 0
    last_accessed: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """Create from dictionary."""
        return cls(**data)


@dataclass
class CacheStats:
    """Statistics about cache usage."""

    total_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    invalidations: int = 0
    pattern_promotions: int = 0

    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        if self.total_queries == 0:
            return 0.0
        return self.cache_hits / self.total_queries


class GitStateTracker:
    """Tracks git repository state for cache invalidation."""

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize git state tracker.

        Args:
            project_root: Root directory of the git repository
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self._current_sha: str | None = None
        self._current_branch: str | None = None

    def get_current_sha(self) -> str | None:
        """
        Get the current git commit SHA.

        Returns:
            Current commit SHA or None if not in a git repository
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                timeout=2,
                cwd=self.project_root,
            )
            self._current_sha = result.stdout.strip()
            return self._current_sha
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def get_current_branch(self) -> str | None:
        """
        Get the current git branch name.

        Returns:
            Current branch name or None if not in a git repository
        """
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True,
                timeout=2,
                cwd=self.project_root,
            )
            self._current_branch = result.stdout.strip()
            return self._current_branch
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def has_changed(self) -> bool:
        """
        Check if the git state has changed since last check.

        Returns:
            True if SHA or branch has changed
        """
        previous_sha = self._current_sha
        previous_branch = self._current_branch

        current_sha = self.get_current_sha()
        current_branch = self.get_current_branch()

        return (
            previous_sha != current_sha
            or previous_branch != current_branch
        )


class QueryCache:
    """
    Query result cache with git SHA-based invalidation.

    Cache entries are invalidated when:
    - Git commit SHA changes
    - Git branch changes
    - Cache entry expires (TTL)
    """

    DEFAULT_TTL_MINUTES = 60
    CACHE_FILE = ".query_cache.json"

    def __init__(
        self,
        project_root: str | None = None,
        ttl_minutes: int = DEFAULT_TTL_MINUTES,
    ) -> None:
        """
        Initialize query cache.

        Args:
            project_root: Root directory of the project
            ttl_minutes: Time-to-live for cache entries in minutes
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.ttl = timedelta(minutes=ttl_minutes)
        self.git_tracker = GitStateTracker(str(self.project_root))

        self._cache: dict[str, CacheEntry] = {}
        self._stats = CacheStats()
        self._cache_file = self.project_root / self.CACHE_FILE

        # Load existing cache if available
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from disk if available."""
        if not self._cache_file.exists():
            return

        try:
            with open(self._cache_file) as f:
                data = json.load(f)

            for key, entry_data in data.get("entries", {}).items():
                self._cache[key] = CacheEntry.from_dict(entry_data)

            stats_data = data.get("stats", {})
            self._stats = CacheStats(**stats_data)

            logger.info(f"Loaded {len(self._cache)} cache entries")

        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load cache: {e}")

    def _save_cache(self) -> None:
        """Save cache to disk."""
        try:
            data = {
                "entries": {
                    key: entry.to_dict()
                    for key, entry in self._cache.items()
                },
                "stats": asdict(self._stats),
                "saved_at": datetime.now().isoformat(),
            }

            with open(self._cache_file, "w") as f:
                json.dump(data, f, indent=2)

        except OSError as e:
            logger.warning(f"Failed to save cache: {e}")

    def _generate_key(self, query: str, handler: str) -> str:
        """
        Generate a cache key for a query.

        Args:
            query: The query string
            handler: The handler name

        Returns:
            A unique cache key
        """
        import hashlib

        key_str = f"{handler}:{query}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    def _is_expired(self, entry: CacheEntry) -> bool:
        """
        Check if a cache entry has expired.

        Args:
            entry: The cache entry to check

        Returns:
            True if the entry has expired
        """
        try:
            entry_time = datetime.fromisoformat(entry.timestamp)
            return datetime.now() - entry_time > self.ttl
        except ValueError:
            return True

    def _invalidate_if_needed(self) -> None:
        """Invalidate cache if git state has changed."""
        if self.git_tracker.has_changed():
            logger.info("Git state changed, invalidating cache")
            self._cache.clear()
            self._stats.invalidations += 1

    def get(
        self,
        query: str,
        handler: str,
    ) -> list[dict[str, Any]] | None:
        """
        Get cached results for a query.

        Args:
            query: The query string
            handler: The handler name

        Returns:
            Cached results or None if not found/invalid
        """
        self._stats.total_queries += 1
        self._invalidate_if_needed()

        key = self._generate_key(query, handler)

        if key not in self._cache:
            self._stats.cache_misses += 1
            return None

        entry = self._cache[key]

        # Check if expired
        if self._is_expired(entry):
            del self._cache[key]
            self._stats.cache_misses += 1
            return None

        # Update access stats
        entry.hit_count += 1
        entry.last_accessed = datetime.now().isoformat()

        self._stats.cache_hits += 1
        logger.debug(f"Cache hit for query: {query[:50]}...")
        return entry.results

    def set(
        self,
        query: str,
        handler: str,
        results: list[dict[str, Any]],
    ) -> None:
        """
        Store query results in cache.

        Args:
            query: The query string
            handler: The handler name
            results: The results to cache
        """
        self._invalidate_if_needed()

        key = self._generate_key(query, handler)
        git_sha = self.git_tracker.get_current_sha() or "unknown"

        entry = CacheEntry(
            query=query,
            results=results,
            handler=handler,
            timestamp=datetime.now().isoformat(),
            git_sha=git_sha,
            hit_count=0,
            last_accessed="",
        )

        self._cache[key] = entry
        self._save_cache()

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._save_cache()

    def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if self._is_expired(entry)
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            self._save_cache()

        return len(expired_keys)


class PatternLearner:
    """
    Learns query patterns and promotes them to fast path.

    Tracks which queries are frequently handled by LLM and suggests
    them as candidates for fast path patterns.
    """

    def __init__(self, min_frequency: int = 5) -> None:
        """
        Initialize pattern learner.

        Args:
            min_frequency: Minimum frequency before suggesting a pattern
        """
        self.min_frequency = min_frequency
        self._query_patterns: dict[str, int] = {}

    def record_query(self, query: str, was_llm: bool) -> None:
        """
        Record a query for pattern learning.

        Args:
            query: The query string
            was_llm: Whether the query was handled by LLM
        """
        if not was_llm:
            return

        # Normalize query for pattern matching
        normalized = self._normalize_query(query)
        self._query_patterns[normalized] = (
            self._query_patterns.get(normalized, 0) + 1
        )

    def _normalize_query(self, query: str) -> str:
        """
        Normalize a query for pattern matching.

        Args:
            query: The query string

        Returns:
            Normalized query string
        """
        # Convert to lowercase and strip extra whitespace
        normalized = " ".join(query.lower().split())
        return normalized

    def get_suggested_patterns(self) -> list[tuple[str, int]]:
        """
        Get patterns that should be promoted to fast path.

        Returns:
            List of (pattern, frequency) tuples
        """
        return [
            (pattern, freq)
            for pattern, freq in self._query_patterns.items()
            if freq >= self.min_frequency
        ]

    def get_pattern_frequency(self, pattern: str) -> int:
        """
        Get the frequency of a pattern.

        Args:
            pattern: The pattern string

        Returns:
            Frequency count
        """
        normalized = self._normalize_query(pattern)
        return self._query_patterns.get(normalized, 0)
