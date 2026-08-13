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


def test_manifest_singleton_predicate_rejects_oversized_blob_without_materializing():
    # PR #1253 Codex thread 3762955388: MIN/MAX must not return hostile payloads.
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
        "(zeroblob(8388608), 'root', 'source', 'index', 0, '{}', 2)"
    )
    statements: list[str] = []
    conn.set_trace_callback(statements.append)

    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        _read_bounded_manifest(conn, float("inf"))

    conn.close()
    aggregate = next(sql for sql in statements if sql.startswith("SELECT COUNT(*)"))
    assert ("MIN(" in aggregate, "MAX(" in aggregate, "CASE WHEN" in aggregate) == (
        False,
        False,
        True,
    )


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


def test_manifest_preflight_rejects_extra_non_singleton_authority_row():
    # PR #1253 review 3762603018: every row in the authority table is counted.
    from tree_sitter_analyzer.index_snapshot import _read_bounded_manifest

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index_snapshot_manifest("
        "singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version)"
    )
    conn.executemany(
        "INSERT INTO ast_index_snapshot_manifest VALUES (?, ?, 's', 'i', 0, '{}', 2)",
        [(1, "valid"), (2, "extra")],
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
                return iter([(1, 1, 1)])
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
                return iter([(2, 1, 1)])
            raise AssertionError("length preflight reached")

    conn = DuplicateCountConnection()
    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(conn, float("inf"))  # type: ignore[arg-type]
    assert len(conn.queries) == 1


@pytest.mark.parametrize(
    "rows",
    [[], [()], [("1", 1, 1)], [(1, 1, 1), (1, 1, 1)], [(1, None, None)]],
)
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
            return iter([(1, 1, 1)]) if self.calls == 1 else iter(())

    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(  # type: ignore[arg-type]
            MissingLengthConnection(), float("inf")
        )


def test_module_exports_exact_focused_surface() -> None:
    from tree_sitter_analyzer import index_snapshot_manifest

    assert index_snapshot_manifest.__all__ == ["_read_bounded_manifest"]


def test_capture_source_wrapper_propagates_body_type_error(monkeypatch):
    import tree_sitter_analyzer.index_snapshot as snapshot

    def broken(_root, _scope, *, deadline):
        raise TypeError("source decoder failed")

    monkeypatch.setattr(snapshot, "capture_current_source_snapshot", broken)

    with pytest.raises(TypeError, match="source decoder failed"):
        snapshot._capture_sources_with_deadline("/root", object(), 1.0)


def test_index_fingerprint_wrapper_propagates_body_type_error(monkeypatch):
    import tree_sitter_analyzer.index_snapshot as snapshot

    def broken(_conn, _root, *, deadline):
        raise TypeError("fingerprint query failed")

    monkeypatch.setattr(snapshot, "index_fingerprint", broken)

    with pytest.raises(TypeError, match="fingerprint query failed"):
        snapshot._index_fingerprint_with_deadline(object(), "/root", 1.0)  # type: ignore[arg-type]


def test_manifest_accepts_iterator_cursor_without_fetchone():
    import tree_sitter_analyzer.index_snapshot as snapshot

    manifest = ("/root", "source", "index", 1, "{}", 2)

    class IteratorConnection:
        def __init__(self):
            self.calls = 0

        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, _query):
            self.calls += 1
            if self.calls == 1:
                return iter(((1, 1, 1),))
            if self.calls == 2:
                return iter(((5, 6, 5, 1, 2, 1),))
            return iter((manifest,))

    result = snapshot._read_bounded_manifest(  # type: ignore[arg-type]
        IteratorConnection(), float("inf")
    )

    assert result == manifest


def test_manifest_progress_handler_interrupts_expired_materialization(monkeypatch):
    import tree_sitter_analyzer.index_snapshot as snapshot

    ticks = iter((0.0, 2.0))
    monkeypatch.setattr(snapshot, "_clock", lambda: next(ticks))

    class InterruptingConnection:
        def __init__(self):
            self.calls = 0
            self.handler = None
            self.cleared = False

        def set_progress_handler(self, handler, _steps):
            self.handler = handler
            if handler is None:
                self.cleared = True

        def execute(self, _query):
            self.calls += 1
            if self.calls == 1:
                return iter(((1, 1, 1),))
            if self.calls == 2:
                return iter(((5, 6, 5, 1, 2, 1),))
            assert self.handler is not None
            if self.handler() == 1:
                raise sqlite3.DatabaseError("interrupted")
            raise AssertionError("deadline handler did not interrupt")

    conn = InterruptingConnection()
    with pytest.raises(sqlite3.DatabaseError, match="interrupted"):
        snapshot._read_bounded_manifest(conn, 1.0)  # type: ignore[arg-type]
    assert conn.cleared is True


@requires_posix_fd
def test_snapshot_lock_timeout_returns_deadline(tmp_path, monkeypatch):
    import tree_sitter_analyzer.index_snapshot as snapshot

    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir()
    (cache_dir / "index.db").write_bytes(b"database")

    class BusyLock:
        def acquire(self, *, timeout):
            assert timeout == 10.0
            return False

    monkeypatch.setattr(snapshot, "_clock", lambda: 5.0)
    monkeypatch.setattr(snapshot, "_CAPTURE_LOCK", BusyLock())

    result = snapshot.read_existing_snapshot(str(tmp_path))

    assert (result.completeness, result.reason) == (
        "unknown",
        "INDEX_SNAPSHOT_DEADLINE",
    )


@requires_posix_fd
def test_backup_expiring_during_copy_returns_deadline(tmp_path, monkeypatch):
    import inspect
    import time

    import tree_sitter_analyzer.index_snapshot as snapshot
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    cache.close()
    real_clock = time.monotonic

    def expire_in_backup_progress():
        caller = inspect.currentframe().f_back
        if caller is not None and caller.f_code.co_name == "progress":
            return real_clock() + snapshot._CAPTURE_DEADLINE_SECONDS + 1.0
        return real_clock()

    monkeypatch.setattr(snapshot, "_clock", expire_in_backup_progress)

    result = snapshot.read_existing_snapshot(str(tmp_path))

    assert (result.completeness, result.reason) == (
        "unknown",
        "INDEX_SNAPSHOT_DEADLINE",
    )


def test_manifest_empty_authority_returns_none() -> None:
    import tree_sitter_analyzer.index_snapshot as snapshot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index_snapshot_manifest("
        "singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version)"
    )
    try:
        result = snapshot._read_bounded_manifest(conn, float("inf"))
    finally:
        conn.close()

    assert result is None


def test_manifest_boundary_delegates_connection_and_deadline(monkeypatch) -> None:
    from tree_sitter_analyzer import index_snapshot, index_snapshot_manifest

    connection = object()
    expected = object()
    observed = []

    def read_bounded_manifest(received_connection, received_deadline):
        observed.append((received_connection, received_deadline))
        return expected

    monkeypatch.setattr(index_snapshot, "_read_bounded_manifest", read_bounded_manifest)

    result = index_snapshot_manifest._read_bounded_manifest(  # type: ignore[arg-type]
        connection, 7.5
    )

    assert result is expected
    assert observed == [(connection, 7.5)]


def test_manifest_writer_uses_portable_source_certifier(tmp_path, monkeypatch) -> None:
    # PR #1254 review 3769193895: Windows-built indexes must stamp authority.
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_snapshot_schema as schema

    class PortableOS:
        name = "nt"
        path = schema.os.path

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        schema.SCHEMA_V13_INDEX_SNAPSHOT
        + "CREATE TABLE ast_index(file_path TEXT, content_hash TEXT, language TEXT);"
    )
    expected_rows = frozenset({("sample.py", "hash", "python")})
    conn.execute("INSERT INTO ast_index VALUES ('sample.py', 'hash', 'python')")
    monkeypatch.setattr(schema, "os", PortableOS())
    monkeypatch.setattr(schema, "strict_call_graph_marker", lambda _conn: True)
    monkeypatch.setattr(
        schema, "index_fingerprint", lambda *_args: "sha256:" + "a" * 64
    )
    monkeypatch.setattr(
        schema, "source_fingerprint", lambda *_args: "sha256:" + "b" * 64
    )
    monkeypatch.setattr(schema, "recorded_source_rows", lambda _conn: expected_rows)
    observed: list[tuple[str, object]] = []
    import tree_sitter_analyzer.portable_source_snapshot as portable

    monkeypatch.setattr(
        portable,
        "capture_portable_source_snapshot",
        lambda root, scope, *, deadline: (
            observed.append((root, scope))
            or SimpleNamespace(state="exact", rows=expected_rows)
        ),
    )

    schema.stamp_full_index_manifest(conn, str(tmp_path))

    row = conn.execute(
        "SELECT canonical_root, file_count, manifest_version "
        "FROM ast_index_snapshot_manifest"
    ).fetchone()
    assert tuple(row) == (schema.os.path.realpath(str(tmp_path)), 1, 2)
    assert len(observed) == 1
    conn.close()
