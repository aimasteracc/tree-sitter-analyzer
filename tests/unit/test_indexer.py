from __future__ import annotations

import errno
import os
import sqlite3
from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.indexer import walk_and_partition
from tree_sitter_analyzer.index_candidate_walker import walk_candidate_entries
from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest
from tree_sitter_analyzer.indexing_snapshot import build_index_candidate_snapshot


class _CacheRoot:
    def __init__(self, project_root: str) -> None:
        self.project_root = project_root


class _OsProxy:
    def __init__(self, **overrides) -> None:
        self._overrides = overrides

    def __getattr__(self, name):
        return self._overrides.get(name, getattr(os, name))


def test_language_scoped_partition_marks_other_language_skip_incomplete(
    tmp_path: Path,
) -> None:
    source = tmp_path / "client.js"
    source.write_text("const answer = 42;\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        language_filter="python",
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "javascript",
    )
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT PRIMARY KEY, content_hash TEXT, "
        "mtime_ns INTEGER, file_size INTEGER, extractor_version INTEGER)"
    )

    stats, candidates, count = walk_and_partition(
        _CacheRoot(str(tmp_path)),
        conn,
        max_files=10,
        force=False,
        activation_enabled=False,
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
        extractor_version=1,
        make_error_entry=lambda path, reason: {"file": path, "reason": reason},
        language_filter="python",
        candidate_snapshot=snapshot,
    )

    assert (stats["skipped"], stats["incomplete_skips"], candidates, count) == (
        1,
        1,
        [],
        1,
    )
    conn.close()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253: authoritative manifest")
def test_force_with_root_scandir_error_preserves_every_persisted_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # GH-1253: incomplete discovery must not authorize the destructive force clear.
    source = tmp_path / "app.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    conn = cache.get_conn()
    tables = (
        "ast_index",
        "ast_symbol_rows",
        "edges",
        "ast_index_snapshot_manifest",
    )

    def persisted_rows() -> dict[str, list[tuple[object, ...]]]:
        return {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table}")]
            for table in tables
        }

    before = persisted_rows()

    def fail_root_scandir(_root_fd):
        raise OSError("root enumeration denied")

    monkeypatch.setattr(os, "scandir", fail_root_scandir)
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda root: walk_candidate_entries(
            root,
            excluded_dir_names=frozenset(),
            entry_budget=10,
            path_byte_budget=10_000,
            discovery_seconds=10.0,
            budget_error="INDEX_CANDIDATE_DISCOVERY_BUDGET",
        ),
        language_fn=lambda path: "python" if path.endswith(".py") else None,
    )

    result = cache.index_project(
        max_files=10,
        force=True,
        exclude_patterns=frozenset(),
        candidate_snapshot=snapshot,
    )

    assert (snapshot.errors, snapshot.discovery_error) == (
        1,
        "INDEX_CANDIDATE_DISCOVERY_ERROR",
    )
    assert (result["verdict"], result["errors"], result["indexed"]) == (
        "WARN",
        1,
        0,
    )
    assert persisted_rows() == before
    cache.close()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_force_with_renamed_directory_swap_preserves_persisted_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # PR #1253 thread 3758928326: a regular-directory swap is incomplete discovery.
    import tree_sitter_analyzer.index_candidate_walker as walker

    package = tmp_path / "pkg"
    package.mkdir()
    source = package / "app.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    conn = cache.get_conn()
    tables = (
        "ast_index",
        "ast_symbol_rows",
        "edges",
        "ast_index_snapshot_manifest",
    )

    def persisted_rows() -> dict[str, list[tuple[object, ...]]]:
        return {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table}")]
            for table in tables
        }

    before = persisted_rows()
    real_open = walker.os.open
    swapped = False

    def swap_before_child_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "pkg" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            package.rename(tmp_path / "original-pkg")
            package.mkdir()
        return real_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(walker.os, "open", swap_before_child_open)
        snapshot = build_index_candidate_snapshot(
            str(tmp_path),
            max_files=10,
            exclude_patterns=frozenset(),
            walk_fn=lambda root: walk_candidate_entries(
                root,
                excluded_dir_names=frozenset(),
                entry_budget=10,
                path_byte_budget=10_000,
                discovery_seconds=10.0,
                budget_error="INDEX_CANDIDATE_DISCOVERY_BUDGET",
            ),
            language_fn=lambda path: "python" if path.endswith(".py") else None,
        )

    result = cache.index_project(
        max_files=10,
        force=True,
        exclude_patterns=frozenset(),
        candidate_snapshot=snapshot,
    )

    assert (swapped, snapshot.errors, snapshot.discovery_error) == (
        True,
        1,
        "INDEX_CANDIDATE_DISCOVERY_ERROR",
    )
    assert (result["verdict"], result["errors"], result["indexed"]) == (
        "WARN",
        1,
        0,
    )
    assert persisted_rows() == before
    cache.close()


def test_force_without_materialized_evidence_preserves_existing_cache(
    tmp_path: Path,
) -> None:
    # PR #1253 thread 3759852177: live-path evidence cannot authorize a clear.
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    before = [tuple(row) for row in cache.get_conn().execute("SELECT * FROM ast_index")]
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )

    result = cache.index_project(
        max_files=10,
        force=True,
        exclude_patterns=frozenset(),
        candidate_snapshot=snapshot,
    )

    after = [tuple(row) for row in cache.get_conn().execute("SELECT * FROM ast_index")]
    assert (result["verdict"], result["indexed"], after) == ("WARN", 0, before)
    cache.close()


def test_incomplete_cached_noop_clears_current_global_marker(tmp_path: Path) -> None:
    # PR #1253 thread 3760046643: no-op scope gaps still revoke certification.
    source = tmp_path / "client.js"
    source.write_text("const value = 1;\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    initial = cache.index_project(max_files=10)
    assert (initial["errors"], cache.call_graph_built()) == (0, True)

    result = cache.index_project(max_files=10, language_filter="python")

    assert (
        result["indexed"],
        result["incomplete_skips"],
        result["verdict"],
        cache.call_graph_built(),
    ) == (0, 1, "WARN", False)
    cache.close()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_owned_truncated_force_materialization_is_cleaned_before_abort(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3759852177: failed authorization cleans private bytes.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    (tmp_path / "a.py").write_text("a = 1\n")
    (tmp_path / "b.py").write_text("b = 1\n")
    cache = ASTCache(str(tmp_path))
    created: list[str] = []
    real_mkdtemp = materialization.tempfile.mkdtemp

    def remember_root(*args, **kwargs):
        root = real_mkdtemp(*args, **kwargs)
        created.append(root)
        return root

    monkeypatch.setattr(materialization.tempfile, "mkdtemp", remember_root)
    result = cache.index_project(max_files=1, force=True)

    assert (result["verdict"], len(created), os.path.exists(created[0])) == (
        "WARN",
        1,
        False,
    )
    cache.close()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_freezes_private_regular_file(tmp_path: Path) -> None:
    # PR #1253: destructive rebuild input is copied into private immutable leaves.
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
        index_candidate_snapshot_is_materialized,
        materialize_index_candidate_snapshot,
    )

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    frozen = materialize_index_candidate_snapshot(snapshot)
    try:
        leaf = Path(frozen.selected_entries[0].frozen_path or "")
        outcome = (
            index_candidate_snapshot_is_materialized(frozen),
            leaf.read_text(),
            leaf.stat().st_mode & 0o777,
        )
    finally:
        cleanup_index_candidate_snapshot(frozen)

    assert outcome == (True, "value = 1\n", 0o600)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_rejects_source_hash_race(tmp_path: Path) -> None:
    # PR #1253: bytes changed after discovery cannot authorize destructive clear.
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        index_candidate_snapshot_is_materialized,
        materialize_index_candidate_snapshot,
    )

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    source.write_text("value = 2\n")
    frozen = materialize_index_candidate_snapshot(snapshot)

    assert (
        frozen.frozen_root,
        frozen.frozen_error,
        index_candidate_snapshot_is_materialized(frozen),
    ) == (None, "INDEX_CANDIDATE_SOURCE_CHANGED", False)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
@pytest.mark.parametrize(
    "tamper",
    [
        "root_mode",
        "max_files",
        "missing_path",
        "leaf_mode",
        "extra_leaf",
        "missing_root",
    ],
)
def test_materialized_candidate_validator_rejects_tampering(
    tmp_path: Path, tamper: str
) -> None:
    # PR #1253: private frozen evidence must retain its exact filesystem shape.
    from dataclasses import replace

    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
        index_candidate_snapshot_is_materialized,
        materialize_index_candidate_snapshot,
    )

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    frozen = materialize_index_candidate_snapshot(snapshot)
    root = Path(frozen.frozen_root or "")
    leaf = Path(frozen.selected_entries[0].frozen_path or "")
    candidate = frozen
    if tamper == "root_mode":
        root.chmod(0o755)
    elif tamper == "max_files":
        candidate = replace(frozen, max_files=0)
    elif tamper == "missing_path":
        candidate = replace(
            frozen, entries=(replace(frozen.selected_entries[0], frozen_path=None),)
        )
    elif tamper == "leaf_mode":
        leaf.chmod(0o644)
    elif tamper == "extra_leaf":
        (root / "extra").write_text("x")
    else:
        cleanup_index_candidate_snapshot(frozen)
    result = index_candidate_snapshot_is_materialized(candidate)
    if tamper != "missing_root":
        cleanup_index_candidate_snapshot(frozen)

    assert result is False


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
@pytest.mark.parametrize(
    "failure",
    ["unsupported", "file_cap", "deadline", "missing_fingerprint", "byte_cap", "hash"],
)
def test_candidate_materialization_reports_fail_closed_reason(
    tmp_path: Path, monkeypatch, failure: str
) -> None:
    # PR #1253: every unsafe freeze boundary returns explicit incomplete evidence.
    from dataclasses import replace

    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    expected = ""
    if failure == "unsupported":
        monkeypatch.setattr(materialization.os, "name", "nt")
        expected = "SECURE_MATERIALIZATION_UNSUPPORTED"
    elif failure == "file_cap":
        snapshot = replace(snapshot, max_files=0)
        expected = "INDEX_CANDIDATE_MATERIALIZATION_BUDGET"
    elif failure == "deadline":
        from types import SimpleNamespace

        times = iter((0.0, 11.0))
        monkeypatch.setattr(
            materialization, "time", SimpleNamespace(monotonic=lambda: next(times))
        )
        expected = "INDEX_CANDIDATE_MATERIALIZATION_DEADLINE"
    elif failure == "missing_fingerprint":
        snapshot = replace(
            snapshot, entries=(replace(snapshot.selected_entries[0], fingerprint=None),)
        )
        expected = "INDEX_CANDIDATE_FROZEN_EVIDENCE_MISSING"
    elif failure == "byte_cap":
        monkeypatch.setattr(materialization, "_MAX_TOTAL_BYTES", 0)
        expected = "INDEX_CANDIDATE_MATERIALIZATION_BUDGET"
    else:
        fingerprint = replace(
            snapshot.selected_entries[0].fingerprint, content_hash="0" * 64
        )
        snapshot = replace(
            snapshot,
            entries=(replace(snapshot.selected_entries[0], fingerprint=fingerprint),),
        )
        expected = "INDEX_CANDIDATE_SOURCE_CHANGED"

    result = materialization.materialize_index_candidate_snapshot(snapshot)

    assert result.frozen_error == expected


def test_materialized_candidate_without_root_identity_is_not_current(tmp_path) -> None:
    # PR #1253 thread 3761703249: legacy/forged snapshots cannot authorize clear.
    from types import SimpleNamespace

    from tree_sitter_analyzer.indexing_candidate_materialization import (
        index_candidate_snapshot_root_is_current,
    )

    snapshot = SimpleNamespace(project_root=str(tmp_path), root_identity=None)

    assert index_candidate_snapshot_root_is_current(snapshot) is False


def test_materialized_candidate_missing_root_is_not_current(tmp_path) -> None:
    # PR #1253 thread 3761703249: a disappeared root fails closed.
    from types import SimpleNamespace

    from tree_sitter_analyzer.indexing_candidate_materialization import (
        index_candidate_snapshot_root_is_current,
    )

    missing = tmp_path / "missing"
    snapshot = SimpleNamespace(
        project_root=str(missing),
        root_identity=(str(missing.resolve()), 1, 1),
    )

    assert index_candidate_snapshot_root_is_current(snapshot) is False


@pytest.mark.skipif(
    os.name != "posix", reason="GH-1253: dir_fd private writer is POSIX-only"
)
def test_private_candidate_write_rejects_zero_progress(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253: a stalled private write cannot publish a frozen source.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    root_fd = os.open(tmp_path, os.O_RDONLY)
    monkeypatch.setattr(materialization.os, "write", lambda *_args: 0)
    try:
        with pytest.raises(OSError, match="no write progress"):
            materialization._write_private_file(root_fd, "leaf", b"x")
    finally:
        os.close(root_fd)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_materialized_candidate_rejects_foreign_owner(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253: caller-owned paths cannot masquerade as process-private evidence.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    frozen = materialization.materialize_index_candidate_snapshot(snapshot)
    real_uid = os.getuid()
    monkeypatch.setattr(materialization.os, "getuid", lambda: real_uid + 1)
    try:
        result = materialization.index_candidate_snapshot_is_materialized(frozen)
    finally:
        materialization.cleanup_index_candidate_snapshot(frozen)

    assert result is False


def test_candidate_cleanup_without_owned_root_is_noop(tmp_path: Path) -> None:
    # PR #1253: an unfrozen snapshot never authorizes recursive cleanup.
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
    )
    cleanup_index_candidate_snapshot(snapshot)

    assert snapshot.frozen_root is None


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_rejects_nonfile_capture(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253: only captured regular-file bytes may enter the private epoch.
    from types import SimpleNamespace

    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    monkeypatch.setattr(
        materialization,
        "safe_workspace_path",
        lambda *_args, **_kwargs: SimpleNamespace(kind="missing", data=None),
    )

    result = materialization.materialize_index_candidate_snapshot(snapshot)

    assert result.frozen_error == "INDEX_CANDIDATE_SOURCE_CHANGED"


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_reports_cleanup_failure(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: cleanup cannot mask the primary freeze failure.
    from dataclasses import replace

    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    snapshot = replace(
        snapshot, entries=(replace(snapshot.selected_entries[0], fingerprint=None),)
    )
    monkeypatch.setattr(
        materialization.os,
        "rmdir",
        lambda *_args: (_ for _ in ()).throw(OSError("cleanup denied")),
    )

    result = materialization.materialize_index_candidate_snapshot(snapshot)

    assert result.frozen_error == "INDEX_CANDIDATE_FROZEN_EVIDENCE_MISSING"


@pytest.mark.skipif(
    os.name != "posix", reason="GH-1253: dir_fd private writer is POSIX-only"
)
def test_private_candidate_write_works_without_nofollow_flag(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253: the portable writer retains exclusive-create semantics.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    class OsProxy:
        def __getattr__(self, name):
            if name == "O_NOFOLLOW":
                raise AttributeError(name)
            return getattr(os, name)

    monkeypatch.setattr(materialization, "os", OsProxy())
    root_fd = os.open(tmp_path, os.O_RDONLY)
    try:
        materialization._write_private_file(root_fd, "leaf", b"x")
    finally:
        os.close(root_fd)

    assert (tmp_path / "leaf").read_bytes() == b"x"


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_owned_cleanup_failure_preserves_success_and_attempts_every_leaf(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: cleanup is bounded telemetry, never authority.
    import shutil

    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    attempted: list[str] = []
    created: list[str] = []
    real_unlink = materialization.os.unlink
    real_mkdtemp = materialization.tempfile.mkdtemp

    def record_root(*args, **kwargs):
        root = real_mkdtemp(*args, **kwargs)
        created.append(root)
        return root

    def record_unlink(path, *args, **kwargs):
        attempted.append(str(path))
        return real_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(materialization.tempfile, "mkdtemp", record_root)
        patcher.setattr(materialization.os, "unlink", record_unlink)
        patcher.setattr(
            materialization.os,
            "rmdir",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("busy")),
        )
        result = cache.index_project(max_files=10, force=True, workers=0)
    cache.close()
    for root in created:
        shutil.rmtree(root, ignore_errors=True)

    assert (result["indexed"], result["errors"]) == (2, 0)
    assert result["cleanup_warning"] == "INDEX_CANDIDATE_CLEANUP_FAILED: busy"
    assert attempted == ["candidate-00000000", "candidate-00000001"]


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_force_preflight_hash_change_preserves_existing_rows(tmp_path: Path) -> None:
    # PR #1253 thread 3760428948: every frozen leaf is hashed before force clear.
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    before = [tuple(row) for row in cache.get_conn().execute("SELECT * FROM ast_index")]
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    frozen_path = Path(snapshot.selected_entries[0].frozen_path or "")
    frozen_path.write_text("value = 2\n", encoding="utf-8")
    try:
        result = cache.index_project(
            max_files=10,
            force=True,
            workers=0,
            exclude_patterns=frozenset(),
            candidate_snapshot=snapshot,
        )
        after = [
            tuple(row) for row in cache.get_conn().execute("SELECT * FROM ast_index")
        ]
    finally:
        cleanup_index_candidate_snapshot(snapshot)
        cache.close()

    assert (result["verdict"], result["indexed"], after) == ("WARN", 0, before)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_certified_frozen_reader_rejects_original_size_mismatch(tmp_path: Path) -> None:
    # PR #1253 thread 3760428948: original byte size is part of replay authority.
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        read_frozen_candidate,
    )

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    fingerprint = snapshot.selected_entries[0].fingerprint
    if fingerprint is None:
        pytest.fail("selected source fingerprint was not captured")
    source.write_text("x", encoding="utf-8")

    with pytest.raises(OSError, match="source size changed"):
        read_frozen_candidate(str(source), expected=fingerprint)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_certified_frozen_reader_checks_deadline_before_each_read(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428948: elapsed clocks stop replay before another read.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "candidate"
    source.write_bytes(b"x")
    from types import SimpleNamespace

    ticks = iter((0.0, 2.0))
    monkeypatch.setattr(
        materialization, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )

    with pytest.raises(OSError, match="read deadline exceeded"):
        materialization.read_frozen_candidate(str(source), deadline=1.0)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_certified_frozen_reader_checks_deadline_after_each_read(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428948: a stalled read cannot publish late bytes.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "candidate"
    source.write_bytes(b"x")
    from types import SimpleNamespace

    ticks = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(
        materialization, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )

    with pytest.raises(OSError, match="read deadline exceeded"):
        materialization.read_frozen_candidate(str(source), deadline=1.0)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_is_idempotent_after_root_disappears(tmp_path: Path) -> None:
    # PR #1253 thread 3760428941: a released root is an idempotent no-op.
    from dataclasses import replace

    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
    )
    missing = replace(snapshot, frozen_root=str(tmp_path / "gone"))

    assert cleanup_index_candidate_snapshot(missing) is None


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_suppresses_root_open_failure(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: root-open errors become bounded telemetry.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    root = tmp_path / "candidate-root"
    root.mkdir()
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
    )
    from dataclasses import replace

    frozen = replace(snapshot, frozen_root=str(root))
    monkeypatch.setattr(
        materialization,
        "os",
        _OsProxy(
            open=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                PermissionError("denied")
            )
        ),
    )

    warning = materialization.cleanup_index_candidate_snapshot(frozen)

    assert warning == "INDEX_CANDIDATE_CLEANUP_FAILED: denied"


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_tolerates_leaf_already_unlinked(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: every missing leaf remains an idempotent success.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    monkeypatch.setattr(
        materialization,
        "os",
        _OsProxy(
            unlink=lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError())
        ),
    )

    warning = materialization.cleanup_index_candidate_snapshot(frozen)
    assert warning == (
        "INDEX_CANDIDATE_CLEANUP_FAILED: "
        + str(
            OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY), frozen.frozen_root)
        )
    )
    import shutil

    shutil.rmtree(frozen.frozen_root or "")


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_chmods_then_retries_denied_unlink(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: permission denial gets one secure chmod retry.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    real_unlink = materialization.os.unlink
    calls = 0

    def deny_once(path, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("readonly")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(materialization, "os", _OsProxy(unlink=deny_once))

    assert (materialization.cleanup_index_candidate_snapshot(frozen), calls) == (
        None,
        2,
    )


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_tolerates_leaf_disappearing_during_retry(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: a retry race cannot become a primary failure.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    outcomes = iter((PermissionError("readonly"), FileNotFoundError()))

    def fail_unlink(*_args, **_kwargs):
        raise next(outcomes)

    monkeypatch.setattr(materialization, "os", _OsProxy(unlink=fail_unlink))

    warning = materialization.cleanup_index_candidate_snapshot(frozen)
    assert warning == (
        "INDEX_CANDIDATE_CLEANUP_FAILED: "
        + str(
            OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY), frozen.frozen_root)
        )
    )
    import shutil

    shutil.rmtree(frozen.frozen_root or "")


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_reports_failed_chmod_retry(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: exhausted retry is warning-only telemetry.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    monkeypatch.setattr(
        materialization,
        "os",
        _OsProxy(
            unlink=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                PermissionError("readonly")
            ),
            chmod=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                PermissionError("still denied")
            ),
        ),
    )

    warning = materialization.cleanup_index_candidate_snapshot(frozen)

    assert warning == (
        "INDEX_CANDIDATE_CLEANUP_FAILED: "
        + str(
            OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY), frozen.frozen_root)
        )
    )
    import shutil

    shutil.rmtree(frozen.frozen_root or "")


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_reports_close_failure(tmp_path: Path, monkeypatch) -> None:
    # PR #1253 thread 3760428941: descriptor-close errors never escape cleanup.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
        materialize=True,
    )
    real_close = materialization.os.close

    def close_then_report(fd):
        real_close(fd)
        raise OSError("close failed")

    monkeypatch.setattr(materialization, "os", _OsProxy(close=close_then_report))

    warning = materialization.cleanup_index_candidate_snapshot(snapshot)

    assert warning == "INDEX_CANDIDATE_CLEANUP_FAILED: close failed"


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_tolerates_rmtree_missing_race(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: missing-at-rmtree remains successful cleanup.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
        materialize=True,
    )
    root = snapshot.frozen_root or ""
    monkeypatch.setattr(
        materialization.os,
        "rmdir",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    try:
        warning = materialization.cleanup_index_candidate_snapshot(snapshot)
    finally:
        try:
            os.rmdir(root)
        except FileNotFoundError:
            pass

    assert warning is None


def test_release_helper_suppresses_unexpected_cleanup_exception(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: final ownership boundary preserves primary output.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
    )
    monkeypatch.setattr(
        materialization,
        "cleanup_index_candidate_snapshot",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )
    result = {"success": True}

    materialization.release_index_candidate_snapshot(snapshot, result)

    assert result == {
        "success": True,
        "cleanup_warning": "INDEX_CANDIDATE_CLEANUP_FAILED: unexpected",
    }


def test_parse_and_write_returns_exact_parser_failure():
    # PR #1253: parse failures never enter any index writer transaction.
    from types import SimpleNamespace

    from tree_sitter_analyzer.cache.indexer import parse_and_write

    cache = SimpleNamespace(
        parser=SimpleNamespace(
            parse_file=lambda *_args: SimpleNamespace(
                success=False, error_message="invalid source"
            )
        )
    )

    result = parse_and_write(
        cache,
        None,
        "/project/bad.py",
        "bad.py",
        "python",
        None,
        "bad source",
        "hash",
        14,
    )

    assert result == {
        "file": "bad.py",
        "status": "error",
        "reason": "invalid source",
    }


def test_candidate_less_windows_scope_restores_only_operational_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1253: Windows keeps legacy call-graph availability while the separate
    # authoritative manifest remains unsupported without descriptor snapshots.
    import tree_sitter_analyzer.cache.indexer as indexer

    (tmp_path / "app.py").write_text("def app(): pass\n", encoding="utf-8")
    monkeypatch.setattr(indexer, "os", _OsProxy(name="nt"))
    monkeypatch.setattr(
        indexer,
        "walk_index_candidate_entries",
        lambda *_args, **_kwargs: pytest.fail("secure candidate walk attempted"),
    )

    result = indexer._bounded_selected_supported_paths(
        str(tmp_path), 10, None, frozenset()
    )

    assert result == {"app.py"}


def test_candidate_less_windows_scope_matches_legacy_directory_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1253: operational completeness excludes hidden/cache directories and
    # preserves the legacy source-looking symlink-directory selection policy.
    import tree_sitter_analyzer.cache.indexer as indexer

    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "ignored.py").write_text("ignored = 1\n")
    (tmp_path / "visible").mkdir()
    (tmp_path / "visible" / "kept.py").write_text("kept = 1\n")
    (tmp_path / "target").mkdir()
    (tmp_path / "module.py").symlink_to(tmp_path / "target", target_is_directory=True)
    (tmp_path / "alias").symlink_to(tmp_path / "target", target_is_directory=True)
    monkeypatch.setattr(indexer, "os", _OsProxy(name="nt"))

    result = indexer._bounded_selected_supported_paths(
        str(tmp_path), 10, None, frozenset()
    )

    assert result == {"module.py", "visible/kept.py"}


def test_candidate_less_windows_scope_fails_closed_on_walk_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1253: operational path equality cannot be issued from a partial walk.
    import tree_sitter_analyzer.cache.indexer as indexer

    class WalkErrorProxy(_OsProxy):
        def walk(self, root, onerror=None):
            assert onerror is not None
            onerror(OSError("enumeration denied"))
            return iter(())

    monkeypatch.setattr(indexer, "os", WalkErrorProxy(name="nt"))

    result = indexer._bounded_selected_supported_paths(
        str(tmp_path), 10, None, frozenset()
    )

    assert result is None


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_rejects_path_identity_change_after_fd_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    captured = Path(frozen.frozen_root or "")
    real_stat = materialization.os.stat

    def replaced_stat(path, *args, **kwargs):
        observed = real_stat(path, *args, **kwargs)
        if os.fspath(path) == os.fspath(captured):
            from types import SimpleNamespace

            return SimpleNamespace(st_dev=observed.st_dev, st_ino=observed.st_ino + 1)
        return observed

    monkeypatch.setattr(materialization.os, "stat", replaced_stat)
    warning = materialization.cleanup_index_candidate_snapshot(frozen)
    assert captured.exists() is True
    assert warning == (
        "INDEX_CANDIDATE_CLEANUP_FAILED: INDEX_CANDIDATE_CLEANUP_ROOT_REPLACED"
    )
    import shutil

    shutil.rmtree(captured)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_chmod_failure_removes_unowned_root(
    tmp_path: Path, monkeypatch
) -> None:
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    roots: list[str] = []
    real_mkdtemp = materialization.tempfile.mkdtemp

    def record_root(*args, **kwargs):
        root = real_mkdtemp(*args, **kwargs)
        roots.append(root)
        return root

    monkeypatch.setattr(materialization.tempfile, "mkdtemp", record_root)
    monkeypatch.setattr(
        materialization.os,
        "chmod",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("chmod denied")),
    )
    result = materialization.materialize_index_candidate_snapshot(snapshot)
    assert result.frozen_error == "chmod denied"
    assert roots and not Path(roots[0]).exists()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_fstat_failure_is_warning_and_closes_fd(
    tmp_path: Path, monkeypatch
) -> None:
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    real_fstat = materialization.os.fstat
    real_open = materialization.os.open
    opened: list[int] = []

    def record_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(materialization.os, "open", record_open)
    monkeypatch.setattr(
        materialization.os,
        "fstat",
        lambda _fd: (_ for _ in ()).throw(OSError("fstat denied")),
    )
    warning = materialization.cleanup_index_candidate_snapshot(frozen)
    monkeypatch.setattr(materialization.os, "fstat", real_fstat)
    assert warning == "INDEX_CANDIDATE_CLEANUP_FAILED: fstat denied"
    assert len(opened) == 1
    with pytest.raises(OSError):
        real_fstat(opened[0])
    import shutil

    shutil.rmtree(frozen.frozen_root or "")


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_fstat_failure_closes_fd_and_root(
    tmp_path: Path, monkeypatch
) -> None:
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    opened: list[int] = []
    roots: list[str] = []
    real_open = materialization.os.open
    real_mkdtemp = materialization.tempfile.mkdtemp

    def record_root(*args, **kwargs):
        root = real_mkdtemp(*args, **kwargs)
        roots.append(root)
        return root

    def record_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(materialization.tempfile, "mkdtemp", record_root)
    monkeypatch.setattr(materialization.os, "open", record_open)
    real_fstat = materialization.os.fstat
    calls = 0

    def fail_first_fstat(fd):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("denied")
        return real_fstat(fd)

    monkeypatch.setattr(materialization.os, "fstat", fail_first_fstat)
    result = materialization.materialize_index_candidate_snapshot(snapshot)
    assert result.frozen_error == "denied"
    assert roots and not Path(roots[0]).exists()
    with pytest.raises(OSError):
        os.fstat(opened[0])


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_never_recursively_removes_post_check_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    import shutil

    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    captured = Path(frozen.frozen_root or "")
    displaced = captured.with_name(captured.name + "-displaced")
    real_rmdir = materialization.os.rmdir

    def swap_then_rmdir(path):
        captured.rename(displaced)
        captured.mkdir()
        (captured / "replacement").write_text("keep", encoding="utf-8")
        return real_rmdir(path)

    monkeypatch.setattr(materialization.os, "rmdir", swap_then_rmdir)
    warning = materialization.cleanup_index_candidate_snapshot(frozen)
    assert (captured / "replacement").read_text(encoding="utf-8") == "keep"
    assert warning is not None
    monkeypatch.setattr(materialization.os, "rmdir", real_rmdir)
    shutil.rmtree(captured)
    shutil.rmtree(displaced)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_keeps_replacement_root(tmp_path: Path) -> None:
    # PR #1253 thread 3763124090: cleanup authority belongs to captured identity.
    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    captured = Path(frozen.frozen_root or "")
    displaced = captured.with_name(captured.name + "-displaced")
    captured.rename(displaced)
    captured.mkdir()
    sentinel = captured / "replacement"
    sentinel.write_text("keep", encoding="utf-8")

    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    warning = cleanup_index_candidate_snapshot(frozen)
    observed = (sentinel.read_text(encoding="utf-8"), displaced.exists())
    import shutil

    shutil.rmtree(captured)
    shutil.rmtree(displaced)

    assert observed == ("keep", True)
    assert (
        warning
        == "INDEX_CANDIDATE_CLEANUP_FAILED: INDEX_CANDIDATE_CLEANUP_ROOT_REPLACED"
    )
