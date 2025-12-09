"""Tests for Go query definitions."""

import pytest

from tree_sitter_analyzer.queries.go import (
    ALL_QUERIES,
    GO_QUERIES,
    GO_QUERY_DESCRIPTIONS,
    get_all_queries,
    get_available_go_queries,
    get_go_query,
    get_go_query_description,
    get_query,
    list_queries,
)


class TestGoQueriesDict:
    """Tests for GO_QUERIES dictionary."""

    def test_go_queries_is_dict(self):
        """GO_QUERIES should be a dictionary."""
        assert isinstance(GO_QUERIES, dict)

    def test_go_queries_not_empty(self):
        """GO_QUERIES should not be empty."""
        assert len(GO_QUERIES) > 0

    def test_all_queries_are_strings(self):
        """All query values should be strings."""
        for name, query in GO_QUERIES.items():
            assert isinstance(query, str), f"Query '{name}' is not a string"

    def test_all_queries_not_empty(self):
        """All query values should not be empty."""
        for name, query in GO_QUERIES.items():
            assert query.strip(), f"Query '{name}' is empty"


class TestGoQueriesContent:
    """Tests for Go query content."""

    def test_package_query_exists(self):
        """Package query should exist."""
        assert "package" in GO_QUERIES
        assert "package_clause" in GO_QUERIES["package"]

    def test_import_query_exists(self):
        """Import query should exist."""
        assert "import" in GO_QUERIES
        assert "import_declaration" in GO_QUERIES["import"]

    def test_function_query_exists(self):
        """Function query should exist."""
        assert "function" in GO_QUERIES
        assert "function_declaration" in GO_QUERIES["function"]

    def test_method_query_exists(self):
        """Method query should exist."""
        assert "method" in GO_QUERIES
        assert "method_declaration" in GO_QUERIES["method"]

    def test_struct_query_exists(self):
        """Struct query should exist."""
        assert "struct" in GO_QUERIES
        assert "struct_type" in GO_QUERIES["struct"]

    def test_interface_query_exists(self):
        """Interface query should exist."""
        assert "interface" in GO_QUERIES
        assert "interface_type" in GO_QUERIES["interface"]

    def test_const_query_exists(self):
        """Const query should exist."""
        assert "const" in GO_QUERIES
        assert "const_declaration" in GO_QUERIES["const"]

    def test_var_query_exists(self):
        """Var query should exist."""
        assert "var" in GO_QUERIES
        assert "var_declaration" in GO_QUERIES["var"]

    def test_goroutine_query_exists(self):
        """Goroutine query should exist."""
        assert "goroutine" in GO_QUERIES
        assert "go_statement" in GO_QUERIES["goroutine"]

    def test_defer_query_exists(self):
        """Defer query should exist."""
        assert "defer" in GO_QUERIES
        assert "defer_statement" in GO_QUERIES["defer"]

    def test_select_query_exists(self):
        """Select query should exist."""
        assert "select" in GO_QUERIES
        assert "select_statement" in GO_QUERIES["select"]

    def test_comment_query_exists(self):
        """Comment query should exist."""
        assert "comment" in GO_QUERIES
        assert "comment" in GO_QUERIES["comment"]


class TestGoQueryDescriptions:
    """Tests for GO_QUERY_DESCRIPTIONS dictionary."""

    def test_descriptions_is_dict(self):
        """GO_QUERY_DESCRIPTIONS should be a dictionary."""
        assert isinstance(GO_QUERY_DESCRIPTIONS, dict)

    def test_descriptions_not_empty(self):
        """GO_QUERY_DESCRIPTIONS should not be empty."""
        assert len(GO_QUERY_DESCRIPTIONS) > 0

    def test_all_descriptions_are_strings(self):
        """All description values should be strings."""
        for name, desc in GO_QUERY_DESCRIPTIONS.items():
            assert isinstance(desc, str), f"Description for '{name}' is not a string"

    def test_all_queries_have_descriptions(self):
        """All queries should have descriptions."""
        for query_name in GO_QUERIES.keys():
            assert (
                query_name in GO_QUERY_DESCRIPTIONS
            ), f"Query '{query_name}' has no description"


class TestGetGoQuery:
    """Tests for get_go_query function."""

    def test_get_valid_query(self):
        """get_go_query should return query for valid name."""
        result = get_go_query("function")
        assert isinstance(result, str)
        assert "function_declaration" in result

    def test_get_all_queries(self):
        """get_go_query should work for all defined queries."""
        for name in GO_QUERIES.keys():
            result = get_go_query(name)
            assert isinstance(result, str)
            assert result == GO_QUERIES[name]

    def test_invalid_query_raises_error(self):
        """get_go_query should raise ValueError for invalid name."""
        with pytest.raises(ValueError) as excinfo:
            get_go_query("nonexistent_query")
        assert "nonexistent_query" in str(excinfo.value)
        assert "Available" in str(excinfo.value)


class TestGetGoQueryDescription:
    """Tests for get_go_query_description function."""

    def test_get_valid_description(self):
        """get_go_query_description should return description for valid name."""
        result = get_go_query_description("function")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_all_descriptions(self):
        """get_go_query_description should work for all defined queries."""
        for name in GO_QUERIES.keys():
            result = get_go_query_description(name)
            assert isinstance(result, str)

    def test_invalid_query_returns_default(self):
        """get_go_query_description should return default for invalid name."""
        result = get_go_query_description("nonexistent_query")
        assert result == "No description"


class TestAllQueries:
    """Tests for ALL_QUERIES dictionary."""

    def test_all_queries_is_dict(self):
        """ALL_QUERIES should be a dictionary."""
        assert isinstance(ALL_QUERIES, dict)

    def test_all_queries_not_empty(self):
        """ALL_QUERIES should not be empty."""
        assert len(ALL_QUERIES) > 0

    def test_all_queries_structure(self):
        """ALL_QUERIES should have correct structure."""
        for name, data in ALL_QUERIES.items():
            assert isinstance(data, dict), f"Query '{name}' data is not a dict"
            assert "query" in data, f"Query '{name}' has no 'query' key"
            assert "description" in data, f"Query '{name}' has no 'description' key"

    def test_contains_all_go_queries(self):
        """ALL_QUERIES should contain all GO_QUERIES."""
        for name in GO_QUERIES.keys():
            assert name in ALL_QUERIES, f"Query '{name}' not in ALL_QUERIES"

    def test_contains_aliases(self):
        """ALL_QUERIES should contain common aliases."""
        assert "functions" in ALL_QUERIES
        assert "methods" in ALL_QUERIES
        assert "classes" in ALL_QUERIES
        assert "structs" in ALL_QUERIES
        assert "interfaces" in ALL_QUERIES


class TestGetQuery:
    """Tests for get_query function."""

    def test_get_valid_query(self):
        """get_query should return query for valid name."""
        result = get_query("function")
        assert isinstance(result, str)
        assert "function_declaration" in result

    def test_get_alias_query(self):
        """get_query should work for aliases."""
        result = get_query("functions")
        assert isinstance(result, str)
        assert "function_declaration" in result

    def test_invalid_query_raises_error(self):
        """get_query should raise ValueError for invalid name."""
        with pytest.raises(ValueError) as excinfo:
            get_query("nonexistent_query")
        assert "nonexistent_query" in str(excinfo.value)


class TestGetAllQueries:
    """Tests for get_all_queries function."""

    def test_returns_dict(self):
        """get_all_queries should return a dictionary."""
        result = get_all_queries()
        assert isinstance(result, dict)

    def test_returns_all_queries(self):
        """get_all_queries should return ALL_QUERIES."""
        result = get_all_queries()
        assert result == ALL_QUERIES


class TestListQueries:
    """Tests for list_queries function."""

    def test_returns_list(self):
        """list_queries should return a list."""
        result = list_queries()
        assert isinstance(result, list)

    def test_not_empty(self):
        """list_queries should not be empty."""
        result = list_queries()
        assert len(result) > 0

    def test_contains_all_query_names(self):
        """list_queries should contain all query names."""
        result = list_queries()
        for name in ALL_QUERIES.keys():
            assert name in result


class TestGetAvailableGoQueries:
    """Tests for get_available_go_queries function."""

    def test_returns_list(self):
        """get_available_go_queries should return a list."""
        result = get_available_go_queries()
        assert isinstance(result, list)

    def test_not_empty(self):
        """get_available_go_queries should not be empty."""
        result = get_available_go_queries()
        assert len(result) > 0

    def test_contains_all_query_names(self):
        """get_available_go_queries should contain all GO_QUERIES names."""
        result = get_available_go_queries()
        for name in GO_QUERIES.keys():
            assert name in result

    def test_no_duplicates(self):
        """get_available_go_queries should have no duplicates."""
        result = get_available_go_queries()
        assert len(result) == len(set(result))
