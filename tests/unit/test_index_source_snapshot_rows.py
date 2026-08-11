"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3
import time

import pytest

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
requires_posix_snapshot = requires_posix_fd
pytestmark = requires_posix_fd


def _fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


def test_fifo_index_database_is_rejected_without_blocking(tmp_path):
    # PR #1253 review 3755216346: untrusted FIFO opens must be nonblocking.
    from tree_sitter_analyzer.index_snapshot_capability import open_bound_database

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    os.mkfifo(cache / "index.db")
    started = time.monotonic()
    with pytest.raises(ValueError, match="INDEX_PATH_UNSAFE"):
        open_bound_database(str(tmp_path))
    assert time.monotonic() - started < 0.2


def test_source_fingerprint_is_order_independent():
    # PR #1255: the set accumulator avoids full-inventory sort copies.
    import tree_sitter_analyzer.index_source_snapshot as source

    rows = (("b.py", "b", "python"), ("a.py", "a", "python"))
    assert source.inventory_fingerprint(rows) == source.inventory_fingerprint(
        reversed(rows)
    )


def test_source_fingerprint_rejects_duplicate_paths():
    # PR #1255: paths are unique inputs to the commutative accumulator.
    import tree_sitter_analyzer.index_source_snapshot as source

    rows = (("a.py", "one", "python"), ("a.py", "two", "python"))
    with pytest.raises(ValueError, match="SOURCE_INVENTORY_DUPLICATE_PATH"):
        source.inventory_fingerprint(rows)


def test_inventory_fingerprint_checks_deadline_inside_each_row(monkeypatch):
    # PR #1253: per-value framing remains within the same deadline.
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_source_snapshot as source

    ticks = iter((0.0, 0.0, 0.0, 2.0))
    monkeypatch.setattr(source, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    with pytest.raises(TimeoutError):
        source.inventory_fingerprint((("a", "b", "c"),), deadline=1.0)


def test_source_capture_maps_fingerprint_deadline_to_unknown(monkeypatch):
    # PR #1253: canonical hashing shares the source scan deadline.
    import tree_sitter_analyzer.index_source_snapshot as source

    inventories = iter(
        [
            (("a.py", "meta|hash", "python"),),
            (("a.py", "meta", "python"),),
        ]
    )
    monkeypatch.setattr(
        source, "_inventory", lambda *_a, **_k: (next(inventories), False)
    )
    monkeypatch.setattr(
        source,
        "inventory_fingerprint",
        lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()),
    )
    result = source.capture_current_source_snapshot(".")
    assert (result.state, result.reason) == ("unknown", "SOURCE_SCAN_DEADLINE")


def test_source_fingerprint_checks_deadline_before_first_row(monkeypatch):
    # PR #1255: the accumulator checks time before retaining each path.
    import tree_sitter_analyzer.index_source_snapshot as source

    monkeypatch.setattr(source.time, "monotonic", lambda: 2.0)
    with pytest.raises(TimeoutError):
        source.inventory_fingerprint((("a.py", "hash", "python"),), deadline=1.0)


def test_recorded_rows_check_deadline_before_materializing(monkeypatch):
    # PR #1255: database inventory materialization shares the deadline.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.execute("INSERT INTO ast_index VALUES ('a.py', 'hash', 'python')")
    monkeypatch.setattr(source.time, "monotonic", lambda: 2.0)
    with pytest.raises(TimeoutError):
        source.recorded_source_rows(conn, deadline=1.0)
    conn.close()


def test_recorded_rows_reject_duplicate_paths():
    # PR #1255: persisted paths must be unique before set comparison.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, 'python')",
        (("a.py", "one"), ("a.py", "two")),
    )
    with pytest.raises(ValueError, match="SOURCE_INVENTORY_DUPLICATE_PATH"):
        source.recorded_source_rows(conn)
    conn.close()


def test_recorded_fingerprint_deadline_is_fail_closed(monkeypatch):
    # PR #1253: writer-side canonical inventory hashing has the same deadline.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    monkeypatch.setattr(
        schema,
        "recorded_source_rows",
        lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()),
    )
    with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
        schema.source_fingerprint(sqlite3.connect(":memory:"), ".")


def test_recorded_rows_rejects_count_before_materialization(monkeypatch):
    # PR #1253 review 3756101913: retained source inventories have a row cap.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.execute("INSERT INTO ast_index VALUES ('a.py', 'hash', 'python')")
    monkeypatch.setattr(source, "_RECORDED_SOURCE_ROW_BUDGET", 0)
    with pytest.raises(OverflowError, match="SOURCE_INVENTORY_BUDGET"):
        source.recorded_source_rows(conn)
    conn.close()


def test_recorded_rows_rejects_oversized_path_before_materialization(monkeypatch):
    # PR #1253 review 3756101913: hostile path cells are bounded in SQLite.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.execute("INSERT INTO ast_index VALUES ('ab', 'h', 'python')")
    monkeypatch.setattr(source, "_RECORDED_SOURCE_CELL_BYTE_BUDGET", 1)
    with pytest.raises(OverflowError, match="SOURCE_INVENTORY_BUDGET"):
        source.recorded_source_rows(conn)
    conn.close()


def test_recorded_rows_rejects_oversized_language_before_materialization(monkeypatch):
    # PR #1253 thread 3760724577: language shares the per-cell SQLite preflight.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.execute("INSERT INTO ast_index VALUES ('a', 'h', 'python')")
    monkeypatch.setattr(source, "_RECORDED_SOURCE_CELL_BYTE_BUDGET", 5)
    with pytest.raises(OverflowError, match="SOURCE_INVENTORY_BUDGET"):
        source.recorded_source_rows(conn)
    conn.close()


def test_recorded_rows_guards_language_again_during_materialization(monkeypatch):
    # PR #1253 thread 3760724577: a post-preflight growth is nulled inside SQLite.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.execute("INSERT INTO ast_index VALUES ('a', 'h', 'py')")

    class EnlargingLanguageConnection:
        def __getattr__(self, name):
            return getattr(conn, name)

        def execute(self, query, params=()):
            if query.startswith("SELECT CASE"):
                conn.execute("UPDATE ast_index SET language = 'oversized'")
            return conn.execute(query, params)

    monkeypatch.setattr(source, "_RECORDED_SOURCE_CELL_BYTE_BUDGET", 2)
    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        source.recorded_source_rows(EnlargingLanguageConnection())  # type: ignore[arg-type]
    conn.close()


def test_recorded_rows_recharges_materialized_rows(monkeypatch):
    # PR #1253 review 3756101913: post-preflight values are charged per fetch.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.execute("INSERT INTO ast_index VALUES ('a', 'h', 'p')")

    class EnlargingConnection:
        def set_progress_handler(self, handler, steps):
            return conn.set_progress_handler(handler, steps)

        def execute(self, query, params=()):
            if query.startswith("SELECT CASE"):
                conn.execute("UPDATE ast_index SET language = 'xx'")
            return conn.execute(query, params)

    monkeypatch.setattr(source, "_RECORDED_SOURCE_TOTAL_BYTE_BUDGET", 3)
    with pytest.raises(OverflowError, match="SOURCE_INVENTORY_BUDGET"):
        source.recorded_source_rows(EnlargingConnection())  # type: ignore[arg-type]
    conn.close()


def test_recorded_rows_rejects_missing_preflight_row():
    # PR #1253 review 3756101913: malformed preflight results fail closed.
    import tree_sitter_analyzer.index_source_snapshot as source

    class EmptyPreflight:
        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, _query, _params=()):
            return self

        def fetchone(self):
            return None

    with pytest.raises(OverflowError, match="SOURCE_INVENTORY_BUDGET"):
        source.recorded_source_rows(EmptyPreflight())  # type: ignore[arg-type]


def test_recorded_rows_rejects_untyped_count():
    # PR #1253 review 3756101913: preflight count coercions are rejected.
    import tree_sitter_analyzer.index_source_snapshot as source

    class UntypedPreflight:
        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, _query, _params=()):
            return self

        def fetchone(self):
            return ("1", 1, 1, 1, 3)

    with pytest.raises(OverflowError, match="SOURCE_INVENTORY_BUDGET"):
        source.recorded_source_rows(UntypedPreflight())  # type: ignore[arg-type]


def test_recorded_rows_rejects_rows_added_after_preflight():
    # PR #1253 review 3756101913: fetches cannot exceed the admitted row count.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.execute("INSERT INTO ast_index VALUES ('a', 'h', 'p')")

    class GrowingConnection:
        def set_progress_handler(self, handler, steps):
            return conn.set_progress_handler(handler, steps)

        def execute(self, query, params=()):
            if query.startswith("SELECT CASE"):
                conn.execute("INSERT INTO ast_index VALUES ('b', 'h', 'p')")
            return conn.execute(query, params)

    with pytest.raises(OverflowError, match="SOURCE_INVENTORY_BUDGET"):
        source.recorded_source_rows(GrowingConnection())  # type: ignore[arg-type]
    conn.close()


def test_recorded_rows_rejects_rows_removed_after_preflight():
    # PR #1253 review 3756101913: materialization must match the admitted count.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.execute("INSERT INTO ast_index VALUES ('a', 'h', 'p')")

    class ShrinkingConnection:
        def set_progress_handler(self, handler, steps):
            return conn.set_progress_handler(handler, steps)

        def execute(self, query, params=()):
            if query.startswith("SELECT CASE"):
                conn.execute("DELETE FROM ast_index")
            return conn.execute(query, params)

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        source.recorded_source_rows(ShrinkingConnection())  # type: ignore[arg-type]
    conn.close()


def test_recorded_rows_rejects_non_text_materialization():
    # PR #1253 review 3756101913: hostile SQLite scalar types are not coerced.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.execute("INSERT INTO ast_index VALUES ('a', X'68', 'p')")
    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        source.recorded_source_rows(conn)
    conn.close()


def test_recorded_rows_progress_interrupt_maps_to_timeout(monkeypatch):
    # PR #1253 review 3756101913: interrupted SQL preserves deadline semantics.
    import tree_sitter_analyzer.index_source_snapshot as source

    class InterruptedConnection:
        def __init__(self):
            self.expired = None

        def set_progress_handler(self, handler, _steps):
            if handler is not None:
                self.expired = handler()

        def execute(self, _query, _params=()):
            raise sqlite3.OperationalError("interrupted")

    conn = InterruptedConnection()
    monkeypatch.setattr(source.time, "monotonic", lambda: 0.0)
    with pytest.raises(TimeoutError):
        source.recorded_source_rows(conn)  # type: ignore[arg-type]
    assert conn.expired == 0


def test_recorded_rows_preserves_non_deadline_sql_errors(monkeypatch):
    # PR #1253 review 3756101913: unrelated SQLite failures are not timeouts.
    import tree_sitter_analyzer.index_source_snapshot as source

    class BrokenConnection:
        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, _query, _params=()):
            raise sqlite3.OperationalError("missing table")

    monkeypatch.setattr(source.time, "monotonic", lambda: 0.0)
    with pytest.raises(sqlite3.OperationalError, match="missing table"):
        source.recorded_source_rows(BrokenConnection())  # type: ignore[arg-type]


def test_module_exports_exact_focused_surface() -> None:
    from tree_sitter_analyzer import index_source_snapshot_rows

    assert index_source_snapshot_rows.__all__ == [
        "inventory_fingerprint",
        "recorded_source_rows",
    ]
