"""Tests for whole-project code/doc knowledge graph projection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.graph.edge_store import Edge, EdgeStore, symbol_node
from tree_sitter_analyzer.knowledge_graph import (
    JsonKnowledgeGraphStore,
    KnowledgeEdge,
    KnowledgeGraphBuilder,
    KnowledgeGraphSnapshot,
    KnowledgeNode,
    LadybugKnowledgeGraphStore,
)
from tree_sitter_analyzer.knowledge_graph.builder import (
    _as_int_or_none,
    _collect_md_files,
    _combine_weight,
    _json_dict,
    _node_from_ref,
    _package_for_file,
)
from tree_sitter_analyzer.knowledge_graph.exporters import (
    _file_from_node_id,
    aggregate_package_graph,
    summarize,
    to_graphology,
)
from tree_sitter_analyzer.knowledge_graph.stores import LadybugUnavailableError
from tree_sitter_analyzer.mcp.tools.knowledge_graph_tool import (
    CodeGraphKnowledgeGraphTool,
    CodeGraphKnowledgeIndexTool,
    _compact_sync_report,
)


def test_builder_projects_ast_cache_and_markdown_links(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "def helper():\n    return 1\n\n\ndef main():\n    return helper()\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "See `src/app.py` for the implementation.\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()

    snapshot = KnowledgeGraphBuilder(str(tmp_path)).build()

    node_ids = {node.id for node in snapshot.nodes}
    assert "file:src/app.py" in node_ids
    assert "doc:README.md" in node_ids
    assert "src/app.py:helper:1" in node_ids
    edge_kinds = {edge.kind for edge in snapshot.edges}
    assert "contains" in edge_kinds
    assert "doc_links" in edge_kinds
    assert snapshot.stats["node_kinds"]["markdown"] == 1
    assert snapshot.stats["edge_kinds"]["doc_links"] == 1


def test_builder_rejects_invalid_bounds(tmp_path: Path) -> None:
    builder = KnowledgeGraphBuilder(str(tmp_path))

    with pytest.raises(ValueError, match="level"):
        builder.build(level="docs")
    with pytest.raises(ValueError, match="max_nodes"):
        builder.build(max_nodes=0)
    with pytest.raises(ValueError, match="max_edges"):
        builder.build(max_edges=0)


def test_builder_focus_and_no_symbol_options_filter_graph(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text("def kept():\n    return 1\n", encoding="utf-8")
    (tmp_path / "skip.py").write_text(
        "def skipped():\n    return 2\n", encoding="utf-8"
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()

    snapshot = KnowledgeGraphBuilder(str(tmp_path)).build(
        focus="keep.py",
        include_docs=False,
        include_symbols=False,
    )

    node_ids = {node.id for node in snapshot.nodes}
    assert "file:keep.py" in node_ids
    assert "file:skip.py" not in node_ids
    assert "keep.py:kept:1" not in node_ids


def test_builder_projects_symbol_file_and_package_edges(tmp_path: Path) -> None:
    (tmp_path / "pkg1").mkdir()
    (tmp_path / "pkg2").mkdir()
    (tmp_path / "pkg1" / "a.py").write_text(
        "def main():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg2" / "b.py").write_text(
        "def helper():\n    return 2\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
        conn = cache.get_conn()
        EdgeStore(conn).upsert_edges(
            [
                Edge(
                    source_node_id=symbol_node("pkg1/a.py", "main", 1),
                    target_node_id=symbol_node("pkg2/b.py", "helper", 1),
                    kind="calls",
                    line=2,
                    metadata={
                        "language": "python",
                        "callee_resolved_file": "pkg2/b.py",
                    },
                )
            ]
        )
        conn.commit()
    finally:
        cache.close()

    snapshot = KnowledgeGraphBuilder(str(tmp_path)).build(level="symbol")

    edges = {(edge.source, edge.target, edge.kind) for edge in snapshot.edges}
    assert (
        "pkg1/a.py:main:1",
        "pkg2/b.py:helper:1",
        "calls",
    ) in edges
    assert ("file:pkg1/a.py", "file:pkg2/b.py", "calls") in edges
    assert ("package:pkg1", "package:pkg2", "calls") in edges


def test_builder_handles_missing_ast_table(tmp_path: Path) -> None:
    cache = ASTCache(str(tmp_path))
    try:
        conn = cache.get_conn()
        conn.execute("DROP TABLE ast_index")
        conn.commit()
    finally:
        cache.close()

    snapshot = KnowledgeGraphBuilder(str(tmp_path)).build()

    assert snapshot.stats["node_count"] == 0
    assert snapshot.stats["edge_count"] == 0


def test_builder_private_defensive_paths(tmp_path: Path) -> None:
    builder = KnowledgeGraphBuilder(str(tmp_path))
    nodes: dict[str, KnowledgeNode] = {}
    edges: dict[str, KnowledgeEdge] = {}

    builder._add_symbol_nodes(  # noqa: SLF001 - targeted branch coverage
        nodes,
        edges,
        "broken.py",
        {"symbols_json": "{bad", "language": "python"},
    )
    builder._add_symbol_nodes(  # noqa: SLF001 - targeted branch coverage
        nodes,
        edges,
        "empty.py",
        {
            "symbols_json": '{"symbols": [[], {"name": ""}, {"name": "ok"}]}',
            "language": "python",
        },
    )

    assert "empty.py:ok" in nodes
    assert _as_int_or_none("bad") is None
    assert _json_dict("{bad") == {}
    assert _package_for_file("src/main/java/com/example/App.java") == "com.example"
    assert _package_for_file("Main.java") == "<root>"
    assert _package_for_file("src/main/java/App.java") == "src/main/java"
    assert _collect_md_files(str(tmp_path), ["missing/**/*.md"]) == []
    assert _json_dict({"ok": True}) == {"ok": True}
    assert _json_dict("") == {}
    ref_node = _node_from_ref(
        "orphan.py:missing:7",
        SimpleNamespace(file_path="orphan.py", name="", line=7),
        "symbol",
    )
    assert ref_node.label == "orphan.py"


def test_builder_handles_edge_query_error_and_skip_paths(tmp_path: Path) -> None:
    builder = KnowledgeGraphBuilder(str(tmp_path))

    class BrokenConn:
        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("boom")

    class BrokenCache:
        def get_conn(self) -> BrokenConn:
            return BrokenConn()

    assert builder._read_ast_rows(BrokenCache()) == []  # noqa: SLF001
    assert builder._iter_file_relationships(BrokenCache(), focus=None) == []  # noqa: SLF001

    edge = KnowledgeEdge(id="edge:a", source="a", target="b", kind="calls")
    combined = _combine_weight(edge, edge)
    assert combined.weight == 2.0


def test_builder_relationship_helpers_cover_skip_and_placeholder_paths(
    tmp_path: Path,
) -> None:
    builder = KnowledgeGraphBuilder(str(tmp_path))

    class Conn:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self.rows = rows

        def execute(self, *_args: object, **_kwargs: object) -> object:
            return self

        def fetchall(self) -> list[dict[str, object]]:
            return self.rows

    class Cache:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self.rows = rows

        def get_conn(self) -> Conn:
            return Conn(self.rows)

    nodes = {
        "package:pkg1": KnowledgeNode(id="package:pkg1", kind="package", label="pkg1"),
        "package:pkg2": KnowledgeNode(id="package:pkg2", kind="package", label="pkg2"),
        "file:pkg1/a.py": KnowledgeNode(
            id="file:pkg1/a.py",
            kind="file",
            label="a.py",
            file_path="pkg1/a.py",
        ),
    }
    edges: dict[str, KnowledgeEdge] = {}
    relationship_rows = [
        {
            "kind": "calls",
            "file_path": "pkg1/a.py",
            "target_node_id": "pkg1/a.py:local:1",
            "callee_resolved_file": "pkg1/local.py",
            "line": 1,
        },
        {
            "kind": "calls",
            "file_path": "pkg1/a.py",
            "target_node_id": "pkg2/b.py:remote:1",
            "callee_resolved_file": "pkg2/b.py",
            "line": 2,
        },
        {
            "kind": "calls",
            "file_path": "pkg3/missing.py",
            "target_node_id": "pkg2/b.py:remote:1",
            "callee_resolved_file": "pkg2/b.py",
            "line": 3,
        },
    ]

    assert (
        builder._iter_file_relationships(  # noqa: SLF001
            Cache(relationship_rows),
            focus="nomatch",
        )
        == []
    )
    builder._add_package_edges(Cache(relationship_rows), nodes, edges, focus=None)  # noqa: SLF001
    builder._add_file_edges(Cache(relationship_rows), nodes, edges, focus=None)  # noqa: SLF001

    assert ("package:pkg1", "package:pkg2", "calls") in {
        (edge.source, edge.target, edge.kind) for edge in edges.values()
    }


def test_builder_symbol_edges_cover_focus_and_missing_node_paths(
    tmp_path: Path,
) -> None:
    builder = KnowledgeGraphBuilder(str(tmp_path))

    class BrokenConn:
        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("boom")

    class BrokenCache:
        def get_conn(self) -> BrokenConn:
            return BrokenConn()

    nodes: dict[str, KnowledgeNode] = {}
    edges: dict[str, KnowledgeEdge] = {}
    builder._add_symbol_edges(BrokenCache(), nodes, edges, focus=None)  # noqa: SLF001
    assert edges == {}

    class Conn:
        def execute(self, *_args: object, **_kwargs: object) -> object:
            return self

        def fetchall(self) -> list[dict[str, object]]:
            return [
                {
                    "source_node_id": "src.py:caller:1",
                    "target_node_id": "dst.py:callee:2",
                    "kind": "calls",
                    "line": 4,
                    "provenance": "",
                    "metadata": "{bad",
                    "file_path": "src.py",
                    "callee_resolved_file": "resolved.py",
                },
                {
                    "source_node_id": "missing-source",
                    "target_node_id": "missing-target",
                    "kind": "references",
                    "line": 5,
                    "provenance": "test",
                    "metadata": "{}",
                    "file_path": "",
                    "callee_resolved_file": "",
                },
            ]

    class Cache:
        def get_conn(self) -> Conn:
            return Conn()

    builder._add_symbol_edges(Cache(), nodes, edges, focus="nomatch")  # noqa: SLF001
    assert edges == {}
    builder._add_symbol_edges(Cache(), nodes, edges, focus=None)  # noqa: SLF001

    assert ("src.py:caller:1", "resolved.py:callee:2", "calls") in {
        (edge.source, edge.target, edge.kind) for edge in edges.values()
    }


def test_builder_doc_link_edge_cases(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "Missing `absent.py`\nSelf `guide.md`\n",
        encoding="utf-8",
    )
    nodes: dict[str, KnowledgeNode] = {}
    edges: dict[str, KnowledgeEdge] = {}
    builder = KnowledgeGraphBuilder(str(tmp_path))

    builder._add_doc_links(nodes, edges, ["docs/*.md"], focus="no-match")  # noqa: SLF001
    assert nodes == {}

    builder._add_doc_links(nodes, edges, ["docs/*.md"], focus=None)  # noqa: SLF001

    assert "doc:docs/guide.md" in nodes
    assert any(node.kind == "markdown" for node in nodes.values())


def test_builder_doc_links_cover_read_error_focus_and_missing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "See `../target.py` and `../other.py`.\n",
        encoding="utf-8",
    )
    (tmp_path / "target.py").write_text("x = 1\n", encoding="utf-8")
    builder = KnowledgeGraphBuilder(str(tmp_path))
    nodes: dict[str, KnowledgeNode] = {}
    edges: dict[str, KnowledgeEdge] = {}

    real_read_text = Path.read_text

    def _raising_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "guide.md":
            raise OSError("blocked")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _raising_read_text)
    builder._add_doc_links(nodes, edges, ["docs/*.md"], focus=None)  # noqa: SLF001
    assert edges == {}

    monkeypatch.setattr(Path, "read_text", real_read_text)
    builder._add_doc_links(nodes, edges, ["docs/*.md"], focus=None)  # noqa: SLF001

    assert ("doc:docs/guide.md", "file:target.py", "doc_links") in {
        (edge.source, edge.target, edge.kind) for edge in edges.values()
    }
    assert "file:target.py" in nodes
    assert "file:other.py" not in nodes


def test_builder_doc_links_resolve_package_prefixed_targets(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "tree_sitter_analyzer").mkdir()
    (tmp_path / "tree_sitter_analyzer" / "module.py").write_text(
        "x = 1\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "guide.md").write_text(
        "See `module.py`.\n",
        encoding="utf-8",
    )
    nodes: dict[str, KnowledgeNode] = {}
    edges: dict[str, KnowledgeEdge] = {}

    KnowledgeGraphBuilder(str(tmp_path))._add_doc_links(  # noqa: SLF001
        nodes,
        edges,
        ["docs/*.md"],
        focus=None,
    )

    assert "file:tree_sitter_analyzer/module.py" in nodes
    assert ("doc:docs/guide.md", "file:tree_sitter_analyzer/module.py") in {
        (edge.source, edge.target) for edge in edges.values()
    }


def test_builder_snapshot_marks_truncation_limits(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()

    snapshot = KnowledgeGraphBuilder(str(tmp_path)).build(max_nodes=1, max_edges=1)

    assert snapshot.truncated is True
    assert snapshot.stats["max_nodes"] == 1
    assert snapshot.stats["max_edges"] == 1
    assert snapshot.stats["node_count"] == 1


def test_json_store_round_trips_snapshot(tmp_path: Path) -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py")
        ],
        edges=[],
        stats={"node_count": 1, "edge_count": 0},
    )
    store = JsonKnowledgeGraphStore(str(tmp_path))

    write_result = store.write(snapshot)
    payload = store.read()

    written_path = Path(write_result["path"])
    assert written_path.parent.name == ".ast-cache"
    assert written_path.name == "knowledge-graph.json"
    assert payload["schema"] == "tsa.knowledge_graph.v1"
    assert payload["nodes"][0]["id"] == "file:a.py"
    assert store.status()["exists"] is True


def test_graphology_export_filters_docs_lod_exactly() -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="doc:README.md", kind="markdown", label="README.md"),
            KnowledgeNode(
                id="file:src/app.py",
                kind="file",
                label="src/app.py",
                file_path="src/app.py",
            ),
            KnowledgeNode(
                id="src/app.py:main:1",
                kind="function",
                label="main",
                file_path="src/app.py",
            ),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:doc",
                source="doc:README.md",
                target="file:src/app.py",
                kind="doc_links",
            ),
            KnowledgeEdge(
                id="edge:contains",
                source="file:src/app.py",
                target="src/app.py:main:1",
                kind="contains",
            ),
        ],
        stats={"node_count": 3, "edge_count": 2},
    )

    graph = to_graphology(snapshot, lod="docs")

    assert graph["attributes"]["lod"] == "docs"
    assert [node["key"] for node in graph["nodes"]] == [
        "doc:README.md",
        "file:src/app.py",
    ]
    assert [edge["key"] for edge in graph["edges"]] == ["edge:doc"]
    assert graph["stats"]["export_node_count"] == 2
    assert graph["stats"]["export_edge_count"] == 1


def test_snapshot_direct_graphology_serialization_includes_metadata() -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(
                id="file:a.py",
                kind="file",
                label="a.py",
                file_path="a.py",
                language="python",
                line=3,
                package="<root>",
                metadata={"rank": 1},
            )
        ],
        edges=[
            KnowledgeEdge(
                id="edge:calls",
                source="file:a.py",
                target="file:a.py",
                kind="calls",
                weight=2.5,
                provenance="unit",
                line=4,
                metadata={"hot": True},
            )
        ],
        stats={"node_count": 1, "edge_count": 1},
        truncated=True,
    )

    graph = snapshot.to_graphology()

    assert graph["nodes"][0]["attributes"]["rank"] == 1
    assert graph["edges"][0]["attributes"]["hot"] is True
    assert graph["metadata"]["truncated"] is True


def test_graphology_export_package_focus_and_summary() -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(
                id="file:pkg1/a.py",
                kind="file",
                label="a.py",
                file_path="pkg1/a.py",
            ),
            KnowledgeNode(
                id="file:pkg2/b.py",
                kind="file",
                label="b.py",
                file_path="pkg2/b.py",
            ),
            KnowledgeNode(id="pkg1/a.py:main:1", kind="method", label="main"),
            KnowledgeNode(id="odd", kind="custom", label="odd"),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:call",
                source="file:pkg1/a.py",
                target="file:pkg2/b.py",
                kind="calls",
            ),
            KnowledgeEdge(
                id="edge:symbol",
                source="pkg1/a.py:main:1",
                target="odd",
                kind="references",
            ),
        ],
        stats={
            "node_count": 4,
            "edge_count": 2,
            "node_kinds": {"file": 2, "method": 1, "custom": 1},
            "edge_kinds": {"calls": 1, "references": 1},
        },
    )

    package = aggregate_package_graph(snapshot)
    graph = to_graphology(snapshot, lod="package", focus="pkg1", max_nodes=1)
    summary = summarize(snapshot)

    assert package.stats["lod"] == "package"
    assert graph["attributes"]["lod"] == "package"
    assert graph["stats"]["export_truncated"] is True
    assert summary["topology"]["node_kinds"]["custom"] == 1


def test_graphology_export_empty_and_doc_target_branches() -> None:
    empty = KnowledgeGraphSnapshot(nodes=[], edges=[], stats={})
    empty_graph = to_graphology(empty, lod="file")
    assert empty_graph["nodes"] == []

    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="doc:README.md", kind="markdown", label="README.md"),
            KnowledgeNode(id="doc:docs/guide.md", kind="markdown", label="guide.md"),
            KnowledgeNode(id="doc:docs/other.md", kind="markdown", label="other.md"),
            KnowledgeNode(id="doc:docs/else.md", kind="markdown", label="else.md"),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:doc-doc",
                source="doc:README.md",
                target="doc:docs/guide.md",
                kind="doc_links",
            ),
            KnowledgeEdge(
                id="edge:unfocused",
                source="doc:docs/other.md",
                target="doc:docs/else.md",
                kind="doc_links",
            ),
        ],
        stats={"node_count": 4, "edge_count": 2},
    )

    graph = to_graphology(snapshot, lod="docs", focus="README")
    target_focus_graph = to_graphology(snapshot, lod="docs", focus="guide")

    assert [edge["key"] for edge in graph["edges"]] == ["edge:doc-doc"]
    assert [edge["key"] for edge in target_focus_graph["edges"]] == ["edge:doc-doc"]
    assert _file_from_node_id("doc:README.md") == "README.md"


def test_ladybug_store_reports_missing_optional_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.stores.importlib.util.find_spec",
        lambda name: None,
    )

    def _missing_ladybug(name: str) -> object:
        if name == "ladybug":
            raise ModuleNotFoundError(name)
        raise AssertionError(name)

    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.stores.importlib.import_module",
        _missing_ladybug,
    )
    store = LadybugKnowledgeGraphStore(str(tmp_path))
    snapshot = KnowledgeGraphSnapshot(nodes=[], edges=[], stats={})

    with pytest.raises(LadybugUnavailableError) as exc_info:
        store.write(snapshot)

    assert "tree-sitter-analyzer[graph]" in str(exc_info.value)
    assert store.status()["available"] is False


def test_ladybug_store_writes_snapshot_when_optional_dependency_exists(
    tmp_path: Path,
) -> None:
    if not LadybugKnowledgeGraphStore.available():
        pytest.skip("tracked: optional LadybugDB extra is not installed")
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py"),
            KnowledgeNode(id="file:b.py", kind="file", label="b.py", file_path="b.py"),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:imports",
                source="file:a.py",
                target="file:b.py",
                kind="imports",
            )
        ],
        stats={"node_count": 2, "edge_count": 1},
    )
    store = LadybugKnowledgeGraphStore(str(tmp_path))

    result = store.write(snapshot)

    assert result["node_count"] == 2
    assert result["edge_count"] == 1
    assert store.status()["available"] is True


@pytest.mark.asyncio
async def test_knowledge_index_tool_status_is_readable(tmp_path: Path) -> None:
    tool = CodeGraphKnowledgeIndexTool(str(tmp_path))

    result = await tool.execute({"mode": "status", "output_format": "json"})

    assert result["success"] is True
    assert result["mode"] == "status"
    assert result["json_store"]["exists"] is False
    status_path = Path(result["json_store"]["path"])
    assert status_path.parent.name == ".ast-cache"
    assert status_path.name == "knowledge-graph.json"


def test_knowledge_index_tool_rejects_invalid_arguments(tmp_path: Path) -> None:
    tool = CodeGraphKnowledgeIndexTool(str(tmp_path))

    with pytest.raises(ValueError, match="mode"):
        tool.validate_arguments({"mode": "refresh"})
    with pytest.raises(ValueError, match="level"):
        tool.validate_arguments({"level": "class"})
    with pytest.raises(ValueError, match="backend"):
        tool.validate_arguments({"backend": "sqlite"})
    with pytest.raises(ValueError, match="max_nodes"):
        tool.validate_arguments({"max_nodes": 0})


@pytest.mark.asyncio
async def test_knowledge_index_tool_reports_missing_project_root() -> None:
    tool = CodeGraphKnowledgeIndexTool()

    result = await tool.execute({"output_format": "json"})

    assert result["success"] is False
    assert result["error"] == "project_root not set"


@pytest.mark.asyncio
async def test_knowledge_index_tool_build_writes_hybrid_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py")
        ],
        edges=[],
        stats={"node_count": 1, "edge_count": 0},
    )

    class FakeBuilder:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        def build(self, **kwargs: object) -> KnowledgeGraphSnapshot:
            assert kwargs["level"] == "file"
            assert kwargs["focus"] == "src"
            assert kwargs["include_docs"] is False
            assert kwargs["include_symbols"] is True
            return snapshot

    class FakeStore:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        def write(self, written_snapshot: KnowledgeGraphSnapshot) -> dict[str, object]:
            assert written_snapshot is snapshot
            return {
                "path": self.project_root,
                "node_count": len(written_snapshot.nodes),
            }

        def status(self) -> dict[str, object]:
            return {"exists": True}

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_index_tool.KnowledgeGraphBuilder",
        FakeBuilder,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_index_tool.JsonKnowledgeGraphStore",
        FakeStore,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_index_tool.LadybugKnowledgeGraphStore",
        FakeStore,
    )
    tool = CodeGraphKnowledgeIndexTool(str(tmp_path))

    result = await tool.execute(
        {
            "mode": "build",
            "backend": "both",
            "focus": "src",
            "include_docs": False,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["storage"]["backend"] == "hybrid"
    assert result["storage"]["json_store"]["node_count"] == 1
    assert result["storage"]["ladybug_store"]["node_count"] == 1


@pytest.mark.asyncio
async def test_knowledge_index_tool_update_adds_compact_sync_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = KnowledgeGraphSnapshot(nodes=[], edges=[], stats={})

    class FakeBuilder:
        def __init__(self, _project_root: str) -> None:
            pass

        def build(self, **_kwargs: object) -> KnowledgeGraphSnapshot:
            return snapshot

    class FakeJsonStore:
        def __init__(self, _project_root: str) -> None:
            pass

        def write(self, _snapshot: KnowledgeGraphSnapshot) -> dict[str, object]:
            return {"path": "kg.json"}

    class FakeLadybugStore(FakeJsonStore):
        pass

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_index_tool.KnowledgeGraphBuilder",
        FakeBuilder,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_index_tool.JsonKnowledgeGraphStore",
        FakeJsonStore,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_index_tool.LadybugKnowledgeGraphStore",
        FakeLadybugStore,
    )
    tool = CodeGraphKnowledgeIndexTool(str(tmp_path))
    monkeypatch.setattr(
        tool,
        "_run_incremental_sync",
        lambda max_files: {
            "scanned": max_files,
            "details": [{"file": "a.py"}],
            "updated": ["a.py"],
        },
    )

    result = await tool.execute(
        {"mode": "update", "max_files": 7, "output_format": "json"}
    )

    assert result["success"] is True
    assert result["incremental_sync"] == {"scanned": 7}


@pytest.mark.asyncio
async def test_knowledge_index_tool_reports_ladybug_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBuilder:
        def __init__(self, _project_root: str) -> None:
            pass

        def build(self, **_kwargs: object) -> KnowledgeGraphSnapshot:
            return KnowledgeGraphSnapshot(nodes=[], edges=[], stats={})

    class FakeJsonStore:
        def __init__(self, _project_root: str) -> None:
            pass

        def write(self, _snapshot: KnowledgeGraphSnapshot) -> dict[str, object]:
            return {}

    class MissingLadybugStore(FakeJsonStore):
        def write(self, _snapshot: KnowledgeGraphSnapshot) -> dict[str, object]:
            raise LadybugUnavailableError("missing ladybug")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_index_tool.KnowledgeGraphBuilder",
        FakeBuilder,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_index_tool.JsonKnowledgeGraphStore",
        FakeJsonStore,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_index_tool.LadybugKnowledgeGraphStore",
        MissingLadybugStore,
    )
    tool = CodeGraphKnowledgeIndexTool(str(tmp_path))

    result = await tool.execute(
        {"mode": "build", "backend": "ladybug", "output_format": "json"}
    )

    assert result["success"] is False
    assert result["error"] == "missing ladybug"


def test_knowledge_index_tool_write_snapshot_backend_selection(
    tmp_path: Path,
) -> None:
    snapshot = KnowledgeGraphSnapshot(nodes=[], edges=[], stats={})
    tool = CodeGraphKnowledgeIndexTool(str(tmp_path))
    json_store = SimpleNamespace(write=lambda _snapshot: {"json": True})
    ladybug_store = SimpleNamespace(write=lambda _snapshot: {"ladybug": True})

    assert tool._write_snapshot(  # noqa: SLF001
        snapshot, json_store, ladybug_store, "ladybug"
    ) == {"backend": "ladybug", "ladybug_store": {"ladybug": True}}
    with pytest.raises(ValueError, match="backend"):
        tool._write_snapshot(snapshot, json_store, ladybug_store, "bad")  # noqa: SLF001


def test_knowledge_index_tool_incremental_sync_closes_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    class FakeResult:
        def to_dict(self) -> dict[str, object]:
            return {"synced": True}

    class FakeCache:
        def __init__(self, project_root: str) -> None:
            events.append(("cache", project_root))

        def close(self) -> None:
            events.append("closed")

    class FakeIncrementalSync:
        def __init__(self, cache: FakeCache) -> None:
            self.cache = cache

        def sync(self, *, max_files: int) -> FakeResult:
            events.append(("sync", max_files))
            return FakeResult()

    monkeypatch.setattr("tree_sitter_analyzer.ast_cache.ASTCache", FakeCache)
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_index_tool.IncrementalSync",
        FakeIncrementalSync,
    )

    result = CodeGraphKnowledgeIndexTool(str(tmp_path))._run_incremental_sync(7)  # noqa: SLF001

    assert result == {"synced": True}
    assert events == [("cache", str(tmp_path)), ("sync", 7), "closed"]


@pytest.mark.asyncio
async def test_knowledge_graph_tool_reports_missing_sidecar(tmp_path: Path) -> None:
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    result = await tool.execute({"output_format": "json"})

    assert result["success"] is False
    assert result["verdict"] == "ERROR"
    assert "knowledge graph sidecar is missing" in result["error"].lower()


@pytest.mark.asyncio
async def test_knowledge_graph_tool_reports_missing_project_root() -> None:
    tool = CodeGraphKnowledgeGraphTool()

    result = await tool.execute({"output_format": "json"})

    assert result["success"] is False
    assert result["error"] == "project_root not set"


@pytest.mark.asyncio
async def test_knowledge_graph_tool_exports_graphology(tmp_path: Path) -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="doc:README.md", kind="markdown", label="README.md"),
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py"),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:doc",
                source="doc:README.md",
                target="file:a.py",
                kind="doc_links",
            )
        ],
        stats={"node_count": 2, "edge_count": 1},
    )
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    result = await tool.execute(
        {"lod": "docs", "max_nodes": 5, "max_edges": 5, "output_format": "json"}
    )

    assert result["success"] is True
    assert result["graph"]["attributes"]["schema"] == "tsa.graphology.v1"
    assert [node["key"] for node in result["graph"]["nodes"]] == [
        "doc:README.md",
        "file:a.py",
    ]
    assert [edge["key"] for edge in result["graph"]["edges"]] == ["edge:doc"]


@pytest.mark.asyncio
async def test_knowledge_graph_tool_exports_raw_and_summary(tmp_path: Path) -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py")
        ],
        edges=[],
        stats={"node_count": 1, "edge_count": 0, "node_kinds": {"file": 1}},
    )
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    raw = await tool.execute({"export_format": "raw", "output_format": "json"})
    summary = await tool.execute({"export_format": "summary", "output_format": "json"})

    assert raw["graph"]["schema"] == "tsa.knowledge_graph.v1"
    assert summary["graph"]["topology"]["node_kinds"]["file"] == 1


def test_knowledge_graph_tool_rejects_invalid_arguments(tmp_path: Path) -> None:
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    with pytest.raises(ValueError, match="export_format"):
        tool.validate_arguments({"export_format": "dot"})
    with pytest.raises(ValueError, match="lod"):
        tool.validate_arguments({"lod": "class"})
    with pytest.raises(ValueError, match="max_nodes"):
        tool.validate_arguments({"max_nodes": 0})


def test_compact_sync_report_drops_per_file_payloads() -> None:
    compact = _compact_sync_report(
        {
            "scanned": 10,
            "deleted_files": 0,
            "details": [{"file": "a.py"}],
            "deleted": ["b.py"],
            "updated": ["c.py"],
            "new": ["d.py"],
        }
    )

    assert compact == {"scanned": 10, "deleted_files": 0}
