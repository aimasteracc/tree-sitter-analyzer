"""Tests for whole-project code/doc knowledge graph projection."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.knowledge_graph import (
    JsonKnowledgeGraphStore,
    KnowledgeEdge,
    KnowledgeGraphBuilder,
    KnowledgeGraphSnapshot,
    KnowledgeNode,
    LadybugKnowledgeGraphStore,
)
from tree_sitter_analyzer.knowledge_graph.exporters import to_graphology
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


@pytest.mark.asyncio
async def test_knowledge_graph_tool_reports_missing_sidecar(tmp_path: Path) -> None:
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    result = await tool.execute({"output_format": "json"})

    assert result["success"] is False
    assert result["verdict"] == "ERROR"
    assert "knowledge graph sidecar is missing" in result["error"].lower()


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
