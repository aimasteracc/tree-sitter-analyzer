"""Tests for queries/kotlin.py module."""

import pytest

from tree_sitter_analyzer.queries.kotlin import (
    ALL_QUERIES,
    KOTLIN_QUERIES,
    KOTLIN_QUERY_DESCRIPTIONS,
    get_all_queries,
    get_available_kotlin_queries,
    get_kotlin_query,
    get_kotlin_query_description,
    get_query,
    list_queries,
)


class TestKotlinQueries:
    """Test Kotlin query definitions."""

    def test_kotlin_queries_not_empty(self):
        """Test that KOTLIN_QUERIES is not empty."""
        assert len(KOTLIN_QUERIES) > 0

    def test_all_queries_not_empty(self):
        """Test that ALL_QUERIES is not empty."""
        assert len(ALL_QUERIES) > 0

    def test_kotlin_query_keys(self):
        """Test that essential queries exist."""
        expected_keys = [
            "package", "class", "object", "interface", "function",
            "lambda", "property", "val", "var", "annotation"
        ]
        for key in expected_keys:
            assert key in KOTLIN_QUERIES, f"Missing query: {key}"

    def test_query_descriptions_exist(self):
        """Test that descriptions exist for queries."""
        for key in KOTLIN_QUERIES:
            assert key in KOTLIN_QUERY_DESCRIPTIONS, f"Missing description for: {key}"

    def test_all_queries_has_common_aliases(self):
        """Test that common aliases exist in ALL_QUERIES."""
        assert "functions" in ALL_QUERIES
        assert "methods" in ALL_QUERIES
        assert "classes" in ALL_QUERIES


class TestGetKotlinQuery:
    """Test get_kotlin_query function."""

    def test_get_existing_query(self):
        """Test getting an existing query."""
        query = get_kotlin_query("class")
        assert query is not None
        assert isinstance(query, str)
        assert "class_declaration" in query

    def test_get_function_query(self):
        """Test getting function query."""
        query = get_kotlin_query("function")
        assert "function_declaration" in query

    def test_get_property_query(self):
        """Test getting property query."""
        query = get_kotlin_query("property")
        assert "property_declaration" in query

    def test_get_nonexistent_query_raises(self):
        """Test that nonexistent query raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_kotlin_query("nonexistent_query")
        
        assert "nonexistent_query" in str(exc_info.value)
        assert "Available:" in str(exc_info.value)

    def test_get_data_class_query(self):
        """Test getting data class query."""
        query = get_kotlin_query("data_class")
        assert "data" in query

    def test_get_suspend_function_query(self):
        """Test getting suspend function query."""
        query = get_kotlin_query("suspend_function")
        assert "suspend" in query


class TestGetKotlinQueryDescription:
    """Test get_kotlin_query_description function."""

    def test_get_existing_description(self):
        """Test getting description for existing query."""
        desc = get_kotlin_query_description("class")
        assert desc is not None
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_get_function_description(self):
        """Test getting function query description."""
        desc = get_kotlin_query_description("function")
        assert "function" in desc.lower()

    def test_get_nonexistent_description_returns_default(self):
        """Test that nonexistent description returns default."""
        desc = get_kotlin_query_description("nonexistent")
        assert desc == "No description"


class TestGetQuery:
    """Test get_query function."""

    def test_get_query_from_all_queries(self):
        """Test getting query from ALL_QUERIES."""
        query = get_query("class")
        assert query is not None
        assert isinstance(query, str)

    def test_get_alias_query(self):
        """Test getting aliased query."""
        functions_query = get_query("functions")
        function_query = get_query("function")
        assert functions_query == function_query

    def test_get_classes_alias(self):
        """Test getting classes alias."""
        classes_query = get_query("classes")
        class_query = get_query("class")
        assert classes_query == class_query

    def test_get_nonexistent_raises(self):
        """Test that nonexistent query raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_query("nonexistent")
        
        assert "not found" in str(exc_info.value)


class TestGetAllQueries:
    """Test get_all_queries function."""

    def test_returns_dict(self):
        """Test that get_all_queries returns a dict."""
        result = get_all_queries()
        assert isinstance(result, dict)

    def test_returns_all_queries(self):
        """Test that all queries are returned."""
        result = get_all_queries()
        assert result is ALL_QUERIES

    def test_queries_have_correct_structure(self):
        """Test that each query has correct structure."""
        result = get_all_queries()
        for name, data in result.items():
            assert "query" in data, f"Missing 'query' in {name}"
            assert "description" in data, f"Missing 'description' in {name}"


class TestListQueries:
    """Test list_queries function."""

    def test_returns_list(self):
        """Test that list_queries returns a list."""
        result = list_queries()
        assert isinstance(result, list)

    def test_contains_expected_queries(self):
        """Test that list contains expected queries."""
        result = list_queries()
        assert "class" in result
        assert "function" in result
        assert "property" in result

    def test_contains_aliases(self):
        """Test that list contains aliases."""
        result = list_queries()
        assert "functions" in result
        assert "methods" in result
        assert "classes" in result


class TestGetAvailableKotlinQueries:
    """Test get_available_kotlin_queries function."""

    def test_returns_list(self):
        """Test that function returns a list."""
        result = get_available_kotlin_queries()
        assert isinstance(result, list)

    def test_returns_kotlin_query_keys(self):
        """Test that function returns KOTLIN_QUERIES keys."""
        result = get_available_kotlin_queries()
        assert set(result) == set(KOTLIN_QUERIES.keys())

    def test_does_not_include_aliases(self):
        """Test that aliases are not included."""
        result = get_available_kotlin_queries()
        # Aliases like "functions", "methods", "classes" should not be in this list
        assert "functions" not in result
        assert "methods" not in result
        assert "classes" not in result


class TestQueryContent:
    """Test actual query content validity."""

    def test_class_query_syntax(self):
        """Test that class query has valid tree-sitter syntax."""
        query = get_kotlin_query("class")
        # Should be a valid tree-sitter query pattern
        assert "(" in query
        assert ")" in query
        assert "@class" in query

    def test_function_query_syntax(self):
        """Test that function query has valid tree-sitter syntax."""
        query = get_kotlin_query("function")
        assert "(" in query
        assert ")" in query
        assert "@function" in query

    def test_package_query_syntax(self):
        """Test that package query has valid tree-sitter syntax."""
        query = get_kotlin_query("package")
        assert "package_header" in query
        assert "@package" in query

    def test_annotation_query_syntax(self):
        """Test that annotation query has valid tree-sitter syntax."""
        query = get_kotlin_query("annotation")
        assert "annotation" in query
        assert "@annotation" in query
