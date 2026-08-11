from __future__ import annotations

import os
import sqlite3
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.indexer import walk_and_partition
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
    IndexSnapshotEntry,
    build_index_candidate_snapshot,
    changed_since_snapshot,
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
        make_error_entry=lambda p, r: {"file": p, "status": "error", "reason": r},
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
        "z.py",
    ]
    assert [entry.rel_path for entry in snapshot.selected_entries] == ["a.py", "z.py"]
    assert snapshot.present_paths == frozenset({"a.py", "generated.py", "z.py"})
    assert snapshot.metrics() == {
        "discovered": 3,
        "selected": 2,
        "excluded": 1,
        "skipped": 0,
        "errors": 0,
        "limited_by_max_files": 0,
        "truncated_by_max_files": False,
        "discovery_reconciled": True,
        "discovery_complete": True,
        "truncated_by_discovery_error": False,
    }


def test_exclusions_do_not_consume_the_selected_file_budget(tmp_path):
    excluded = tmp_path / "generated.py"
    later = tmp_path / "later.py"
    overflow = tmp_path / "overflow.py"
    excluded.write_text("generated = 1\n")
    later.write_text("later = 1\n")
    overflow.write_text("overflow = 1\n")

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=1,
        exclude_patterns=frozenset({"generated.py"}),
        walk_fn=lambda _root: (str(excluded), str(later), str(overflow)),
        language_fn=_python_language,
    )

    assert snapshot.selected == 1
    assert snapshot.excluded == 1
    assert snapshot.limited == 1


def test_candidate_discovery_closes_generator_after_first_overflow(tmp_path):
    # PR #1253 review thread 3755591652: discovery must consume max_files + 1.
    paths = [tmp_path / f"candidate-{index}.py" for index in range(4)]
    for path in paths:
        path.write_text("value = 1\n")
    consumed = 0
    closed = False

    def million_candidates(_root):
        nonlocal consumed, closed
        try:
            for index in range(1_000_000):
                consumed += 1
                yield str(paths[index]) if index < len(paths) else str(tmp_path / index)
        finally:
            closed = True

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=3,
        exclude_patterns=frozenset(),
        walk_fn=million_candidates,
        language_fn=_python_language,
    )

    assert (snapshot.selected, snapshot.limited, consumed, closed) == (3, 1, 4, True)
    assert snapshot.present_paths == frozenset(path.name for path in paths)


def test_candidate_discovery_bounds_million_unsupported_entries(tmp_path, monkeypatch):
    # PR #1253 review thread 3755842989: every yielded path consumes discovery budget.
    import tree_sitter_analyzer.indexing_snapshot as snapshot_module

    monkeypatch.setattr(snapshot_module.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(snapshot_module, "_CANDIDATE_ENTRY_BUDGET", 10)
    monkeypatch.setattr(snapshot_module, "_CANDIDATE_PATH_BYTE_BUDGET", 1_000_000_000)
    consumed = 0
    closed = False

    def million_unsupported(_root):
        nonlocal consumed, closed
        try:
            for index in range(snapshot_module._CANDIDATE_ENTRY_BUDGET + 1):
                consumed += 1
                yield str(tmp_path / f"unsupported-{index}.txt")
        finally:
            closed = True

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=1,
        exclude_patterns=frozenset(),
        walk_fn=million_unsupported,
        language_fn=_python_language,
    )

    assert (consumed, closed) == (11, True)
    assert len(snapshot.entries) == 10
    assert len(snapshot.present_paths) == 10
    assert snapshot.discovery_error == "INDEX_CANDIDATE_DISCOVERY_BUDGET"


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
    assert (
        snapshot.discovered,
        snapshot.selected,
        snapshot.errors,
        tuple(entry.decision for entry in snapshot.entries),
    ) == (2, 1, 1, ("selected", "error"))


def test_snapshot_ignores_repeated_walker_path(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("value = 1\n")

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source), str(source)),
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
            fingerprint.content_hash,
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


def test_excluded_supported_symlink_is_not_a_candidate_error(tmp_path) -> None:
    # PR #1253 review 3757950779: exclusions precede supported-path safety.
    target = tmp_path / "target.py"
    target.write_text("value = 1\n")
    excluded = tmp_path / "tests" / "golden" / "corpus_link.py"
    excluded.parent.mkdir(parents=True)
    excluded.symlink_to(target)

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset({"tests/golden/*"}),
        walk_fn=lambda _root: (str(excluded),),
        language_fn=lambda _path: "python",
    )

    assert (snapshot.excluded, snapshot.errors) == (1, 0)
    assert snapshot.entries[0].decision == "excluded"
