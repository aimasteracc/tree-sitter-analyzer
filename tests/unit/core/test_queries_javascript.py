#!/usr/bin/env python3
"""
Tests for JavaScript queries module
"""

import pytest

from tree_sitter_analyzer.queries.javascript import (
    ALL_QUERIES,
    CLASSES,
    COMMENTS,
    EXPORTS,
    FUNCTIONS,
    IMPORTS,
    OBJECTS,
    VARIABLES,
    get_all_queries,
    get_query,
    list_queries,
)


class TestJavaScriptQueries:
    """Test JavaScript queries functionality"""

    def test_get_query_valid(self) -> None:
        """Test getting a valid JavaScript query"""
        query = get_query("functions")
        assert query is not None
        assert "function_declaration" in query
        assert "@function" in query

    def test_get_query_invalid(self) -> None:
        """Test getting an invalid JavaScript query raises ValueError"""
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
        essential_queries = ["functions", "classes", "variables", "imports", "exports"]
        for query_name in essential_queries:
            assert query_name in ALL_QUERIES
            assert "query" in ALL_QUERIES[query_name]
            assert "description" in ALL_QUERIES[query_name]
            assert isinstance(ALL_QUERIES[query_name]["query"], str)
            assert isinstance(ALL_QUERIES[query_name]["description"], str)

    def test_query_constants(self) -> None:
        """Test that query constants are properly defined"""
        constants = [FUNCTIONS, CLASSES, VARIABLES, IMPORTS, EXPORTS, OBJECTS, COMMENTS]
        for constant in constants:
            assert isinstance(constant, str)
            assert len(constant.strip()) > 0

    def test_functions_query(self) -> None:
        """Test functions query content"""
        assert "function_declaration" in FUNCTIONS
        assert "function_expression" in FUNCTIONS
        assert "arrow_function" in FUNCTIONS
        assert "method_definition" in FUNCTIONS

    def test_classes_query(self) -> None:
        """Test classes query content"""
        assert "class_declaration" in CLASSES
        assert "@class" in CLASSES

    def test_variables_query(self) -> None:
        """Test variables query content"""
        assert "variable_declaration" in VARIABLES
        assert "lexical_declaration" in VARIABLES
        assert "@variable" in VARIABLES

    def test_imports_query(self) -> None:
        """Test imports query content"""
        assert "import_statement" in IMPORTS
        assert "import_clause" in IMPORTS
        assert "@import" in IMPORTS

    def test_exports_query(self) -> None:
        """Test exports query content"""
        assert "export_statement" in EXPORTS
        assert "export_clause" in EXPORTS
        assert "@export" in EXPORTS

    def test_objects_query(self) -> None:
        """Test objects query content"""
        assert "object" in OBJECTS
        assert "property_definition" in OBJECTS
        assert "@property" in OBJECTS

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
        assert ALL_QUERIES["exports"]["query"] == EXPORTS
        assert ALL_QUERIES["objects"]["query"] == OBJECTS
        assert ALL_QUERIES["comments"]["query"] == COMMENTS

    # --- Merged from test_queries_javascript_enhanced.py and _extended.py ---

    def test_javascript_queries_structure(self) -> None:
        """Test JAVASCRIPT_QUERIES dictionary structure"""
        from tree_sitter_analyzer.queries.javascript import JAVASCRIPT_QUERIES

        assert isinstance(JAVASCRIPT_QUERIES, dict)
        assert len(JAVASCRIPT_QUERIES) > 50

        essential_queries = [
            "function",
            "function_declaration",
            "arrow_function",
            "async_function",
            "class",
            "class_declaration",
            "constructor",
            "variable",
            "import",
            "export",
            "jsx_element",
            "react_component",
        ]
        for query_name in essential_queries:
            assert query_name in JAVASCRIPT_QUERIES
            assert isinstance(JAVASCRIPT_QUERIES[query_name], str)
            assert len(JAVASCRIPT_QUERIES[query_name].strip()) > 0

    def test_get_javascript_query_valid(self) -> None:
        """Test getting valid JavaScript queries via dedicated function"""
        from tree_sitter_analyzer.queries.javascript import get_javascript_query

        function_query = get_javascript_query("function")
        assert "function_declaration" in function_query

        async_query = get_javascript_query("async_function")
        assert "async" in async_query

        arrow_query = get_javascript_query("arrow_function")
        assert "arrow_function" in arrow_query

    def test_jsx_queries(self) -> None:
        """Test JSX-related queries"""
        from tree_sitter_analyzer.queries.javascript import JAVASCRIPT_QUERIES

        jsx_query_names = [
            "jsx_element",
            "jsx_self_closing",
            "jsx_attribute",
            "jsx_expression",
        ]
        for query_name in jsx_query_names:
            assert query_name in JAVASCRIPT_QUERIES
            assert "jsx" in JAVASCRIPT_QUERIES[query_name]

    def test_framework_queries(self) -> None:
        """Test framework-specific queries"""
        from tree_sitter_analyzer.queries.javascript import JAVASCRIPT_QUERIES

        framework_query_names = [
            "react_component",
            "react_hook",
            "node_require",
            "module_exports",
        ]
        for query_name in framework_query_names:
            assert query_name in JAVASCRIPT_QUERIES
            assert len(JAVASCRIPT_QUERIES[query_name].strip()) > 0

    def test_query_syntax_validation(self) -> None:
        """Test basic syntax validation for all queries"""
        for query_name, query_data in ALL_QUERIES.items():
            query_string = query_data["query"]
            assert query_string.count("(") == query_string.count(
                ")"
            ), f"Unbalanced parentheses in {query_name} query"
            assert query_string.count("[") == query_string.count(
                "]"
            ), f"Unbalanced brackets in {query_name} query"
            assert query_string.count("{") == query_string.count(
                "}"
            ), f"Unbalanced braces in {query_name} query"
