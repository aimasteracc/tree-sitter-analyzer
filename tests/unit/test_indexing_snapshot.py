from __future__ import annotations

import os
import sqlite3
from dataclasses import replace
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.indexer import walk_and_partition
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
    IndexFileFingerprint,
    IndexSnapshotEntry,
    build_index_candidate_snapshot,
    changed_since_snapshot,
)


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


def test_snapshot_freezes_order_scope_and_reconciled_metrics(tmp_path):
    selected = tmp_path / "a.py"
    excluded = tmp_path / "generated.py"
    limited = tmp_path / "z.py"
    selected.write_text("a = 1\n")
    excluded.write_text("generated = 1\n")
    limited.write_text("z = 1\n")

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=2,
        exclude_patterns=frozenset({"generated.py"}),
        walk_fn=lambda _root: (str(selected), str(excluded), str(limited)),
        language_fn=_python_language,
    )

    assert [entry.rel_path for entry in snapshot.entries] == [
        "a.py",
        "generated.py",
    ]
    assert [entry.rel_path for entry in snapshot.selected_entries] == ["a.py"]
    assert snapshot.present_paths == frozenset({"a.py", "generated.py", "z.py"})
    assert snapshot.metrics() == {
        "discovered": 3,
        "selected": 1,
        "excluded": 1,
        "skipped": 0,
        "errors": 0,
        "limited_by_max_files": 1,
        "truncated_by_max_files": True,
        "discovery_reconciled": True,
    }


def test_max_files_window_is_evaluated_before_exclusions(tmp_path):
    excluded = tmp_path / "generated.py"
    later = tmp_path / "later.py"
    excluded.write_text("generated = 1\n")
    later.write_text("later = 1\n")

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=1,
        exclude_patterns=frozenset({"generated.py"}),
        walk_fn=lambda _root: (str(excluded), str(later)),
        language_fn=_python_language,
    )

    assert snapshot.selected == 0
    assert snapshot.excluded == 1
    assert snapshot.limited == 1


def test_snapshot_detects_modification(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
    )
    entry = snapshot.selected_entries[0]
    assert changed_since_snapshot(entry) is None
    path.write_text("value = 200\n")
    os.utime(path, None)
    assert changed_since_snapshot(entry) == "file changed after candidate snapshot"


def test_snapshot_detects_deletion(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
    )
    entry = snapshot.selected_entries[0]
    path.unlink()
    assert changed_since_snapshot(entry) == "file disappeared after candidate snapshot"


def test_non_selected_entry_never_reports_snapshot_change(tmp_path):
    # PR #1172 review 2026-07-27: validation covers every snapshot decision.
    entry = IndexSnapshotEntry(
        abs_path=str(tmp_path / "excluded.py"),
        rel_path="excluded.py",
        language=None,
        decision="excluded",
    )

    assert changed_since_snapshot(entry) is None


def test_snapshot_is_structurally_immutable(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
    )
    assert isinstance(snapshot.entries, tuple)
    assert isinstance(snapshot.present_paths, frozenset)


def test_snapshot_deduplicates_candidates_after_path_resolution(tmp_path):
    # PR #1172: in-root symlink aliases must not index one source twice.
    target = tmp_path / "app.py"
    alias = tmp_path / "alias.py"
    target.write_text("value = 1\n")
    realpath = os.path.realpath

    def resolve(path):
        return str(target) if path == str(alias) else realpath(path)

    with patch(
        "tree_sitter_analyzer.indexing_snapshot.os.path.realpath", side_effect=resolve
    ):
        snapshot = build_index_candidate_snapshot(
            str(tmp_path),
            max_files=10,
            exclude_patterns=frozenset(),
            walk_fn=lambda _root: (str(target), str(alias)),
            language_fn=_python_language,
        )
    assert (snapshot.discovered, snapshot.selected, len(snapshot.entries)) == (1, 1, 1)


def test_ast_partition_consumes_every_frozen_decision(tmp_path):
    cached = tmp_path / "cached.py"
    changed = tmp_path / "changed.py"
    unsupported = tmp_path / "notes.md"
    filtered = tmp_path / "frontend.js"
    excluded = tmp_path / "generated.py"
    missing = tmp_path / "missing.py"
    cached.write_text("cached = 1\n")
    changed.write_text("changed = 1\n")
    unsupported.write_text("# notes\n")
    filtered.write_text("const value = 1;\n")
    excluded.write_text("generated = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset({"generated.py"}),
        walk_fn=lambda _root: (
            str(cached),
            str(changed),
            str(unsupported),
            str(filtered),
            str(excluded),
            str(missing),
        ),
        language_fn=lambda path: (
            "javascript" if path.endswith(".js") else _python_language(path)
        ),
        language_filter="python",
    )
    cached_entry = snapshot.selected_entries[0]
    fingerprint = cached_entry.fingerprint
    assert fingerprint is not None
    conn = _index_conn()
    conn.execute(
        "INSERT INTO ast_index VALUES (?, ?, ?, ?, ?)",
        (
            "cached.py",
            "hash",
            fingerprint.mtime_ns,
            fingerprint.file_size,
            1,
        ),
    )
    changed.write_text("changed = 200\n")
    stats, candidates, count = _partition(snapshot, conn)

    assert candidates == []
    assert count == 6
    assert stats["cached"] == 1
    assert stats["skipped"] == 4
    assert stats["errors"] == 1
    assert stats["processed"] == 1
    assert stats["changed_during_run"] == 1
    assert stats["changed_during_run_files"] == ["changed.py"]


def test_ast_partition_rejects_snapshot_from_another_root(tmp_path):
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=_python_language,
    )
    other = tmp_path / "other"
    other.mkdir()
    conn = _index_conn()

    with pytest.raises(ValueError, match="different project root"):
        walk_and_partition(
            _CacheRoot(str(other)),
            conn,
            max_files=10,
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


def test_ast_partition_rejects_snapshot_limit_mismatch(tmp_path):
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=_python_language,
    )

    with pytest.raises(ValueError, match="different max_files"):
        walk_and_partition(
            _CacheRoot(str(tmp_path)),
            _index_conn(),
            max_files=11,
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


def test_ast_cache_discards_worker_result_changed_after_snapshot(tmp_path):
    from tree_sitter_analyzer.cache import extraction

    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
    )
    cache = ASTCache(str(tmp_path))
    real_worker = extraction._worker_index_file

    def worker_then_mutate(args):
        result = real_worker(args)
        path.write_text("value = 200\n")
        return result

    try:
        with patch.object(
            extraction,
            "_worker_index_file",
            side_effect=worker_then_mutate,
        ):
            result = cache.index_project(
                max_files=10,
                workers=0,
                exclude_patterns=frozenset(),
                candidate_snapshot=snapshot,
            )
        rows = cache.get_conn().execute("SELECT file_path FROM ast_index").fetchall()
    finally:
        cache.close()

    assert rows == []
    assert result["processed"] == 0
    assert result["changed_during_run_files"] == ["app.py"]
    assert result["files"] == [
        {
            "file": "app.py",
            "status": "skipped",
            "reason": "file changed after candidate snapshot",
        }
    ]


def test_ast_cache_discards_worker_result_with_mismatched_fingerprint(tmp_path):
    from tree_sitter_analyzer.cache import extraction

    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
    )
    cache = ASTCache(str(tmp_path))
    real_worker = extraction._worker_index_file

    def worker_with_mismatched_fingerprint(args):
        result = real_worker(args)
        result["mtime_ns"] += 1
        return result

    try:
        with patch.object(
            extraction,
            "_worker_index_file",
            side_effect=worker_with_mismatched_fingerprint,
        ):
            result = cache.index_project(
                max_files=10,
                workers=0,
                exclude_patterns=frozenset(),
                candidate_snapshot=snapshot,
            )
        rows = cache.get_conn().execute("SELECT file_path FROM ast_index").fetchall()
    finally:
        cache.close()

    assert rows == []
    assert result["changed_during_run_files"] == ["app.py"]


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
