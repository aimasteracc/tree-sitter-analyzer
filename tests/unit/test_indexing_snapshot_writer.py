from __future__ import annotations

import os
import sqlite3
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.indexer import walk_and_partition
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
    IndexFileFingerprint,
    IndexSnapshotEntry,
    build_index_candidate_snapshot,
)

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


def _python_language(path: str) -> str | None:
    return "python" if path.endswith(".py") else None


class _CacheRoot:
    def __init__(self, project_root: str) -> None:
        self.project_root = project_root


def _index_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index ("
        "file_path TEXT PRIMARY KEY, content_hash TEXT, mtime_ns INTEGER, "
        "file_size INTEGER, extractor_version INTEGER)"
    )
    return conn


def _partition(snapshot: IndexCandidateSnapshot, conn: sqlite3.Connection):
    return walk_and_partition(
        _CacheRoot(snapshot.project_root),
        conn,
        max_files=snapshot.max_files,
        force=False,
        activation_enabled=False,
        walk_fn=lambda _root: (),
        language_fn=_python_language,
        extractor_version=1,
        make_error_entry=lambda path, reason: {
            "file": path,
            "status": "error",
            "reason": reason,
        },
        candidate_snapshot=snapshot,
    )


def test_ast_cache_revalidates_each_result_at_write_point(tmp_path):
    from tree_sitter_analyzer.cache import indexer

    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("a = 1\n")
    second.write_text("b = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(first), str(second)),
        language_fn=_python_language,
    )
    cache = ASTCache(str(tmp_path))
    real_insert = indexer.insert_index_row

    def insert_first_then_mutate_second(*args, **kwargs):
        real_insert(*args, **kwargs)
        result = args[2]
        if result["rel_path"] == "a.py":
            second.write_text("b = 200\n")

    try:
        with patch.object(
            indexer,
            "insert_index_row",
            side_effect=insert_first_then_mutate_second,
        ):
            result = cache.index_project(
                max_files=10,
                workers=0,
                exclude_patterns=frozenset(),
                candidate_snapshot=snapshot,
            )
        rows = [
            row["file_path"]
            for row in cache.get_conn()
            .execute("SELECT file_path FROM ast_index ORDER BY file_path")
            .fetchall()
        ]
    finally:
        cache.close()

    assert (rows, result["processed"], result["changed_during_run_files"]) == (
        ["a.py"],
        1,
        ["b.py"],
    )


def test_partial_force_snapshot_does_not_fallback_to_existing_edges(tmp_path):
    from tree_sitter_analyzer.cache import extraction

    changed = tmp_path / "a.py"
    stable = tmp_path / "b.py"
    changed.write_text("a = 1\n")
    stable.write_text("def caller():\n    return caller()\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(changed), str(stable)),
        language_fn=_python_language,
    )
    cache = ASTCache(str(tmp_path))
    real_worker = extraction._worker_index_file

    def mutate_first_after_worker(args):
        result = real_worker(args)
        if result["rel_path"] == "a.py":
            changed.write_text("a = 200\n")
        return result

    try:
        with patch.object(
            extraction,
            "_worker_index_file",
            side_effect=mutate_first_after_worker,
        ):
            cache.index_project(
                max_files=10,
                workers=0,
                force=True,
                exclude_patterns=frozenset(),
                candidate_snapshot=snapshot,
            )
        has_edges = cache.has_call_edges()
        graph_built = cache.call_graph_built()
    finally:
        cache.close()

    assert (has_edges, graph_built) == (True, False)


def test_ast_partition_rejects_selected_entry_without_metadata(tmp_path):
    snapshot = IndexCandidateSnapshot(
        project_root=os.path.abspath(tmp_path),
        max_files=10,
        entries=(
            IndexSnapshotEntry(
                abs_path=str(tmp_path / "bad.py"),
                rel_path="bad.py",
                language="python",
                decision="selected",
            ),
        ),
        present_paths=frozenset({"bad.py"}),
        discovered=1,
        selected=1,
        excluded=0,
        skipped=0,
        errors=0,
        limited=0,
    )

    with pytest.raises(ValueError, match="lacks metadata"):
        _partition(snapshot, _index_conn())


def test_ast_partition_rejects_selected_entry_without_language(tmp_path):
    # PR #1172 review 2026-07-27: forged snapshots must retain parse metadata.
    path = tmp_path / "bad.py"
    path.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
    )
    malformed = replace(
        snapshot,
        entries=(replace(snapshot.selected_entries[0], language=None),),
    )

    with pytest.raises(ValueError, match="lacks language"):
        _partition(malformed, _index_conn())


def test_supported_symlink_is_candidate_error_and_never_selected(tmp_path):
    # PR #1253: writer selection matches the status oracle's no-symlink policy.
    target = tmp_path / "target.py"
    target.write_text("value = 1\n")
    linked = tmp_path / "linked.py"
    try:
        linked.symlink_to(target)
    except OSError:
        pytest.skip("GH-1253: symlink creation unavailable")

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: [str(linked)],
        language_fn=_python_language,
    )

    assert (
        snapshot.selected,
        snapshot.errors,
        snapshot.entries[0].decision,
        snapshot.entries[0].reason,
    ) == (0, 1, "error", "supported source is symlinked or non-regular")


def test_validate_selected_symlink_is_rejected(tmp_path):
    # PR #1253: forged selected symlink candidates cannot reach certification.
    from tree_sitter_analyzer.indexing_snapshot import validate_index_candidate_snapshot

    target = tmp_path / "target.py"
    target.write_text("x = 1")
    linked = tmp_path / "linked.py"
    try:
        linked.symlink_to(target)
    except OSError:
        pytest.skip("GH-1253: symlink creation unavailable")
    changed_fingerprint = (
        build_index_candidate_snapshot(
            str(tmp_path),
            max_files=1,
            exclude_patterns=frozenset(),
            walk_fn=lambda _root: [str(target)],
            language_fn=_python_language,
        )
        .selected_entries[0]
        .fingerprint
    )
    entry = IndexSnapshotEntry(
        str(linked),
        "linked.py",
        "python",
        "selected",
        fingerprint=changed_fingerprint,
    )
    snapshot = IndexCandidateSnapshot(
        str(tmp_path), 1, (entry,), frozenset({"linked.py"}), 1, 1, 0, 0, 0, 0
    )
    assert changed_fingerprint == IndexFileFingerprint.from_stat(target.stat())
    with pytest.raises(ValueError, match="symlinked or non-regular"):
        validate_index_candidate_snapshot(str(tmp_path), 1, snapshot)


def test_validate_selected_stat_error_is_rejected(tmp_path, monkeypatch):
    # PR #1253: unreadable selected candidates fail validation explicitly.
    import tree_sitter_analyzer.indexing_snapshot as snapshot_module

    source = tmp_path / "sample.py"
    source.write_text("x = 1")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=1,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: [str(source)],
        language_fn=_python_language,
    )
    original_stat = snapshot_module.os.stat

    def denied(path, *args, **kwargs):
        if os.fspath(path) == str(source) and kwargs.get("follow_symlinks") is False:
            raise PermissionError
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(snapshot_module.os, "stat", denied)
    with pytest.raises(ValueError, match="selected candidate is unreadable"):
        snapshot_module.validate_index_candidate_snapshot(str(tmp_path), 1, snapshot)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_supported_suffix_directory_symlink_is_writer_error(tmp_path):
    # PR #1253 review thread 3878: os.walk exposes directory symlinks separately.
    from tree_sitter_analyzer.cache.indexer import _walk_source_files

    target = tmp_path / "vendor"
    target.mkdir()
    linked = tmp_path / "vendor.py"
    linked.symlink_to(target, target_is_directory=True)
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=_walk_source_files,
        language_fn=_python_language,
    )

    assert (snapshot.selected, snapshot.errors, snapshot.entries[0].decision) == (
        0,
        1,
        "error",
    )


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_literal_backslash_supported_path_is_writer_error(tmp_path):
    # PR #1253 review thread 1266: POSIX backslashes are filename bytes, not separators.
    source = tmp_path / "pkg\\sample.py"
    source.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=_python_language,
    )

    assert (snapshot.selected, snapshot.errors, snapshot.entries[0].rel_path) == (
        0,
        1,
        "pkg\\sample.py",
    )


def test_windows_candidate_path_normalization_is_platform_aware(tmp_path, monkeypatch):
    # PR #1253 review thread 1266: Windows separators remain canonical slashes.
    import tree_sitter_analyzer.indexing_snapshot as snapshot_module

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")

    fake_path = SimpleNamespace(
        abspath=os.path.abspath,
        realpath=os.path.realpath,
        relpath=lambda *_args: "pkg\\sample.py",
    )
    monkeypatch.setattr(
        snapshot_module, "os", SimpleNamespace(name="nt", path=fake_path, stat=os.stat)
    )
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=_python_language,
    )

    assert snapshot.entries[0].rel_path == "pkg/sample.py"


def test_windows_snapshot_validation_normalizes_expected_path(tmp_path, monkeypatch):
    # PR #1253 review thread 1266: validation uses the same Windows-only rule.
    import tree_sitter_analyzer.indexing_snapshot as snapshot_module

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    fingerprint = IndexFileFingerprint.from_stat(source.stat())
    entry = IndexSnapshotEntry(
        str(source), "pkg/sample.py", "python", "selected", fingerprint=fingerprint
    )
    snapshot = IndexCandidateSnapshot(
        os.path.abspath(tmp_path),
        10,
        (entry,),
        frozenset({"pkg/sample.py"}),
        1,
        1,
        0,
        0,
        0,
        0,
    )

    fake_path = SimpleNamespace(
        abspath=os.path.abspath,
        realpath=os.path.realpath,
        relpath=lambda *_args: "pkg\\sample.py",
    )
    monkeypatch.setattr(
        snapshot_module, "os", SimpleNamespace(name="nt", path=fake_path, stat=os.stat)
    )

    snapshot_module.validate_index_candidate_snapshot(str(tmp_path), 10, snapshot)


def test_module_exports_exact_focused_surface() -> None:
    from tree_sitter_analyzer import indexing_snapshot_writer

    assert indexing_snapshot_writer.__all__ == [
        "changed_since_snapshot",
        "validate_index_candidate_snapshot",
    ]


def test_partial_projection_forces_full_file_repair_and_callee_rebind(tmp_path):
    # PR #1253 thread 3756769301: partial ordinary rows disable cache fast paths.
    source = tmp_path / "app.py"
    source.write_text(
        "def target():\n    return 1\ndef caller():\n    return target()\n"
    )
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    conn = cache.get_conn()
    conn.execute("DELETE FROM ast_symbol_rows WHERE name='caller'")
    conn.execute(
        "INSERT OR REPLACE INTO ast_symbol_activation "
        "(symbol_id, file_path, computed_at, git_state) VALUES (999, 'orphan.py', 1, 'clean')"
    )
    conn.commit()
    cache.close()

    cache = ASTCache(str(tmp_path))
    conn = cache.get_conn()
    constructor_rows = [
        tuple(row)
        for row in conn.execute("SELECT id, name FROM ast_symbol_rows ORDER BY id")
    ]
    result = cache.index_project(workers=1)
    repaired_rows = [
        tuple(row)
        for row in conn.execute("SELECT id, name FROM ast_symbol_rows ORDER BY id")
    ]
    fts_rowids = [
        row[0]
        for row in conn.execute("SELECT rowid FROM ast_symbols_fts ORDER BY rowid")
    ]
    activation_paths = [
        row[0]
        for row in conn.execute(
            "SELECT file_path FROM ast_symbol_activation ORDER BY file_path"
        )
    ]
    target_id = conn.execute(
        "SELECT id FROM ast_symbol_rows WHERE name='target'"
    ).fetchone()[0]
    callee_ids = [
        row[0]
        for row in conn.execute(
            "SELECT callee_symbol_id FROM edges WHERE kind='calls' ORDER BY id"
        )
    ]
    cache.close()

    assert constructor_rows == [(1, "target")]
    assert (result["indexed"], result["cached"]) == (1, 0)
    assert [name for _symbol_id, name in repaired_rows] == ["target", "caller"]
    assert fts_rowids == [symbol_id for symbol_id, _name in repaired_rows]
    assert activation_paths == []
    assert callee_ids == [target_id]
