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
        ],
        stats={"node_count": 6, "edge_count": 2},
    )

    component = to_mermaid_uml(snapshot, diagram="component")
    package = to_mermaid_uml(snapshot, diagram="package")
    class_view = to_mermaid_uml(snapshot, diagram="class")

    assert component["syntax"] == "mermaid"
    assert component["diagram"] == "component"
    assert component["mermaid"].splitlines()[0] == "flowchart LR"
    assert component["stats"]["export_node_count"] == 4
    assert component["stats"]["export_edge_count"] == 1
    assert package["diagram"] == "package"
    assert package["stats"]["export_node_count"] == 2
    assert package["stats"]["export_edge_count"] == 2
    assert class_view["mermaid"].splitlines()[0] == "classDiagram"
    assert " <|-- " in class_view["mermaid"]
    assert class_view["stats"]["export_node_count"] == 2
    assert class_view["stats"]["export_edge_count"] == 1
    with pytest.raises(ValueError, match="diagram"):
        to_mermaid_uml(snapshot, diagram="sequence")


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


def test_knowledge_graph_tool_rejects_bad_uml_kind(tmp_path: Path) -> None:
    tool = CodeGraphKnowledgeGraphTool(str(tmp_path))

    with pytest.raises(ValueError, match="uml_kind must be one of"):
        tool.validate_arguments({"uml_kind": "sequence"})


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
        ],
        edges=[
            KnowledgeEdge(
                id="edge:contains",
                source="package:src",
                target="file:src/app.py",
                kind="contains",
            )
        ],
        stats={"node_count": 2, "edge_count": 1},
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
