#!/usr/bin/env python3
"""
Tests for YAML Query Functions

Covers get_yaml_query, get_yaml_query_description, and get_available_yaml_queries.
These functions provide access to tree-sitter queries for YAML language analysis.
"""

import pytest

from tree_sitter_analyzer.queries.yaml import (
    get_available_yaml_queries,
    get_yaml_query,
    get_yaml_query_description,
)


class TestGetYamlQuery:
    """Tests for get_yaml_query(name: str) -> str."""

    def test_returns_string_query_for_valid_name(self):
        """get_yaml_query should return a non-empty string for a known query name."""
        query = get_yaml_query("document")
        assert isinstance(query, str)
        assert len(query.strip()) > 0

    def test_known_query_names_return_queries(self):
        """All names returned by get_available_yaml_queries should produce a query."""
        for name in get_available_yaml_queries():
            query = get_yaml_query(name)
            assert isinstance(query, str), f"Query '{name}' should be a string"
            assert len(query.strip()) > 0, f"Query '{name}' should not be empty"

    def test_raises_value_error_for_unknown_query(self):
        """get_yaml_query should raise ValueError for an unknown query name."""
        with pytest.raises(ValueError, match="does not exist"):
            get_yaml_query("nonexistent_query_xyz")

    def test_raises_value_error_mentions_available(self):
        """ValueError message should list available query names."""
        with pytest.raises(ValueError) as exc_info:
            get_yaml_query("totally_unknown")
        assert "Available" in str(exc_info.value) or "available" in str(exc_info.value)

    def test_key_query_returns_yaml_capture(self):
        """The 'key' query should contain a @key capture."""
        query = get_yaml_query("key")
        assert "@key" in query

    def test_document_query_returns_document_capture(self):
        """The 'document' query should target document nodes."""
        query = get_yaml_query("document")
        assert "document" in query


class TestGetYamlQueryDescription:
    """Tests for get_yaml_query_description(name: str) -> str."""

    def test_returns_string_for_known_name(self):
        """get_yaml_query_description should return a non-empty string."""
        desc = get_yaml_query_description("document")
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_returns_fallback_for_unknown_name(self):
        """get_yaml_query_description should return the fallback for unknown names."""
        desc = get_yaml_query_description("totally_unknown_xyz")
        assert isinstance(desc, str)
        assert desc == "No description"

    def test_all_known_queries_have_descriptions(self):
        """Every name in get_available_yaml_queries should have a description."""
        for name in get_available_yaml_queries():
            desc = get_yaml_query_description(name)
            assert isinstance(desc, str), f"'{name}' description should be a string"
            assert len(desc) > 0, f"'{name}' description should not be empty"


class TestGetAvailableYamlQueries:
    """Tests for get_available_yaml_queries() -> list[str]."""

    def test_returns_list(self):
        """get_available_yaml_queries should return a list."""
        result = get_available_yaml_queries()
        assert isinstance(result, list)

    def test_list_is_not_empty(self):
        """get_available_yaml_queries should return a non-empty list."""
        result = get_available_yaml_queries()
        assert len(result) > 0

    def test_list_contains_core_yaml_queries(self):
        """Core YAML query names should be present in the available list."""
        available = get_available_yaml_queries()
        for expected in ("document", "key", "comment"):
            assert expected in available, f"'{expected}' should be in available queries"

    def test_list_contains_only_strings(self):
        """All entries in the available list should be strings."""
        for name in get_available_yaml_queries():
            assert isinstance(name, str), f"Query name '{name}' should be a string"

    def test_no_duplicates(self):
        """get_available_yaml_queries should return no duplicate names."""
        available = get_available_yaml_queries()
        assert len(available) == len(set(available))
