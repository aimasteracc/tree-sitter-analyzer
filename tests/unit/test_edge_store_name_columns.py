"""B1.1 — edges table name columns + SQL pushdown for CALLS queries.

These tests pin the non-breaking first step of B1 (single edge table):
- ``edges`` gains ``caller_name`` / ``callee_name`` / ``file_path`` real columns
  (schema v10) plus indexes on the two name columns.
- The CALLS read paths (``query_callers`` / ``query_callees``) push the name
  filter down to SQL ``WHERE callee_name = ?`` / ``WHERE caller_name = ?``
  instead of pulling the whole ``kind='calls'`` slice into Python.
- Results stay byte-for-byte identical to the pre-change behaviour.

The JSON ``metadata`` blob is intentionally retained (B1.3 removes it).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.graph.edge_store import (
    Edge,
    EdgeKind,
    EdgeStore,
    symbol_node,
)


def _edges_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(edges)").fetchall()}


def _edges_indexes(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA index_list(edges)").fetchall()}


def test_edges_table_has_name_and_file_columns(tmp_path: Path) -> None:
    """edges schema exposes caller_name / callee_name / file_path real columns."""
    store = EdgeStore(str(tmp_path / "edges.db"))
    try:
        cols = _edges_columns(store.conn)
        assert {"caller_name", "callee_name", "file_path"}.issubset(cols)
        # JSON blob is still present (removal is B1.3, not B1.1).
        assert "metadata" in cols
    finally:
        store.close()


def test_edges_table_indexes_name_columns(tmp_path: Path) -> None:
    """Name columns are indexed so CALLS queries can push the filter to SQL."""
    store = EdgeStore(str(tmp_path / "edges.db"))
    try:
        indexes = _edges_indexes(store.conn)
        assert "idx_edges_callee_name" in indexes
        assert "idx_edges_caller_name" in indexes
    finally:
        store.close()


def test_ast_cache_migration_v10_recorded(tmp_path: Path) -> None:
    """A fresh ASTCache stamps schema version 10 and the new edges columns."""
    cache = ASTCache(str(tmp_path))
    try:
        conn = cache.get_conn()
        cols = _edges_columns(conn)
        assert {"caller_name", "callee_name", "file_path"}.issubset(cols)
        row = conn.execute(
            "SELECT version FROM ast_schema_version WHERE version = 10"
        ).fetchone()
        assert row is not None
    finally:
        cache.close()


def test_upsert_populates_name_columns_from_metadata(tmp_path: Path) -> None:
    """upsert_edges writes caller_name/callee_name/file_path real columns."""
    store = EdgeStore(str(tmp_path / "edges.db"))
    try:
        store.upsert_edges(
            [
                Edge(
                    symbol_node("pkg/a.py", "foo", 10),
                    symbol_node("pkg/a.py", "bar", 11),
                    EdgeKind.CALLS,
                    11,
                    metadata={
                        "caller_name": "foo",
                        "callee_name": "bar",
                        "callee_full": "bar",
                    },
                )
            ]
        )
        row = store.conn.execute(
            "SELECT caller_name, callee_name, file_path FROM edges WHERE kind = 'calls'"
        ).fetchone()
        assert row["caller_name"] == "foo"
        assert row["callee_name"] == "bar"
        assert row["file_path"] == "pkg/a.py"
    finally:
        store.close()


def test_calls_query_uses_index_not_full_scan(tmp_path: Path) -> None:
    """query_callers' direct lookup plans use the callee_name index, not a scan."""
    store = EdgeStore(str(tmp_path / "edges.db"))
    try:
        store.upsert_edges(
            [
                Edge(
                    symbol_node("pkg/a.py", "foo", 10),
                    symbol_node("pkg/a.py", "bar", 11),
                    EdgeKind.CALLS,
                    11,
                    metadata={"callee_full": "bar"},
                )
            ]
        )
        plan = store.conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM edges WHERE callee_name = ? AND kind = ?",
            ("bar", "calls"),
        ).fetchall()
        detail = " ".join(str(r[-1]) for r in plan)
        assert "idx_edges_callee_name" in detail
        assert "SCAN edges" not in detail
    finally:
        store.close()


def test_calls_queries_results_unchanged(tmp_path: Path) -> None:
    """Pushed-down CALLS queries return identical entries to the legacy path."""
    store = EdgeStore(str(tmp_path / "edges.db"))
    try:
        store.upsert_edges(
            [
                Edge(
                    symbol_node("pkg/a.py", "foo", 10),
                    symbol_node("pkg/a.py", "bar", 11),
                    EdgeKind.CALLS,
                    11,
                    metadata={"callee_full": "bar"},
                ),
                Edge(
                    symbol_node("pkg/b.py", "baz", 20),
                    symbol_node("pkg/a.py", "foo", 10),
                    EdgeKind.CALLS,
                    21,
                    metadata={"callee_full": "foo"},
                ),
                Edge(
                    symbol_node("pkg/a.py", "bar", 11),
                    symbol_node("pkg/c.py", "qux", 30),
                    EdgeKind.CALLS,
                    31,
                    metadata={"callee_full": "qux"},
                ),
            ]
        )

        assert store.query_callees("foo", "pkg/a.py") == [
            {
                "caller_name": "foo",
                "caller_file": "pkg/a.py",
                "caller_line": 10,
                "callee_name": "bar",
                "callee_full": "bar",
                "callee_file": "pkg/a.py",
                "callee_resolved_file": "",
                "callee_line": 11,
                "depth": 1,
            }
        ]
        callees_depth2 = store.query_callees("foo", "pkg/a.py", max_depth=2)
        assert [(entry["callee_name"], entry["depth"]) for entry in callees_depth2] == [
            ("bar", 1),
            ("qux", 2),
        ]
        callers = store.query_callers("bar", max_depth=2)
        assert [entry["caller_name"] for entry in callers] == ["foo", "baz"]
        assert [
            entry["caller_name"] for entry in store.query_callers("bar", "pkg/a.py")
        ] == ["foo"]
    finally:
        store.close()


def test_indexed_file_populates_name_columns(tmp_path: Path) -> None:
    """Indexing a real file fills the new columns end-to-end via the write path."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def foo():\n    bar()\n\ndef bar():\n    return 1\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.index_file(str(sample))["status"] == "indexed"
        row = (
            cache.get_conn()
            .execute(
                "SELECT caller_name, callee_name, file_path FROM edges "
                "WHERE kind = 'calls' AND callee_name = 'bar'"
            )
            .fetchone()
        )
        assert row is not None
        assert row["caller_name"] == "foo"
        assert row["callee_name"] == "bar"
        assert row["file_path"] == "sample.py"
    finally:
        cache.close()


def test_legacy_v9_db_upgrades_to_v10(tmp_path: Path) -> None:
    """A pre-existing edges table without name columns is migrated to v10."""
    db_path = tmp_path / ".ast-cache" / "cache.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        # Simulate a v8/v9 edges table missing the new columns.
        conn.executescript(
            """
            CREATE TABLE edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                line INTEGER,
                provenance TEXT DEFAULT 'tree-sitter',
                metadata TEXT,
                UNIQUE(source_node_id, target_node_id, kind, line)
            );
            INSERT INTO edges
                (source_node_id, target_node_id, kind, line, provenance, metadata)
            VALUES
                ('pkg/a.py:foo:10', 'pkg/a.py:bar:11', 'calls', 11,
                 'tree-sitter',
                 '{"caller_name": "foo", "callee_name": "bar"}');
            """
        )
        conn.commit()
    finally:
        conn.close()

    # Opening through EdgeStore.ensure_schema must add the columns idempotently.
    store = EdgeStore(str(db_path))
    try:
        cols = _edges_columns(store.conn)
        assert {"caller_name", "callee_name", "file_path"}.issubset(cols)
    finally:
        store.close()
