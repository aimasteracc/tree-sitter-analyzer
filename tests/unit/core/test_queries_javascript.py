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
    JAVASCRIPT_QUERIES,
    JAVASCRIPT_QUERY_DESCRIPTIONS,
    OBJECTS,
    VARIABLES,
    get_all_queries,
    get_available_javascript_queries,
    get_javascript_query,
    get_javascript_query_description,
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


class TestJavaScriptQueryFunctions:
    """Cover get_javascript_query, get_javascript_query_description, and related functions."""

    def test_get_javascript_query_returns_string(self) -> None:
        result = get_javascript_query("function")
        assert isinstance(result, str)
        assert "function_declaration" in result

    def test_get_javascript_query_all_keys(self) -> None:
        for key in JAVASCRIPT_QUERIES:
            result = get_javascript_query(key)
            assert isinstance(result, str)
            assert len(result.strip()) > 0

    def test_get_javascript_query_invalid_raises(self) -> None:
        with pytest.raises(
            ValueError, match="JavaScript query 'no_such_query' does not exist"
        ):
            get_javascript_query("no_such_query")

    def test_get_javascript_query_description_known(self) -> None:
        desc = get_javascript_query_description("function")
        assert isinstance(desc, str)
        assert "function" in desc.lower()

    def test_get_javascript_query_description_unknown(self) -> None:
        assert get_javascript_query_description("zzz_missing") == "No description"

    def test_get_javascript_query_description_all_keys(self) -> None:
        for key in JAVASCRIPT_QUERIES:
            desc = get_javascript_query_description(key)
            assert isinstance(desc, str)
            assert len(desc) > 0

    def test_get_query_through_all_queries(self) -> None:
        for key in ALL_QUERIES:
            result = get_query(key)
            assert isinstance(result, str)

    def test_get_all_queries_returns_dict(self) -> None:
        queries = get_all_queries()
        assert isinstance(queries, dict)
        assert len(queries) >= len(JAVASCRIPT_QUERIES)

    def test_list_queries_returns_list(self) -> None:
        names = list_queries()
        assert isinstance(names, list)
        assert "functions" in names

    def test_get_available_javascript_queries(self) -> None:
        names = get_available_javascript_queries()
        assert isinstance(names, list)
        assert "function" in names
        assert "class" in names
        assert set(names) == set(JAVASCRIPT_QUERIES.keys())

    def test_all_queries_built_from_javascript_queries(self) -> None:
        for key in JAVASCRIPT_QUERIES:
            assert key in ALL_QUERIES
            assert ALL_QUERIES[key]["query"] == JAVASCRIPT_QUERIES[key]
            assert ALL_QUERIES[key]["description"] == JAVASCRIPT_QUERY_DESCRIPTIONS.get(
                key, "No description"
            )
