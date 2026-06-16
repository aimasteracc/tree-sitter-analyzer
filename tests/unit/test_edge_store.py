from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer._ast_cache_schema import apply_migration_v8
from tree_sitter_analyzer._ast_cache_write import (
    write_graph_edges_for_file,
)
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.graph import edge_store as edge_store_module
from tree_sitter_analyzer.graph.edge_store import (
    Edge,
    EdgeKind,
    EdgeStore,
    parse_node_id,
    symbol_node,
)


def test_edge_kind_covers_unified_relationship_surface() -> None:
    expected = {
        "calls",
        "imports",
        "extends",
        "implements",
        "references",
        "contains",
        "overrides",
    }
    assert expected.issubset({kind.value for kind in EdgeKind})


def test_edge_store_crud_and_neighbors(tmp_path: Path) -> None:
    db_path = tmp_path / "edges.db"
    store = EdgeStore(str(db_path))
    try:
        source = "pkg/a.py:caller:10"
        middle = "pkg/b.py:callee:20"
        target = "pkg/c.py:leaf:30"
        store.upsert_edges(
            [
                Edge(source, middle, EdgeKind.CALLS, 11),
                Edge(middle, target, EdgeKind.REFERENCES, 21),
            ]
        )

        outgoing = store.get_edges(source, EdgeKind.CALLS)
        assert [edge.target_node_id for edge in outgoing] == [middle]

        subgraph = store.get_neighbors(source, depth=2)
        assert subgraph.nodes == sorted([source, middle, target])
        assert [edge.normalized_kind() for edge in subgraph.edges] == [
            "calls",
            "references",
        ]
    finally:
        store.close()


def test_edge_store_serializes_edges_and_subgraphs(tmp_path: Path) -> None:
    db_path = tmp_path / "edges.db"
    store = EdgeStore(str(db_path))
    try:
        source = "pkg/a.py:caller:10"
        target = "pkg/b.py:callee:20"
        edge = Edge(
            source,
            target,
            EdgeKind.CALLS,
            11,
            metadata={"z": 1},
        )
        store.upsert_edges([edge])

        subgraph = store.get_neighbors(source, depth=1)
        assert edge.to_dict()["metadata"] == {"z": 1}
        assert subgraph.to_dict() == {
            "nodes": [source, target],
            "edges": [edge.to_dict()],
        }
        assert store.conn is not None
    finally:
        store.close()


def test_edge_store_reuses_external_transaction(tmp_path: Path) -> None:
    db_path = tmp_path / "edges.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        conn.commit()
        conn.execute("INSERT INTO marker (value) VALUES ('pending')")

        store = EdgeStore(conn)
        assert store.conn is conn
        store.upsert_edges(
            [
                Edge(
                    "pkg/a.py:caller:10",
                    "pkg/b.py:callee:20",
                    EdgeKind.CALLS,
                    11,
                )
            ]
        )
        store.close()

        other = sqlite3.connect(str(db_path))
        try:
            marker_count = other.execute("SELECT COUNT(*) FROM marker").fetchone()[0]
            assert marker_count == 0
        finally:
            other.close()

        conn.commit()

        other = sqlite3.connect(str(db_path))
        try:
            marker_count = other.execute("SELECT COUNT(*) FROM marker").fetchone()[0]
            edge_count = other.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            assert marker_count == 1
            assert edge_count == 1
        finally:
            other.close()
    finally:
        conn.close()


def test_edge_store_query_directions_filters_and_fallbacks(tmp_path: Path) -> None:
    db_path = tmp_path / "edges.db"
    store = EdgeStore(str(db_path))
    try:
        source = "pkg/a.py:caller:10"
        middle = "pkg/b.py:callee:20"
        leaf = "pkg/c.py:leaf:30"
        store.upsert_edges(
            [
                Edge(source, middle, EdgeKind.CALLS, 11),
                Edge(middle, leaf, "custom", 21),
                Edge(leaf, source, EdgeKind.REFERENCES, 31),
            ]
        )
        store.conn.execute(
            """INSERT INTO edges
               (source_node_id, target_node_id, kind, line, provenance, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("manual", source, EdgeKind.CALLS.value, 1, None, "{broken"),
        )
        store.conn.commit()

        assert [
            edge.source_node_id
            for edge in store.get_edges(source, direction="incoming")
        ] == [
            "manual",
            leaf,
        ]
        assert [
            edge.source_node_id
            for edge in store.get_edges(source, EdgeKind.CALLS, direction="incoming")
        ] == ["manual"]
        assert {
            edge.target_node_id
            for edge in store.get_edges(source, EdgeKind.CALLS, direction="both")
        } == {middle, source}
        assert {
            edge.source_node_id for edge in store.get_edges(source, direction="both")
        } == {source, leaf, "manual"}
        fallback_edge = store.get_edges("manual", EdgeKind.CALLS)[0]
        assert fallback_edge.provenance == "tree-sitter"
        assert fallback_edge.metadata == {}
        assert store.get_neighbors(source, depth=0).to_dict() == {
            "nodes": [source],
            "edges": [],
        }
        assert store.get_neighbors(source, kinds=[EdgeKind.CALLS]).nodes == [
            source,
            middle,
        ]
        assert store.get_neighbors(source, depth=3).nodes == [source, middle, leaf]
        with pytest.raises(ValueError, match="direction"):
            store.get_edges(source, direction="sideways")
    finally:
        store.close()


def test_edge_store_neighbors_deduplicates_null_line_edges(tmp_path: Path) -> None:
    db_path = tmp_path / "edges.db"
    store = EdgeStore(str(db_path))
    try:
        source = "pkg/a.py:caller"
        target = "pkg/b.py:callee"
        store.upsert_edges(
            [
                Edge(source, target, EdgeKind.CALLS),
                Edge(source, target, EdgeKind.CALLS),
            ]
        )

        subgraph = store.get_neighbors(source)
        assert len(subgraph.edges) == 1
    finally:
        store.close()


def test_edge_store_inheritance_tree_and_node_helpers(tmp_path: Path) -> None:
    db_path = tmp_path / "edges.db"
    store = EdgeStore(str(db_path))
    try:
        store.upsert_edges(
            [
                Edge("pkg/model.py:Child:10", "pkg/model.py:Base:1", EdgeKind.EXTENDS),
                Edge("pkg/model.py:Child:10", "class:Protocol", EdgeKind.IMPLEMENTS),
            ]
        )

        assert symbol_node("pkg/model.py", "Child") == "pkg/model.py:Child"
        assert [
            edge["source_node_id"] for edge in store.get_inheritance_tree("Base")
        ] == ["pkg/model.py:Child:10"]
        assert [
            edge["target_node_id"] for edge in store.get_inheritance_tree("Protocol")
        ] == ["class:Protocol"]
    finally:
        store.close()


def _insert_raw_edge(
    conn: sqlite3.Connection,
    source_node_id: str,
    target_node_id: str,
    kind: str,
    file_path: str,
) -> None:
    """Insert one edge row with explicit source/file_path columns.

    Bypasses ``upsert_edges`` so a test can craft the belt-and-braces case
    where ``file_path`` is empty (pre-B1.1 rows) and only the ``source_node_id``
    predicate matches — the path that justified keeping all three deletion
    predicates in ``replace_edges_for_file``.
    """
    conn.execute(
        "INSERT INTO edges (source_node_id, target_node_id, kind, file_path) "
        "VALUES (?, ?, ?, ?)",
        (source_node_id, target_node_id, kind, file_path),
    )


def test_replace_edges_for_file_deletes_all_predicate_kinds(tmp_path: Path) -> None:
    """``replace_edges_for_file`` removes file_path / file-node / symbol-prefix
    rows for the target file and leaves every other file's rows intact (#990).

    The deletion was split from one ``OR`` predicate into three index-driven
    statements; this pins the exact surviving row set so a future refactor that
    drops a predicate (or mis-bounds the prefix range) goes red.
    """
    store = EdgeStore(str(tmp_path / "edges.db"))
    conn = store.conn
    try:
        # Rows that MUST be deleted for "pkg/a.py":
        _insert_raw_edge(conn, "file:pkg/a.py", "module:dep", "imports", "pkg/a.py")
        _insert_raw_edge(
            conn, "pkg/a.py:foo:10", "pkg/a.py:bar:11", "calls", "pkg/a.py"
        )
        # Symbol-prefixed row with EMPTY file_path — only the source-prefix
        # range predicate catches it (the belt-and-braces fallback).
        _insert_raw_edge(conn, "pkg/a.py:Baz:20", "class:Thing", "extends", "")
        # Row whose file_path is pkg/a.py but source is another file's node —
        # caught by the file_path equality predicate.
        _insert_raw_edge(conn, "pkg/z.py:q:2", "pkg/a.py:r:3", "calls", "pkg/a.py")

        # Rows that MUST survive (different file):
        _insert_raw_edge(conn, "pkg/ab.py:x:1", "pkg/ab.py:y:2", "calls", "pkg/ab.py")
        _insert_raw_edge(conn, "file:pkg/ab.py", "module:dep", "imports", "pkg/ab.py")
        conn.commit()

        store.replace_edges_for_file("pkg/a.py", [])

        survivors = sorted(
            row[0] for row in conn.execute("SELECT source_node_id FROM edges")
        )
        assert survivors == ["file:pkg/ab.py", "pkg/ab.py:x:1"]
    finally:
        store.close()


def test_replace_edges_for_file_preserve_calls_keeps_calls_rows(
    tmp_path: Path,
) -> None:
    """``preserve_calls=True`` deletes structural edges for the file but keeps
    its CALLS rows (#990 — same three-predicate split must honor the clause)."""
    store = EdgeStore(str(tmp_path / "edges.db"))
    conn = store.conn
    try:
        _insert_raw_edge(conn, "file:pkg/a.py", "module:dep", "imports", "pkg/a.py")
        _insert_raw_edge(
            conn, "pkg/a.py:foo:10", "pkg/a.py:bar:11", "calls", "pkg/a.py"
        )
        _insert_raw_edge(conn, "pkg/a.py:Baz:20", "class:Thing", "extends", "")
        conn.commit()

        store.replace_edges_for_file("pkg/a.py", [], preserve_calls=True)

        rows = sorted(
            (row[0], row[1])
            for row in conn.execute("SELECT source_node_id, kind FROM edges")
        )
        # Only the CALLS row survives; imports + extends are removed.
        assert rows == [("pkg/a.py:foo:10", "calls")]
    finally:
        store.close()


class _SQLCapturingConnection:
    """Wraps a sqlite3 connection, recording every ``execute`` SQL/params.

    Used to assert the EXACT statements ``replace_edges_for_file`` issues are
    index-driven — so reintroducing the old single ``OR`` predicate (which the
    planner turns into a full table SCAN) goes red here, not just in prod.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        self.calls.append((sql, params))
        return self._conn.execute(sql, params)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def test_replace_edges_for_file_deletes_use_indexes_not_full_scan(
    tmp_path: Path,
) -> None:
    """Every DELETE ``replace_edges_for_file`` issues must be index-driven (#990).

    A single ``file_path = ? OR source_node_id = ? OR source_node_id LIKE ?``
    forced a full ``edges`` SCAN — ~1.8 s per file on a 160k-edge warm cache,
    so the per-file resolve refresh read as a hang. We capture the real SQL the
    method runs and EXPLAIN each DELETE: any plan step that SCANs without an
    index fails the test, so a regression reintroducing the OR goes red.
    """
    real_conn = sqlite3.connect(str(tmp_path / "edges.db"))
    real_conn.row_factory = sqlite3.Row
    store = EdgeStore(real_conn)
    try:
        capture = _SQLCapturingConnection(real_conn)
        store._conn = capture  # type: ignore[assignment]

        store.replace_edges_for_file("pkg/a.py", [])

        delete_calls = [
            (sql, params)
            for sql, params in capture.calls
            if sql.strip().upper().startswith("DELETE")
        ]
        # Exactly three index-driven deletes replace the one OR-scan.
        assert len(delete_calls) == 3

        scan_steps = []
        for sql, params in delete_calls:
            plan = real_conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
            for step in plan:
                detail = step["detail"]
                if "SCAN" in detail and "USING INDEX" not in detail:
                    scan_steps.append(detail)
        assert scan_steps == []
    finally:
        store.close()


def test_edge_store_call_queries_and_node_parser(tmp_path: Path) -> None:
    db_path = tmp_path / "edges.db"
    store = EdgeStore(str(db_path))
    try:
        assert store.has_edges() is False
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

        assert parse_node_id("pkg/a.py:foo:10").name == "foo"
        assert parse_node_id("file:pkg/a.py").file_path == "pkg/a.py"
        assert parse_node_id("module:pkg.a").name == "pkg.a"
        assert parse_node_id("class:Thing").name == "Thing"
        assert parse_node_id("pkg/a.py:foo:not-int").line == 0
        assert parse_node_id("loose").name == "loose"
        assert store.has_edges() is True
        assert store.has_edges(EdgeKind.CALLS) is True
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
        assert store.query_callees("foo", "pkg/other.py") == []
        assert store.query_callees("foo", "pkg/a.py", max_depth=0) == []
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


def test_edge_store_call_queries_deduplicate_and_fallback_to_call_site_file(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "edges.db"
    store = EdgeStore(str(db_path))
    try:
        source = symbol_node("pkg/a.py", "foo", 10)
        target = symbol_node("pkg/b.py", "bar", 20)
        store.upsert_edges(
            [
                Edge(source, target, EdgeKind.CALLS, metadata={"callee_full": "bar"}),
                Edge(source, target, EdgeKind.CALLS, metadata={"callee_full": "bar"}),
            ]
        )

        assert len(store.query_callers("bar")) == 1
        assert [
            entry["caller_name"] for entry in store.query_callers("bar", "pkg/a.py")
        ] == ["foo"]
        assert [
            entry["caller_name"] for entry in store.query_callers("bar", "pkg/b.py")
        ] == ["foo"]
        assert store.query_callers("bar", "pkg/other.py") == []
    finally:
        store.close()


def test_ast_cache_creates_edges_schema(tmp_path: Path) -> None:
    cache = ASTCache(str(tmp_path))
    try:
        conn = sqlite3.connect(cache.db_path)
        conn.row_factory = sqlite3.Row
        try:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(edges)")}
            assert {
                "source_node_id",
                "target_node_id",
                "kind",
                "line",
                "provenance",
                "metadata",
            }.issubset(columns)
            version = conn.execute(
                "SELECT version FROM ast_schema_version WHERE version = 8"
            ).fetchone()
            assert version is not None
        finally:
            conn.close()
    finally:
        cache.close()


def test_edge_store_migration_ignores_operational_error() -> None:
    class FailingConn:
        def executescript(self, _schema: str) -> None:
            raise sqlite3.OperationalError("boom")

    def record_fn(*_args: Any) -> None:
        raise AssertionError("record_fn should not run after DDL failure")

    apply_migration_v8(FailingConn(), record_fn)  # type: ignore[arg-type]


def test_ast_cache_writes_calls_imports_contains_and_extends_edges(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "\n".join(
            [
                "import os",
                "",
                "class Base:",
                "    pass",
                "",
                "class Child(Base):",
                "    def method(self):",
                "        helper()",
                "",
                "def helper():",
                "    return os.getcwd()",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cache = ASTCache(str(tmp_path))
    try:
        result = cache.index_file(str(sample))
        assert result["status"] == "indexed"

        store = EdgeStore(cache.get_conn())
        kinds = {
            row["kind"]
            for row in cache.get_conn()
            .execute("SELECT kind FROM edges ORDER BY kind")
            .fetchall()
        }
        assert {"calls", "imports", "contains", "extends"}.issubset(kinds)

        child_node = symbol_node("sample.py", "Child", 6)
        inheritance = store.get_edges(child_node, EdgeKind.EXTENDS)
        assert inheritance
        assert inheritance[0].target_node_id == symbol_node("sample.py", "Base", 3)

        contains = store.get_edges(child_node, EdgeKind.CONTAINS)
        assert [edge.target_node_id for edge in contains] == [
            symbol_node("sample.py", "method", 7)
        ]

        imports = store.get_edges("file:sample.py", EdgeKind.IMPORTS)
        assert any(edge.target_node_id == "module:os" for edge in imports)
    finally:
        cache.close()


def test_ast_cache_call_queries_read_from_edge_store_when_legacy_edges_missing(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def foo():\n    bar()\n\ndef bar():\n    return 1\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.index_file(str(sample))["status"] == "indexed"
        # B1.3: CALLS rows live only in the unified ``edges`` table.
        assert cache.has_call_edges() is True
        callers = cache.query_callers("bar")
        callees = cache.query_callees("foo", caller_file="sample.py")
        assert [entry["caller_name"] for entry in callers] == ["foo"]
        assert [entry["callee_name"] for entry in callees] == ["bar"]
    finally:
        cache.close()


def test_ast_cache_call_queries_fall_back_when_edge_store_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class BrokenStore:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def has_edges(self, *_args: Any, **_kwargs: Any) -> bool:
            raise sqlite3.OperationalError("missing edges")

    monkeypatch.setattr(edge_store_module, "EdgeStore", BrokenStore)
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.query_callers("missing") == []
        assert cache.query_callees("missing") == []
    finally:
        cache.close()


def test_ast_cache_call_queries_fall_back_when_edge_store_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class EmptyStore:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def has_edges(self, *_args: Any, **_kwargs: Any) -> bool:
            return False

    monkeypatch.setattr(edge_store_module, "EdgeStore", EmptyStore)
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.query_callees("missing") == []
    finally:
        cache.close()


def test_ast_cache_get_call_edges_handles_missing_table(tmp_path: Path) -> None:
    cache = ASTCache(str(tmp_path))
    try:
        # B1.3: CALLS rows live in the unified ``edges`` table. Dropping it
        # exercises the missing-table degrade path for both readers.
        cache.get_conn().execute("DROP TABLE edges")
        cache.get_conn().commit()

        assert cache.get_call_edges() == []
        assert cache.has_call_edges() is False
    finally:
        cache.close()


def test_ast_cache_resolve_only_refreshes_edge_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache = ASTCache(str(tmp_path))
    try:
        monkeypatch.setattr(
            cache,
            "_run_synapse_backfill",
            lambda: {"updated": 1},
        )
        monkeypatch.setattr(
            cache,
            "_refresh_graph_edges_from_cache",
            lambda: {"files": 2, "errors": 0},
        )

        stats = cache.index_project(resolve_only=True)

        assert stats["mode_used"] == "resolve_only"
        assert stats["synapse_backfill"] == {"updated": 1}
        assert stats["edge_store_refresh"] == {"files": 2, "errors": 0}
    finally:
        cache.close()


def test_ast_cache_post_index_backfill_swallows_edge_refresh_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache = ASTCache(str(tmp_path))
    try:
        monkeypatch.setattr(
            cache,
            "backfill_cross_file_edges",
            lambda: {"processed": 1},
        )
        monkeypatch.setattr(cache, "_run_synapse_backfill", lambda: None)

        def fail_refresh(file_paths: list[str] | None = None) -> dict[str, int]:
            assert file_paths == ["sample.py"]
            raise RuntimeError("refresh failed")

        monkeypatch.setattr(cache, "_refresh_graph_edges_from_cache", fail_refresh)
        stats: dict[str, Any] = {"files": [{"file": "sample.py", "status": "indexed"}]}

        cache._post_index_backfill(stats)

        assert stats["cross_file_backfill"] == {"processed": 1}
        assert "edge_store_refresh" not in stats
    finally:
        cache.close()


def test_ast_cache_refresh_edges_from_all_cached_rows_counts_json_errors(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text("def ok():\n    return 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.index_file(str(sample))["status"] == "indexed"
        cache.get_conn().execute(
            """INSERT OR REPLACE INTO ast_index
               (file_path, content_hash, language, mtime_ns, file_size,
                extractor_version, symbols_json, imports_json, structure_json,
                indexed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "broken.py",
                "hash",
                "python",
                0,
                0,
                0,
                "{broken",
                "[]",
                "{}",
                "now",
            ),
        )
        cache.get_conn().commit()

        assert cache._refresh_graph_edges_from_cache() == {"files": 1, "errors": 1}
    finally:
        cache.close()


def test_project_index_refreshes_edge_store_with_resolved_call_metadata(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def foo():\n    bar()\n\ndef bar():\n    return 1\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        stats = cache.index_project(force=True)
        assert stats["indexed"] == 1

        # B1.3: CALLS rows live only in the unified ``edges`` table; querying
        # callees reads them directly (no ast_call_edges to clear).
        callees = cache.query_callees("foo", caller_file="sample.py")
        assert callees == [
            {
                "caller_name": "foo",
                "caller_file": "sample.py",
                "caller_line": 1,
                "callee_name": "bar",
                "callee_full": "bar",
                "callee_file": "sample.py",
                "callee_resolved_file": "sample.py",
                "callee_line": 2,
                "depth": 1,
            }
        ]
    finally:
        cache.close()


def test_write_graph_edges_handles_empty_imports_and_missing_parent(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "edges.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        EdgeStore(conn)
        write_graph_edges_for_file(
            conn,
            "pkg/sample.py",
            "python",
            {
                "symbols": [
                    {"kind": "class", "name": "Child", "line": 3, "parents": ["Base"]},
                    {"kind": "function", "name": "module_call", "line": 8},
                ]
            },
            ["", {"text": "from os import path", "line": 1}],
            [
                {
                    "caller_name": "",
                    "caller_line": 0,
                    "callee_name": "module_call",
                    "callee_full": "module_call",
                    "callee_line": 8,
                }
            ],
        )
        store = EdgeStore(conn)
        kinds = {row["kind"] for row in conn.execute("SELECT kind FROM edges")}
        assert {"calls", "extends", "imports"}.issubset(kinds)
        assert store.get_inheritance_tree("Base")[0]["target_node_id"] == "class:Base"
    finally:
        conn.close()


def test_write_graph_edges_logs_operational_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class BrokenEdgeStore:
        def __init__(self, _conn: sqlite3.Connection, **_kwargs: Any) -> None:
            pass

        def replace_edges_for_file(
            self, _file_path: str, _edges: list[Edge], **_kwargs: Any
        ) -> None:
            raise sqlite3.OperationalError("boom")

    monkeypatch.setattr(edge_store_module, "EdgeStore", BrokenEdgeStore)
    conn = sqlite3.connect(str(tmp_path / "edges.db"))
    try:
        write_graph_edges_for_file(
            conn,
            "pkg/sample.py",
            "python",
            {"symbols": []},
            [],
            [],
        )
    finally:
        conn.close()
