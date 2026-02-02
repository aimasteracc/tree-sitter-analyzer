"""
Tests for cross-file call resolution.

This module tests the CrossFileCallResolver class, ensuring correct
resolution of function calls across file boundaries using import context.
"""

import networkx as nx

from tree_sitter_analyzer_v2.graph.cross_file import CrossFileCallResolver
from tree_sitter_analyzer_v2.graph.symbols import SymbolEntry, SymbolTable


class TestCrossFileCallResolverBasics:
    """Test basic CrossFileCallResolver initialization and utilities."""

    def test_init(self):
        """Test CrossFileCallResolver initialization."""
        import_graph = nx.DiGraph()
        symbol_table = SymbolTable()

        resolver = CrossFileCallResolver(import_graph, symbol_table)

        assert resolver.import_graph is import_graph
        assert resolver.symbol_table is symbol_table
        assert resolver.unresolved == []

    def test_get_unresolved_calls_empty(self):
        """Test get_unresolved_calls returns empty list initially."""
        resolver = CrossFileCallResolver(nx.DiGraph(), SymbolTable())
        assert resolver.get_unresolved_calls() == []

    def test_get_file(self):
        """Test extracting file path from node ID."""
        resolver = CrossFileCallResolver(nx.DiGraph(), SymbolTable())

        assert resolver._get_file("app/main.py:main") == "app/main.py"
        assert resolver._get_file("utils.py:helper") == "utils.py"
        assert resolver._get_file("package/sub/module.py:process") == "package/sub/module.py"


class TestCallResolutionSameFile:
    """Test same-file call resolution (highest priority)."""

    def test_resolve_same_file_call(self):
        """Test resolving a call to function in same file."""
        # Setup symbol table
        symbol_table = SymbolTable()
        helper_entry = SymbolEntry(
            node_id="app.py:helper",
            file_path="app.py",
            name="helper",
            type="FUNCTION",
            line_start=10,
            line_end=20,
        )
        symbol_table.add(helper_entry)

        # Setup resolver
        import_graph = nx.DiGraph()
        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve call to helper from same file
        target = resolver._resolve_call("helper", "app.py", "app.py:main")

        assert target == "app.py:helper"
        assert resolver.unresolved == []

    def test_resolve_same_file_prioritized_over_imports(self):
        """Test that same-file definitions are prioritized over imported ones."""
        # Setup symbol table with two "helper" definitions
        symbol_table = SymbolTable()

        # Same-file helper
        local_helper = SymbolEntry(
            node_id="app.py:helper",
            file_path="app.py",
            name="helper",
            type="FUNCTION",
            line_start=10,
            line_end=20,
        )
        symbol_table.add(local_helper)

        # Imported helper
        imported_helper = SymbolEntry(
            node_id="utils.py:helper",
            file_path="utils.py",
            name="helper",
            type="FUNCTION",
            line_start=5,
            line_end=15,
        )
        symbol_table.add(imported_helper)

        # Setup import graph (app.py imports utils.py)
        import_graph = nx.DiGraph()
        import_graph.add_edge("app.py", "utils.py", type="IMPORTS", imported_names=["helper"])

        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve call - should return same-file definition
        target = resolver._resolve_call("helper", "app.py", "app.py:main")

        assert target == "app.py:helper"  # Same file wins
        assert resolver.unresolved == []


class TestCallResolutionImports:
    """Test call resolution via imports."""

    def test_resolve_imported_call(self):
        """Test resolving a call to a directly imported function."""
        # Setup symbol table
        symbol_table = SymbolTable()
        helper_entry = SymbolEntry(
            node_id="utils.py:helper",
            file_path="utils.py",
            name="helper",
            type="FUNCTION",
            line_start=5,
            line_end=15,
        )
        symbol_table.add(helper_entry)

        # Setup import graph (main.py imports helper from utils.py)
        import_graph = nx.DiGraph()
        import_graph.add_edge("main.py", "utils.py", type="IMPORTS", imported_names=["helper"])

        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve call to helper from main.py
        target = resolver._resolve_call("helper", "main.py", "main.py:main")

        assert target == "utils.py:helper"
        assert resolver.unresolved == []

    def test_resolve_wildcard_import(self):
        """Test resolving a call via wildcard import (from x import *)."""
        # Setup symbol table
        symbol_table = SymbolTable()
        process_entry = SymbolEntry(
            node_id="data.py:process",
            file_path="data.py",
            name="process",
            type="FUNCTION",
            line_start=10,
            line_end=30,
        )
        symbol_table.add(process_entry)

        # Setup import graph (main.py imports * from data.py)
        import_graph = nx.DiGraph()
        import_graph.add_edge("main.py", "data.py", type="IMPORTS", imported_names=["*"])

        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve call to process
        target = resolver._resolve_call("process", "main.py", "main.py:main")

        assert target == "data.py:process"
        assert resolver.unresolved == []

    def test_find_imported_symbols_single_match(self):
        """Test finding a symbol in imported files."""
        # Setup symbol table
        symbol_table = SymbolTable()
        helper_entry = SymbolEntry(
            node_id="utils.py:helper",
            file_path="utils.py",
            name="helper",
            type="FUNCTION",
            line_start=5,
            line_end=15,
        )
        symbol_table.add(helper_entry)

        # Setup import graph
        import_graph = nx.DiGraph()
        import_graph.add_edge("main.py", "utils.py", type="IMPORTS", imported_names=["helper"])

        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Find helper in imports
        results = resolver._find_imported_symbols("helper", "main.py")

        assert len(results) == 1
        assert results[0].file_path == "utils.py"
        assert results[0].name == "helper"

    def test_find_imported_symbols_no_imports(self):
        """Test finding symbols when file has no imports."""
        symbol_table = SymbolTable()
        import_graph = nx.DiGraph()
        resolver = CrossFileCallResolver(import_graph, symbol_table)

        results = resolver._find_imported_symbols("helper", "main.py")

        assert results == []


class TestCallResolutionAmbiguous:
    """Test handling of ambiguous and unresolved calls."""

    def test_resolve_ambiguous_import(self):
        """Test that ambiguous imports are skipped with warning."""
        # Setup symbol table with two different "format" functions
        symbol_table = SymbolTable()

        format1 = SymbolEntry(
            node_id="string.py:format",
            file_path="string.py",
            name="format",
            type="FUNCTION",
            line_start=10,
            line_end=20,
        )
        symbol_table.add(format1)

        format2 = SymbolEntry(
            node_id="number.py:format",
            file_path="number.py",
            name="format",
            type="FUNCTION",
            line_start=5,
            line_end=15,
        )
        symbol_table.add(format2)

        # Setup import graph (app.py imports from both)
        import_graph = nx.DiGraph()
        import_graph.add_edge("app.py", "string.py", type="IMPORTS", imported_names=["format"])
        import_graph.add_edge("app.py", "number.py", type="IMPORTS", imported_names=["format"])

        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve call - should return None and log warning
        target = resolver._resolve_call("format", "app.py", "app.py:main")

        assert target is None
        assert len(resolver.unresolved) == 1
        assert "Ambiguous" in resolver.unresolved[0]
        assert "format" in resolver.unresolved[0]
        assert "2" in resolver.unresolved[0]  # Found in 2 files

    def test_resolve_not_found(self):
        """Test that calls to undefined functions return None."""
        symbol_table = SymbolTable()
        import_graph = nx.DiGraph()
        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve call to nonexistent function
        target = resolver._resolve_call("nonexistent", "app.py", "app.py:main")

        assert target is None
        # No warning for not found (could be stdlib/external)
        assert resolver.unresolved == []

    def test_find_imported_symbols_multiple_matches(self):
        """Test finding multiple definitions of same symbol in imports."""
        # Setup symbol table with two "helper" definitions
        symbol_table = SymbolTable()

        helper1 = SymbolEntry(
            node_id="utils1.py:helper",
            file_path="utils1.py",
            name="helper",
            type="FUNCTION",
            line_start=5,
            line_end=10,
        )
        symbol_table.add(helper1)

        helper2 = SymbolEntry(
            node_id="utils2.py:helper",
            file_path="utils2.py",
            name="helper",
            type="FUNCTION",
            line_start=20,
            line_end=30,
        )
        symbol_table.add(helper2)

        # Setup import graph (main.py imports from both)
        import_graph = nx.DiGraph()
        import_graph.add_edge("main.py", "utils1.py", type="IMPORTS", imported_names=["helper"])
        import_graph.add_edge("main.py", "utils2.py", type="IMPORTS", imported_names=["helper"])

        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Find helper - should return both matches
        results = resolver._find_imported_symbols("helper", "main.py")

        assert len(results) == 2
        file_paths = {e.file_path for e in results}
        assert file_paths == {"utils1.py", "utils2.py"}


class TestGetCallNodes:
    """Test extracting call nodes from graph."""

    def test_get_call_nodes_from_function(self):
        """Test extracting outgoing CALLS from a function node."""
        graph = nx.DiGraph()

        # Add function node
        graph.add_node("app.py:main", type="FUNCTION", name="main")

        # Add call nodes
        graph.add_node("app.py:helper", type="FUNCTION", name="helper")
        graph.add_node("app.py:validate", type="FUNCTION", name="validate")

        # Add CALLS edges
        graph.add_edge("app.py:main", "app.py:helper", type="CALLS")
        graph.add_edge("app.py:main", "app.py:validate", type="CALLS")

        resolver = CrossFileCallResolver(nx.DiGraph(), SymbolTable())

        # Extract calls
        calls = resolver._get_call_nodes(graph, "app.py:main")

        assert len(calls) == 2
        assert set(calls) == {"helper", "validate"}

    def test_get_call_nodes_no_calls(self):
        """Test extracting calls from node with no outgoing calls."""
        graph = nx.DiGraph()
        graph.add_node("app.py:helper", type="FUNCTION", name="helper")

        resolver = CrossFileCallResolver(nx.DiGraph(), SymbolTable())

        calls = resolver._get_call_nodes(graph, "app.py:helper")

        assert calls == []


class TestGraphIntegration:
    """Test resolve() method for graph integration."""

    def test_resolve_combines_file_graphs(self):
        """Test that resolve() combines all file graphs into one."""
        # Setup symbol table
        symbol_table = SymbolTable()

        # Create two file graphs
        graph1 = nx.DiGraph()
        graph1.add_node("main.py:main", type="FUNCTION", name="main")

        graph2 = nx.DiGraph()
        graph2.add_node("utils.py:helper", type="FUNCTION", name="helper")

        file_graphs = {"main.py": graph1, "utils.py": graph2}

        # Setup resolver
        import_graph = nx.DiGraph()
        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve
        combined = resolver.resolve(file_graphs)

        # Check that both nodes are in combined graph
        assert "main.py:main" in combined
        assert "utils.py:helper" in combined

    def test_resolve_adds_cross_file_edge(self):
        """Test that resolve() adds cross-file CALLS edges."""
        # Setup symbol table with helper in utils.py
        symbol_table = SymbolTable()
        helper_entry = SymbolEntry(
            node_id="utils.py:helper",
            file_path="utils.py",
            name="helper",
            type="FUNCTION",
            line_start=5,
            line_end=15,
        )
        symbol_table.add(helper_entry)

        # Setup import graph (main.py imports helper from utils.py)
        import_graph = nx.DiGraph()
        import_graph.add_edge("main.py", "utils.py", type="IMPORTS", imported_names=["helper"])

        # Create file graphs
        # main.py has main() that calls helper()
        graph1 = nx.DiGraph()
        graph1.add_node("main.py:main", type="FUNCTION", name="main")
        graph1.add_node("main.py:helper_ref", type="FUNCTION", name="helper")
        graph1.add_edge("main.py:main", "main.py:helper_ref", type="CALLS")

        # utils.py has helper()
        graph2 = nx.DiGraph()
        graph2.add_node("utils.py:helper", type="FUNCTION", name="helper")

        file_graphs = {"main.py": graph1, "utils.py": graph2}

        # Setup resolver
        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve
        combined = resolver.resolve(file_graphs)

        # Check that cross-file edge was added
        assert combined.has_edge("main.py:main", "utils.py:helper")

        # Check edge attributes
        edge_data = combined["main.py:main"]["utils.py:helper"]
        assert edge_data["type"] == "CALLS"
        assert edge_data["cross_file"] is True

    def test_resolve_preserves_same_file_edges(self):
        """Test that resolve() preserves same-file CALLS edges."""
        # Setup symbol table
        symbol_table = SymbolTable()
        main_entry = SymbolEntry(
            node_id="app.py:main",
            file_path="app.py",
            name="main",
            type="FUNCTION",
            line_start=10,
            line_end=20,
        )
        helper_entry = SymbolEntry(
            node_id="app.py:helper",
            file_path="app.py",
            name="helper",
            type="FUNCTION",
            line_start=25,
            line_end=35,
        )
        symbol_table.add(main_entry)
        symbol_table.add(helper_entry)

        # Create file graph with same-file call
        graph = nx.DiGraph()
        graph.add_node("app.py:main", type="FUNCTION", name="main")
        graph.add_node("app.py:helper", type="FUNCTION", name="helper")
        graph.add_edge("app.py:main", "app.py:helper", type="CALLS")

        file_graphs = {"app.py": graph}

        # Setup resolver
        import_graph = nx.DiGraph()
        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve
        combined = resolver.resolve(file_graphs)

        # Check that same-file edge is preserved
        assert combined.has_edge("app.py:main", "app.py:helper")

        # Check edge attributes (same-file should have cross_file=False)
        edge_data = combined["app.py:main"]["app.py:helper"]
        assert edge_data["type"] == "CALLS"
        assert edge_data.get("cross_file", False) is False

    def test_resolve_skips_ambiguous_calls(self):
        """Test that resolve() skips ambiguous calls without adding edges."""
        # Setup symbol table with two "format" functions
        symbol_table = SymbolTable()

        format1 = SymbolEntry(
            node_id="string.py:format",
            file_path="string.py",
            name="format",
            type="FUNCTION",
            line_start=10,
            line_end=20,
        )
        symbol_table.add(format1)

        format2 = SymbolEntry(
            node_id="number.py:format",
            file_path="number.py",
            name="format",
            type="FUNCTION",
            line_start=5,
            line_end=15,
        )
        symbol_table.add(format2)

        # Setup import graph (app.py imports from both)
        import_graph = nx.DiGraph()
        import_graph.add_edge("app.py", "string.py", type="IMPORTS", imported_names=["format"])
        import_graph.add_edge("app.py", "number.py", type="IMPORTS", imported_names=["format"])

        # Create file graphs
        # app.py has main() that calls format()
        graph1 = nx.DiGraph()
        graph1.add_node("app.py:main", type="FUNCTION", name="main")
        graph1.add_node("app.py:format_ref", type="FUNCTION", name="format")
        graph1.add_edge("app.py:main", "app.py:format_ref", type="CALLS")

        graph2 = nx.DiGraph()
        graph2.add_node("string.py:format", type="FUNCTION", name="format")

        graph3 = nx.DiGraph()
        graph3.add_node("number.py:format", type="FUNCTION", name="format")

        file_graphs = {"app.py": graph1, "string.py": graph2, "number.py": graph3}

        # Setup resolver
        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve
        combined = resolver.resolve(file_graphs)

        # Check that no cross-file edge was added (ambiguous)
        assert not combined.has_edge("app.py:main", "string.py:format")
        assert not combined.has_edge("app.py:main", "number.py:format")

        # Check that unresolved warning was logged
        assert len(resolver.unresolved) > 0
        assert "Ambiguous" in resolver.unresolved[0]

    def test_resolve_avoids_self_loops(self):
        """Test that resolve() avoids creating self-loops."""
        # Setup symbol table
        symbol_table = SymbolTable()
        main_entry = SymbolEntry(
            node_id="app.py:main",
            file_path="app.py",
            name="main",
            type="FUNCTION",
            line_start=10,
            line_end=20,
        )
        symbol_table.add(main_entry)

        # Create file graph where main() calls itself
        graph = nx.DiGraph()
        graph.add_node("app.py:main", type="FUNCTION", name="main")
        graph.add_node("app.py:main_ref", type="FUNCTION", name="main")
        graph.add_edge("app.py:main", "app.py:main_ref", type="CALLS")

        file_graphs = {"app.py": graph}

        # Setup resolver
        import_graph = nx.DiGraph()
        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve
        combined = resolver.resolve(file_graphs)

        # Check that no self-loop was created
        # (the original edge to main_ref should exist, but no edge from main to main)
        assert not combined.has_edge("app.py:main", "app.py:main")

    def test_resolve_handles_multiple_files(self):
        """Test resolve() with multiple files and cross-file calls."""
        # Setup symbol table
        symbol_table = SymbolTable()

        # Functions in utils.py
        helper = SymbolEntry(
            node_id="utils.py:helper",
            file_path="utils.py",
            name="helper",
            type="FUNCTION",
            line_start=5,
            line_end=15,
        )
        symbol_table.add(helper)

        # Functions in data.py
        process = SymbolEntry(
            node_id="data.py:process",
            file_path="data.py",
            name="process",
            type="FUNCTION",
            line_start=10,
            line_end=30,
        )
        symbol_table.add(process)

        # Setup import graph
        import_graph = nx.DiGraph()
        import_graph.add_edge("main.py", "utils.py", type="IMPORTS", imported_names=["helper"])
        import_graph.add_edge("main.py", "data.py", type="IMPORTS", imported_names=["process"])

        # Create file graphs
        # main.py calls both helper and process
        graph1 = nx.DiGraph()
        graph1.add_node("main.py:main", type="FUNCTION", name="main")
        graph1.add_node("main.py:helper_ref", type="FUNCTION", name="helper")
        graph1.add_node("main.py:process_ref", type="FUNCTION", name="process")
        graph1.add_edge("main.py:main", "main.py:helper_ref", type="CALLS")
        graph1.add_edge("main.py:main", "main.py:process_ref", type="CALLS")

        graph2 = nx.DiGraph()
        graph2.add_node("utils.py:helper", type="FUNCTION", name="helper")

        graph3 = nx.DiGraph()
        graph3.add_node("data.py:process", type="FUNCTION", name="process")

        file_graphs = {"main.py": graph1, "utils.py": graph2, "data.py": graph3}

        # Setup resolver
        resolver = CrossFileCallResolver(import_graph, symbol_table)

        # Resolve
        combined = resolver.resolve(file_graphs)

        # Check that both cross-file edges were added
        assert combined.has_edge("main.py:main", "utils.py:helper")
        assert combined.has_edge("main.py:main", "data.py:process")

        # Check edge attributes
        assert combined["main.py:main"]["utils.py:helper"]["cross_file"] is True
        assert combined["main.py:main"]["data.py:process"]["cross_file"] is True
