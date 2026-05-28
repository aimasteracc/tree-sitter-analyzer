"""Tests for shared CodeGraph visualization hub helpers."""

from __future__ import annotations

from tree_sitter_analyzer.mcp.tools.codegraph_visualization_hub import (
    CodeGraphVisualizationHub,
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
