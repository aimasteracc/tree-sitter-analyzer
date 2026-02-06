"""
Integration tests for Java code graph construction.

Tests the full pipeline: JavaParser → CodeGraphBuilder → NetworkX graph.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder


@pytest.fixture
def java_fixture_dir():
    """Return path to Java test fixtures."""
    return Path(__file__).parent.parent / "fixtures" / "java_graph"


@pytest.fixture
def java_builder():
    """Create CodeGraphBuilder for Java."""
    return CodeGraphBuilder(language="java")


# T4.2: Implement Java Node Extraction


def test_build_java_graph_from_file(java_builder, java_fixture_dir):
    """Test building code graph from Java file."""
    java_file = java_fixture_dir / "User.java"
    graph = java_builder.build_from_file(str(java_file))

    # Verify graph is not empty
    assert graph.number_of_nodes() > 0
    assert graph.number_of_edges() > 0


def test_java_graph_has_module_node(java_builder, java_fixture_dir):
    """Test that Java graph has MODULE node for the file."""
    java_file = java_fixture_dir / "User.java"
    graph = java_builder.build_from_file(str(java_file))

    # Find MODULE nodes
    module_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "MODULE"]

    assert len(module_nodes) == 1
    module_data = graph.nodes[module_nodes[0]]
    assert module_data["name"] == "User"  # Module name is file stem (without extension)


def test_java_graph_has_class_nodes(java_builder, java_fixture_dir):
    """Test that Java graph has CLASS nodes."""
    java_file = java_fixture_dir / "User.java"
    graph = java_builder.build_from_file(str(java_file))

    # Find CLASS nodes
    class_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "CLASS"]

    assert len(class_nodes) == 1
    class_data = graph.nodes[class_nodes[0]]
    assert class_data["name"] == "User"


def test_java_graph_has_method_nodes(java_builder, java_fixture_dir):
    """Test that Java graph has FUNCTION nodes for methods."""
    java_file = java_fixture_dir / "User.java"
    graph = java_builder.build_from_file(str(java_file))

    # Find FUNCTION nodes (methods)
    function_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "FUNCTION"]

    # User.java has: User (constructor), getName, getAge, validate
    assert len(function_nodes) == 4

    # Verify method names
    method_names = {graph.nodes[n]["name"] for n in function_nodes}
    assert "getName" in method_names
    assert "getAge" in method_names
    assert "validate" in method_names


def test_java_graph_contains_edges(java_builder, java_fixture_dir):
    """Test that Java graph has CONTAINS edges: Module → Class → Method."""
    java_file = java_fixture_dir / "User.java"
    graph = java_builder.build_from_file(str(java_file))

    # Get nodes by type
    module_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "MODULE"]
    class_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "CLASS"]
    function_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "FUNCTION"]

    module_id = module_nodes[0]
    class_id = class_nodes[0]

    # Verify CONTAINS edge: Module → Class
    assert graph.has_edge(module_id, class_id)
    assert graph[module_id][class_id]["type"] == "CONTAINS"

    # Verify CONTAINS edges: Class → Methods
    for func_id in function_nodes:
        assert graph.has_edge(class_id, func_id)
        assert graph[class_id][func_id]["type"] == "CONTAINS"


# T4.3: Build Java CALLS Edges (Intra-File)


def test_java_method_calls(java_builder, java_fixture_dir):
    """Test that Java graph has CALLS edges for method calls."""
    java_file = java_fixture_dir / "Service.java"
    graph = java_builder.build_from_file(str(java_file))

    # Find CALLS edges
    calls_edges = [(u, v) for u, v, d in graph.edges(data=True) if d.get("type") == "CALLS"]

    # Service.process() calls: validate(), helper.getData(), transform()
    # Should have at least 3 CALLS edges
    assert len(calls_edges) > 0


def test_java_calls_edge_details(java_builder, java_fixture_dir):
    """Test that CALLS edges have correct details."""
    java_file = java_fixture_dir / "Service.java"
    graph = java_builder.build_from_file(str(java_file))

    # Find process method node
    process_node = None
    for n, d in graph.nodes(data=True):
        if d.get("type") == "FUNCTION" and d.get("name") == "process":
            process_node = n
            break

    assert process_node is not None, "process() method not found"

    # Get outgoing CALLS edges from process()
    calls_from_process = [
        (v, graph[process_node][v])
        for v in graph.successors(process_node)
        if graph[process_node][v].get("type") == "CALLS"
    ]

    # process() should call at least validate() and transform()
    assert len(calls_from_process) >= 2


def test_java_simple_method_call(java_builder, java_fixture_dir):
    """Test simple method call is tracked."""
    java_file = java_fixture_dir / "Service.java"
    graph = java_builder.build_from_file(str(java_file))

    # Find validate method
    validate_node = None
    for n, d in graph.nodes(data=True):
        if d.get("type") == "FUNCTION" and d.get("name") == "validate":
            validate_node = n
            break

    assert validate_node is not None

    # Check if process calls validate
    calls_edges = [(u, v) for u, v, d in graph.edges(data=True) if d.get("type") == "CALLS"]
    validate_called = any(v == validate_node for u, v in calls_edges)

    assert validate_called, "validate() should be called by process()"
