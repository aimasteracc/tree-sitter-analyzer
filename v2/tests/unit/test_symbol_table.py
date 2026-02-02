"""
Tests for symbol table construction and lookup.

This module tests the SymbolTable and SymbolTableBuilder classes,
ensuring correct symbol extraction and lookup across files.
"""

import networkx as nx

from tree_sitter_analyzer_v2.graph.symbols import (
    SymbolEntry,
    SymbolTable,
    SymbolTableBuilder,
)


class TestSymbolTableBasics:
    """Test basic SymbolTable operations (add, lookup)."""

    def test_add_single_entry(self):
        """Test adding a single symbol entry to the table."""
        table = SymbolTable()
        entry = SymbolEntry(
            node_id="app.py:main",
            file_path="app.py",
            name="main",
            type="FUNCTION",
            line_start=10,
            line_end=25,
        )

        table.add(entry)
        results = table.lookup("main")

        assert len(results) == 1
        assert results[0].name == "main"
        assert results[0].file_path == "app.py"
        assert results[0].type == "FUNCTION"

    def test_add_multiple_entries_same_name(self):
        """Test adding multiple symbols with the same name (duplicates across files)."""
        table = SymbolTable()

        entry1 = SymbolEntry(
            node_id="app.py:helper",
            file_path="app.py",
            name="helper",
            type="FUNCTION",
            line_start=5,
            line_end=10,
        )

        entry2 = SymbolEntry(
            node_id="utils.py:helper",
            file_path="utils.py",
            name="helper",
            type="FUNCTION",
            line_start=20,
            line_end=30,
        )

        table.add(entry1)
        table.add(entry2)

        results = table.lookup("helper")
        assert len(results) == 2

        file_paths = {e.file_path for e in results}
        assert file_paths == {"app.py", "utils.py"}

    def test_lookup_nonexistent_symbol(self):
        """Test looking up a symbol that doesn't exist."""
        table = SymbolTable()
        results = table.lookup("nonexistent")
        assert results == []

    def test_lookup_with_context_file(self):
        """Test lookup with context file prioritizes same-file definitions."""
        table = SymbolTable()

        entry1 = SymbolEntry(
            node_id="string.py:format",
            file_path="string.py",
            name="format",
            type="FUNCTION",
            line_start=10,
            line_end=20,
        )

        entry2 = SymbolEntry(
            node_id="number.py:format",
            file_path="number.py",
            name="format",
            type="FUNCTION",
            line_start=5,
            line_end=15,
        )

        table.add(entry1)
        table.add(entry2)

        # Lookup without context returns all
        results = table.lookup("format")
        assert len(results) == 2

        # Lookup with context prioritizes same file
        results = table.lookup("format", context_file="string.py")
        assert len(results) == 1
        assert results[0].file_path == "string.py"

    def test_lookup_in_file(self):
        """Test looking up a symbol in a specific file."""
        table = SymbolTable()

        entry1 = SymbolEntry(
            node_id="app.py:helper",
            file_path="app.py",
            name="helper",
            type="FUNCTION",
            line_start=5,
            line_end=10,
        )

        entry2 = SymbolEntry(
            node_id="utils.py:helper",
            file_path="utils.py",
            name="helper",
            type="FUNCTION",
            line_start=20,
            line_end=30,
        )

        table.add(entry1)
        table.add(entry2)

        # Find in specific file
        result = table.lookup_in_file("helper", "utils.py")
        assert result is not None
        assert result.file_path == "utils.py"
        assert result.line_start == 20

        # Not found in different file
        result = table.lookup_in_file("nonexistent", "utils.py")
        assert result is None


class TestSymbolTableBuilder:
    """Test SymbolTableBuilder functionality."""

    def test_build_symbol_table_from_single_file(self):
        """Test building symbol table from a single file graph."""
        # Create a simple file graph with one function
        graph = nx.DiGraph()
        graph.add_node(
            "app.py:main",
            type="FUNCTION",
            name="main",
            line_start=10,
            line_end=25,
        )

        file_graphs = {"app.py": graph}
        builder = SymbolTableBuilder()
        table = builder.build(file_graphs)

        # Verify the symbol was extracted
        entry = table.lookup_in_file("main", "app.py")
        assert entry is not None
        assert entry.name == "main"
        assert entry.type == "FUNCTION"
        assert entry.line_start == 10
        assert entry.line_end == 25

    def test_build_symbol_table_from_multiple_files(self):
        """Test building symbol table from multiple file graphs."""
        # Create two file graphs
        graph1 = nx.DiGraph()
        graph1.add_node(
            "app.py:main",
            type="FUNCTION",
            name="main",
            line_start=10,
            line_end=25,
        )

        graph2 = nx.DiGraph()
        graph2.add_node(
            "utils.py:helper",
            type="FUNCTION",
            name="helper",
            line_start=5,
            line_end=15,
        )

        file_graphs = {"app.py": graph1, "utils.py": graph2}
        builder = SymbolTableBuilder()
        table = builder.build(file_graphs)

        # Verify both symbols were extracted
        main_entry = table.lookup_in_file("main", "app.py")
        assert main_entry is not None
        assert main_entry.name == "main"

        helper_entry = table.lookup_in_file("helper", "utils.py")
        assert helper_entry is not None
        assert helper_entry.name == "helper"

    def test_build_extracts_only_functions_classes_methods(self):
        """Test that builder only extracts FUNCTION, CLASS, and METHOD nodes."""
        graph = nx.DiGraph()

        # Add various node types
        graph.add_node("app.py:main", type="FUNCTION", name="main", line_start=10, line_end=20)
        graph.add_node("app.py:MyClass", type="CLASS", name="MyClass", line_start=25, line_end=50)
        graph.add_node(
            "app.py:MyClass.method", type="METHOD", name="method", line_start=30, line_end=40
        )
        graph.add_node("app.py:var", type="VARIABLE", name="var", line_start=5, line_end=5)
        graph.add_node("app.py:if_stmt", type="IF", name="if", line_start=15, line_end=18)

        file_graphs = {"app.py": graph}
        builder = SymbolTableBuilder()
        table = builder.build(file_graphs)

        # Verify only FUNCTION, CLASS, METHOD were extracted
        main_entry = table.lookup_in_file("main", "app.py")
        assert main_entry is not None
        assert main_entry.type == "FUNCTION"

        class_entry = table.lookup_in_file("MyClass", "app.py")
        assert class_entry is not None
        assert class_entry.type == "CLASS"

        method_entry = table.lookup_in_file("method", "app.py")
        assert method_entry is not None
        assert method_entry.type == "METHOD"

        # VARIABLE and IF should not be in table
        var_entry = table.lookup_in_file("var", "app.py")
        assert var_entry is None

    def test_build_handles_duplicate_names_across_files(self):
        """Test that builder correctly handles symbols with same name in different files."""
        # Create two graphs with same function name
        graph1 = nx.DiGraph()
        graph1.add_node(
            "module1.py:process",
            type="FUNCTION",
            name="process",
            line_start=10,
            line_end=20,
        )

        graph2 = nx.DiGraph()
        graph2.add_node(
            "module2.py:process",
            type="FUNCTION",
            name="process",
            line_start=15,
            line_end=25,
        )

        file_graphs = {"module1.py": graph1, "module2.py": graph2}
        builder = SymbolTableBuilder()
        table = builder.build(file_graphs)

        # Verify both definitions are in the table
        results = table.lookup("process")
        assert len(results) == 2

        file_paths = {e.file_path for e in results}
        assert file_paths == {"module1.py", "module2.py"}

        # Verify context-based lookup works
        module1_result = table.lookup("process", context_file="module1.py")
        assert len(module1_result) == 1
        assert module1_result[0].file_path == "module1.py"

    def test_build_handles_missing_line_info(self):
        """Test that builder handles nodes with missing line_start/line_end."""
        graph = nx.DiGraph()

        # Add node without line info
        graph.add_node("app.py:helper", type="FUNCTION", name="helper")

        file_graphs = {"app.py": graph}
        builder = SymbolTableBuilder()
        table = builder.build(file_graphs)

        entry = table.lookup_in_file("helper", "app.py")
        assert entry is not None
        assert entry.line_start == 0  # Default value
        assert entry.line_end == 0  # Default value
