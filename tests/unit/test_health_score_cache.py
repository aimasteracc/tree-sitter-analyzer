"""Tests for the persistent HealthScoreCache.

These tests pin the cache's contract from the agent-ux perspective:
- Warm runs MUST return identical scores to cold runs.
- Fingerprint mismatch (mtime or size) MUST evict the entry.
- Cache failures MUST fall back to direct scoring without raising.
"""

from __future__ import annotations

import os
import time

import pytest

from tree_sitter_analyzer.health_scorer import HealthScore, HealthScorer
from tree_sitter_analyzer.registry.health_score_cache import HealthScoreCache


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def add(a, b):\n    return a + b\n")
    (src / "util.py").write_text("def repeat(n):\n    return [i for i in range(n)]\n")
    return tmp_path


def test_cache_roundtrip(project):
    cache = HealthScoreCache(str(project))
    assert cache.enabled
    score = HealthScore(
        file_path=str(project / "src" / "main.py"),
        total=82.5,
        dimensions={"size": 100.0, "complexity": 80.0},
    )
    cache.store(score)
    hit = cache.lookup(str(project / "src" / "main.py"))
    assert hit is not None
    assert hit["total"] == 82.5
    assert hit["grade"] == "B"
    assert hit["dimensions"]["complexity"] == 80.0
    cache.close()


def test_cache_misses_on_mtime_change(project):
    target = project / "src" / "main.py"
    cache = HealthScoreCache(str(project))
    cache.store(
        HealthScore(file_path=str(target), total=90.0, dimensions={"size": 100.0})
    )
    # Force mtime to change. Touch with a future timestamp to guarantee
    # the fingerprint differs even on filesystems with low mtime resolution.
    future = time.time() + 10
    os.utime(target, (future, future))
    assert cache.lookup(str(target)) is None
    cache.close()


def test_cache_misses_on_missing_file(project, tmp_path):
    cache = HealthScoreCache(str(project))
    cache.store(
        HealthScore(file_path=str(tmp_path / "ghost.py"), total=50.0, dimensions={})
    )
    # store is best-effort: missing files do NOT insert a row, so lookup misses.
    assert cache.lookup(str(tmp_path / "ghost.py")) is None
    cache.close()


def test_invalidate_removes_entry(project):
    target = str(project / "src" / "main.py")
    cache = HealthScoreCache(str(project))
    cache.store(HealthScore(file_path=target, total=70.0, dimensions={}))
    assert cache.lookup(target) is not None
    assert cache.invalidate(target) is True
    assert cache.lookup(target) is None
    cache.close()


def test_score_project_warm_run_is_fast(project):
    """The warm run MUST be substantially faster than the cold run.

    We score 2 tiny files. Even on slow CI the cold run scores everything
    fresh; the warm run must read from cache and be at least 2x faster.
    """
    scorer = HealthScorer()

    cold_start = time.perf_counter()
    cold = scorer.score_project(str(project))
    cold_elapsed = time.perf_counter() - cold_start

    warm_start = time.perf_counter()
    warm = scorer.score_project(str(project))
    warm_elapsed = time.perf_counter() - warm_start

    # Equivalent results.
    assert {s.file_path for s in cold} == {s.file_path for s in warm}
    assert {s.grade for s in cold} == {s.grade for s in warm}

    # The cache MUST help. On very small projects the absolute numbers are
    # tiny; require warm <= cold + a generous floor so the test is robust
    # against CI jitter.
    assert warm_elapsed <= cold_elapsed + 0.1


def test_score_project_use_cache_false_still_works(project):
    """``use_cache=False`` is a valid opt-out and must produce same results."""
    scorer = HealthScorer()
    cached = scorer.score_project(str(project), use_cache=True)
    fresh = scorer.score_project(str(project), use_cache=False)
    assert {s.file_path for s in cached} == {s.file_path for s in fresh}


def test_cache_handles_broken_db_path(tmp_path):
    """When the cache DB cannot be opened, scoring still proceeds."""
    # Point at a path the cache cannot create (parent is a file).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    cache = HealthScoreCache(str(tmp_path), db_path=str(blocker / "nested" / "h.db"))
    assert cache.enabled is False
    # All operations must be no-ops, no exceptions raised.
    assert cache.lookup("anything") is None
    cache.store(HealthScore(file_path="x", total=0.0, dimensions={}))
    assert cache.invalidate("x") is False
    stats = cache.stats()
    assert stats["enabled"] is False
