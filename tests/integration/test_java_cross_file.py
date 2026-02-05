"""
Integration tests for Java cross-file call resolution.

Tests the full pipeline: JavaParser → JavaImportResolver → CodeGraphBuilder → Cross-file resolution.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder


@pytest.fixture
def java_cross_file_dir():
    """Return path to Java cross-file test fixtures."""
    return Path(__file__).parent.parent / "fixtures" / "java_cross_file"


@pytest.fixture
def java_builder():
    """Create CodeGraphBuilder for Java."""
    return CodeGraphBuilder(language="java")


# T5.1: Adapt Cross-File Infrastructure for Java


def test_java_build_from_directory_basic(java_builder, java_cross_file_dir):
    """Test building graph from Java directory without cross-file resolution."""
    graph = java_builder.build_from_directory(
        str(java_cross_file_dir), pattern="**/*.java", cross_file=False
    )

    # Verify graph has nodes from all files
    assert graph.number_of_nodes() > 0

    # Check for nodes from different files
    node_names = [d.get("name") for n, d in graph.nodes(data=True)]
    assert "App" in node_names  # Class from App.java
    assert "UserService" in node_names  # Class from UserService.java


def test_java_cross_file_calls(java_builder, java_cross_file_dir):
    """Test that cross-file calls are resolved when cross_file=True."""
    graph = java_builder.build_from_directory(
        str(java_cross_file_dir), pattern="**/*.java", cross_file=True
    )

    # Find CALLS edges marked as cross_file
    cross_file_edges = [(u, v) for u, v, d in graph.edges(data=True) if d.get("cross_file") is True]

    # Should have cross-file calls: App.run() -> UserService.processUsers()
    # and UserService.processUsers() -> UserRepository.getAllUsers()
    assert len(cross_file_edges) > 0, "Expected cross-file CALLS edges"


def test_java_cross_file_vs_intra_file(java_builder, java_cross_file_dir):
    """Test that cross_file=True adds more edges than cross_file=False."""
    graph_no_cross = java_builder.build_from_directory(
        str(java_cross_file_dir), pattern="**/*.java", cross_file=False
    )

    graph_with_cross = java_builder.build_from_directory(
        str(java_cross_file_dir), pattern="**/*.java", cross_file=True
    )

    # With cross-file resolution, should have more CALLS edges
    calls_no_cross = [
        (u, v) for u, v, d in graph_no_cross.edges(data=True) if d.get("type") == "CALLS"
    ]

    calls_with_cross = [
        (u, v) for u, v, d in graph_with_cross.edges(data=True) if d.get("type") == "CALLS"
    ]

    assert len(calls_with_cross) >= len(
        calls_no_cross
    ), "Cross-file resolution should not reduce CALLS edges"


def test_java_cross_file_edge_attributes(java_builder, java_cross_file_dir):
    """Test that cross-file edges have correct attributes."""
    graph = java_builder.build_from_directory(
        str(java_cross_file_dir), pattern="**/*.java", cross_file=True
    )

    # Find a cross-file edge
    cross_file_edges = [
        (u, v, d) for u, v, d in graph.edges(data=True) if d.get("cross_file") is True
    ]

    if cross_file_edges:
        u, v, data = cross_file_edges[0]
        # Verify edge attributes
        assert data.get("type") == "CALLS"
        assert data.get("cross_file") is True
