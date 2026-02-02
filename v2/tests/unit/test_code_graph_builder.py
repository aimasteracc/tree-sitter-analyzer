"""
Unit tests for Code Graph Builder (Milestone 1: Basic Graph Construction).

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 8 - Milestone 1: Basic Graph Construction (6 tests)
"""

import tempfile
from pathlib import Path

import pytest


class TestCodeGraphBuilder:
    """Tests for basic code graph construction."""

    def test_build_module_node(self):
        """Test extraction of module node metadata."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

        code = '''
"""Sample module for testing."""
import pathlib
from typing import Dict

def hello():
    pass
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Should have 1 module node
            module_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "MODULE"]
            assert len(module_nodes) == 1

            module_data = graph.nodes[module_nodes[0]]
            assert module_data["type"] == "MODULE"
            assert "file_path" in module_data
            assert "mtime" in module_data
            assert module_data["imports"] == ["pathlib", "typing.Dict"]
        finally:
            Path(temp_path).unlink()

    def test_build_class_node(self):
        """Test extraction of class node with methods."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

        code = '''
class Calculator:
    """A simple calculator."""

    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Should have 1 class node
            class_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "CLASS"]
            assert len(class_nodes) == 1

            class_data = graph.nodes[class_nodes[0]]
            assert class_data["type"] == "CLASS"
            assert class_data["name"] == "Calculator"
            assert "add" in class_data["methods"]
            assert "subtract" in class_data["methods"]
            assert "start_line" in class_data
            assert "end_line" in class_data
        finally:
            Path(temp_path).unlink()

    def test_build_function_node(self):
        """Test extraction of function node with parameters and return type."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

        code = '''
async def process_data(file_path: str, options: dict) -> dict:
    """Process data from file."""
    result = {'status': 'success'}
    return result
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Should have 1 function node (module-level function)
            func_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "FUNCTION"]
            assert len(func_nodes) == 1

            func_data = graph.nodes[func_nodes[0]]
            assert func_data["type"] == "FUNCTION"
            assert func_data["name"] == "process_data"
            assert func_data["is_async"] == True
            assert "file_path" in func_data["params"]
            assert "options" in func_data["params"]
            assert func_data["return_type"] == "dict"
        finally:
            Path(temp_path).unlink()

    def test_build_contains_edges(self):
        """Test building CONTAINS edges: Module → Class → Function."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

        code = """
class MyClass:
    def my_method(self):
        pass

def my_function():
    pass
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Find nodes
            module_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "MODULE"]
            class_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "CLASS"]
            func_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "FUNCTION"]

            assert len(module_nodes) == 1
            assert len(class_nodes) == 1
            assert len(func_nodes) == 2  # my_method + my_function

            # Check CONTAINS edges
            module_id = module_nodes[0]
            class_id = class_nodes[0]

            # Module CONTAINS Class
            assert graph.has_edge(module_id, class_id)
            edge_data = graph.edges[module_id, class_id]
            assert edge_data["type"] == "CONTAINS"

            # Module CONTAINS my_function (module-level)
            module_funcs = [f for f in func_nodes if graph.has_edge(module_id, f)]
            assert len(module_funcs) >= 1

            # Class CONTAINS my_method
            class_methods = [f for f in func_nodes if graph.has_edge(class_id, f)]
            assert len(class_methods) == 1
        finally:
            Path(temp_path).unlink()

    def test_persist_and_load_graph(self):
        """Test saving graph to .gpickle and loading it back."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

        code = """
class TestClass:
    def test_method(self):
        return "test"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        with tempfile.NamedTemporaryFile(suffix=".gpickle", delete=False) as f:
            graph_path = f.name

        try:
            # Build and save
            builder = CodeGraphBuilder()
            original_graph = builder.build_from_file(temp_path)
            builder.save_graph(original_graph, graph_path)

            # Load
            loaded_graph = builder.load_graph(graph_path)

            # Verify structure preserved
            assert loaded_graph.number_of_nodes() == original_graph.number_of_nodes()
            assert loaded_graph.number_of_edges() == original_graph.number_of_edges()

            # Verify node data preserved
            for node in original_graph.nodes():
                assert node in loaded_graph.nodes()
                assert loaded_graph.nodes[node] == original_graph.nodes[node]
        finally:
            Path(temp_path).unlink()
            Path(graph_path).unlink()

    def test_analyze_self(self):
        """Test building graph of tree-sitter-analyzer v2 project itself."""
        from pathlib import Path

        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

        # Analyze a core module from v2 project
        project_root = Path(__file__).parent.parent.parent
        core_module = project_root / "tree_sitter_analyzer_v2" / "core" / "parser.py"

        # Skip if file doesn't exist (may not be in final structure yet)
        if not core_module.exists():
            pytest.skip("Core module not yet available")

        builder = CodeGraphBuilder()
        graph = builder.build_from_file(str(core_module))

        # Should extract some nodes
        assert graph.number_of_nodes() > 0

        # Should have at least module node
        module_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "MODULE"]
        assert len(module_nodes) >= 1

        # Should have some CONTAINS edges
        contains_edges = [(u, v) for u, v, d in graph.edges(data=True) if d["type"] == "CONTAINS"]
        assert len(contains_edges) > 0
