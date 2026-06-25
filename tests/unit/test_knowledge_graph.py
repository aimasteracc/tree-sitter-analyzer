"""Tests for whole-project code/doc knowledge graph projection."""

from __future__ import annotations

import importlib
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cli.commands import codegraph_index_commands
from tree_sitter_analyzer.cli.commands.codegraph_index_commands import (
    run_knowledge_graph_serve,
)
from tree_sitter_analyzer.cli.special_commands import (
    SpecialCommandContext,
    _handle_knowledge_graph_index,
    _handle_knowledge_graph_serve,
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
from tree_sitter_analyzer.knowledge_graph.ladybug_query import (
    LadybugKnowledgeGraphQuery,
)
from tree_sitter_analyzer.knowledge_graph.query import (
    JsonKnowledgeGraphQuery,
    _empty_graph,
    _nullable_line,
    open_query_backend,
)
from tree_sitter_analyzer.knowledge_graph.query import (
    _json_obj as _query_json_obj,
)
from tree_sitter_analyzer.knowledge_graph.server import (
    KnowledgeGraphService,
    _content_type,
    _first,
    _int_param,
    _make_handler,
    _mtime_ns,
    _prepare_reason,
    ensure_knowledge_graph_ready,
    serve_knowledge_graph,
)
from tree_sitter_analyzer.knowledge_graph.stores import LadybugUnavailableError
from tree_sitter_analyzer.mcp.tools.knowledge_graph_tool import (
    CodeGraphKnowledgeGraphTool,
    CodeGraphKnowledgeIndexTool,
    _compact_sync_report,
    _stores_ready,
    _sync_has_changes,
)


def _read_url(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def _graph_snapshot_for_query_tests() -> KnowledgeGraphSnapshot:
    return KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py"),
            KnowledgeNode(
                id="file:.git/config",
                kind="file",
                label=".git/config",
                file_path=".git/config",
            ),
            KnowledgeNode(
                id="doc:README.md",
                kind="markdown",
                label="README.md",
                file_path="README.md",
            ),
            KnowledgeNode(
                id="a.py:main:1",
                kind="function",
                label="main",
                file_path="a.py",
                metadata={"line": 1},
            ),
            KnowledgeNode(
                id="a.py:helper:4",
                kind="function",
                label="helper",
                file_path="a.py",
                metadata={"line": 4},
            ),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:missing-peer",
                source="missing.py:ghost:1",
                target="a.py:main:1",
                kind="calls",
            ),
            KnowledgeEdge(
                id="edge:contains",
                source="file:a.py",
                target="a.py:main:1",
                kind="contains",
            ),
            KnowledgeEdge(
                id="edge:calls",
                source="a.py:main:1",
                target="a.py:helper:4",
                kind="calls",
                metadata={"callee_name": "helper"},
            ),
            KnowledgeEdge(
                id="edge:return",
                source="a.py:helper:4",
                target="a.py:main:1",
                kind="calls",
            ),
        ],
        stats={"node_count": 5, "edge_count": 4},
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


def test_builder_zero_caps_mean_unlimited(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "one.py").write_text(
        "def one():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "src" / "two.py").write_text(
        "def two():\n    return one()\n", encoding="utf-8"
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()

    snapshot = KnowledgeGraphBuilder(str(tmp_path)).build(
        include_docs=False,
        max_nodes=0,
        max_edges=0,
    )

    assert snapshot.stats["truncated"] is False
    assert snapshot.stats["node_count"] == len(snapshot.nodes)
    assert snapshot.stats["edge_count"] == len(snapshot.edges)
    assert {node.kind for node in snapshot.nodes} >= {"file", "symbol"}
    assert {edge.kind for edge in snapshot.edges} >= {"contains", "calls"}


def test_scale_benchmark_builds_java_shaped_snapshot() -> None:
    benchmark = importlib.import_module("scripts.benchmark_knowledge_graph_scale")

    snapshot = benchmark.build_java_snapshot(
        files=3,
        packages=2,
        methods_per_file=2,
    )

    assert snapshot.stats["indexed_files"] == 3
    assert snapshot.stats["node_kinds"] == {
        "class": 3,
        "file": 3,
        "method": 6,
        "package": 2,
    }
    assert snapshot.stats["edge_kinds"] == {
        "calls": 6,
        "contains": 12,
        "imports": 3,
    }
    assert snapshot.stats["truncated"] is False


def test_java_end_to_end_benchmark_generates_real_java_corpus(tmp_path: Path) -> None:
    benchmark = importlib.import_module("scripts.benchmark_java_corpus_end_to_end")

    result = benchmark.create_java_corpus(
        tmp_path,
        files=3,
        packages=2,
        methods_per_file=2,
    )

    java_files = sorted((tmp_path / "src" / "main" / "java").rglob("*.java"))
    assert result["files_written"] == 3
    assert len(java_files) == 3
    first = java_files[0].read_text(encoding="utf-8")
    assert "package com.example.p0000;" in first
    assert "public class Service000000" in first
    assert "public int method0(int value)" in first
    assert "new Service000001().method0(value)" in first


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


def test_cli_parser_accepts_knowledge_graph_uml_export_flags() -> None:
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    args = parser.parse_args(
        [
            "--knowledge-graph-export",
            "--knowledge-graph-export-format",
            "uml",
            "--knowledge-graph-uml-kind",
            "class",
        ]
    )

    assert args.knowledge_graph_export is True
    assert args.knowledge_graph_export_format == "uml"
    assert args.knowledge_graph_uml_kind == "class"


def test_knowledge_graph_service_serves_node_and_neighborhood(tmp_path: Path) -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py"),
            KnowledgeNode(
                id="file:.ast-cache/index.db",
                kind="file",
                label=".ast-cache/index.db",
                file_path=".ast-cache/index.db",
            ),
            KnowledgeNode(
                id="file:../wiki/outside.md",
                kind="file",
                label="../wiki/outside.md",
                file_path="../wiki/outside.md",
            ),
            KnowledgeNode(
                id="a.py:main:1",
                kind="function",
                label="main",
                file_path="a.py",
                metadata={"line": 1},
            ),
            KnowledgeNode(
                id="a.py:helper:4",
                kind="function",
                label="helper",
                file_path="a.py",
                metadata={"line": 4},
            ),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:contains",
                source="file:a.py",
                target="a.py:main:1",
                kind="contains",
            ),
            KnowledgeEdge(
                id="edge:calls",
                source="a.py:main:1",
                target="a.py:helper:4",
                kind="calls",
            ),
        ],
        stats={"node_count": 5, "edge_count": 2},
    )
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)

    service = KnowledgeGraphService(str(tmp_path))
    node = service.node("a.py:helper:4")
    graph = service.neighborhood("a.py:main:1", edge_kind="calls")
    files = service.files("a.py", limit=5)

    assert node["found"] is True
    assert node["incoming_count"] == 1
    assert node["outgoing_count"] == 0
    assert node["incoming"][0]["peer"]["label"] == "main"
    assert graph["stats"]["service_view"] == "neighborhood"
    assert graph["stats"]["center"] == "a.py:main:1"
    assert graph["stats"]["node_count"] == 5
    assert graph["stats"]["service_node_count"] == 2
    assert graph["stats"]["export_node_count"] == 2
    assert graph["stats"]["export_edge_count"] == 1
    assert service.search("helper", limit=1)["matches"][0]["id"] == "a.py:helper:4"
    assert files["backend"] == "json"
    assert files["returned"] == 1
    assert files["total_matches"] == 1
    assert files["files"][0]["id"] == "file:a.py"


def test_json_query_backend_covers_empty_missing_and_filter_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    JsonKnowledgeGraphStore(str(tmp_path)).write(_graph_snapshot_for_query_tests())
    monkeypatch.setattr(LadybugKnowledgeGraphStore, "available", lambda: False)

    backend = JsonKnowledgeGraphQuery(str(tmp_path))
    selected = backend.node("a.py:main:1", limit=10)
    neighborhood = backend.neighborhood(
        "a.py:main:1",
        depth=3,
        edge_kind="bad-kind",
        max_nodes=3,
        max_edges=10,
    )
    files = backend.files("", limit=10)

    assert open_query_backend(str(tmp_path)).backend_name == "json"
    assert backend.search("", limit=10)["matches"] == []
    assert backend.search("HELPER", limit=1)["matches"][0]["id"] == "a.py:helper:4"
    assert backend.node("missing", limit=1) == {
        "backend": "json",
        "found": False,
        "id": "missing",
    }
    assert selected["incoming"][0]["peer"] == {
        "id": "missing.py:ghost:1",
        "label": "missing.py:ghost:1",
    }
    missing_graph = backend.neighborhood(
        "missing", depth=1, edge_kind="all", max_nodes=5, max_edges=5
    )
    assert missing_graph["nodes"] == []
    assert neighborhood["stats"]["backend"] == "json"
    assert neighborhood["stats"]["service_node_count"] == 3
    assert {node["key"] for node in neighborhood["nodes"]} == {
        "file:a.py",
        "a.py:main:1",
        "a.py:helper:4",
    }
    assert [node["id"] for node in files["files"]] == [
        "doc:README.md",
        "file:a.py",
    ]
    assert _query_json_obj("") == {}
    assert _query_json_obj("{bad") == {}
    assert _query_json_obj("[]") == {}
    assert _query_json_obj('{"ok": true}') == {"ok": True}
    assert _nullable_line(None) is None
    assert _nullable_line(-1) is None
    assert _nullable_line("7") == 7
    assert _empty_graph("missing", "json")["stats"] == {
        "export_node_count": 0,
        "export_edge_count": 0,
        "backend": "json",
    }
    with pytest.raises(FileNotFoundError, match="Knowledge graph sidecar is missing"):
        JsonKnowledgeGraphQuery(str(tmp_path / "empty"))


def test_knowledge_graph_http_service_serves_static_studio_and_api(
    tmp_path: Path,
) -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py"),
            KnowledgeNode(
                id="file:.ast-cache/index.db",
                kind="file",
                label=".ast-cache/index.db",
                file_path=".ast-cache/index.db",
            ),
            KnowledgeNode(
                id="file:../wiki/outside.md",
                kind="file",
                label="../wiki/outside.md",
                file_path="../wiki/outside.md",
            ),
            KnowledgeNode(
                id="a.py:main:1",
                kind="function",
                label="main",
                file_path="a.py",
            ),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:contains",
                source="file:a.py",
                target="a.py:main:1",
                kind="contains",
            )
        ],
        stats={"node_count": 2, "edge_count": 1},
    )
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)
    service = KnowledgeGraphService(str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(service))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        index_html = _read_url(f"{base_url}/")
        app_js = _read_url(f"{base_url}/static/app.js")
        app_css = _read_url(f"{base_url}/static/app.css")
        graph_payload = _read_url(f"{base_url}/api/graph?lod=symbol")
        node_payload = _read_url(f"{base_url}/api/node?id=file:a.py")
        neighborhood_payload = _read_url(
            f"{base_url}/api/neighborhood?id=file:a.py&depth=1&edge_kind=contains"
        )
        search_payload = _read_url(f"{base_url}/api/search?q=main&limit=5")
        files_payload = _read_url(f"{base_url}/api/files?q=a.py&limit=5")
        with pytest.raises(HTTPError) as missing_exc:
            _read_url(f"{base_url}/missing")
        with pytest.raises(HTTPError) as invalid_exc:
            _read_url(f"{base_url}/api/search?limit=bad")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert "TSA Graph Studio" in index_html
    assert "loadExplorer" in app_js
    assert ".stage" in app_css
    assert '"schema": "tsa.graphology.v1"' in graph_payload
    assert '"backend": "json"' in graph_payload
    assert '"found": true' in node_payload
    assert '"service_view": "neighborhood"' in neighborhood_payload
    assert '"matches":' in search_payload
    assert '"files":' in files_payload
    assert '"id": "file:a.py"' in files_payload
    assert missing_exc.value.code == 404
    assert invalid_exc.value.code == 400


def test_http_param_and_content_type_helpers() -> None:
    assert _first({"x": ["1"]}, "x", "0") == "1"
    assert _first({}, "x", "0") == "0"
    assert _int_param({"x": ["12"]}, "x", 0) == 12
    with pytest.raises(ValueError, match="x must be an integer"):
        _int_param({"x": ["bad"]}, "x", 0)
    assert _content_type("app.css") == "text/css; charset=utf-8"
    assert _content_type("app.js") == "application/javascript; charset=utf-8"
    assert _content_type("index.html") == "text/html; charset=utf-8"


def test_serve_knowledge_graph_starts_and_closes_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class FakeServer:
        server_port = 9999

        def __init__(self, address: tuple[str, int], handler: object) -> None:
            assert address == ("127.0.0.1", 8765)
            assert handler is not None

        def serve_forever(self) -> None:
            events.append("serve")

        def server_close(self) -> None:
            events.append("close")

    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.server._prepare_reason",
        lambda project_root: "",
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.server.ensure_knowledge_graph_ready",
        lambda project_root: {"prepared": True, "reason": "startup incremental update"},
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.server.KnowledgeGraphService",
        lambda project_root: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.server.ThreadingHTTPServer",
        FakeServer,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.server.webbrowser.open",
        lambda url: events.append(url),
    )

    serve_knowledge_graph(str(tmp_path), open_browser=True)

    assert events == ["http://127.0.0.1:9999/", "serve", "close"]

    events.clear()
    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.server.ensure_knowledge_graph_ready",
        lambda project_root: {"prepared": False, "reason": "fresh"},
    )
    serve_knowledge_graph(str(tmp_path), open_browser=False)
    assert events == ["serve", "close"]


def test_prepare_reason_and_ready_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _prepare_reason(str(tmp_path)) == "json sidecar missing"
    assert _mtime_ns(str(tmp_path / "missing")) is None

    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py")
        ],
        edges=[],
        stats={},
    )
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)
    monkeypatch.setattr(LadybugKnowledgeGraphStore, "available", lambda: True)
    assert _prepare_reason(str(tmp_path)) == "LadybugDB mirror missing"

    monkeypatch.setattr(LadybugKnowledgeGraphStore, "available", lambda: False)
    assert _prepare_reason(str(tmp_path)) == ""
    monkeypatch.setattr(LadybugKnowledgeGraphStore, "available", lambda: True)

    ast_cache = tmp_path / ".ast-cache"
    ast_cache.mkdir(exist_ok=True)
    index_path = ast_cache / "index.db"
    index_path.write_bytes(b"sqlite")
    ladybug_path = Path(LadybugKnowledgeGraphStore(str(tmp_path)).path)
    ladybug_path.write_bytes(b"ladybug")

    mtimes = {
        str(index_path): 30,
        str(ast_cache / "knowledge-graph.json"): 10,
        str(ladybug_path): 40,
    }
    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.server._mtime_ns",
        lambda path: mtimes.get(path),
    )
    assert _prepare_reason(str(tmp_path)) == "json sidecar older than SQLite index"

    mtimes[str(ast_cache / "knowledge-graph.json")] = 50
    mtimes[str(ladybug_path)] = 20
    assert _prepare_reason(str(tmp_path)) == "LadybugDB mirror older than SQLite index"

    mtimes[str(ladybug_path)] = 60
    assert _prepare_reason(str(tmp_path)) == ""

    class FailingKnowledgeIndexTool:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": False, "error": "index failed"}

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool.CodeGraphKnowledgeIndexTool",
        FailingKnowledgeIndexTool,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.server._prepare_reason",
        lambda project_root: "forced",
    )
    with pytest.raises(RuntimeError, match="index failed"):
        ensure_knowledge_graph_ready(str(tmp_path))


def test_cli_knowledge_graph_serve_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    errors: list[str] = []
    args = SimpleNamespace(
        project_root=str(tmp_path),
        knowledge_graph_host="127.0.0.1",
        knowledge_graph_port=8765,
        knowledge_graph_open=False,
    )

    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.server.serve_knowledge_graph",
        lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    assert run_knowledge_graph_serve(args, errors.append) == 0

    monkeypatch.setattr(
        "tree_sitter_analyzer.knowledge_graph.server.serve_knowledge_graph",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert run_knowledge_graph_serve(args, errors.append) == 1
    assert errors[-1] == "--knowledge-graph-serve failed: boom"


def test_mcp_graph_store_ready_helpers(tmp_path: Path) -> None:
    json_store = JsonKnowledgeGraphStore(str(tmp_path))
    ladybug_store = LadybugKnowledgeGraphStore(str(tmp_path))

    assert _sync_has_changes({"new_files": "1"}) is True
    assert _sync_has_changes({"updated_files": 0, "deleted_files": None}) is False
    assert _stores_ready("json", json_store, ladybug_store) is False

    json_store.write(_graph_snapshot_for_query_tests())
    assert _stores_ready("json", json_store, ladybug_store) is True
    assert _stores_ready("ladybug", json_store, ladybug_store) is False


def test_ensure_knowledge_graph_ready_skips_fresh_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ast_cache = tmp_path / ".ast-cache"
    ast_cache.mkdir()
    (ast_cache / "index.db").write_bytes(b"sqlite")
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py")
        ],
        edges=[],
        stats={"node_count": 1, "edge_count": 0},
    )
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)
    os.utime(ast_cache / "index.db", ns=(1, 1))
    os.utime(ast_cache / "knowledge-graph.json", ns=(2, 2))
    monkeypatch.setattr(LadybugKnowledgeGraphStore, "available", lambda: False)

    result = ensure_knowledge_graph_ready(str(tmp_path), force_update=False)

    assert result == {"prepared": False, "reason": "fresh"}


def test_ensure_knowledge_graph_ready_updates_by_default_even_when_fresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeKnowledgeIndexTool:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            calls.append(arguments)
            return {"success": True, "writes": {"json": {"path": "kg.json"}}}

    ast_cache = tmp_path / ".ast-cache"
    ast_cache.mkdir()
    (ast_cache / "index.db").write_bytes(b"sqlite")
    JsonKnowledgeGraphStore(str(tmp_path)).write(
        KnowledgeGraphSnapshot(
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
    )
    os.utime(ast_cache / "index.db", ns=(1, 1))
    os.utime(ast_cache / "knowledge-graph.json", ns=(2, 2))
    monkeypatch.setattr(LadybugKnowledgeGraphStore, "available", lambda: False)
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool.CodeGraphKnowledgeIndexTool",
        FakeKnowledgeIndexTool,
    )

    result = ensure_knowledge_graph_ready(str(tmp_path))

    assert result["prepared"] is True
    assert result["reason"] == "startup incremental update"
    assert calls[0]["mode"] == "update"


def test_ensure_knowledge_graph_ready_updates_missing_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeKnowledgeIndexTool:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            calls.append({"project_root": self.project_root, "arguments": arguments})
            return {"success": True, "writes": {"json": {"path": "kg.json"}}}

    monkeypatch.setattr(LadybugKnowledgeGraphStore, "available", lambda: False)
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool.CodeGraphKnowledgeIndexTool",
        FakeKnowledgeIndexTool,
    )

    result = ensure_knowledge_graph_ready(str(tmp_path))

    assert result["prepared"] is True
    assert result["reason"] == "json sidecar missing"
    assert calls == [
        {
            "project_root": str(tmp_path),
            "arguments": {
                "mode": "update",
                "backend": "auto",
                "max_files": 1_000_000,
                "max_nodes": 0,
                "max_edges": 0,
                "include_docs": True,
                "output_format": "json",
            },
        }
    ]


def test_ladybug_query_backend_serves_node_and_neighborhood(tmp_path: Path) -> None:
    if not LadybugKnowledgeGraphStore.available():
        pytest.skip("tracked: optional LadybugDB extra is not installed")
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="file:a.py", kind="file", label="a.py", file_path="a.py"),
            KnowledgeNode(
                id="a.py:main:1",
                kind="function",
                label="main",
                file_path="a.py",
                metadata={"line": 1},
            ),
            KnowledgeNode(
                id="a.py:helper:4",
                kind="function",
                label="helper",
                file_path="a.py",
                metadata={"line": 4},
            ),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:contains",
                source="file:a.py",
                target="a.py:main:1",
                kind="contains",
            ),
            KnowledgeEdge(
                id="edge:calls",
                source="a.py:main:1",
                target="a.py:helper:4",
                kind="calls",
            ),
            KnowledgeEdge(
                id="edge:return",
                source="a.py:helper:4",
                target="a.py:main:1",
                kind="calls",
            ),
        ],
        stats={"node_count": 5, "edge_count": 3},
    )
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)
    LadybugKnowledgeGraphStore(str(tmp_path)).write(snapshot)

    with pytest.raises(FileNotFoundError, match="LadybugDB graph mirror is missing"):
        LadybugKnowledgeGraphQuery(str(tmp_path / "empty"))

    backend = LadybugKnowledgeGraphQuery(str(tmp_path))
    service = KnowledgeGraphService(str(tmp_path))
    overview = service.graph(lod="bad", focus="helper", max_nodes=10, max_edges=10)
    node = backend.node("a.py:helper:4", limit=10)
    graph = service.neighborhood("a.py:main:1", depth=9, edge_kind="calls")
    capped = backend.neighborhood(
        "a.py:main:1", depth=2, edge_kind="bad", max_nodes=2, max_edges=10
    )
    files = service.files("a.py", limit=5)
    all_files = backend.files("", limit=10)

    assert service.backend.backend_name == "ladybug"
    assert overview["stats"]["backend"] == "ladybug"
    assert overview["stats"]["service_view"] == "overview"
    assert overview["stats"]["export_node_count"] == 0
    assert overview["stats"]["export_edge_count"] == 0
    assert node["backend"] == "ladybug"
    assert node["found"] is True
    assert node["incoming_count"] == 1
    assert node["outgoing_count"] == 1
    assert node["incoming"][0]["peer"]["label"] == "main"
    assert graph["stats"]["backend"] == "ladybug"
    assert graph["stats"]["service_view"] == "neighborhood"
    assert graph["stats"]["export_node_count"] == 2
    assert graph["stats"]["export_edge_count"] == 2
    assert capped["stats"]["export_node_count"] == 2
    assert backend.search("", limit=1)["matches"] == []
    assert backend.search("helper", limit=1)["matches"][0]["id"] == "a.py:helper:4"
    assert backend._walk_nodes(
        "a.py:main:1", depth=0, edge_kind="all", max_nodes=10
    ) == {"a.py:main:1"}
    assert backend.node("missing", limit=1) == {
        "backend": "ladybug",
        "found": False,
        "id": "missing",
    }
    assert (
        backend.neighborhood(
            "missing", depth=1, edge_kind="all", max_nodes=5, max_edges=5
        )["nodes"]
        == []
    )
    assert backend._edges_between(set(), max_edges=1) == []
    assert files["backend"] == "ladybug"
    assert files["returned"] == 1
    assert files["total_matches"] == 1
    assert files["files"][0]["id"] == "file:a.py"
    assert [node["id"] for node in all_files["files"]] == ["file:a.py"]


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
            KnowledgeNode(
                id="a.py:Service:5",
                kind="class",
                label="Service",
                file_path="a.py",
                metadata={"line": 5, "end_line": 17},
            ),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:imports",
                source="file:a.py",
                target="file:b.py",
                kind="imports",
            ),
            KnowledgeEdge(
                id="edge:missing",
                source="file:a.py",
                target="file:missing.py",
                kind="imports",
            ),
        ],
        stats={"node_count": 2, "edge_count": 1},
    )
    store = LadybugKnowledgeGraphStore(str(tmp_path))
    wal_path = Path(store.path).with_name(f"{Path(store.path).name}.wal")
    wal_path.parent.mkdir(parents=True, exist_ok=True)
    wal_path.write_bytes(b"stale")

    result = store.write(snapshot)

    assert result["method"] == "copy"
    assert result["node_count"] == 3
    assert result["edge_count"] == 1
    assert result["skipped_edge_count"] == 1
    db_path = Path(store.path)
    status = store.status()
    assert status["available"] is True
    assert status["bytes"] == db_path.stat().st_size
    assert status["mtime_ns"] == db_path.stat().st_mtime_ns
    assert not wal_path.exists() or wal_path.read_bytes() != b"stale"
    backend = LadybugKnowledgeGraphQuery(str(tmp_path))
    assert (
        backend.graph(lod="symbol", focus=None, max_nodes=10, max_edges=10)["stats"][
            "export_edge_count"
        ]
        == 1
    )


def test_ladybug_store_falls_back_when_copy_import_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
            ),
            KnowledgeEdge(
                id="edge:missing",
                source="file:a.py",
                target="file:missing.py",
                kind="imports",
            ),
        ],
        stats={"node_count": 2, "edge_count": 2},
    )
    store = LadybugKnowledgeGraphStore(str(tmp_path))

    def _raise_copy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("copy failed")

    monkeypatch.setattr(store, "_write_with_copy", _raise_copy)
    result = store.write(snapshot)

    assert result["method"] == "row_by_row_fallback"
    assert result["fallback_error"] == "copy failed"
    assert result["node_count"] == 2
    assert result["edge_count"] == 1
    assert result["skipped_edge_count"] == 1
    assert (
        LadybugKnowledgeGraphQuery(str(tmp_path)).node("file:b.py", limit=5)[
            "incoming_count"
        ]
        == 1
    )


def test_ladybug_store_replaces_existing_path_and_wal(tmp_path: Path) -> None:
    store = LadybugKnowledgeGraphStore(str(tmp_path))
    target = Path(store.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old", encoding="utf-8")
    target_wal = LadybugKnowledgeGraphStore._wal_path(target)
    target_wal.write_text("old wal", encoding="utf-8")
    old_path = target.with_name(f"{target.name}.old-{os.getpid()}")
    old_path.mkdir()
    old_wal = LadybugKnowledgeGraphStore._wal_path(old_path)
    old_wal.mkdir()
    source = tmp_path / "incoming.lbug"
    source.write_text("new", encoding="utf-8")
    source_wal = LadybugKnowledgeGraphStore._wal_path(source)
    source_wal.write_text("new wal", encoding="utf-8")

    store._replace_path(source)

    assert target.read_text(encoding="utf-8") == "new"
    assert target_wal.read_text(encoding="utf-8") == "new wal"
    assert not old_path.exists()
    assert not old_wal.exists()
    assert not source.exists()
    assert not source_wal.exists()


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

        @staticmethod
        def available() -> bool:
            return False

        def status(self) -> dict[str, Any]:
            return {"available": False}

        def write(self, snapshot: KnowledgeGraphSnapshot) -> dict[str, Any]:
            raise LadybugUnavailableError("missing ladybug")

    class FakeLadybugSuccessStore:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        @staticmethod
        def available() -> bool:
            return True

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

    auto_result = await tool.execute(
        {"mode": "build", "backend": "auto", "output_format": "json"}
    )
    assert auto_result["success"] is True
    assert auto_result["backend"] == "auto"
    assert auto_result["effective_backend"] == "hybrid"


@pytest.mark.asyncio
async def test_knowledge_index_tool_skips_writes_when_update_has_no_changes(
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
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)

    class ExplodingBuilder:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        def build(self, **kwargs: Any) -> KnowledgeGraphSnapshot:
            raise AssertionError("builder should not run on no-op update")

    class FakeLadybugStore:
        def __init__(self, project_root: str) -> None:
            self.project_root = project_root

        @staticmethod
        def available() -> bool:
            return False

        def exists(self) -> bool:
            return False

        def status(self) -> dict[str, Any]:
            return {"available": False}

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool.KnowledgeGraphBuilder",
        ExplodingBuilder,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool.LadybugKnowledgeGraphStore",
        FakeLadybugStore,
    )
    tool = CodeGraphKnowledgeIndexTool(str(tmp_path))
    monkeypatch.setattr(
        tool,
        "_prepare_index",
        lambda **kwargs: {
            "new_files": 0,
            "updated_files": 0,
            "deleted_files": 0,
            "unchanged_files": 1,
        },
    )

    result = await tool.execute(
        {"mode": "update", "backend": "auto", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["effective_backend"] == "json"
    assert result["writes"] == {}
    assert result["skipped_write_reason"] == "no indexed file changes"
    assert result["graph"]["stats"]["node_count"] == 1


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
            "files": [{"file": "a.py"}],
            "deleted": ["b.py"],
            "updated": ["c.py"],
            "new": ["d.py"],
        }
    )

    assert compact == {"scanned": 10, "deleted_files": 0}


def test_cli_knowledge_graph_import_and_special_command_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tree_sitter_analyzer.cli.commands import mcp_commands

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
    assert (
        _handle_knowledge_graph_serve(
            SimpleNamespace(knowledge_graph_serve=False), context
        )
        is None
    )
    monkeypatch.setattr(
        codegraph_index_commands,
        "run_knowledge_graph_serve",
        lambda args, output_error: 9,
    )
    assert (
        _handle_knowledge_graph_serve(
            SimpleNamespace(knowledge_graph_serve=True), context
        )
        == 9
    )
