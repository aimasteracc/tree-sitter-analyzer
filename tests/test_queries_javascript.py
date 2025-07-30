#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for JavaScript queries module
"""

import pytest
from tree_sitter_analyzer.queries.javascript import (
    get_query,
    get_all_queries,
    list_queries,
    ALL_QUERIES,
    FUNCTIONS,
    CLASSES,
    VARIABLES,
    IMPORTS,
    EXPORTS,
    OBJECTS,
    COMMENTS,
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
        assert "class_expression" in CLASSES
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
        for query_name, query_data in ALL_QUERIES.items():
            description = query_data["description"]
            assert isinstance(description, str)
            assert len(description) > 0
            assert "検索" in description  # All descriptions should mention "search" in Japanese

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