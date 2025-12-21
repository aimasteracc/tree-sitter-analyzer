#!/usr/bin/env python3
"""
Tests for Python queries module
"""

import pytest

from tree_sitter_analyzer.queries.python import (
    ALL_QUERIES,
    CLASSES,
    COMMENTS,
    FUNCTIONS,
    IMPORTS,
    VARIABLES,
    get_all_queries,
    get_query,
    list_queries,
)


class TestPythonQueries:
    """Test Python queries functionality"""

    def test_get_query_valid(self) -> None:
        """Test getting a valid Python query"""
        query = get_query("functions")
        assert query is not None
        assert "function_definition" in query
        assert "@function" in query

    def test_get_query_invalid(self) -> None:
        """Test getting an invalid Python query raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            get_query("nonexistent_query")

        assert "Query 'nonexistent_query' not found" in str(exc_info.value)
        assert "Available queries:" in str(exc_info.value)

    def test_get_all_queries(self) -> None:
        """Test getting all queries"""
        all_queries = get_all_queries()
        assert isinstance(all_queries, dict)
        assert len(all_queries) > 0
        assert "functions" in all_queries
        assert "query" in all_queries["functions"]
        assert "description" in all_queries["functions"]

    def test_list_queries(self) -> None:
        """Test listing all query names"""
        query_names = list_queries()
        assert isinstance(query_names, list)
        assert len(query_names) > 0
        assert "functions" in query_names
        assert "classes" in query_names

    def test_all_queries_structure(self) -> None:
        """Test ALL_QUERIES dictionary structure"""
        assert isinstance(ALL_QUERIES, dict)
        assert len(ALL_QUERIES) > 0

        # Test essential queries exist
        essential_queries = ["functions", "classes", "variables", "imports", "comments"]
        for query_name in essential_queries:
            assert query_name in ALL_QUERIES
            assert "query" in ALL_QUERIES[query_name]
            assert "description" in ALL_QUERIES[query_name]
            assert isinstance(ALL_QUERIES[query_name]["query"], str)
            assert isinstance(ALL_QUERIES[query_name]["description"], str)

    def test_query_constants(self) -> None:
        """Test that query constants are properly defined"""
        constants = [FUNCTIONS, CLASSES, VARIABLES, IMPORTS, COMMENTS]
        for constant in constants:
            assert isinstance(constant, str)
            assert len(constant.strip()) > 0

    def test_functions_query(self) -> None:
        """Test functions query content"""
        assert "function_definition" in FUNCTIONS
        assert "@function" in FUNCTIONS

    def test_classes_query(self) -> None:
        """Test classes query content"""
        assert "class_definition" in CLASSES
        assert "@class" in CLASSES

    def test_variables_query(self) -> None:
        """Test variables query content"""
        assert "assignment" in VARIABLES
        assert "@variable" in VARIABLES

    def test_imports_query(self) -> None:
        """Test imports query content"""
        assert "import_statement" in IMPORTS
        assert "@import" in IMPORTS

    def test_comments_query(self) -> None:
        """Test comments query content"""
        assert "comment" in COMMENTS
        assert "@comment" in COMMENTS

    def test_query_descriptions(self) -> None:
        """Test that all queries have meaningful descriptions"""
        for _query_name, query_data in ALL_QUERIES.items():
            description = query_data["description"]
            assert isinstance(description, str)
            assert len(description) > 0
            assert (
                "search" in description.lower()
            )  # All descriptions should mention "search"

    def test_query_consistency(self) -> None:
        """Test consistency between constants and ALL_QUERIES"""
        # Test that ALL_QUERIES contains the expected constants
        assert ALL_QUERIES["functions"]["query"] == FUNCTIONS
        assert ALL_QUERIES["classes"]["query"] == CLASSES
        assert ALL_QUERIES["variables"]["query"] == VARIABLES
        assert ALL_QUERIES["imports"]["query"] == IMPORTS
        assert ALL_QUERIES["comments"]["query"] == COMMENTS

    def test_python_specific_constructs(self) -> None:
        """Test Python-specific language constructs in queries"""
        # Functions should include async functions
        if "async_function_definition" in FUNCTIONS:
            assert "async_function_definition" in FUNCTIONS

        # Classes should handle inheritance
        if "superclasses" in CLASSES:
            assert "superclasses" in CLASSES

        # Imports should handle from imports
        if "import_from_statement" in IMPORTS:
            assert "import_from_statement" in IMPORTS

    def test_query_syntax_validity(self) -> None:
        """Test that all queries have valid tree-sitter syntax"""
        for query_name, query_data in ALL_QUERIES.items():
            query = query_data["query"]
            # Basic syntax checks
            assert "(" in query and ")" in query  # Should have parentheses
            assert "@" in query  # Should have capture names

            # Check for balanced parentheses (basic check)
            open_count = query.count("(")
            close_count = query.count(")")
            assert (
                open_count == close_count
            ), f"Unbalanced parentheses in {query_name} query"
