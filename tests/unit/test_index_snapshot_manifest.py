"""Exact behavioral tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

requires_posix_snapshot = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
requires_posix_fd = requires_posix_snapshot


def test_manifest_preflight_rejects_huge_control_cell_before_fetch():
    # PR #1253 thread 3756001898: control rows are size-checked inside SQLite.
    from tree_sitter_analyzer.index_snapshot import _read_bounded_manifest

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index_snapshot_manifest("
        "singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version)"
    )
    conn.execute(
        "INSERT INTO ast_index_snapshot_manifest VALUES "
        "(1, zeroblob(2097152), 'source', 'index', 0, '{}', 2)"
    )

    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        _read_bounded_manifest(conn, float("inf"))

    conn.close()


def test_manifest_preflight_rejects_duplicate_singleton_rows():
    # PR #1253 thread 3756001898: malformed control tables remain bounded.
    from tree_sitter_analyzer.index_snapshot import _read_bounded_manifest

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index_snapshot_manifest("
        "singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version)"
    )
    conn.executemany(
        "INSERT INTO ast_index_snapshot_manifest VALUES (1, ?, 's', 'i', 0, '{}', 2)",
        [("first",), ("second",)],
    )
    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        _read_bounded_manifest(conn, float("inf"))
    conn.close()


def test_manifest_preflight_enforces_total_budget(monkeypatch):
    # PR #1253 thread 3756001898: aggregate scalar bytes are bounded before fetch.
    import tree_sitter_analyzer.index_snapshot as snapshot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index_snapshot_manifest("
        "singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version)"
    )
    conn.execute(
        "INSERT INTO ast_index_snapshot_manifest VALUES "
        "(1, zeroblob(10), zeroblob(10), zeroblob(10), 0, '{}', 2)"
    )
    monkeypatch.setattr(snapshot, "_MANIFEST_TOTAL_BYTE_BUDGET", 20)
    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(conn, float("inf"))
    conn.close()


def test_manifest_materialization_disappearance_fails_closed():
    # PR #1253 thread 3756001898: a preflight/fetch race cannot look absent.
    import tree_sitter_analyzer.index_snapshot as snapshot

    class EmptyCursor:
        def fetchone(self):
            return None

    class RacedConnection:
        def __init__(self):
            self.calls = 0

        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, _query):
            self.calls += 1
            if self.calls == 1:
                return iter([(1,)])
            if self.calls == 2:
                return iter([(1, 1, 1, 1, 2, 1)])
            return EmptyCursor()

    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(RacedConnection(), float("inf"))  # type: ignore[arg-type]


def test_manifest_duplicate_count_rejects_before_length_preflight():
    # PR #1253 review 3756101926: ambiguity is rejected before any cell fetch.
    import tree_sitter_analyzer.index_snapshot as snapshot

    class DuplicateCountConnection:
        def __init__(self):
            self.queries = []

        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, query):
            self.queries.append(query)
            if query.startswith("SELECT COUNT(*)"):
                return iter([(2,)])
            raise AssertionError("length preflight reached")

    conn = DuplicateCountConnection()
    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(conn, float("inf"))  # type: ignore[arg-type]
    assert len(conn.queries) == 1


@pytest.mark.parametrize("rows", [[], [()], [("1",)], [(1,), (1,)]])
def test_manifest_count_scalar_shape_is_strict(rows):
    # PR #1253: the bounded aggregate must return exactly one integer scalar.
    import tree_sitter_analyzer.index_snapshot as snapshot

    class CountConnection:
        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, _query):
            return iter(rows)

    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(  # type: ignore[arg-type]
            CountConnection(), float("inf")
        )


def test_manifest_missing_length_row_is_invalid():
    # PR #1253 review 3756101926: admitted singleton loss cannot look absent.
    import tree_sitter_analyzer.index_snapshot as snapshot

    class MissingLengthConnection:
        def __init__(self):
            self.calls = 0

        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, _query):
            self.calls += 1
            return iter([(1,)]) if self.calls == 1 else iter(())

    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(  # type: ignore[arg-type]
            MissingLengthConnection(), float("inf")
        )


def test_module_exports_exact_focused_surface() -> None:
    from tree_sitter_analyzer import index_snapshot_manifest

    assert index_snapshot_manifest.__all__ == ["_read_bounded_manifest"]
