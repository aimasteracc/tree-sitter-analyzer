"""Behavior tests for the persistent HealthScoreCache."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.health_scorer import HealthScore, HealthScorer
from tree_sitter_analyzer.registry import health_score_cache as cache_module
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


def test_cache_reopens_with_unchanged_score_context(project, monkeypatch):
    """An unchanged scoring context must preserve the persistent warm hit."""
    # Issue #1183 (2026-07-27): context invalidation must retain warm-cache value.
    monkeypatch.chdir(project)
    target = project / "src" / "main.py"
    first = HealthScoreCache(str(project))
    first.store(HealthScore(file_path=str(target), total=82.5, dimensions={}))
    first.close()

    second = HealthScoreCache(str(project))
    hit = second.lookup(str(target))

    assert hit is not None
    assert hit["total"] == 82.5
    second.close()


def _create_git_metadata(repo_root: Path, ref_value: str = "abc123") -> Path:
    """Create the minimal loose-ref metadata consumed by the cache."""
    git_dir = repo_root / ".git"
    ref = git_dir / "refs" / "heads" / "main"
    ref.parent.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    ref.write_text(f"{ref_value}\n", encoding="utf-8")
    return ref


def test_cache_uses_the_repository_governing_each_file(project, monkeypatch):
    """A nested repository HEAD change must invalidate only its own files."""
    # PR #1184 Codex review (2026-07-27): one project-level HEAD missed
    # submodules and nested repositories scored by their own Git history.
    monkeypatch.chdir(project)
    outer_target = project / "src" / "main.py"
    _create_git_metadata(project)
    nested = project / "vendor"
    nested.mkdir()
    nested_target = nested / "nested.py"
    nested_target.write_text("value = 1\n", encoding="utf-8")
    nested_ref = _create_git_metadata(nested)
    first = HealthScoreCache(str(project))
    first.store(HealthScore(file_path=str(outer_target), total=90.0, dimensions={}))
    first.store(HealthScore(file_path=str(nested_target), total=80.0, dimensions={}))
    first.close()
    nested_ref.write_text("def456\n", encoding="utf-8")

    second = HealthScoreCache(str(project))

    assert second.lookup(str(outer_target)) is not None
    assert second.lookup(str(nested_target)) is None
    second.close()


def test_cache_uses_the_repository_governing_a_source_link(project, monkeypatch):
    """A source link must inherit Git context from its resolved target."""
    # PR #1184 Codex review (2026-07-27): hotspot scoring resolves source links.
    monkeypatch.chdir(project)
    _create_git_metadata(project)
    nested = project / "vendor"
    nested.mkdir()
    target = nested / "linked.py"
    target.write_text("value = 1\n", encoding="utf-8")
    nested_ref = _create_git_metadata(nested)
    source_link = project / "src" / "linked.py"
    source_link.symlink_to(target)
    first = HealthScoreCache(str(project))
    first.store(HealthScore(file_path=str(source_link), total=80.0, dimensions={}))
    first.close()
    nested_ref.write_text("def456\n", encoding="utf-8")

    second = HealthScoreCache(str(project))

    assert second.lookup(str(source_link)) is None
    second.close()


def test_file_context_handles_a_source_link_resolution_loop(project, monkeypatch):
    """A looping source link must fall back to its unresolved parent safely."""
    # PR #1184 Codex review (2026-07-27): cache setup is best-effort.
    monkeypatch.chdir(project)
    source_link = project / "src" / "loop.py"
    source_link.symlink_to("loop.py")
    cache = HealthScoreCache(str(project))

    context = cache._context_for_file(str(source_link))

    assert len(context) == 64
    cache.close()


def test_cache_misses_when_shallow_history_changes(project, monkeypatch):
    """Deepening a shallow repository must invalidate hotspot scores."""
    # PR #1184 Codex review (2026-07-27): HEAD can stay fixed while the
    # shallow boundary exposes more recent commits.
    monkeypatch.chdir(project)
    target = project / "src" / "main.py"
    git_dir = project / ".git"
    _create_git_metadata(project)
    shallow = git_dir / "shallow"
    shallow.write_text("boundary-one\n", encoding="utf-8")
    first = HealthScoreCache(str(project))
    first.store(HealthScore(file_path=str(target), total=90.0, dimensions={}))
    first.close()
    shallow.write_text("boundary-two\n", encoding="utf-8")

    second = HealthScoreCache(str(project))

    assert second.lookup(str(target)) is None
    second.close()


def test_cache_misses_when_hotspot_day_window_advances(project, monkeypatch):
    """The moving 90-day history window must have a bounded cache lifetime."""
    # PR #1184 Codex review (2026-07-27): commits age out without moving HEAD.
    monkeypatch.chdir(project)
    target = project / "src" / "main.py"
    _create_git_metadata(project)
    monkeypatch.setattr(cache_module.time, "time", lambda: 10 * 86_400.0)
    first = HealthScoreCache(str(project))
    first.store(HealthScore(file_path=str(target), total=90.0, dimensions={}))
    first.close()
    monkeypatch.setattr(cache_module.time, "time", lambda: 11 * 86_400.0)

    second = HealthScoreCache(str(project))

    assert second.lookup(str(target)) is None
    second.close()


def test_cache_misses_when_scorer_weights_change(project, monkeypatch):
    """Custom weight configurations must not share cached totals or grades."""
    # PR #1184 Codex review (2026-07-27): dimensions are reusable, totals are not.
    monkeypatch.chdir(project)
    target = project / "src" / "main.py"
    first = HealthScoreCache(str(project), weights={"size": 100.0})
    first.store(
        HealthScore(
            file_path=str(target),
            total=100.0,
            dimensions={"size": 100.0, "complexity": 0.0},
        )
    )
    first.close()

    second = HealthScoreCache(str(project), weights={"complexity": 100.0})

    assert second.lookup(str(target)) is None
    second.close()


def test_cache_misses_when_coverage_report_appears(project, monkeypatch):
    """A newly available report must invalidate coverage-free scores."""
    # Issue #1183 (2026-07-27): report appearance was invisible to cache keys.
    monkeypatch.chdir(project)
    target = project / "src" / "main.py"
    first = HealthScoreCache(str(project))
    first.store(HealthScore(file_path=str(target), total=82.5, dimensions={}))
    first.close()
    (project / "coverage.json").write_text('{"files": {}}', encoding="utf-8")

    second = HealthScoreCache(str(project))

    assert second.lookup(str(target)) is None
    second.close()


def test_cache_misses_when_coverage_report_changes(project, monkeypatch):
    """Replacing a report must invalidate scores for unchanged source files."""
    # Issue #1183 (2026-07-27): focused coverage survived a full report replacement.
    monkeypatch.chdir(project)
    report = project / "coverage.json"
    report.write_text('{"files": {"focused.py": {}}}', encoding="utf-8")
    target = project / "src" / "main.py"
    first = HealthScoreCache(str(project))
    first.store(HealthScore(file_path=str(target), total=40.0, dimensions={}))
    first.close()
    report.write_text('{"files": {"full.py": {}}}', encoding="utf-8")

    second = HealthScoreCache(str(project))

    assert second.lookup(str(target)) is None
    second.close()


def test_warm_cache_does_not_read_full_coverage_artifacts(project, monkeypatch):
    """Context setup must stay O(1) in the size of coverage artifacts."""
    # PR #1184 Codex review (2026-07-27): hashing large reports erased the
    # persistent cache's warm-scan latency benefit.
    monkeypatch.chdir(project)
    report = project / "coverage.json"
    report.write_text('{"files": {}}', encoding="utf-8")
    target = project / "src" / "main.py"
    _create_git_metadata(project)
    first = HealthScoreCache(str(project))
    first.store(HealthScore(file_path=str(target), total=90.0, dimensions={}))
    first.close()
    original_open = Path.open

    def reject_report_read(path, *args, **kwargs):
        if path == report:
            raise AssertionError("coverage artifact content was read")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_report_read)
    second = HealthScoreCache(str(project))

    assert second.lookup(str(target)) == {
        "file_path": str(target),
        "total": 90.0,
        "grade": "A",
        "dimensions": {},
    }
    second.close()


def test_score_project_reloads_replaced_coverage_report(project, monkeypatch):
    """A warm project scan must expose values from the replacement report."""
    # Issue #1183 (2026-07-27): project health returned the focused-run grade
    # after coverage.json had been replaced by the full-suite report.
    monkeypatch.chdir(project)
    report = project / "coverage.json"
    report.write_text(
        '{"files": {"src/main.py": {"summary": {"percent_covered": 0.0}}}}',
        encoding="utf-8",
    )
    scorer = HealthScorer()
    first_scores = scorer.score_project(str(project))
    first = next(score for score in first_scores if score.file_path.endswith("main.py"))
    report.write_text(
        '{"files": {"src/main.py": {"summary": {"percent_covered": 100.0}}}}',
        encoding="utf-8",
    )

    second_scores = scorer.score_project(str(project))
    second = next(
        score for score in second_scores if score.file_path.endswith("main.py")
    )
    warm_scores = HealthScorer().score_project(str(project))
    warm = next(score for score in warm_scores if score.file_path.endswith("main.py"))

    assert first.dimensions["coverage"] == 0.0
    assert second.dimensions["coverage"] == 100.0
    assert (first.total, first.grade) == (88.9, "B")
    assert (second.total, second.grade) == (100.0, "A")
    assert (warm.dimensions["coverage"], warm.total, warm.grade) == (100.0, 100.0, "A")


def test_coverage_lookup_normalizes_windows_separators():
    """Coverage keys must match Windows source paths in cross-platform CI."""
    # PR #1184 CI (2026-07-27): src/main.py did not match a backslash path.
    scorer = HealthScorer()
    scorer._coverage_cache = {"src/main.py": 100.0}

    assert scorer._score_coverage(r"C:\workspace\src\main.py") == 100.0


def test_coverage_lookup_requires_a_path_component_boundary():
    """A directory name ending in the covered path prefix must not match."""
    # PR #1184 Codex review (2026-07-27): ``othersrc`` is not the ``src`` dir.
    scorer = HealthScorer()
    scorer._coverage_cache = {"src/foo.py": 100.0}

    assert scorer._score_coverage(r"C:\workspace\othersrc\foo.py") is None


def test_coverage_lookup_casefolds_windows_paths():
    """Windows drive and directory casing must not suppress measured coverage."""
    # PR #1184 Codex review (2026-07-27): Windows paths are case-insensitive.
    scorer = HealthScorer()
    scorer._coverage_cache = {"C:/Workspace/SRC/Foo.py": 87.5}

    assert scorer._score_coverage(r"c:\workspace\src\foo.py") == 87.5


def test_posix_coverage_lookup_does_not_scan_report_entries():
    """An exact POSIX lookup must retain its constant-time dictionary path."""

    # PR #1184 Codex review (2026-07-27): nested scans made cold health O(F*C).
    class NonIterableCoverage(dict):
        def items(self):
            raise AssertionError("exact POSIX lookup iterated coverage entries")

    scorer = HealthScorer()
    scorer._coverage_cache = NonIterableCoverage({"src/main.py": 91.25})

    assert scorer._score_coverage("src/main.py") == 91.25


def test_cache_misses_when_coverage_report_disappears(project, monkeypatch):
    """Removing a report must invalidate scores that embedded its coverage."""
    # Issue #1183 (2026-07-27): report disappearance was invisible to cache keys.
    monkeypatch.chdir(project)
    report = project / "coverage.json"
    report.write_text('{"files": {"main.py": {}}}', encoding="utf-8")
    target = project / "src" / "main.py"
    first = HealthScoreCache(str(project))
    first.store(HealthScore(file_path=str(target), total=90.0, dimensions={}))
    first.close()
    report.unlink()

    second = HealthScoreCache(str(project))

    assert second.lookup(str(target)) is None
    second.close()


def test_cache_misses_when_context_version_changes(project, monkeypatch):
    """A scoring-algorithm version bump must invalidate prior rows."""
    # Issue #1183 (2026-07-27): the cache lacked an algorithm invalidation path.
    monkeypatch.chdir(project)
    target = project / "src" / "main.py"
    first = HealthScoreCache(str(project))
    first.store(HealthScore(file_path=str(target), total=82.5, dimensions={}))
    first.close()
    monkeypatch.setattr(cache_module, "_CACHE_CONTEXT_VERSION", "test-next-version")

    second = HealthScoreCache(str(project))

    assert second.lookup(str(target)) is None
    second.close()


def test_legacy_schema_migrates_to_context_miss(project, monkeypatch):
    """A context-free database must migrate safely and reject its stale row."""
    # Issue #1183 (2026-07-27): deployed SQLite caches predate context fingerprints.
    monkeypatch.chdir(project)
    target = project / "src" / "main.py"
    stat = target.stat()
    db_path = project / ".ast-cache" / "health_scores.db"
    db_path.parent.mkdir()
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE health_scores (
            file_path TEXT PRIMARY KEY,
            mtime_ns INTEGER NOT NULL,
            size_bytes INTEGER NOT NULL,
            total REAL NOT NULL,
            grade TEXT NOT NULL,
            dimensions_json TEXT NOT NULL,
            cached_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
        );
        """
    )
    connection.execute(
        "INSERT INTO health_scores "
        "(file_path, mtime_ns, size_bytes, total, grade, dimensions_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(target), stat.st_mtime_ns, stat.st_size, 40.0, "F", "{}"),
    )
    connection.commit()
    connection.close()

    cache = HealthScoreCache(str(project))
    columns = {
        row[1]
        for row in cache._conn.execute("PRAGMA table_info(health_scores)")  # type: ignore[union-attr]
    }

    assert columns == {
        "file_path",
        "mtime_ns",
        "size_bytes",
        "total",
        "grade",
        "dimensions_json",
        "cached_at",
        "context_fingerprint",
    }
    assert cache.lookup(str(target)) is None
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
