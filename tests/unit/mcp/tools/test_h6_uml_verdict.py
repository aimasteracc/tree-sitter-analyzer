"""H6 regression tests: viz uml verdict for single node (no edges).

H6 bug: a diagram with nodes but no edges returned verdict=NOT_FOUND because
the logic was ``"INFO" if diagram.edges else "NOT_FOUND"``.

Fix: verdict is INFO when ``not_found==False AND node_count >= 1``, regardless
of whether the diagram has edges.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


class _FakeDiagram:
    """Minimal diagram object mirroring the interface used in CodeGraphUMLTool."""

    def __init__(
        self,
        *,
        edges: list | None = None,
        nodes: list | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.edges = edges or []
        self.nodes = nodes or []
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "nodes": [str(n) for n in self.nodes],
            "edges": [str(e) for e in self.edges],
            "metadata": self.metadata,
        }


def _run_uml_execute(diagram: _FakeDiagram) -> dict:
    """Invoke CodeGraphUMLTool.execute with a pre-baked diagram, patching the exporter."""
    from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool

    tool = CodeGraphUMLTool(project_root="/fake")

    # Build a mock exporter that returns our fake diagram for any diagram type
    mock_exporter = MagicMock()
    mock_exporter.class_diagram.return_value = diagram

    # Patch CodeGraphVisualizationHub so it returns our mock exporter
    mock_hub = MagicMock()
    mock_hub.uml_exporter.return_value = mock_exporter

    with patch(
        "tree_sitter_analyzer.mcp.tools.uml_tool.CodeGraphVisualizationHub",
        return_value=mock_hub,
    ):
        return asyncio.run(
            tool.execute(
                {
                    "diagram": "class",
                    "class_name": "MyClass",
                    "output_format": "json",
                }
            )
        )


def test_h6_single_class_no_edges_returns_info() -> None:
    """H6 regression: a diagram with 1 node and 0 edges must return INFO, not NOT_FOUND."""
    diagram = _FakeDiagram(
        nodes=["MyClass"],
        edges=[],
        metadata={"not_found": False},
    )
    result = _run_uml_execute(diagram)

    assert result.get("verdict") == "INFO", (
        f"H6 regression: single node diagram should return INFO, got {result.get('verdict')}"
    )


def test_h6_no_nodes_no_edges_returns_not_found() -> None:
    """H6: when neither nodes nor edges are present, NOT_FOUND must be returned."""
    diagram = _FakeDiagram(
        nodes=[],
        edges=[],
        metadata={"not_found": False},
    )
    result = _run_uml_execute(diagram)

    assert result.get("verdict") == "NOT_FOUND", (
        f"H6: empty diagram (no nodes or edges) should return NOT_FOUND, got {result.get('verdict')}"
    )


def test_h6_not_found_flag_overrides_nodes() -> None:
    """H6: when not_found==True in metadata, verdict must be NOT_FOUND even with nodes."""
    diagram = _FakeDiagram(
        nodes=["SomeClass"],
        edges=[],
        metadata={"not_found": True},
    )
    result = _run_uml_execute(diagram)

    assert result.get("verdict") == "NOT_FOUND", (
        f"H6: not_found=True should still yield NOT_FOUND, got {result.get('verdict')}"
    )


def test_h6_edges_present_returns_info() -> None:
    """H6: existing test must still pass — edges also trigger INFO."""
    diagram = _FakeDiagram(
        nodes=["ClassA", "ClassB"],
        edges=[("ClassA", "ClassB")],
        metadata={"not_found": False},
    )
    result = _run_uml_execute(diagram)

    assert result.get("verdict") == "INFO", (
        f"H6: diagram with edges should return INFO, got {result.get('verdict')}"
    )
