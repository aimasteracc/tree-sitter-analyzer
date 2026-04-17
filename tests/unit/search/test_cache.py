"""
Unit tests for Query Cache.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from tree_sitter_analyzer.search.cache import (
    CacheEntry,
    CacheStats,
    GitStateTracker,
    PatternLearner,
    QueryCache,
)


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_init(self) -> None:
        """Test CacheEntry initialization."""
        entry = CacheEntry(
            query="test query",
            results=[{"file": "test.py"}],
            handler="test_handler",
            timestamp="2026-04-17T00:00:00",
            git_sha="abc123",
            hit_count=5,
            last_accessed="2026-04-17T01:00:00",
        )

        assert entry.query == "test query"
        assert entry.results == [{"file": "test.py"}]
        assert entry.handler == "test_handler"
        assert entry.git_sha == "abc123"
        assert entry.hit_count == 5

    def test_to_dict(self) -> None:
        """Test converting CacheEntry to dictionary."""
        entry = CacheEntry(
            query="test",
            results=[],
            handler="handler",
            timestamp="2026-04-17T00:00:00",
            git_sha="abc123",
        )

        data = entry.to_dict()

        assert isinstance(data, dict)
        assert data["query"] == "test"
        assert data["results"] == []

    def test_from_dict(self) -> None:
        """Test creating CacheEntry from dictionary."""
        data = {
            "query": "test",
            "results": [],
            "handler": "handler",
            "timestamp": "2026-04-17T00:00:00",
            "git_sha": "abc123",
            "hit_count": 0,
            "last_accessed": "",
        }

        entry = CacheEntry.from_dict(data)

        assert entry.query == "test"
        assert entry.handler == "handler"


class TestCacheStats:
    """Test CacheStats dataclass."""

    def test_init(self) -> None:
        """Test CacheStats initialization."""
        stats = CacheStats(
            total_queries=100,
            cache_hits=60,
            cache_misses=40,
        )

        assert stats.total_queries == 100
        assert stats.cache_hits == 60
        assert stats.cache_misses == 40

    def test_hit_rate(self) -> None:
        """Test hit rate calculation."""
        stats = CacheStats(
            total_queries=100,
            cache_hits=60,
            cache_misses=40,
        )

        assert stats.hit_rate() == 0.6

    def test_hit_rate_no_queries(self) -> None:
        """Test hit rate with no queries."""
        stats = CacheStats()

        assert stats.hit_rate() == 0.0


class TestGitStateTracker:
    """Test GitStateTracker class."""

    @pytest.fixture
    def tracker(self, tmp_path: Path) -> GitStateTracker:
        """Get GitStateTracker instance."""
        # Create a temporary directory (not a git repo)
        return GitStateTracker(project_root=str(tmp_path))

    def test_init(self, tracker: GitStateTracker) -> None:
        """Test GitStateTracker initialization."""
        assert tracker.project_root == tracker.project_root
        assert tracker._current_sha is None

    def test_get_current_sha_no_git(self, tracker: GitStateTracker) -> None:
        """Test get_current_sha when not in a git repository."""
        sha = tracker.get_current_sha()
        assert sha is None

    def test_get_current_branch_no_git(self, tracker: GitStateTracker) -> None:
        """Test get_current_branch when not in a git repository."""
        branch = tracker.get_current_branch()
        assert branch is None

    def test_has_changed_no_git(self, tracker: GitStateTracker) -> None:
        """Test has_changed when not in a git repository."""
        assert not tracker.has_changed()


class TestQueryCache:
    """Test QueryCache class."""

    @pytest.fixture
    def cache(self, tmp_path: Path) -> QueryCache:
        """Get QueryCache instance."""
        return QueryCache(project_root=str(tmp_path), ttl_minutes=60)

    def test_init(self, cache: QueryCache) -> None:
        """Test QueryCache initialization."""
        assert cache.project_root == cache.project_root
        assert isinstance(cache._cache, dict)
        assert isinstance(cache._stats, CacheStats)

    def test_set_and_get(self, cache: QueryCache) -> None:
        """Test setting and getting cache entries."""
        results = [{"file": "test.py", "line": 10}]

        cache.set("test query", "test_handler", results)
        cached = cache.get("test query", "test_handler")

        assert cached == results

    def test_get_miss(self, cache: QueryCache) -> None:
        """Test cache miss."""
        result = cache.get("nonexistent", "handler")
        assert result is None

    def test_cache_hit_count(self, cache: QueryCache) -> None:
        """Test cache hit count increment."""
        results = [{"file": "test.py"}]

        cache.set("query", "handler", results)
        cache.get("query", "handler")
        cache.get("query", "handler")

        key = cache._generate_key("query", "handler")
        assert cache._cache[key].hit_count == 2

    def test_get_stats(self, cache: QueryCache) -> None:
        """Test getting cache statistics."""
        results = [{"file": "test.py"}]

        cache.set("query", "handler", results)
        cache.get("query", "handler")  # Hit
        cache.get("other", "handler")  # Miss

        stats = cache.get_stats()

        assert stats.total_queries == 2
        assert stats.cache_hits == 1
        assert stats.cache_misses == 1

    def test_clear(self, cache: QueryCache) -> None:
        """Test clearing cache."""
        cache.set("query", "handler", [{"file": "test.py"}])
        assert len(cache._cache) == 1

        cache.clear()
        assert len(cache._cache) == 0

    def test_cleanup_expired(self, cache: QueryCache) -> None:
        """Test cleaning up expired entries."""
        # Set TTL to 0 minutes for immediate expiration
        cache.ttl = timedelta(minutes=0)

        cache.set("query", "handler", [{"file": "test.py"}])

        # Entry should be expired
        removed = cache.cleanup_expired()
        assert removed == 1
        assert len(cache._cache) == 0


class TestPatternLearner:
    """Test PatternLearner class."""

    @pytest.fixture
    def learner(self) -> PatternLearner:
        """Get PatternLearner instance."""
        return PatternLearner(min_frequency=3)

    def test_init(self, learner: PatternLearner) -> None:
        """Test PatternLearner initialization."""
        assert learner.min_frequency == 3
        assert learner._query_patterns == {}

    def test_record_query_llm(self, learner: PatternLearner) -> None:
        """Test recording an LLM query."""
        learner.record_query("test query", was_llm=True)

        assert "test query" in learner._query_patterns
        assert learner._query_patterns["test query"] == 1

    def test_record_query_fast_path(self, learner: PatternLearner) -> None:
        """Test that fast path queries are not recorded."""
        learner.record_query("test query", was_llm=False)

        assert "test query" not in learner._query_patterns

    def test_normalize_query(self, learner: PatternLearner) -> None:
        """Test query normalization."""
        normalized = learner._normalize_query("  Test  Query  ")

        assert normalized == "test query"

    def test_get_suggested_patterns(self, learner: PatternLearner) -> None:
        """Test getting suggested patterns."""
        # Record a query 3 times (meets threshold)
        for _ in range(3):
            learner.record_query("frequent query", was_llm=True)

        suggestions = learner.get_suggested_patterns()

        assert len(suggestions) == 1
        assert suggestions[0] == ("frequent query", 3)

    def test_get_suggested_patterns_below_threshold(self, learner: PatternLearner) -> None:
        """Test that patterns below threshold are not suggested."""
        learner.record_query("rare query", was_llm=True)

        suggestions = learner.get_suggested_patterns()

        assert len(suggestions) == 0

    def test_get_pattern_frequency(self, learner: PatternLearner) -> None:
        """Test getting pattern frequency."""
        learner.record_query("test query", was_llm=True)
        learner.record_query("test query", was_llm=True)

        freq = learner.get_pattern_frequency("test query")

        assert freq == 2

    def test_get_pattern_frequency_zero(self, learner: PatternLearner) -> None:
        """Test getting frequency of non-existent pattern."""
        freq = learner.get_pattern_frequency("nonexistent")

        assert freq == 0


class TestQueryCacheIntegration:
    """Integration tests for QueryCache."""

    @pytest.fixture
    def cache(self, tmp_path: Path) -> QueryCache:
        """Get QueryCache instance with temp cache file."""
        return QueryCache(project_root=str(tmp_path), ttl_minutes=60)

    def test_cache_persistence(self, tmp_path: Path) -> None:
        """Test that cache persists across instances."""
        cache_file = tmp_path / ".query_cache.json"

        # First instance
        cache1 = QueryCache(project_root=str(tmp_path), ttl_minutes=60)
        cache1.set("query", "handler", [{"file": "test.py"}])

        # Verify cache file was created
        assert cache_file.exists()

        # Second instance should load from file
        cache2 = QueryCache(project_root=str(tmp_path), ttl_minutes=60)
        results = cache2.get("query", "handler")

        assert results == [{"file": "test.py"}]

    def test_cache_file_corruption_recovery(self, tmp_path: Path) -> None:
        """Test recovery from corrupted cache file."""
        cache_file = tmp_path / ".query_cache.json"

        # Write invalid JSON
        cache_file.write_text("invalid json")

        # Should handle corruption gracefully
        cache = QueryCache(project_root=str(tmp_path), ttl_minutes=60)

        assert cache._cache == {}
        assert cache._stats.total_queries == 0
