"""Boundary contracts for the focused :mod:`ast_cache` mixins."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from typing import Any

from tree_sitter_analyzer import _ast_cache_database_mixin as database_mixin
from tree_sitter_analyzer import _ast_cache_graph_mixin as graph_mixin
from tree_sitter_analyzer._ast_cache_database_mixin import ASTCacheDatabaseMixin
from tree_sitter_analyzer._ast_cache_graph_mixin import (
    ASTCacheGraphMixin,
    _edge_query,
)
from tree_sitter_analyzer._ast_cache_index_mixin import (
    ASTCacheIndexMixin,
    _cached_graph_rows,
)
from tree_sitter_analyzer._ast_cache_query_mixin import ASTCacheQueryMixin


class _GraphCache(ASTCacheGraphMixin):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _get_conn(self) -> sqlite3.Connection:
        return self.conn


class _IndexCache(ASTCacheIndexMixin):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _get_conn(self) -> sqlite3.Connection:
        return self.conn


class _QueryCache(ASTCacheQueryMixin):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _get_conn(self) -> sqlite3.Connection:
        return self.conn


def _row_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_schema_version_row_returns_none_before_registry_exists() -> None:
    conn = _row_connection()
    try:
        assert database_mixin._schema_version_row(conn, 12) is None
    finally:
        conn.close()


def test_verify_schema_version_backfills_complete_legacy_payload(monkeypatch) -> None:
    backfills: list[tuple[int, str, list[str]]] = []
    missing: list[str] = []
    conn = _row_connection()
    monkeypatch.setattr(
        database_mixin,
        "_check_schema_expectations",
        lambda conn, expectations, target: True,
    )
    monkeypatch.setattr(
        database_mixin,
        "_schema_version_row",
        lambda conn, version: None,
    )
    monkeypatch.setattr(
        database_mixin,
        "_backfill_schema_version_row",
        lambda conn, version, description, target: backfills.append(
            (version, description, target)
        ),
    )

    try:
        database_mixin._verify_schema_version(
            conn,
            12,
            "complete payload",
            object(),
            missing,
        )

        assert backfills == [(12, "complete payload", missing)]
    finally:
        conn.close()


def test_database_close_releases_thread_local_connection() -> None:
    conn = _row_connection()
    cache = object.__new__(ASTCacheDatabaseMixin)
    cache._local = SimpleNamespace(conn=conn)

    cache.close()

    assert cache._local.conn is None
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("close() left the SQLite connection usable")


def test_database_close_is_idempotent_without_connection() -> None:
    cache = object.__new__(ASTCacheDatabaseMixin)
    cache._local = SimpleNamespace(conn=None)

    cache.close()

    assert cache._local.conn is None


def test_edge_query_includes_both_endpoint_filters() -> None:
    sql, params = _edge_query("calls", "caller", "callee", 7)

    assert sql.endswith("AND caller_name = ? AND callee_name = ? LIMIT ?")
    assert params == ["calls", "caller", "callee", 7]


def test_edge_query_omits_unspecified_endpoint_filters() -> None:
    sql, params = _edge_query("imports", None, None, 11)

    assert "caller_name = ?" not in sql
    assert "callee_name = ?" not in sql
    assert sql.endswith("LIMIT ?")
    assert params == ["imports", 11]


def test_get_resolved_call_edges_degrades_when_table_is_missing() -> None:
    conn = _row_connection()
    try:
        assert _GraphCache(conn).get_resolved_call_edges() == []
    finally:
        conn.close()


def test_query_edges_applies_filters_and_limit() -> None:
    conn = _row_connection()
    try:
        conn.execute(
            "CREATE TABLE edges ("
            "kind TEXT, caller_name TEXT, callee_name TEXT, file_path TEXT, "
            "caller_line INTEGER, callee_line INTEGER, "
            "callee_resolved_file TEXT)"
        )
        conn.executemany(
            "INSERT INTO edges VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("calls", "source", "target", "a.py", 1, 2, "b.py"),
                ("calls", "source", "other", "a.py", 3, 4, "c.py"),
            ],
        )

        rows = _GraphCache(conn).query_edges(
            "calls",
            caller_name="source",
            callee_name="target",
            limit=1,
        )

        assert rows == [
            {
                "caller_name": "source",
                "callee_name": "target",
                "file_path": "a.py",
                "caller_line": 1,
                "callee_line": 2,
                "callee_resolved_file": "b.py",
            }
        ]
    finally:
        conn.close()


def test_query_edges_degrades_when_table_is_missing() -> None:
    conn = _row_connection()
    try:
        assert _GraphCache(conn).query_edges("calls", limit=1) == []
    finally:
        conn.close()


def test_query_callers_degrades_when_legacy_bfs_query_fails(monkeypatch) -> None:
    conn = _row_connection()
    monkeypatch.setattr(
        graph_mixin,
        "_edge_store_traversal",
        lambda *args: None,
    )

    def raise_operational_error(*args: Any) -> list[dict[str, Any]]:
        raise sqlite3.OperationalError("legacy table unavailable")

    monkeypatch.setattr(graph_mixin, "_bfs_callers_impl", raise_operational_error)
    try:
        assert _GraphCache(conn).query_callers("target") == []
    finally:
        conn.close()


def test_query_callees_degrades_when_legacy_bfs_query_fails(monkeypatch) -> None:
    conn = _row_connection()
    monkeypatch.setattr(
        graph_mixin,
        "_edge_store_traversal",
        lambda *args: None,
    )

    def raise_operational_error(*args: Any) -> list[dict[str, Any]]:
        raise sqlite3.OperationalError("legacy table unavailable")

    monkeypatch.setattr(graph_mixin, "_bfs_callees_impl", raise_operational_error)
    try:
        assert _GraphCache(conn).query_callees("source") == []
    finally:
        conn.close()


def test_cached_graph_rows_returns_every_row_without_filter() -> None:
    conn = _row_connection()
    try:
        conn.execute(
            "CREATE TABLE ast_index ("
            "file_path TEXT, language TEXT, symbols_json TEXT, imports_json TEXT)"
        )
        conn.executemany(
            "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
            [
                ("a.py", "python", "{}", "[]"),
                ("b.py", "python", "{}", "[]"),
            ],
        )

        rows = _cached_graph_rows(conn, None)

        assert [row["file_path"] for row in rows] == ["a.py", "b.py"]
    finally:
        conn.close()


def test_cached_graph_rows_skips_missing_requested_files() -> None:
    conn = _row_connection()
    try:
        conn.execute(
            "CREATE TABLE ast_index ("
            "file_path TEXT, language TEXT, symbols_json TEXT, imports_json TEXT)"
        )
        conn.execute(
            "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
            ("a.py", "python", "{}", "[]"),
        )

        rows = _cached_graph_rows(conn, ["missing.py", "a.py"])

        assert [row["file_path"] for row in rows] == ["a.py"]
    finally:
        conn.close()


def test_worker_count_ignores_invalid_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("TSA_INDEX_WORKERS", "many")

    workers = _IndexCache._resolve_worker_count(3, [object()])

    assert workers == 3


def test_get_functions_by_file_returns_empty_for_unknown_file() -> None:
    conn = _row_connection()
    try:
        conn.execute(
            "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
        )

        assert _QueryCache(conn).get_functions_by_file("missing.py") == []
    finally:
        conn.close()


def test_get_symbols_by_kind_returns_flat_rows() -> None:
    conn = _row_connection()
    try:
        conn.execute(
            "CREATE TABLE ast_symbol_rows ("
            "name TEXT, file_path TEXT, line INTEGER, end_line INTEGER, "
            "language TEXT, kind TEXT)"
        )
        conn.execute(
            "INSERT INTO ast_symbol_rows VALUES (?, ?, ?, ?, ?, ?)",
            ("run", "worker.py", 3, 5, "python", "function"),
        )

        rows = _QueryCache(conn).get_symbols_by_kind("function", limit=1)

        assert rows == [
            {
                "name": "run",
                "file": "worker.py",
                "line": 3,
                "end_line": 5,
                "language": "python",
                "kind": "function",
            }
        ]
    finally:
        conn.close()


def test_get_symbols_by_kind_degrades_when_flat_table_is_missing() -> None:
    conn = _row_connection()
    try:
        assert _QueryCache(conn).get_symbols_by_kind("function") == []
    finally:
        conn.close()
