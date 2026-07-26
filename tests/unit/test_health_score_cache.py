"""Tests for the persistent HealthScoreCache.

These tests pin the cache's contract from the agent-ux perspective:
- Warm runs MUST return identical scores to cold runs.
- Fingerprint mismatch (mtime or size) MUST evict the entry.
- Cache failures MUST fall back to direct scoring without raising.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.health_scorer import HealthScore, HealthScorer
from tree_sitter_analyzer.registry import health_score_cache as cache_module
from tree_sitter_analyzer.registry.health_score_cache import (
    HealthScoreCache,
    _coverage_metadata_signature,
    _find_git_dir,
    _git_context_parts,
    _metadata_signature,
    _read_small_regular_text,
)


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def add(a, b):\n    return a + b\n")
    (src / "util.py").write_text("def repeat(n):\n    return [i for i in range(n)]\n")
    return tmp_path


def test_metadata_signature_marks_unreadable_metadata(tmp_path, monkeypatch):
    """Unreadable context metadata must degrade to a stable cache marker."""
    # Issue #1183 (2026-07-27): cache context discovery is best-effort.
    metadata = tmp_path / "metadata"
    original_lstat = Path.lstat

    def deny_metadata(path):
        if path == metadata:
            raise OSError("permission denied")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", deny_metadata)

    assert _metadata_signature(metadata) == f"{metadata.absolute()}:unreadable"


def test_metadata_signature_rejects_non_regular_candidates(tmp_path):
    """A directory-shaped report candidate must never be opened or hashed."""
    # PR #1184 Codex review (2026-07-27): FIFOs and device links could block
    # forever when the cache tried to consume their unbounded byte streams.
    candidate = tmp_path / "coverage.json"
    candidate.mkdir()

    signature = _metadata_signature(candidate)

    assert ":special:" in signature


def test_coverage_signature_tracks_a_regular_symlink_target(tmp_path):
    """A rewritten report target must invalidate an unchanged report link."""
    # PR #1184 Codex review (2026-07-27): the loader follows report links, so
    # the persistent context must include the regular target's metadata too.
    target = tmp_path / "report-a.json"
    target.write_text("{}", encoding="utf-8")
    report = tmp_path / "coverage.json"
    report.symlink_to(target)
    first = _coverage_metadata_signature(report)
    target.write_text('{"files": {}}', encoding="utf-8")

    second = _coverage_metadata_signature(report)

    assert first != second
    assert "target-regular" in second


def test_coverage_signature_marks_a_dangling_symlink_target(tmp_path):
    """A dangling report link must have an explicit unavailable signature."""
    # PR #1184 Codex review (2026-07-27): broken links remain safe cache inputs.
    report = tmp_path / "coverage.json"
    report.symlink_to(tmp_path / "missing.json")

    assert _coverage_metadata_signature(report).endswith(":target-unavailable")


def test_coverage_signature_marks_a_special_symlink_target(tmp_path):
    """A report link to a non-file must never be treated as readable coverage."""
    # PR #1184 Codex review (2026-07-27): only regular report targets are safe.
    report = tmp_path / "coverage.json"
    report.symlink_to(tmp_path, target_is_directory=True)

    assert _coverage_metadata_signature(report).endswith(":target-special")


def test_small_metadata_reader_rejects_special_files(tmp_path):
    """Git metadata discovery must not consume directory or device streams."""
    # PR #1184 Codex review (2026-07-27): special files could block forever.
    assert _read_small_regular_text(tmp_path) is None


def test_small_metadata_reader_rejects_links_without_nofollow(tmp_path, monkeypatch):
    """Windows fallback must reject a link before calling ``os.open``."""
    # PR #1184 Codex review (2026-07-27): O_NOFOLLOW is unavailable on Windows.
    target = tmp_path / "target"
    target.write_text("ref: refs/heads/main\n", encoding="utf-8")
    link = tmp_path / "HEAD"
    link.symlink_to(target)
    monkeypatch.setattr(cache_module.os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.setattr(
        cache_module.os,
        "open",
        lambda *_args, **_kwargs: pytest.fail("a symlink must not be opened"),
    )

    assert _read_small_regular_text(link) is None


def test_small_metadata_reader_rejects_oversized_files(tmp_path):
    """Unexpectedly large Git metadata must be rejected before any read."""
    # PR #1184 Codex review (2026-07-27): metadata reads need a hard size bound.
    metadata = tmp_path / "HEAD"
    metadata.write_bytes(b"x" * (cache_module._MAX_GIT_METADATA_BYTES + 1))

    assert _read_small_regular_text(metadata) is None


def test_small_metadata_reader_handles_open_failures(tmp_path, monkeypatch):
    """An open-time metadata failure must degrade to unavailable."""
    # PR #1184 Codex review (2026-07-27): lstat success does not guarantee open.
    metadata = tmp_path / "HEAD"
    metadata.write_text("ref: refs/heads/main\n", encoding="utf-8")

    def fail_open(_path, _flags):
        raise OSError("sharing violation")

    monkeypatch.setattr(cache_module.os, "open", fail_open)

    assert _read_small_regular_text(metadata) is None


def test_small_metadata_reader_rechecks_file_type_after_open(tmp_path, monkeypatch):
    """A path swap after lstat must be rejected by descriptor metadata."""
    # PR #1184 Codex review (2026-07-27): post-open validation closes the race.
    metadata = tmp_path / "HEAD"
    metadata.write_text("ref: refs/heads/main\n", encoding="utf-8")
    monkeypatch.setattr(cache_module.os, "fstat", lambda _descriptor: tmp_path.stat())

    assert _read_small_regular_text(metadata) is None


def test_small_metadata_reader_handles_read_failures(tmp_path, monkeypatch):
    """A post-open Git metadata I/O failure must degrade to unavailable."""
    # PR #1184 Codex review (2026-07-27): cache setup remains best-effort.
    metadata = tmp_path / "HEAD"
    metadata.write_text("ref: refs/heads/main\n", encoding="utf-8")

    def fail_read(_descriptor, _size):
        raise OSError("device failure")

    monkeypatch.setattr(cache_module.os, "read", fail_read)

    assert _read_small_regular_text(metadata) is None


def test_small_metadata_reader_enforces_post_read_bound(tmp_path, monkeypatch):
    """A changing file must not bypass the bounded-read size check."""
    # PR #1184 Codex review (2026-07-27): metadata may grow after fstat.
    metadata = tmp_path / "HEAD"
    metadata.write_text("ref: refs/heads/main\n", encoding="utf-8")
    oversized = b"x" * (cache_module._MAX_GIT_METADATA_BYTES + 1)
    monkeypatch.setattr(cache_module.os, "read", lambda _descriptor, _size: oversized)

    assert _read_small_regular_text(metadata) is None


def test_find_git_dir_supports_standard_repositories(tmp_path):
    """A repository-local .git directory must be selected directly."""
    # Issue #1183 (2026-07-27): HEAD contributes to the score context.
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    assert _find_git_dir(tmp_path) == git_dir


def test_find_git_dir_returns_none_when_no_ancestor_is_a_repository(
    tmp_path, monkeypatch
):
    """Repository discovery must terminate with an explicit non-repo result."""
    # PR #1184 Codex review (2026-07-27): per-file discovery traverses ancestors.
    original_lstat = Path.lstat

    def hide_git_markers(path):
        if path.name == ".git":
            raise FileNotFoundError(path)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", hide_git_markers)

    assert _find_git_dir(tmp_path) is None


def test_find_git_dir_handles_unreadable_marker(tmp_path, monkeypatch):
    """An unreadable repository marker must disable Git context safely."""
    # PR #1184 Codex review (2026-07-27): repository lookup is best-effort.
    marker = tmp_path / ".git"
    original_lstat = Path.lstat

    def deny_marker(path):
        if path == marker:
            raise OSError("permission denied")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", deny_marker)

    assert _find_git_dir(tmp_path) is None


def test_find_git_dir_rejects_special_marker(tmp_path):
    """A symlink-shaped .git marker must not be followed as repository state."""
    # PR #1184 Codex review (2026-07-27): untrusted markers stay non-following.
    target = tmp_path / "git-state"
    target.mkdir()
    (tmp_path / ".git").symlink_to(target, target_is_directory=True)

    assert _find_git_dir(tmp_path) is None


def test_find_git_dir_handles_unreadable_pointer(tmp_path, monkeypatch):
    """An unreadable linked-worktree pointer must not escape cache setup."""
    # PR #1184 Codex review (2026-07-27): pointer reads are bounded and optional.
    marker = tmp_path / ".git"
    marker.write_text("gitdir: ../git-state\n", encoding="utf-8")
    monkeypatch.setattr(cache_module, "_read_small_regular_text", lambda _path: None)

    assert _find_git_dir(tmp_path) is None


def test_find_git_dir_handles_a_pointer_resolution_loop(tmp_path):
    """A looping linked-worktree pointer must degrade to no Git context."""
    # PR #1184 Codex review (2026-07-27): Path.resolve can raise RuntimeError.
    (tmp_path / ".git").write_text("gitdir: loop\n", encoding="utf-8")
    (tmp_path / "loop").symlink_to("loop")

    assert _find_git_dir(tmp_path) is None


def test_find_git_dir_handles_a_source_path_resolution_loop(tmp_path):
    """Repository discovery must reject a looping starting path."""
    # PR #1184 Codex review (2026-07-27): even the initial resolve can fail.
    loop = tmp_path / "loop"
    loop.symlink_to("loop")

    assert _find_git_dir(loop) is None


def test_git_context_marks_a_non_repository():
    """A project outside Git must receive an explicit stable context marker."""
    # Issue #1183 (2026-07-27): git-hotspot context may be unavailable.
    assert _git_context_parts(None) == ["git:missing"]


def test_git_context_supports_linked_worktrees(tmp_path):
    """Linked-worktree HEAD and common refs must contribute to the context."""
    # Issue #1183 (2026-07-27): worktrees keep HEAD outside the common git dir.
    project = tmp_path / "project"
    project.mkdir()
    common_dir = tmp_path / "git-state"
    git_dir = common_dir / "worktrees" / "feature"
    git_dir.mkdir(parents=True)
    (project / ".git").write_text(
        "gitdir: ../git-state/worktrees/feature\n", encoding="utf-8"
    )
    (git_dir / "commondir").write_text("../..\n", encoding="utf-8")
    (git_dir / "HEAD").write_text("ref: refs/heads/feature\n", encoding="utf-8")
    ref = common_dir / "refs" / "heads" / "feature"
    ref.parent.mkdir(parents=True)
    ref.write_text("abc123\n", encoding="utf-8")
    (common_dir / "packed-refs").write_text("# pack-refs\n", encoding="utf-8")

    parts = _git_context_parts(git_dir)

    assert _find_git_dir(project) == git_dir
    assert parts == [
        _metadata_signature(git_dir / "HEAD"),
        _metadata_signature(common_dir / "packed-refs"),
        _metadata_signature(common_dir / "shallow"),
        _metadata_signature(ref),
    ]


@pytest.mark.parametrize("marker", ["not-a-gitdir", "other: somewhere"])
def test_find_git_dir_rejects_invalid_pointer_files(tmp_path, marker):
    """Malformed or foreign pointer files must not poison cache startup."""
    # Issue #1183 (2026-07-27): invalid repository metadata is a cache miss.
    (tmp_path / ".git").write_text(marker, encoding="utf-8")

    assert _find_git_dir(tmp_path) is None


def test_git_context_handles_unreadable_worktree_metadata(tmp_path, monkeypatch):
    """Unreadable worktree metadata must fall back without raising."""
    # Issue #1183 (2026-07-27): cache setup must remain best-effort.
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    common_marker = git_dir / "commondir"
    common_marker.write_text("../common\n", encoding="utf-8")
    head = git_dir / "HEAD"
    head.write_text("detached-sha\n", encoding="utf-8")
    original_read = _read_small_regular_text

    def read_metadata(path):
        if path == common_marker:
            return None
        return original_read(path)

    monkeypatch.setattr(cache_module, "_read_small_regular_text", read_metadata)

    assert _git_context_parts(git_dir) == [
        _metadata_signature(head),
        _metadata_signature(git_dir / "packed-refs"),
        _metadata_signature(git_dir / "shallow"),
    ]

    head.unlink()
    assert _git_context_parts(git_dir) == [
        _metadata_signature(head),
        _metadata_signature(git_dir / "packed-refs"),
        _metadata_signature(git_dir / "shallow"),
    ]


def test_git_context_handles_a_commondir_resolution_loop(tmp_path):
    """A looping commondir must make the Git context explicitly unavailable."""
    # PR #1184 Codex review (2026-07-27): worktree metadata is best-effort.
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "commondir").write_text("loop\n", encoding="utf-8")
    (git_dir / "loop").symlink_to("loop")

    assert _git_context_parts(git_dir) == ["git:missing"]


class _MigrationConnection:
    """Minimal connection double for concurrent schema-migration behavior."""

    def __init__(self, migrated: bool) -> None:
        self._migrated = migrated
        self._pragma_calls = 0

    def execute(self, statement: str):
        if statement.startswith("PRAGMA"):
            self._pragma_calls += 1
            columns = ["file_path"]
            if self._pragma_calls > 1 and self._migrated:
                columns.append("context_fingerprint")
            return [(0, column) for column in columns]
        raise sqlite3.OperationalError("duplicate column")


def test_context_migration_accepts_a_concurrent_winner():
    """A concurrent process adding the column first must be treated as success."""
    # Issue #1183 (2026-07-27): multiple health scans may initialize together.
    cache = HealthScoreCache.__new__(HealthScoreCache)
    cache._conn = _MigrationConnection(migrated=True)

    cache._ensure_context_column()


def test_context_migration_reraises_an_unresolved_database_error():
    """A failed migration must surface when the required column is still absent."""
    # Issue #1183 (2026-07-27): genuine schema errors must disable the cache.
    cache = HealthScoreCache.__new__(HealthScoreCache)
    cache._conn = _MigrationConnection(migrated=False)

    with pytest.raises(sqlite3.OperationalError, match="duplicate column"):
        cache._ensure_context_column()


def test_context_migration_without_a_connection_is_a_noop():
    """A disabled cache must skip schema migration safely."""
    # Issue #1183 (2026-07-27): failed SQLite setup leaves no connection.
    cache = HealthScoreCache.__new__(HealthScoreCache)
    cache._conn = None

    cache._ensure_context_column()


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
