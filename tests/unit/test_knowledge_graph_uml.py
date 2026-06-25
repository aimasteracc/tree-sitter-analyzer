"""Tests for knowledge graph Mermaid UML export."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.knowledge_graph import (
    JsonKnowledgeGraphStore,
    KnowledgeEdge,
    KnowledgeGraphSnapshot,
    KnowledgeNode,
)
from tree_sitter_analyzer.knowledge_graph.exporters import to_mermaid_uml
from tree_sitter_analyzer.mcp.tools.knowledge_graph_tool import (
    CodeGraphKnowledgeGraphTool,
)


def test_mermaid_uml_export_supports_component_package_and_class_views() -> None:
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
                id="src/app.py:UserService:1",
                kind="class",
                label="UserService",
                file_path="src/app.py",
            ),
            KnowledgeNode(
                id="lib/util.py:BaseService:1",
                kind="class",
                label="BaseService",
                file_path="lib/util.py",
            ),
            KnowledgeNode(
                id="src/app.py:main:10",
                kind="function",
                label="main",
                file_path="src/app.py",
            ),
            KnowledgeNode(
                id="lib/util.py:helper:20",
                kind="function",
                label="helper",
                file_path="lib/util.py",
            ),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:import",
                source="file:src/app.py",
                target="file:lib/util.py",
                kind="imports",
            ),
            KnowledgeEdge(
                id="edge:extends",
                source="src/app.py:UserService:1",
                target="lib/util.py:BaseService:1",
                kind="extends",
            ),
            KnowledgeEdge(
                id="edge:calls",
                source="src/app.py:main:10",
                target="lib/util.py:helper:20",
                kind="calls",
                metadata={"callee_name": "helper"},
            ),
        ],
        stats={"node_count": 8, "edge_count": 3},
    )

    component = to_mermaid_uml(snapshot, diagram="component")
    package = to_mermaid_uml(snapshot, diagram="package")
    class_view = to_mermaid_uml(snapshot, diagram="class")
    sequence = to_mermaid_uml(snapshot, diagram="sequence")

    assert component["syntax"] == "mermaid"
    assert component["diagram"] == "component"
    assert component["mermaid"].splitlines()[0] == "flowchart LR"
    assert component["stats"]["export_node_count"] == 4
    assert component["stats"]["export_edge_count"] == 1
    assert package["diagram"] == "package"
    assert package["stats"]["export_node_count"] == 2
    assert package["stats"]["export_edge_count"] == 3
    assert class_view["mermaid"].splitlines()[0] == "classDiagram"
    assert " <|-- " in class_view["mermaid"]
    assert class_view["stats"]["export_node_count"] == 2
    assert class_view["stats"]["export_edge_count"] == 1
    assert sequence["diagram"] == "sequence"
    assert sequence["mermaid"].splitlines()[0] == "sequenceDiagram"
    assert "participant" in sequence["mermaid"]
    assert "->>+" in sequence["mermaid"]
    assert ": helper" in sequence["mermaid"]
    assert sequence["stats"]["export_node_count"] == 2
    assert sequence["stats"]["export_edge_count"] == 1
    with pytest.raises(ValueError, match="diagram"):
        to_mermaid_uml(snapshot, diagram="state")


def test_mermaid_uml_class_view_covers_focus_and_relation_variants() -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="app.py:Service:1", kind="class", label="Service"),
            KnowledgeNode(id="app.py:Repo:1", kind="interface", label="Repo"),
            KnowledgeNode(id="app.py:Mode:1", kind="enum", label="Mode"),
            KnowledgeNode(id="app.py:Hidden:1", kind="class", label="Hidden"),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:implements",
                source="app.py:Service:1",
                target="app.py:Repo:1",
                kind="implements",
            ),
            KnowledgeEdge(
                id="edge:references",
                source="app.py:Service:1",
                target="app.py:Mode:1",
                kind="references",
            ),
            KnowledgeEdge(
                id="edge:hidden",
                source="app.py:Hidden:1",
                target="app.py:Repo:1",
                kind="imports",
            ),
        ],
        stats={"node_count": 4, "edge_count": 3},
    )

    class_view = to_mermaid_uml(snapshot, diagram="class", focus="app.py")
    capped = to_mermaid_uml(snapshot, diagram="class", max_nodes=2, max_edges=1)

    assert "<<interface>>" in class_view["mermaid"]
    assert "<<enum>>" in class_view["mermaid"]
    assert " <|.. " in class_view["mermaid"]
    assert " ..> " in class_view["mermaid"]
    assert class_view["stats"]["export_node_count"] == 4
    assert class_view["stats"]["export_edge_count"] == 3
    assert capped["stats"]["export_node_count"] == 2
    assert capped["stats"]["export_edge_count"] == 0
    assert capped["stats"]["export_truncated"] is True


def test_mermaid_uml_class_view_keeps_placeholder_bases_and_focused_neighbors() -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(
                id="src/app.py:Child:1",
                kind="class",
                label="Child",
                file_path="src/app.py",
            ),
            KnowledgeNode(
                id="class:FrameworkBase",
                kind="symbol",
                label="FrameworkBase",
            ),
            KnowledgeNode(
                id="src/app.py:Worker:8",
                kind="interface",
                label="Worker",
                file_path="src/app.py",
            ),
            KnowledgeNode(
                id="src/app.py:Unrelated:20",
                kind="class",
                label="Unrelated",
                file_path="src/app.py",
            ),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:extends",
                source="src/app.py:Child:1",
                target="class:FrameworkBase",
                kind="extends",
            ),
            KnowledgeEdge(
                id="edge:implements",
                source="src/app.py:Child:1",
                target="src/app.py:Worker:8",
                kind="implements",
            ),
            KnowledgeEdge(
                id="edge:unfocused",
                source="src/app.py:Unrelated:20",
                target="src/app.py:Worker:8",
                kind="references",
            ),
            KnowledgeEdge(
                id="edge:non-uml",
                source="src/app.py:Child:1",
                target="src/app.py:Worker:8",
                kind="calls",
            ),
        ],
        stats={"node_count": 4, "edge_count": 4},
    )

    focused = to_mermaid_uml(snapshot, diagram="class", focus="Child")

    assert "n_Child_" in focused["mermaid"]
    assert "n_FrameworkBase_" in focused["mermaid"]
    assert "n_Worker_" in focused["mermaid"]
    assert "src_app_py_Child" not in focused["mermaid"]
    assert " <|-- " in focused["mermaid"]
    assert " <|.. " in focused["mermaid"]
    assert focused["stats"]["export_node_count"] == 3
    assert focused["stats"]["export_edge_count"] == 2


def test_mermaid_sequence_view_covers_focus_missing_nodes_and_caps() -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(
                id="src/app.py:main:1",
                kind="function",
                label="main",
                file_path="src/app.py",
            ),
            KnowledgeNode(
                id="src/app.py:helper:4",
                kind="function",
                label="helper",
                file_path="src/app.py",
            ),
            KnowledgeNode(
                id="src/app.py:worker:8",
                kind="function",
                label="worker",
                file_path="",
            ),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:missing",
                source="src/app.py:missing:0",
                target="src/app.py:main:1",
                kind="calls",
            ),
            KnowledgeEdge(
                id="edge:helper",
                source="src/app.py:main:1",
                target="src/app.py:helper:4",
                kind="calls",
                line=2,
                metadata={"callee_name": 'say "hi"'},
            ),
            KnowledgeEdge(
                id="edge:worker",
                source="src/app.py:helper:4",
                target="src/app.py:worker:8",
                kind="calls",
                line=3,
            ),
        ],
        stats={"node_count": 3, "edge_count": 3},
    )

    focused = to_mermaid_uml(
        snapshot,
        diagram="sequence",
        focus="main",
        max_nodes=2,
        max_edges=1,
    )

    assert focused["stats"]["export_node_count"] == 2
    assert focused["stats"]["export_edge_count"] == 1
    assert focused["stats"]["export_truncated"] is True
    assert "say 'hi'" in focused["mermaid"]
    assert "worker" not in focused["mermaid"]

    capped_by_nodes = to_mermaid_uml(
        snapshot,
        diagram="sequence",
        max_nodes=2,
        max_edges=10,
    )
    full = to_mermaid_uml(snapshot, diagram="sequence", max_nodes=10, max_edges=10)
    assert capped_by_nodes["stats"]["export_node_count"] == 2
    assert capped_by_nodes["stats"]["export_truncated"] is True
    assert "worker" in full["mermaid"]


def test_knowledge_graph_tool_rejects_bad_uml_kind(tmp_path: Path) -> None:
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    with pytest.raises(ValueError, match="uml_kind must be one of"):
        tool.validate_arguments({"uml_kind": "state"})


@pytest.mark.asyncio
async def test_knowledge_graph_tool_exports_mermaid_uml(tmp_path: Path) -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[
            KnowledgeNode(id="package:src", kind="package", label="src"),
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
            KnowledgeNode(
                id="src/app.py:helper:4",
                kind="function",
                label="helper",
                file_path="src/app.py",
            ),
        ],
        edges=[
            KnowledgeEdge(
                id="edge:contains",
                source="package:src",
                target="file:src/app.py",
                kind="contains",
            ),
            KnowledgeEdge(
                id="edge:calls",
                source="src/app.py:main:1",
                target="src/app.py:helper:4",
                kind="calls",
                metadata={"callee_name": "helper"},
            ),
        ],
        stats={"node_count": 4, "edge_count": 2},
    )
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    result = await tool.execute(
        {
            "export_format": "uml",
            "uml_kind": "component",
            "max_nodes": 5,
            "max_edges": 5,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["graph"]["schema"] == "tsa.knowledge_graph.uml.v1"
    assert result["graph"]["diagram"] == "component"
    assert result["graph"]["mermaid"].splitlines()[0] == "flowchart LR"
    assert result["graph"]["stats"]["export_node_count"] == 2
    assert result["graph"]["stats"]["export_edge_count"] == 1

    sequence = await tool.execute(
        {
            "export_format": "uml",
            "uml_kind": "sequence",
            "max_nodes": 5,
            "max_edges": 5,
            "output_format": "json",
        }
    )

    assert sequence["success"] is True
    assert sequence["graph"]["diagram"] == "sequence"
    assert sequence["graph"]["mermaid"].splitlines()[0] == "sequenceDiagram"
    assert "helper" in sequence["graph"]["mermaid"]
    assert sequence["graph"]["stats"]["export_edge_count"] == 1


@pytest.mark.asyncio
async def test_knowledge_graph_tool_uses_uml_sized_default_caps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = KnowledgeGraphSnapshot(
        nodes=[KnowledgeNode(id="file:src/app.py", kind="file", label="src/app.py")],
        edges=[],
        stats={"node_count": 1, "edge_count": 0},
    )
    JsonKnowledgeGraphStore(str(tmp_path)).write(snapshot)
    captured: dict[str, object] = {}

    def _fake_to_mermaid_uml(
        snapshot: KnowledgeGraphSnapshot,
        **kwargs: object,
    ) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "schema": "tsa.knowledge_graph.uml.v1",
            "syntax": "mermaid",
            "diagram": kwargs["diagram"],
            "mermaid": "flowchart LR",
            "stats": {"export_node_count": 1, "export_edge_count": 0},
        }

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool.to_mermaid_uml",
        _fake_to_mermaid_uml,
    )
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    result = await tool.execute({"export_format": "uml", "output_format": "json"})

    assert result["success"] is True
    assert captured["max_nodes"] == 200
    assert captured["max_edges"] == 500
