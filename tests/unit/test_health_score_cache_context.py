"""Metadata and Git-context tests for the persistent health-score cache."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tree_sitter_analyzer.health_scorer import HealthScorer
from tree_sitter_analyzer.registry import health_score_cache as cache_module
from tree_sitter_analyzer.registry.health_score_cache import (
    HealthScoreCache,
    _coverage_metadata_signature,
    _find_git_dir,
    _git_context_parts,
    _metadata_signature,
    _read_small_regular_text,
)


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


def test_coverage_loader_indexes_windows_report_paths(tmp_path, monkeypatch):
    """Windows report keys must enter the case-insensitive lookup index."""
    # PR #1184 Codex review (2026-07-27): Windows normalization stays O(C), once.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "coverage.json").write_text(
        '{"files":{"C:\\\\Workspace\\\\src\\\\main.py":'
        '{"summary":{"percent_covered":72.5}}}}',
        encoding="utf-8",
    )
    scorer = HealthScorer()

    scorer._load_coverage_data()

    assert scorer._windows_coverage_cache == {"c:/workspace/src/main.py": 72.5}


def test_windows_coverage_lookup_casefolds_suffix_once():
    """A Windows source may match a shorter report path by folded suffix."""
    # PR #1184 Codex review (2026-07-27): suffix fallback uses the built index.
    scorer = HealthScorer()
    scorer._coverage_cache = {"SRC/Foo.py": 84.0}

    assert scorer._score_coverage(r"C:\workspace\src\foo.py") == 84.0


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


def test_small_metadata_reader_reads_short_chunks_through_eof(tmp_path, monkeypatch):
    """Short descriptor reads must not truncate a valid symbolic ref."""
    # PR #1184 Codex review (2026-07-27): one os.read call could cache a
    # partial but valid ref and then miss changes to the real branch.
    metadata = tmp_path / "HEAD"
    metadata.write_text("ref: refs/heads/main\n", encoding="utf-8")
    chunks = iter((b"ref: refs/heads/ma", b"in\n", b""))
    monkeypatch.setattr(
        cache_module.os, "read", lambda _descriptor, _size: next(chunks)
    )
    assert _read_small_regular_text(metadata) == "ref: refs/heads/main"


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


@pytest.mark.parametrize("namespace", ["bisect", "rewritten", "worktree"])
def test_git_context_reads_per_worktree_ref_namespaces(tmp_path, namespace):
    """Per-worktree refs must be fingerprinted below the worktree Git dir."""
    # PR #1184 Codex review (2026-07-27): common-dir lookup stayed permanently missing.
    common_dir = tmp_path / "common"
    git_dir = common_dir / "worktrees" / "feature"
    git_dir.mkdir(parents=True)
    (git_dir / "commondir").write_text("../..\n", encoding="utf-8")
    ref_name = f"refs/{namespace}/current"
    (git_dir / "HEAD").write_text(f"ref: {ref_name}\n", encoding="utf-8")
    worktree_ref = git_dir / ref_name
    worktree_ref.parent.mkdir(parents=True)
    worktree_ref.write_text("abc123\n", encoding="utf-8")
    original_signature = _metadata_signature(worktree_ref)

    first = _git_context_parts(git_dir)
    worktree_ref.write_text("def456-expanded\n", encoding="utf-8")
    second = _git_context_parts(git_dir)

    assert (first[-1], first == second) == (original_signature, False)


def test_git_context_follows_a_symbolic_ref_chain(tmp_path):
    """Every loose ref in a recursive symbolic chain must be fingerprinted."""
    # PR #1184 Codex review (2026-07-27): Git dereferences symbolic refs by default.
    git_dir = tmp_path / ".git"
    current = git_dir / "refs" / "heads" / "current"
    terminal = git_dir / "refs" / "heads" / "terminal"
    current.parent.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/current\n", encoding="utf-8")
    current.write_text("ref: refs/heads/terminal\n", encoding="utf-8")
    terminal.write_text("abc123\n", encoding="utf-8")
    terminal_signature = _metadata_signature(terminal)

    first = _git_context_parts(git_dir)
    terminal.write_text("def456-expanded\n", encoding="utf-8")
    second = _git_context_parts(git_dir)

    assert first[-2:] == [_metadata_signature(current), terminal_signature]
    assert first != second


def test_git_context_marks_an_invalid_symbolic_ref(tmp_path):
    """A symbolic ref outside ``refs/`` must not escape the Git directory."""
    # PR #1184 Codex review (2026-07-27): ref traversal stays bounded to Git refs.
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: ../outside\n", encoding="utf-8")

    assert _git_context_parts(git_dir)[-1] == "git:invalid-symbolic-ref"


def test_git_context_marks_a_symbolic_ref_loop(tmp_path):
    """A recursive symbolic-ref cycle must terminate with an explicit marker."""
    # PR #1184 Codex review (2026-07-27): malformed ref chains cannot loop.
    git_dir = tmp_path / ".git"
    first = git_dir / "refs" / "heads" / "first"
    second = git_dir / "refs" / "heads" / "second"
    first.parent.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/first\n", encoding="utf-8")
    first.write_text("ref: refs/heads/second\n", encoding="utf-8")
    second.write_text("ref: refs/heads/first\n", encoding="utf-8")

    assert _git_context_parts(git_dir)[-1] == "git:symbolic-ref-loop"


def test_git_context_marks_a_missing_symbolic_ref(tmp_path):
    """A packed-only ref must retain its loose-ref missing signature."""
    # PR #1184 Codex review (2026-07-27): packed-refs is fingerprinted separately.
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/packed\n", encoding="utf-8")

    expected = f"{(git_dir / 'refs' / 'heads' / 'packed').absolute()}:missing"
    assert _git_context_parts(git_dir)[-1] == expected


def test_git_context_bounds_a_deep_symbolic_ref_chain(tmp_path):
    """An excessive symbolic-ref chain must terminate at the configured cap."""
    # PR #1184 Codex review (2026-07-27): recursive dereferencing needs a bound.
    git_dir = tmp_path / ".git"
    refs = git_dir / "refs" / "heads"
    refs.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/ref0\n", encoding="utf-8")
    for index in range(cache_module._MAX_SYMBOLIC_REF_DEPTH):
        (refs / f"ref{index}").write_text(
            f"ref: refs/heads/ref{index + 1}\n",
            encoding="utf-8",
        )

    assert _git_context_parts(git_dir)[-1] == "git:symbolic-ref-depth"


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
