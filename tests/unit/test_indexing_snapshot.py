from __future__ import annotations

import os
import sqlite3
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.indexer import walk_and_partition
from tree_sitter_analyzer.incremental_sync import IncrementalSync
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
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


def test_incremental_sync_preserves_snapshot_candidate_order(tmp_path):
    first = tmp_path / "z.py"
    second = tmp_path / "a.py"
    first.write_text("z = 1\n")
    second.write_text("a = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(first), str(second)),
        language_fn=_python_language,
    )
    cache = ASTCache(str(tmp_path))
    seen: list[str] = []
    original = cache.index_file

    def record(path: str, language: str | None = None):
        seen.append(os.path.basename(path))
        return original(path, language)

    try:
        with patch.object(cache, "index_file", side_effect=record):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()

    assert result.processed == 2
    assert seen == ["z.py", "a.py"]


def test_incremental_sync_detects_mutation_during_processing(tmp_path):
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
    original = cache.index_file
    callback_details: list[dict] = []

    def index_then_mutate(file_path: str, language: str | None = None):
        indexed = original(file_path, language)
        path.write_text("value = 200\n")
        return indexed

    try:
        with patch.object(cache, "index_file", side_effect=index_then_mutate):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
                callback=callback_details.append,
            )
    finally:
        cache.close()

    assert result.changed_during_run == 1
    assert result.changed_during_run_files == ["app.py"]
    assert result.processed == 0
    assert result.details[-1]["reason"] == "file changed after candidate snapshot"
    assert callback_details[-1]["reason"] == "file changed after candidate snapshot"


def test_incremental_sync_detects_late_mutation_without_callback(tmp_path):
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
    original = cache.index_file

    def index_then_mutate(file_path: str, language: str | None = None):
        indexed = original(file_path, language)
        path.write_text("value = 200\n")
        return indexed

    try:
        with patch.object(cache, "index_file", side_effect=index_then_mutate):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()

    assert result.changed_during_run_files == ["app.py"]


def test_incremental_sync_reports_preexisting_snapshot_change_to_callback(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
    )
    path.unlink()
    cache = ASTCache(str(tmp_path))
    callback_details: list[dict] = []

    try:
        result = IncrementalSync(cache).sync(
            max_files=10,
            candidate_snapshot=snapshot,
            callback=callback_details.append,
        )
    finally:
        cache.close()

    assert result.changed_during_run == 1
    assert result.processed == 0
    assert callback_details == [
        {
            "file": "app.py",
            "considered": "skipped",
            "action": "skipped",
            "status": "skipped",
            "reason": "file disappeared after candidate snapshot",
        }
    ]


def test_incremental_sync_rejects_snapshot_root_mismatch(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
    )
    other = tmp_path / "other"
    other.mkdir()
    other_cache = ASTCache(str(other))

    try:
        with pytest.raises(ValueError, match="different project root"):
            IncrementalSync(other_cache)._scan_disk_files(
                10,
                candidate_snapshot=snapshot,
            )
    finally:
        other_cache.close()


def test_incremental_sync_rejects_snapshot_limit_mismatch(tmp_path):
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

    try:
        with pytest.raises(ValueError, match="different max_files"):
            IncrementalSync(cache)._scan_disk_files(
                11,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()


def test_incremental_sync_rejects_selected_entry_without_fingerprint(tmp_path):
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
    cache = ASTCache(str(tmp_path))

    try:
        with pytest.raises(ValueError, match="lacks fingerprint"):
            IncrementalSync(cache)._scan_disk_files(
                10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()
