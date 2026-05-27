"""Tests for the codegraph_uml MCP tool."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool


def test_uml_tool_definition() -> None:
    tool = CodeGraphUMLTool()
    definition = tool.get_tool_definition()

    assert definition["name"] == "codegraph_uml"
    assert "UML" in definition["description"]
    assert definition["annotations"]["readOnlyHint"] is True


def test_uml_tool_schema_lists_diagrams() -> None:
    tool = CodeGraphUMLTool()
    schema = tool.get_tool_schema()

    assert schema["properties"]["diagram"]["enum"] == [
        "class",
        "package",
        "component",
        "sequence",
    ]


def test_sequence_requires_source_and_target() -> None:
    tool = CodeGraphUMLTool()

    with pytest.raises(ValueError, match="source and target"):
        tool.validate_arguments({"diagram": "sequence", "source": "entry"})


def test_positive_integer_validation() -> None:
    tool = CodeGraphUMLTool()

    with pytest.raises(ValueError, match="max_edges"):
        tool.validate_arguments({"diagram": "class", "max_edges": 0})


def test_unsupported_diagram_validation() -> None:
    tool = CodeGraphUMLTool()

    with pytest.raises(ValueError, match="Unsupported UML diagram"):
        tool.validate_arguments({"diagram": "deployment"})


@pytest.mark.asyncio
async def test_class_diagram_execute_with_mock_exporter(monkeypatch) -> None:
    from tree_sitter_analyzer.mcp.tools import uml_tool
    from tree_sitter_analyzer.uml_export import UMLDiagram, UMLEdge

    monkeypatch.setattr(uml_tool, "ensure_indexed", lambda project_root: object())

    class FakeExporter:
        def __init__(self, project_root: str, cache: object | None = None) -> None:
            assert project_root == "/repo"
            assert cache is not None

        def class_diagram(
            self, max_edges: int, include_external_bases: bool
        ) -> UMLDiagram:
            assert max_edges == 5
            assert include_external_bases is False
            return UMLDiagram(
                diagram_type="class",
                mermaid_type="classDiagram",
                mermaid="classDiagram\n  Base <|-- Child",
                nodes=["Base", "Child"],
                edges=[UMLEdge("Base", "Child")],
            )

    monkeypatch.setattr(uml_tool, "UMLExporter", FakeExporter)

    tool = CodeGraphUMLTool("/repo")
    result = await tool.execute(
        {
            "diagram": "class",
            "max_edges": 5,
            "include_external_bases": False,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["diagram_type"] == "class"
    assert result["mermaid"].startswith("classDiagram")
    assert result["edge_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("diagram", "expected_mermaid"),
    [
        ("package", "flowchart LR\n  cli --> mcp"),
        ("component", "flowchart LR\n  cli --> mcp"),
        ("sequence", "sequenceDiagram\n  cli->>mcp: call"),
    ],
)
async def test_execute_dispatches_non_class_diagrams(
    monkeypatch,
    diagram: str,
    expected_mermaid: str,
) -> None:
    from tree_sitter_analyzer.mcp.tools import uml_tool
    from tree_sitter_analyzer.uml_export import UMLDiagram, UMLEdge

    monkeypatch.setattr(uml_tool, "ensure_indexed", lambda project_root: object())

    class FakeExporter:
        def __init__(self, project_root: str, cache: object | None = None) -> None:
            assert project_root == "/repo"
            assert cache is not None

        def package_diagram(self, max_edges: int, package_depth: int) -> UMLDiagram:
            assert (max_edges, package_depth) == (7, 3)
            return self._diagram("package")

        def component_diagram(self, max_edges: int) -> UMLDiagram:
            assert max_edges == 7
            return self._diagram("component")

        def sequence_diagram(
            self,
            source: str,
            target: str,
            max_depth: int,
            max_paths: int,
        ) -> UMLDiagram:
            assert (source, target, max_depth, max_paths) == (
                "cli",
                "mcp",
                4,
                2,
            )
            return self._diagram("sequence")

        def _diagram(self, diagram_type: str) -> UMLDiagram:
            return UMLDiagram(
                diagram_type=diagram_type,
                mermaid_type="sequenceDiagram"
                if diagram_type == "sequence"
                else "flowchart",
                mermaid=expected_mermaid,
                nodes=["cli", "mcp"],
                edges=[UMLEdge("cli", "mcp")],
            )

    monkeypatch.setattr(uml_tool, "UMLExporter", FakeExporter)

    arguments = {
        "diagram": diagram,
        "max_edges": 7,
        "package_depth": 3,
        "source": "cli",
        "target": "mcp",
        "max_depth": 4,
        "max_paths": 2,
        "output_format": "json",
    }
    result = await CodeGraphUMLTool("/repo").execute(arguments)

    assert result["success"] is True
    assert result["diagram_type"] == diagram
    assert result["mermaid"] == expected_mermaid


@pytest.mark.asyncio
async def test_no_project_root_returns_error() -> None:
    tool = CodeGraphUMLTool()

    result = await tool.execute({"diagram": "class", "output_format": "json"})

    assert result["success"] is False
    assert result["verdict"] == "ERROR"
