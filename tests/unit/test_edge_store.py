from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer._ast_cache_schema import apply_migration_v8
from tree_sitter_analyzer._ast_cache_write import write_graph_edges_for_file
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.graph import edge_store as edge_store_module
from tree_sitter_analyzer.graph.edge_store import Edge, EdgeKind, EdgeStore, symbol_node


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


def test_write_graph_edges_handles_empty_imports_and_missing_parent(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "edges.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
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
        def __init__(self, _conn: sqlite3.Connection) -> None:
            pass

        def replace_edges_for_file(self, _file_path: str, _edges: list[Edge]) -> None:
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
