"""Tests for whole-project code/doc knowledge graph projection."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cli.special_commands import (
    SpecialCommandContext,
    _handle_knowledge_graph_index,
)
from tree_sitter_analyzer.graph.edge_store import Edge, EdgeStore
from tree_sitter_analyzer.knowledge_graph import (
    JsonKnowledgeGraphStore,
    KnowledgeEdge,
    KnowledgeGraphBuilder,
    KnowledgeGraphSnapshot,
    KnowledgeNode,
    LadybugKnowledgeGraphStore,
)
from tree_sitter_analyzer.knowledge_graph.builder import (
    _iter_markdown_files,
    _json_obj,
    _nullable_int,
    _resolve_project_ref,
)
from tree_sitter_analyzer.knowledge_graph.exporters import (
    aggregate_package_graph,
    summarize,
    to_graphology,
)
from tree_sitter_analyzer.knowledge_graph.html_viewer import to_html_viewer
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


def test_builder_respects_caps_and_skips_bad_markdown_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "one.py").write_text(
        "def one():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "src" / "two.py").write_text(
        "def two():\n    return 2\n", encoding="utf-8"
    )
    (tmp_path / "guide.md").write_text(
        "Missing `missing.py`, present `src/one.py`.\n",
        encoding="utf-8",
    )
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.md").write_text("`src/one.py`\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()

    snapshot = KnowledgeGraphBuilder(str(tmp_path)).build(max_nodes=1, max_edges=1)

    assert snapshot.stats["truncated"] is True
    assert snapshot.nodes[0].id == "file:src/one.py"
    md_files = {
        Path(path).relative_to(tmp_path).as_posix()
        for path in _iter_markdown_files(str(tmp_path), ["**/*.md"])
    }
    assert md_files == {"guide.md"}
    assert _resolve_project_ref("missing.py", "guide.md", str(tmp_path)) is None
    assert _resolve_project_ref("src/one.py", "guide.md", str(tmp_path)) == "src/one.py"

    def _raise_os_error(*args: Any, **kwargs: Any) -> str:
        raise OSError("unreadable")

    monkeypatch.setattr(Path, "read_text", _raise_os_error)
    unreadable = KnowledgeGraphBuilder(str(tmp_path)).build(
        include_docs=True,
        max_nodes=100,
        max_edges=100,
    )
    assert "doc_links" not in unreadable.stats["edge_kinds"]


def test_builder_private_edge_and_value_boundaries() -> None:
    builder = KnowledgeGraphBuilder(".")
    nodes: dict[str, KnowledgeNode] = {}
    edges: dict[str, KnowledgeEdge] = {}

    builder._add_file_and_symbols(
        nodes,
        edges,
        {
            "file_path": "app.py",
            "language": "python",
            "symbols_json": '{"symbols":[{"name":""},{"name":"main","line":"bad"}]}',
        },
    )
    assert "app.py:main:0" in nodes
    assert builder._package_node_id("app.py") == "package:<root>"

    builder._add_existing_edge(
        nodes,
        edges,
        {
            "source_node_id": "missing.py:caller:7",
            "target_node_id": "file:target.py",
            "kind": "calls",
            "line": "bad",
            "provenance": "",
            "metadata": "{bad",
            "callee_resolved_file": "resolved.py",
            "language": "python",
        },
    )
    assert "missing.py:caller:7" in nodes
    edge = next(edge for edge in edges.values() if edge.kind == "calls")
    assert edge.line is None
    assert edge.metadata == {"callee_resolved_file": "resolved.py"}
    builder._add_existing_edge(
        nodes,
        edges,
        {
            "source_node_id": "missing.py:caller:7",
            "target_node_id": "file:target.py",
            "kind": "imports",
            "line": 3,
            "provenance": "test",
            "metadata": "{}",
            "callee_resolved_file": "",
            "language": "python",
        },
    )
    assert any(edge.kind == "imports" for edge in edges.values())
    assert _json_obj(None) == {}
    assert _json_obj("{bad") == {}
    assert _nullable_int(None) is None
    assert _nullable_int("bad") is None


def test_builder_edge_and_markdown_caps_cover_relationship_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    (tmp_path / "doc.md").write_text(
        "Missing `missing.py`, then `src/a.py` and `src/b.py`.\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
        EdgeStore(cache.get_conn()).upsert_edges(
            [
                Edge("file:src/a.py", "file:src/b.py", "imports", line=1),
                Edge("file:src/b.py", "file:src/a.py", "imports", line=2),
            ]
        )
        cache.get_conn().commit()
    finally:
        cache.close()

    edge_capped = KnowledgeGraphBuilder(str(tmp_path)).build(
        include_docs=False,
        max_nodes=100,
        max_edges=1,
    )
    assert edge_capped.stats["truncated"] is True

    builder = KnowledgeGraphBuilder(str(tmp_path))
    nodes: dict[str, KnowledgeNode] = {}
    edges: dict[str, KnowledgeEdge] = {}
    builder._add_markdown_links(
        {"file:x.py": KnowledgeNode(id="file:x.py", kind="file", label="x.py")},
        {},
        ["doc.md"],
        max_nodes=1,
        max_edges=100,
    )
    builder._add_markdown_links(
        nodes,
        edges,
        ["doc.md"],
        max_nodes=100,
        max_edges=1,
    )
    assert "file:src/a.py" in nodes
    assert len(edges) == 1

    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.md").write_text("ignored\n", encoding="utf-8")
    markdown_files = {
        Path(path).relative_to(tmp_path).as_posix()
        for path in _iter_markdown_files(str(tmp_path), ["**"])
    }
    assert "src" not in markdown_files
    assert "doc.md" in markdown_files
    assert ".venv/ignored.md" not in markdown_files
    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.builder.glob.glob",
        lambda *args, **kwargs: [str(tmp_path / ".venv" / "ignored.md")],
    )
    assert _iter_markdown_files(str(tmp_path), ["**/*.md"]) == []


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


def test_graphology_export_supports_package_focus_and_empty_graph() -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="package:src", kind="package", label="src"),
            KnowledgeNode(id="package:lib", kind="package", label="lib"),
            KnowledgeNode(
                id="file:src/app.py",
                kind="file",
                label="src/app.py",
                file_path="src/app.py",
            ),
            KnowledgeNode(
                id="file:lib/util.py",
                kind="file",
                label="lib/util.py",
                file_path="lib/util.py",
            ),
            KnowledgeNode(
                id="doc:docs/readme.md",
                kind="markdown",
                label="docs/readme.md",
                file_path="docs/readme.md",
            ),
            KnowledgeNode(
                id="file:other/loose.py",
                kind="file",
                label="other/loose.py",
                file_path="other/loose.py",
            ),
            KnowledgeNode(
                id="src/app.py:main:1",
                kind="function",
                label="main",
                file_path="src/app.py",
            ),
            KnowledgeNode(id="custom:node", kind="unknown", label="custom"),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:import",
                source="file:src/app.py",
                target="file:lib/util.py",
                kind="imports",
            ),
            KnowledgeEdge(
                id="edge:contains",
                source="file:src/app.py",
                target="src/app.py:main:1",
                kind="contains",
            ),
            KnowledgeEdge(
                id="edge:doc",
                source="doc:docs/readme.md",
                target="file:other/loose.py",
                kind="doc_links",
            ),
        ],
        stats={"node_count": 8, "edge_count": 3},
    )

    package_snapshot = aggregate_package_graph(snapshot)
    assert package_snapshot.stats["lod"] == "package"
    assert len(package_snapshot.edges) == 2
    assert {edge.metadata["weight"] for edge in package_snapshot.edges} == {1}
    package_graph = to_graphology(snapshot, lod="package")
    assert package_graph["attributes"]["lod"] == "package"

    focused = to_graphology(snapshot, lod="symbol", focus="main")
    assert {node["key"] for node in focused["nodes"]} == {
        "file:src/app.py",
        "src/app.py:main:1",
    }
    capped = to_graphology(snapshot, lod="symbol", max_nodes=1, max_edges=1)
    assert capped["attributes"]["truncated"] is True
    assert (
        to_graphology(KnowledgeGraphSnapshot(nodes=[], edges=[], stats={}))["nodes"]
        == []
    )
    assert summarize(snapshot)["topology"] == {"node_kinds": {}, "edge_kinds": {}}


def test_html_viewer_embeds_graphology_payload_safely() -> None:
    graph = {
        "attributes": {"name": "A </script> graph", "lod": "file"},
        "nodes": [
            {
                "key": "file:a.py",
                "attributes": {
                    "label": "a.py",
                    "kind": "file",
                    "x": 0,
                    "y": 0,
                },
            }
        ],
        "edges": [],
        "stats": {"export_node_count": 1, "export_edge_count": 0},
    }

    html = to_html_viewer(graph)

    assert html.startswith("<!doctype html>")
    assert '<canvas id="graph-canvas"></canvas>' in html
    assert "TSA Knowledge Graph" in html
    assert "A &lt;/script&gt; graph" in html
    assert "<\\/script>" in html
    assert "file:a.py" in html


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


def test_knowledge_index_tool_validation_rejects_bad_values(tmp_path: Path) -> None:
    tool = CodeGraphKnowledgeIndexTool(str(tmp_path))

    with pytest.raises(ValueError, match="mode must be one of"):
        tool.validate_arguments({"mode": "bad"})
    with pytest.raises(ValueError, match="backend must be one of"):
        tool.validate_arguments({"backend": "bad"})


@pytest.mark.asyncio
async def test_knowledge_index_tool_requires_project_root() -> None:
    tool = CodeGraphKnowledgeIndexTool(None)

    result = await tool.execute({"output_format": "json"})

    assert result["success"] is False
    assert result["error"] == "project_root not set"


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
async def test_knowledge_index_tool_builds_json_and_hybrid_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeBuilder:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        def build(self, **kwargs: Any) -> KnowledgeGraphSnapshot:
            return KnowledgeGraphSnapshot(
                nodes=[
                    KnowledgeNode(
                        id="file:a.py",
                        kind="file",
                        label="a.py",
                        file_path="a.py",
                    )
                ],
                edges=[],
                stats={"node_count": 1, "edge_count": 0},
            )

    class FakeLadybugStore:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        def status(self) -> dict[str, Any]:
            return {"available": False}

        def write(self, snapshot: KnowledgeGraphSnapshot) -> dict[str, Any]:
            raise LadybugUnavailableError("missing ladybug")

    class FakeLadybugSuccessStore:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        def status(self) -> dict[str, Any]:
            return {"available": True}

        def write(self, snapshot: KnowledgeGraphSnapshot) -> dict[str, Any]:
            return {"path": "graph.lbug", "node_count": len(snapshot.nodes)}

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool.KnowledgeGraphBuilder",
        FakeBuilder,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool.LadybugKnowledgeGraphStore",
        FakeLadybugStore,
    )
    tool = CodeGraphKnowledgeIndexTool(str(tmp_path))
    monkeypatch.setattr(
        tool,
        "_prepare_index",
        lambda **kwargs: {"scanned": 1, "updated_files": 1},
    )

    json_result = await tool.execute(
        {"mode": "build", "backend": "json", "output_format": "json"}
    )
    hybrid_result = await tool.execute(
        {"mode": "build", "backend": "hybrid", "output_format": "json"}
    )

    assert json_result["success"] is True
    written_graph = Path(json_result["writes"]["json"]["path"]).read_text(
        encoding="utf-8"
    )
    assert '"schema": "tsa.knowledge_graph.v1"' in written_graph
    assert hybrid_result["success"] is False
    assert hybrid_result["backend"] == "hybrid"
    assert "missing ladybug" in hybrid_result["error"]

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool.LadybugKnowledgeGraphStore",
        FakeLadybugSuccessStore,
    )
    ladybug_result = await tool.execute(
        {"mode": "build", "backend": "ladybug", "output_format": "json"}
    )
    assert ladybug_result["success"] is True
    assert ladybug_result["writes"]["ladybug"]["node_count"] == 1


def test_knowledge_index_prepare_index_build_and_update(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    tool = CodeGraphKnowledgeIndexTool(str(tmp_path))

    build_report = tool._prepare_index(mode="build", max_files=10)
    update_report = tool._prepare_index(mode="update", max_files=1)

    assert build_report["indexed"] == 1
    assert build_report["total_files"] == 1
    assert "details" not in update_report


def test_knowledge_graph_tool_validation_rejects_bad_values(tmp_path: Path) -> None:
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    with pytest.raises(ValueError, match="export_format must be one of"):
        tool.validate_arguments({"export_format": "bad"})
    with pytest.raises(ValueError, match="lod must be one of"):
        tool.validate_arguments({"lod": "bad"})


@pytest.mark.asyncio
async def test_knowledge_graph_tool_requires_project_root() -> None:
    tool = CodeGraphKnowledgeGraphTool(None)

    result = await tool.execute({"output_format": "json"})

    assert result["success"] is False
    assert result["error"] == "project_root not set"


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


@pytest.mark.asyncio
async def test_knowledge_graph_tool_exports_raw_and_summary(tmp_path: Path) -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py")
        ],
        edges=[],
        stats={"node_count": 1, "edge_count": 0},
    )
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    raw = await tool.execute({"export_format": "raw", "output_format": "json"})
    summary = await tool.execute({"export_format": "summary", "output_format": "json"})

    assert raw["graph"]["schema"] == "tsa.knowledge_graph.v1"
    assert summary["graph"]["topology"] == {"node_kinds": {}, "edge_kinds": {}}


@pytest.mark.asyncio
async def test_knowledge_graph_tool_exports_html_viewer(tmp_path: Path) -> None:
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
        {
            "export_format": "html",
            "lod": "docs",
            "max_nodes": 5,
            "max_edges": 5,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["html"].startswith("<!doctype html>")
    assert "graph-canvas" in result["html"]
    assert result["graph"]["schema"] == "tsa.knowledge_graph.v1"
    assert result["export_stats"]["export_node_count"] == 2
    assert result["export_stats"]["export_edge_count"] == 1


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


def test_cli_knowledge_graph_import_and_special_command_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tree_sitter_analyzer.cli.commands import codegraph_index_commands, mcp_commands

    importlib.reload(mcp_commands)
    errors: list[str] = []
    monkeypatch.setitem(
        sys.modules,
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool",
        None,
    )
    args = SimpleNamespace(format="json", output_format="json", project_root=".")

    exit_code = codegraph_index_commands.run_knowledge_graph_index(args, errors.append)

    assert exit_code == 1
    assert "failed to import tool" in errors[0]

    context = SpecialCommandContext(
        asyncio_run=lambda awaitable: None,
        output_json=lambda payload: None,
        output_error=errors.append,
        output_info=lambda payload: None,
        output_list=lambda payload: None,
        query_loader=None,
    )
    assert (
        _handle_knowledge_graph_index(
            SimpleNamespace(knowledge_graph_index=False), context
        )
        is None
    )
    monkeypatch.setattr(
        codegraph_index_commands,
        "run_knowledge_graph_index",
        lambda args, output_error: 7,
    )
    assert (
        _handle_knowledge_graph_index(
            SimpleNamespace(knowledge_graph_index=True), context
        )
        == 7
    )
