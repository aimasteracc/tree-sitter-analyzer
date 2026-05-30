"""Tests for shared CodeGraph visualization hub helpers."""

from __future__ import annotations

from tree_sitter_analyzer.mcp.tools.codegraph_visualization_hub import (
    CodeGraphVisualizationHub,
    query_flow_uml_facet,
    render_call_flowchart,
    safe_node_id,
    short_label,
)


def test_render_call_flowchart_keeps_visualize_compatibility() -> None:
    mermaid = render_call_flowchart(
        [("src_py__run", "src.py::run", "util_py__helper", "util.py::helper")],
        "TD",
    )

    assert mermaid == "\n".join(
        [
            "flowchart TD",
            '    src_py__run["src.py::run"]',
            '    util_py__helper["util.py::helper"]',
            "    src_py__run --> util_py__helper",
        ]
    )


def test_render_call_flowchart_deduplicates_edges() -> None:
    mermaid = render_call_flowchart(
        [
            ("a", "A", "b", "B"),
            ("a", "A", "b", "B"),
        ]
    )

    assert mermaid.count("a --> b") == 1


def test_node_label_helpers_are_stable() -> None:
    assert safe_node_id("my-func", "src/dir/file.py") == "src_dir_file_py__my_func"
    assert short_label("parse", "src/dir/file.py") == "file.py::parse"


def test_hub_returns_no_graph_or_exporter_without_project_root() -> None:
    hub = CodeGraphVisualizationHub(None)

    assert hub.call_graph() is None
    assert hub.uml_exporter() is None


def test_query_flow_uml_facet_renders_callee_relationships() -> None:
    run = {"file": "main.py", "line": 1, "name": "run"}
    facet = query_flow_uml_facet(
        symbols=[run],
        current=[run],
        relationships={
            "callees": {
                "main.py:1:run": [{"file": "main.py", "line": 4, "name": "helper"}]
            },
            "callers": {},
        },
        direction="TD",
        max_edges=10,
    )

    assert facet["status"] == "included"
    assert facet["diagram_type"] == "query_flow"
    assert facet["metadata"] == {"source": "codegraph_query", "direction": "TD"}
    assert facet["nodes"] == ["helper", "run"]
    assert facet["edges"] == [
        {"source": "run", "target": "helper", "weight": 1, "label": "calls"}
    ]
    assert 'run["run"]' in facet["mermaid"]
    assert "run -->|calls| helper" in facet["mermaid"]


def test_query_flow_uml_facet_clamps_invalid_direction_and_edges() -> None:
    run = {"file": "main.py", "line": 1, "name": "run"}
    facet = query_flow_uml_facet(
        symbols=[run],
        current=[run],
        relationships={
            "callees": {
                "main.py:1:run": [
                    {"file": "main.py", "line": 4, "name": "helper"},
                    {"file": "main.py", "line": 5, "name": "other"},
                ]
            },
            "callers": {},
        },
        direction="sideways",
        max_edges=1,
    )

    assert facet["metadata"]["direction"] == "LR"
    assert facet["edge_count"] == 1
    assert facet["truncated"] is True
