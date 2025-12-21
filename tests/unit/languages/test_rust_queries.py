"""Tests for Rust query definitions."""

import pytest

from tree_sitter_analyzer.queries.rust import (
    ALL_QUERIES,
    RUST_QUERIES,
    RUST_QUERY_DESCRIPTIONS,
    get_all_queries,
    get_available_rust_queries,
    get_query,
    get_rust_query,
    get_rust_query_description,
    list_queries,
)


class TestRustQueriesDict:
    """Tests for RUST_QUERIES dictionary."""

    def test_rust_queries_is_dict(self):
        """RUST_QUERIES should be a dictionary."""
        assert isinstance(RUST_QUERIES, dict)

    def test_rust_queries_not_empty(self):
        """RUST_QUERIES should not be empty."""
        assert len(RUST_QUERIES) > 0

    def test_all_queries_are_strings(self):
        """All query values should be strings."""
        for name, query in RUST_QUERIES.items():
            assert isinstance(query, str), f"Query '{name}' is not a string"

    def test_all_queries_not_empty(self):
        """All query values should not be empty."""
        for name, query in RUST_QUERIES.items():
            assert query.strip(), f"Query '{name}' is empty"


class TestRustQueriesContent:
    """Tests for Rust query content."""

    def test_mod_query_exists(self):
        """Module query should exist."""
        assert "mod" in RUST_QUERIES
        assert "mod_item" in RUST_QUERIES["mod"]

    def test_struct_query_exists(self):
        """Struct query should exist."""
        assert "struct" in RUST_QUERIES
        assert "struct_item" in RUST_QUERIES["struct"]

    def test_enum_query_exists(self):
        """Enum query should exist."""
        assert "enum" in RUST_QUERIES
        assert "enum_item" in RUST_QUERIES["enum"]

    def test_trait_query_exists(self):
        """Trait query should exist."""
        assert "trait" in RUST_QUERIES
        assert "trait_item" in RUST_QUERIES["trait"]

    def test_impl_query_exists(self):
        """Impl query should exist."""
        assert "impl" in RUST_QUERIES
        assert "impl_item" in RUST_QUERIES["impl"]

    def test_fn_query_exists(self):
        """Function query should exist."""
        assert "fn" in RUST_QUERIES
        assert "function_item" in RUST_QUERIES["fn"]

    def test_const_query_exists(self):
        """Const query should exist."""
        assert "const" in RUST_QUERIES
        assert "const_item" in RUST_QUERIES["const"]

    def test_static_query_exists(self):
        """Static query should exist."""
        assert "static" in RUST_QUERIES
        assert "static_item" in RUST_QUERIES["static"]

    def test_macro_query_exists(self):
        """Macro query should exist."""
        assert "macro" in RUST_QUERIES
        assert "macro_definition" in RUST_QUERIES["macro"]

    def test_attribute_query_exists(self):
        """Attribute query should exist."""
        assert "attribute" in RUST_QUERIES
        assert "attribute_item" in RUST_QUERIES["attribute"]

    def test_field_query_exists(self):
        """Field query should exist."""
        assert "field" in RUST_QUERIES
        assert "field_declaration" in RUST_QUERIES["field"]

    def test_enum_variant_query_exists(self):
        """Enum variant query should exist."""
        assert "enum_variant" in RUST_QUERIES
        assert "enum_variant" in RUST_QUERIES["enum_variant"]


class TestRustQueryDescriptions:
    """Tests for RUST_QUERY_DESCRIPTIONS dictionary."""

    def test_descriptions_is_dict(self):
        """RUST_QUERY_DESCRIPTIONS should be a dictionary."""
        assert isinstance(RUST_QUERY_DESCRIPTIONS, dict)

    def test_descriptions_not_empty(self):
        """RUST_QUERY_DESCRIPTIONS should not be empty."""
        assert len(RUST_QUERY_DESCRIPTIONS) > 0

    def test_all_descriptions_are_strings(self):
        """All description values should be strings."""
        for name, desc in RUST_QUERY_DESCRIPTIONS.items():
            assert isinstance(desc, str), f"Description for '{name}' is not a string"

    def test_all_queries_have_descriptions(self):
        """All queries should have descriptions."""
        for query_name in RUST_QUERIES.keys():
            assert (
                query_name in RUST_QUERY_DESCRIPTIONS
            ), f"Query '{query_name}' has no description"


class TestGetRustQuery:
    """Tests for get_rust_query function."""

    def test_get_valid_query(self):
        """get_rust_query should return query for valid name."""
        result = get_rust_query("fn")
        assert isinstance(result, str)
        assert "function_item" in result

    def test_get_all_queries(self):
        """get_rust_query should work for all defined queries."""
        for name in RUST_QUERIES.keys():
            result = get_rust_query(name)
            assert isinstance(result, str)
            assert result == RUST_QUERIES[name]

    def test_invalid_query_raises_error(self):
        """get_rust_query should raise ValueError for invalid name."""
        with pytest.raises(ValueError) as excinfo:
            get_rust_query("nonexistent_query")
        assert "nonexistent_query" in str(excinfo.value)
        assert "Available" in str(excinfo.value)


class TestGetRustQueryDescription:
    """Tests for get_rust_query_description function."""

    def test_get_valid_description(self):
        """get_rust_query_description should return description for valid name."""
        result = get_rust_query_description("fn")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_all_descriptions(self):
        """get_rust_query_description should work for all defined queries."""
        for name in RUST_QUERIES.keys():
            result = get_rust_query_description(name)
            assert isinstance(result, str)

    def test_invalid_query_returns_default(self):
        """get_rust_query_description should return default for invalid name."""
        result = get_rust_query_description("nonexistent_query")
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

    def test_contains_all_rust_queries(self):
        """ALL_QUERIES should contain all RUST_QUERIES."""
        for name in RUST_QUERIES.keys():
            assert name in ALL_QUERIES, f"Query '{name}' not in ALL_QUERIES"

    def test_contains_aliases(self):
        """ALL_QUERIES should contain common aliases."""
        assert "functions" in ALL_QUERIES
        assert "methods" in ALL_QUERIES
        assert "classes" in ALL_QUERIES


class TestGetQuery:
    """Tests for get_query function."""

    def test_get_valid_query(self):
        """get_query should return query for valid name."""
        result = get_query("fn")
        assert isinstance(result, str)
        assert "function_item" in result

    def test_get_alias_query(self):
        """get_query should work for aliases."""
        result = get_query("functions")
        assert isinstance(result, str)
        assert "function_item" in result

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


class TestGetAvailableRustQueries:
    """Tests for get_available_rust_queries function."""

    def test_returns_list(self):
        """get_available_rust_queries should return a list."""
        result = get_available_rust_queries()
        assert isinstance(result, list)

    def test_not_empty(self):
        """get_available_rust_queries should not be empty."""
        result = get_available_rust_queries()
        assert len(result) > 0

    def test_contains_all_query_names(self):
        """get_available_rust_queries should contain all RUST_QUERIES names."""
        result = get_available_rust_queries()
        for name in RUST_QUERIES.keys():
            assert name in result

    def test_no_duplicates(self):
        """get_available_rust_queries should have no duplicates."""
        result = get_available_rust_queries()
        assert len(result) == len(set(result))
