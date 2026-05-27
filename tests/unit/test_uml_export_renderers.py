"""Focused tests for UML Export Suite pure Mermaid renderers."""

from __future__ import annotations

from tree_sitter_analyzer.uml_export import (
    UMLDiagram,
    UMLEdge,
    render_class_mermaid,
    render_flowchart_mermaid,
    render_sequence_mermaid,
)


def test_class_mermaid_renderer_sanitizes_ids_and_keeps_inheritance_direction() -> None:
    mermaid = render_class_mermaid(
        ["Base.Tool", "2Child"],
        [UMLEdge("Base.Tool", "2Child", "inherits")],
    )

    assert mermaid.splitlines()[0] == "classDiagram"
    assert "class Base_Tool" in mermaid
    assert "class N_2Child" in mermaid
    assert "Base_Tool <|-- N_2Child" in mermaid


def test_class_mermaid_renderer_has_explicit_empty_state() -> None:
    mermaid = render_class_mermaid([], [])

    assert mermaid == "classDiagram\n  class EmptyProject"


def test_flowchart_renderer_supports_direction_labels_and_quote_escaping() -> None:
    mermaid = render_flowchart_mermaid(
        ['cli"core', "mcp.tools"],
        [UMLEdge('cli"core', "mcp.tools", "dispatches", 2)],
        direction="TD",
    )

    assert mermaid.splitlines()[0] == "flowchart TD"
    assert 'cli_core["cli\'core"]' in mermaid
    assert 'mcp_tools["mcp.tools"]' in mermaid
    assert "cli_core -->|dispatches| mcp_tools" in mermaid


def test_flowchart_renderer_has_explicit_empty_state() -> None:
    mermaid = render_flowchart_mermaid([], [])

    assert mermaid == 'flowchart LR\n  empty["No edges found"]'


def test_sequence_renderer_preserves_first_path_order_and_return_edges() -> None:
    mermaid = render_sequence_mermaid(
        [
            {
                "hops": [
                    {"caller": "CLI", "callee": "UMLTool"},
                    {"caller": "UMLTool", "callee": "Renderer"},
                ]
            },
            {
                "hops": [
                    {"caller": "Alternative", "callee": "Path"},
                ]
            },
        ],
        max_hops=10,
    )

    assert mermaid.splitlines()[0] == "sequenceDiagram"
    assert 'participant CLI as "CLI"' in mermaid
    assert 'participant UMLTool as "UMLTool"' in mermaid
    assert 'participant Renderer as "Renderer"' in mermaid
    assert "CLI->>+UMLTool: call" in mermaid
    assert "UMLTool-->>-CLI: return" in mermaid
    assert "UMLTool->>+Renderer: call" in mermaid
    assert "Alternative" not in mermaid


def test_sequence_renderer_clamps_to_max_hops() -> None:
    mermaid = render_sequence_mermaid(
        [
            {
                "hops": [
                    {"caller": "a", "callee": "b"},
                    {"caller": "b", "callee": "c"},
                ]
            }
        ],
        max_hops=1,
    )

    assert "a->>+b: call" in mermaid
    assert "b->>+c: call" not in mermaid


def test_uml_diagram_to_dict_keeps_mermaid_and_relationship_counts() -> None:
    diagram = UMLDiagram(
        diagram_type="component",
        mermaid_type="flowchart",
        mermaid="flowchart LR\n  cli --> tool",
        nodes=["cli", "tool"],
        edges=[UMLEdge("cli", "tool", "uses", 3)],
        truncated=True,
    )

    assert diagram.to_dict() == {
        "diagram_type": "component",
        "mermaid_type": "flowchart",
        "node_count": 2,
        "edge_count": 1,
        "truncated": True,
        "nodes": ["cli", "tool"],
        "edges": [{"source": "cli", "target": "tool", "weight": 3, "label": "uses"}],
        "mermaid": "flowchart LR\n  cli --> tool",
        "metadata": {},
    }
