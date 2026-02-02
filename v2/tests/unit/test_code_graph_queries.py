"""
Unit tests for Code Graph Queries (Milestone 2: Call Relationship Analysis).

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 8 - Milestone 2: Call Relationship Analysis (6 tests)
"""

import tempfile
from pathlib import Path


class TestCallRelationshipAnalysis:
    """Tests for function call extraction and CALLS edge construction."""

    def test_extract_function_calls(self):
        """Test extraction of function calls from code."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

        code = """
def helper():
    return 42

def main():
    result = helper()
    print(result)
    return result
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Should have CALLS edges
            calls_edges = [(u, v, d) for u, v, d in graph.edges(data=True) if d["type"] == "CALLS"]
            assert len(calls_edges) > 0

            # main() should call helper()
            main_node = [n for n, d in graph.nodes(data=True) if d.get("name") == "main"][0]
            helper_node = [n for n, d in graph.nodes(data=True) if d.get("name") == "helper"][0]

            # Check if main CALLS helper
            assert graph.has_edge(main_node, helper_node)
            edge_data = graph.edges[main_node, helper_node]
            assert edge_data["type"] == "CALLS"
        finally:
            Path(temp_path).unlink()

    def test_resolve_method_call(self):
        """Test resolving method calls on objects."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

        code = """
class Calculator:
    def add(self, a, b):
        return a + b

def compute():
    calc = Calculator()
    result = calc.add(1, 2)
    return result
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # compute() should call Calculator.add()
            compute_node = [n for n, d in graph.nodes(data=True) if d.get("name") == "compute"][0]
            add_node = [
                n
                for n, d in graph.nodes(data=True)
                if d.get("name") == "add" and d["type"] == "FUNCTION"
            ][0]

            # Check CALLS edge exists
            calls_edges = [(u, v, d) for u, v, d in graph.edges(data=True) if d["type"] == "CALLS"]
            assert len(calls_edges) > 0

            # compute should call add (even if indirect through object)
            # This tests that we can resolve calc.add(1, 2) -> Calculator.add
            edge_exists = any(
                u == compute_node and "add" in graph.nodes[v].get("name", "")
                for u, v, d in calls_edges
            )
            assert edge_exists
        finally:
            Path(temp_path).unlink()

    def test_handle_import_aliases(self):
        """Test handling of import aliases in call resolution."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

        code = """
from pathlib import Path as P

def use_path():
    p = P("/tmp")
    return p.exists()
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Should recognize P as alias for Path
            # Check that imports are tracked correctly
            module_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "MODULE"]
            assert len(module_nodes) == 1

            module_data = graph.nodes[module_nodes[0]]
            # Import with alias should be recorded
            assert any("Path" in imp or "pathlib" in imp for imp in module_data.get("imports", []))
        finally:
            Path(temp_path).unlink()

    def test_get_callers_query(self):
        """Test get_callers() query to find who calls a function."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.queries import get_callers

        code = """
def utility():
    return 100

def process():
    return utility() + 1

def execute():
    return utility() + process()
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Find utility() function node
            utility_node = [n for n, d in graph.nodes(data=True) if d.get("name") == "utility"][0]

            # Get callers of utility()
            callers = get_callers(graph, utility_node)

            # Both process() and execute() call utility()
            assert len(callers) == 2
            caller_names = [graph.nodes[c].get("name") for c in callers]
            assert "process" in caller_names
            assert "execute" in caller_names
        finally:
            Path(temp_path).unlink()

    def test_get_call_chain_query(self):
        """Test get_call_chain() query to trace call paths."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.queries import get_call_chain

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

            # Find nodes
            main_node = [n for n, d in graph.nodes(data=True) if d.get("name") == "main"][0]
            level3_node = [n for n, d in graph.nodes(data=True) if d.get("name") == "level3"][0]

            # Get call chain from main to level3
            chains = get_call_chain(graph, main_node, level3_node)

            # Should find at least one path: main -> level1 -> level2 -> level3
            assert len(chains) > 0

            # Verify the chain has 4 functions
            first_chain = chains[0]
            assert len(first_chain) == 4

            # Verify chain order: main -> level1 -> level2 -> level3
            chain_names = [graph.nodes[n].get("name") for n in first_chain]
            assert chain_names == ["main", "level1", "level2", "level3"]
        finally:
            Path(temp_path).unlink()

    def test_call_resolution_accuracy(self):
        """Test that call resolution handles multiple call types."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

        code = """
def standalone():
    pass

class MyClass:
    def method(self):
        pass

    def caller(self):
        self.method()
        standalone()

def module_func():
    obj = MyClass()
    obj.method()
    standalone()
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Count CALLS edges
            calls_edges = [(u, v, d) for u, v, d in graph.edges(data=True) if d["type"] == "CALLS"]

            # Should have multiple CALLS edges:
            # - caller() calls method()
            # - caller() calls standalone()
            # - module_func() calls method()
            # - module_func() calls standalone()
            assert len(calls_edges) >= 2  # At least some calls resolved

            # Verify standalone() has callers
            standalone_node = [
                n for n, d in graph.nodes(data=True) if d.get("name") == "standalone"
            ][0]
            callers_of_standalone = [u for u, v, d in calls_edges if v == standalone_node]
            assert len(callers_of_standalone) > 0
        finally:
            Path(temp_path).unlink()


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_find_definition_existing(self):
        """Test finding existing function and class definitions."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.queries import find_definition

        code = """
class MyClass:
    def method(self):
        pass

def my_function():
    pass

def another_function():
    pass
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Find class by name
            class_results = find_definition(graph, "MyClass")
            assert len(class_results) == 1
            assert "MyClass" in class_results[0]

            # Find function by name
            func_results = find_definition(graph, "my_function")
            assert len(func_results) == 1
            assert "my_function" in func_results[0]

            # Find another function
            another_results = find_definition(graph, "another_function")
            assert len(another_results) == 1
        finally:
            Path(temp_path).unlink()

    def test_find_definition_nonexistent(self):
        """Test finding nonexistent definition returns empty list."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.queries import find_definition

        code = """
def existing_function():
    pass
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Search for nonexistent function
            results = find_definition(graph, "nonexistent_function")
            assert len(results) == 0
            assert results == []
        finally:
            Path(temp_path).unlink()

    def test_get_call_chain_no_path(self):
        """Test get_call_chain when no path exists between functions."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.queries import get_call_chain

        code = """
def isolated_a():
    return 1

def isolated_b():
    return 2
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Find both functions
            a_node = [n for n, d in graph.nodes(data=True) if d.get("name") == "isolated_a"][0]
            b_node = [n for n, d in graph.nodes(data=True) if d.get("name") == "isolated_b"][0]

            # Try to find path (should be empty since no calls exist)
            chains = get_call_chain(graph, a_node, b_node)
            assert len(chains) == 0
            assert chains == []
        finally:
            Path(temp_path).unlink()

    def test_get_call_chain_node_not_found(self):
        """Test get_call_chain with nonexistent node IDs."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.queries import get_call_chain

        code = """
def some_function():
    pass
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Use nonexistent node IDs
            chains = get_call_chain(graph, "nonexistent_start", "nonexistent_end")
            assert len(chains) == 0
            assert chains == []
        finally:
            Path(temp_path).unlink()

    def test_get_callers_no_callers(self):
        """Test get_callers when function has no callers."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.queries import get_callers

        code = """
def never_called():
    return 42

def main():
    return 100
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Find the never_called function
            never_called_node = [
                n for n, d in graph.nodes(data=True) if d.get("name") == "never_called"
            ][0]

            # Should have no callers
            callers = get_callers(graph, never_called_node)
            assert len(callers) == 0
            assert callers == []
        finally:
            Path(temp_path).unlink()
