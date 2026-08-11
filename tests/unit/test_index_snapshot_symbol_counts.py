"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


def _fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


def _untyped_legacy_connection(file_path="a.py", language="python", symbols_json="{}"):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, language, symbols_json)")
    conn.execute(
        "INSERT INTO ast_index VALUES (?, ?, ?)", (file_path, language, symbols_json)
    )
    return conn


def test_ordinary_symbol_counts_enforces_output_budget(monkeypatch):
    # PR #1253: grouped output bytes are independently bounded.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_symbol_rows(kind TEXT, language TEXT)")
    conn.execute("INSERT INTO ast_symbol_rows VALUES ('function', 'python')")
    monkeypatch.setattr(symbols, "_ORDINARY_OUTPUT_BYTE_BUDGET", 0)
    with pytest.raises(RuntimeError, match="SNAPSHOT_READ_FAILED"):
        symbols.ordinary_symbol_counts(conn)
    conn.close()


def test_ordinary_symbol_counts_rejects_excessive_total(monkeypatch):
    # PR #1253: total symbol count obeys the row budget.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_symbol_rows(kind TEXT, language TEXT)")
    conn.execute("INSERT INTO ast_symbol_rows VALUES ('function', 'python')")
    monkeypatch.setattr(symbols, "_ORDINARY_ROW_BUDGET", 0)
    with pytest.raises(RuntimeError, match="SNAPSHOT_READ_FAILED"):
        symbols.ordinary_symbol_counts(conn)
    conn.close()


def test_ordinary_symbol_counts_wraps_sqlite_errors():
    # PR #1253: missing projections expose one stable read failure.
    from tree_sitter_analyzer.index_snapshot_symbols import ordinary_symbol_counts

    conn = sqlite3.connect(":memory:")
    with pytest.raises(RuntimeError, match="SNAPSHOT_READ_FAILED"):
        ordinary_symbol_counts(conn)
    conn.close()


def test_symbol_upgrade_savepoint_open_failure_preserves_original_error():
    # PR #1253: rollback is attempted only after savepoint ownership.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    class SavepointFailure:
        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, query, _params=()):
            if query.startswith("SAVEPOINT"):
                raise sqlite3.OperationalError("savepoint denied")
            raise AssertionError(query)

    with pytest.raises(sqlite3.OperationalError, match="savepoint denied"):
        symbols.ensure_symbol_rows_backfilled(SavepointFailure())  # type: ignore[arg-type]


def test_ordinary_edge_counts_rejects_excess_groups(monkeypatch):
    # PR #1253 review 3756101917: edge-kind output has an absolute group cap.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.executemany("INSERT INTO edges VALUES (?)", (("a",), ("b",)))
    monkeypatch.setattr(symbols, "_ORDINARY_GROUP_BUDGET", 1)
    with pytest.raises(RuntimeError, match="^SNAPSHOT_READ_FAILED$"):
        symbols.ordinary_edge_counts(conn)
    conn.close()


def test_ordinary_edge_counts_rejects_oversized_kind(monkeypatch):
    # PR #1253 review 3756101917: oversized edge kinds never enter Python output.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('ab')")
    monkeypatch.setattr(symbols, "_ORDINARY_CELL_BYTE_BUDGET", 1)
    with pytest.raises(RuntimeError, match="^SNAPSHOT_READ_FAILED$"):
        symbols.ordinary_edge_counts(conn)
    conn.close()


def test_ordinary_edge_counts_rejects_excess_total(monkeypatch):
    # PR #1253 review 3756101917: the edge COUNT cannot exceed its row cap.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('call')")
    monkeypatch.setattr(symbols, "_ORDINARY_ROW_BUDGET", 0)
    with pytest.raises(RuntimeError, match="^SNAPSHOT_READ_FAILED$"):
        symbols.ordinary_edge_counts(conn)
    conn.close()


def test_fallback_symbol_counts_rejects_excess_kind_groups(monkeypatch):
    # PR #1253 review 3756101919: legacy JSON cannot retain unbounded kind keys.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = _untyped_legacy_connection(
        symbols_json='{"symbols":[{"kind":"a"},{"kind":"b"}]}'
    )
    monkeypatch.setattr(symbols, "_ORDINARY_GROUP_BUDGET", 1)
    with pytest.raises(RuntimeError, match="INDEX_SYMBOL_FALLBACK_BUDGET"):
        symbols.fallback_symbol_counts(conn)
    conn.close()


def test_fallback_symbol_counts_rejects_oversized_kind_key(monkeypatch):
    # PR #1253 review 3756101919: legacy keys are checked before dict insertion.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = _untyped_legacy_connection(symbols_json='{"symbols":[{"kind":"ab"}]}')
    monkeypatch.setattr(symbols, "_ORDINARY_CELL_BYTE_BUDGET", 1)
    with pytest.raises(RuntimeError, match="INDEX_SYMBOL_FALLBACK_BUDGET"):
        symbols.fallback_symbol_counts(conn)
    conn.close()


def test_fallback_symbol_counts_rejects_output_budget(monkeypatch):
    # PR #1253 review 3756101919: legacy breakdown output has a shared byte cap.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = _untyped_legacy_connection(symbols_json='{"symbols":[{"kind":"a"}]}')
    monkeypatch.setattr(symbols, "_ORDINARY_OUTPUT_BYTE_BUDGET", 0)
    with pytest.raises(RuntimeError, match="INDEX_SYMBOL_FALLBACK_BUDGET"):
        symbols.fallback_symbol_counts(conn)
    conn.close()


def test_ordinary_edge_counts_rejects_output_budget(monkeypatch):
    # PR #1253 review 3756101917: edge breakdown bytes are bounded.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('call')")
    monkeypatch.setattr(symbols, "_ORDINARY_OUTPUT_BYTE_BUDGET", 0)
    with pytest.raises(RuntimeError, match="^SNAPSHOT_READ_FAILED$"):
        symbols.ordinary_edge_counts(conn)
    conn.close()


def test_ordinary_edge_counts_deadline_interrupt_is_stable(monkeypatch):
    # PR #1253 review 3756101917: progress interruption has one stable failure.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    class InterruptedConnection:
        def __init__(self):
            self.expired = None

        def set_progress_handler(self, handler, _steps):
            if handler is not None:
                self.expired = handler()

        def execute(self, _query, _params=()):
            raise sqlite3.OperationalError("interrupted")

    conn = InterruptedConnection()
    monkeypatch.setattr(symbols, "_ORDINARY_DEADLINE_SECONDS", -1.0)
    with pytest.raises(RuntimeError, match="^SNAPSHOT_READ_FAILED$"):
        symbols.ordinary_edge_counts(conn)  # type: ignore[arg-type]
    assert conn.expired == 1


def test_ordinary_edge_counts_wraps_sqlite_errors():
    # PR #1253 review 3756101917: SQLite failures use one stable read reason.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = sqlite3.connect(":memory:")
    with pytest.raises(RuntimeError, match="^SNAPSHOT_READ_FAILED$"):
        symbols.ordinary_edge_counts(conn)
    conn.close()


def test_index_content_hash_probe_preserves_unrelated_sqlite_error():
    # PR #1253: compatibility fallback accepts only a missing-column error.
    from tree_sitter_analyzer.index_symbol_projection import index_content_hash_sql

    class LockedConnection:
        def execute(self, _query):
            raise sqlite3.OperationalError("database is locked")

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        index_content_hash_sql(LockedConnection())  # type: ignore[arg-type]


def test_projection_state_delete_preserves_unrelated_sqlite_error():
    # PR #1253: compatibility cleanup accepts only a missing-table error.
    from tree_sitter_analyzer.index_symbol_projection import (
        delete_projection_state_if_present,
    )

    class LockedConnection:
        def execute(self, _query, _params):
            raise sqlite3.OperationalError("database is locked")

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        delete_projection_state_if_present(LockedConnection(), "app.py")  # type: ignore[arg-type]


def test_projection_upsert_deletes_state_without_source():
    # PR #1253: removed sources cannot retain authoritative projection state.
    from tree_sitter_analyzer.index_symbol_projection import (
        upsert_symbol_projection_state,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path TEXT, content_hash TEXT)")
    conn.execute(
        "CREATE TABLE ast_symbol_projection_state("
        "file_path TEXT PRIMARY KEY, content_hash TEXT, symbol_count INTEGER)"
    )
    conn.execute("CREATE TABLE ast_symbol_rows(file_path TEXT)")
    conn.execute("INSERT INTO ast_symbol_projection_state VALUES ('app.py', 'old', 1)")

    upsert_symbol_projection_state(conn, "app.py")
    remaining = conn.execute(
        "SELECT COUNT(*) FROM ast_symbol_projection_state"
    ).fetchone()[0]
    conn.close()

    assert remaining == 0


@pytest.mark.parametrize("malformed_table", ["rows", "state"])
def test_projection_exactness_rejects_malformed_schema(malformed_table):
    # PR #1253: projection evidence requires both exact trusted schemas.
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index(file_path TEXT, symbols_json TEXT, content_hash TEXT)"
    )
    row_columns = (
        "file_path TEXT, name TEXT, kind TEXT, language TEXT, "
        "line INTEGER, end_line INTEGER"
        if malformed_table == "state"
        else "file_path TEXT"
    )
    state_columns = (
        "file_path TEXT, content_hash TEXT, symbol_count INTEGER"
        if malformed_table == "rows"
        else "file_path TEXT, symbol_count INTEGER"
    )
    conn.execute(f"CREATE TABLE ast_symbol_rows({row_columns})")
    conn.execute(f"CREATE TABLE ast_symbol_projection_state({state_columns})")

    result = symbol_projection_is_exact(conn, 10)
    conn.close()

    assert result is False


def test_symbol_upgrade_rejects_inexact_rebuilt_projection(monkeypatch):
    # PR #1253: a rebuilt projection is certified before its marker is written.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols

    conn = _untyped_legacy_connection(symbols_json='{"symbols": []}')
    monkeypatch.setattr(symbols, "_symbol_projection_is_exact", lambda *_args: False)

    with pytest.raises(
        sqlite3.OperationalError, match="^LEGACY_SYMBOL_PROJECTION_INVALID$"
    ):
        symbols.ensure_symbol_rows_backfilled(conn)
    marker_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ast_cache_metadata'"
    ).fetchone()
    conn.close()

    assert marker_table is None


def test_module_exports_exact_focused_surface() -> None:
    from tree_sitter_analyzer import index_snapshot_symbol_counts

    assert index_snapshot_symbol_counts.__all__ == [
        "fallback_symbol_counts",
        "ordinary_edge_counts",
        "ordinary_symbol_counts",
    ]
