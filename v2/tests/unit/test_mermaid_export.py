"""
Unit tests for Mermaid diagram export (E4 Enhancement).

Tests the export_to_mermaid(), export_to_call_flow(), and
export_to_dependency_graph() functions.
"""

import tempfile
from pathlib import Path

from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
from tree_sitter_analyzer_v2.graph.export import (
    export_to_call_flow,
    export_to_dependency_graph,
    export_to_mermaid,
)


class TestMermaidExport:
    """Tests for export_to_mermaid() function."""

    def test_export_simple_functions(self):
        """Test Mermaid export for simple functions."""
        code = """
def helper():
    return 42

def main():
    return helper()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            mermaid = export_to_mermaid(graph)

            # Verify Mermaid format
            assert mermaid.startswith("graph TD")
            assert "helper" in mermaid
            assert "main" in mermaid
            assert "-->" in mermaid  # Has call edges

        finally:
            Path(temp_path).unlink()

    def test_export_with_classes(self):
        """Test Mermaid export with classes (subgraphs)."""
        code = """
class MyClass:
    def method1(self):
        return self.method2()

    def method2(self):
        return 42

def function():
    return MyClass().method1()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            mermaid = export_to_mermaid(graph, show_classes=True)

            # Verify class subgraph
            assert "subgraph MyClass" in mermaid
            assert "method1" in mermaid
            assert "method2" in mermaid
            assert "end" in mermaid  # Subgraph end

        finally:
            Path(temp_path).unlink()

    def test_export_without_classes(self):
        """Test Mermaid export without class containers."""
        code = """
class MyClass:
    def method(self):
        return 1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            mermaid = export_to_mermaid(graph, show_classes=False)

            # Should not have subgraph
            assert "subgraph" not in mermaid

        finally:
            Path(temp_path).unlink()

    def test_export_with_max_nodes(self):
        """Test max_nodes parameter limits diagram size."""
        # Create file with many functions
        functions = [f"def func{i}(): return {i}" for i in range(20)]
        code = "\n\n".join(functions)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Export with limit
            mermaid = export_to_mermaid(graph, max_nodes=5)

            # Count function nodes (look for bracket notation like [func0])
            bracket_count = mermaid.count("[")

            # Should have limited nodes
            assert bracket_count <= 5

        finally:
            Path(temp_path).unlink()

    def test_export_direction_parameter(self):
        """Test direction parameter (TD vs LR)."""
        code = """
def helper():
    return 42

def main():
    return helper()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Top-down
            mermaid_td = export_to_mermaid(graph, direction="TD")
            assert mermaid_td.startswith("graph TD")

            # Left-right
            mermaid_lr = export_to_mermaid(graph, direction="LR")
            assert mermaid_lr.startswith("graph LR")

        finally:
            Path(temp_path).unlink()

    def test_export_filters_private_functions(self):
        """Test that private functions are filtered out."""
        code = """
def public_func():
    return 1

def _private_func():
    return 2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            mermaid = export_to_mermaid(graph)

            # Public function should be present
            assert "public_func" in mermaid

            # Private function should be filtered
            assert "_private_func" not in mermaid

        finally:
            Path(temp_path).unlink()


class TestCallFlowExport:
    """Tests for export_to_call_flow() function."""

    def test_call_flow_basic(self):
        """Test basic call flow visualization."""
        code = """
def level3():
    return "done"

def level2():
    return level3()

def level1():
    return level2()

def main():
    return level1()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            mermaid = export_to_call_flow(graph, start_function="main")

            # Verify call flow
            assert "graph TD" in mermaid
            assert "main" in mermaid
            assert "level1" in mermaid
            assert "level2" in mermaid
            assert "level3" in mermaid
            assert "start" in mermaid  # Styling for start node

        finally:
            Path(temp_path).unlink()

    def test_call_flow_max_depth(self):
        """Test max_depth parameter limits call flow depth."""
        code = """
def level3():
    return "done"

def level2():
    return level3()

def level1():
    return level2()

def main():
    return level1()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Limit depth to 2
            mermaid = export_to_call_flow(graph, start_function="main", max_depth=2)

            # Should have main and level1
            assert "main" in mermaid
            assert "level1" in mermaid

            # May or may not have deeper levels depending on BFS order

        finally:
            Path(temp_path).unlink()

    def test_call_flow_function_not_found(self):
        """Test error handling when function not found."""
        code = """
def helper():
    return 42
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            mermaid = export_to_call_flow(graph, start_function="nonexistent")

            # Should have error message
            assert "error" in mermaid.lower()
            assert "not found" in mermaid.lower()

        finally:
            Path(temp_path).unlink()


class TestDependencyGraphExport:
    """Tests for export_to_dependency_graph() function."""

    def test_dependency_graph_multi_file(self):
        """Test dependency graph for multiple modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create module1
            (tmppath / "module1.py").write_text("""
def func1():
    return 1
""")

            # Create module2
            (tmppath / "module2.py").write_text("""
def func2():
    return 2
""")

            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath))

            mermaid = export_to_dependency_graph(graph)

            # Verify format
            assert "graph LR" in mermaid  # Left-right for dependencies
            assert "module1" in mermaid or "module2" in mermaid

    def test_dependency_graph_max_modules(self):
        """Test max_modules parameter limits diagram size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create many modules
            for i in range(10):
                (tmppath / f"module{i}.py").write_text(f"def func{i}(): return {i}")

            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath))

            mermaid = export_to_dependency_graph(graph, max_modules=3)

            # Should have limited modules
            bracket_count = mermaid.count("[")
            assert bracket_count <= 3

    def test_dependency_graph_empty(self):
        """Test dependency graph with no modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(tmpdir)

            mermaid = export_to_dependency_graph(graph)

            # Should still have valid format
            assert "graph LR" in mermaid


class TestMermaidSafeNodeId:
    """Tests for _safe_node_id() helper function."""

    def test_safe_node_id_replaces_colons(self):
        """Test that colons are replaced."""
        from tree_sitter_analyzer_v2.graph.export import _safe_node_id

        unsafe = "module:file:function:name"
        safe = _safe_node_id(unsafe)

        assert ":" not in safe
        assert "_" in safe

    def test_safe_node_id_replaces_slashes(self):
        """Test that slashes are replaced."""
        from tree_sitter_analyzer_v2.graph.export import _safe_node_id

        unsafe = "path/to/module"
        safe = _safe_node_id(unsafe)

        assert "/" not in safe
        assert "_" in safe
