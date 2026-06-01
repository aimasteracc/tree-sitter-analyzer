from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache
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
