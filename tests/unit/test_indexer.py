from __future__ import annotations

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
    # PR #1253: failed private cleanup remains explicit incomplete evidence.
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
        materialization.shutil,
        "rmtree",
        lambda *_args: (_ for _ in ()).throw(OSError("cleanup denied")),
    )

    result = materialization.materialize_index_candidate_snapshot(snapshot)

    assert result.frozen_error == "INDEX_CANDIDATE_CLEANUP_FAILED: cleanup denied"


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
