#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.core.query_filter module.

This module tests the QueryFilter class.
"""

import pytest

from tree_sitter_analyzer.core.query_filter import QueryFilter


class TestQueryFilterInit:
    """Tests for QueryFilter initialization."""

    def test_query_filter_init(self) -> None:
        """Test QueryFilter initialization."""
        filter_obj = QueryFilter()
        assert filter_obj is not None


class TestQueryFilterFilterResults:
    """Tests for QueryFilter.filter_results method."""

    def test_filter_results_no_filter(self, query_filter: QueryFilter) -> None:
        """Test filtering with no filter expression."""
        results = [
            {"content": "def main(): pass", "name": "main"},
            {"content": "def test(): pass", "name": "test"},
        ]
        filtered = query_filter.filter_results(results, "")
        assert len(filtered) == 2

    def test_filter_results_empty_filter(self, query_filter: QueryFilter) -> None:
        """Test filtering with empty filter expression."""
        results = [
            {"content": "def main(): pass", "name": "main"},
            {"content": "def test(): pass", "name": "test"},
        ]
        filtered = query_filter.filter_results(results, "")
        assert len(filtered) == 2

    def test_filter_results_name_exact(self, query_filter: QueryFilter) -> None:
        """Test filtering by exact name."""
        results = [
            {"content": "def main(): pass", "name": "main"},
            {"content": "def test(): pass", "name": "test"},
            {"content": "def main2(): pass", "name": "main2"},
        ]
        filtered = query_filter.filter_results(results, "name=main")
        assert len(filtered) == 1
        assert filtered[0]["name"] == "main"

    def test_filter_results_name_pattern(self, query_filter: QueryFilter) -> None:
        """Test filtering by name pattern."""
        results = [
            {"content": "def main(): pass", "name": "main"},
            {"content": "def test(): pass", "name": "test"},
            {"content": "def main2(): pass", "name": "main2"},
            {"content": "def authenticate(): pass", "name": "authenticate"},
        ]
        filtered = query_filter.filter_results(results, "name=~main*")
        assert len(filtered) == 2

    def test_filter_results_multiple_conditions(
        self, query_filter: QueryFilter
    ) -> None:
        """Test filtering with multiple conditions."""
        results = [
            {"content": "def main(): pass", "name": "main"},
            {"content": "def test(): pass", "name": "test"},
            {"content": "def authenticate(): pass", "name": "authenticate"},
        ]
        filtered = query_filter.filter_results(results, "name=~auth*,params=0")
        assert len(filtered) == 1

    def test_filter_results_no_matches(self, query_filter: QueryFilter) -> None:
        """Test filtering with no matches."""
        results = [
            {"content": "def main(): pass", "name": "main"},
            {"content": "def test(): pass", "name": "test"},
        ]
        filtered = query_filter.filter_results(results, "name=nonexistent")
        assert len(filtered) == 0


class TestQueryFilterParseExpression:
    """Tests for QueryFilter._parse_filter_expression method."""

    def test_parse_expression_single_condition(self, query_filter: QueryFilter) -> None:
        """Test parsing single condition."""
        filters = query_filter._parse_filter_expression("name=main")
        assert "name" in filters
        assert filters["name"]["type"] == "exact"
        assert filters["name"]["value"] == "main"

    def test_parse_expression_pattern_condition(
        self, query_filter: QueryFilter
    ) -> None:
        """Test parsing pattern condition."""
        filters = query_filter._parse_filter_expression("name=~main*")
        assert "name" in filters
        assert filters["name"]["type"] == "pattern"
        assert filters["name"]["value"] == "main*"

    def test_parse_expression_multiple_conditions(
        self, query_filter: QueryFilter
    ) -> None:
        """Test parsing multiple conditions."""
        filters = query_filter._parse_filter_expression("name=main,params=0")
        assert "name" in filters
        assert "params" in filters
        assert len(filters) == 2

    def test_parse_expression_with_spaces(self, query_filter: QueryFilter) -> None:
        """Test parsing expression with spaces."""
        filters = query_filter._parse_filter_expression(" name = main , params = 0 ")
        assert "name" in filters
        assert "params" in filters
        assert filters["name"]["value"] == "main"
        assert filters["params"]["value"] == "0"


class TestQueryFilterMatchName:
    """Tests for QueryFilter._match_name method."""

    def test_match_name_exact(self, query_filter: QueryFilter) -> None:
        """Test exact name match."""
        result = {"content": "def main(): pass"}
        assert query_filter._match_name(result, "exact", "main") is True
        assert query_filter._match_name(result, "exact", "test") is False

    def test_match_name_pattern(self, query_filter: QueryFilter) -> None:
        """Test pattern name match."""
        result = {"content": "def main(): pass"}
        assert query_filter._match_name(result, "pattern", "main*") is True
        assert query_filter._match_name(result, "pattern", "test*") is False

    def test_match_name_case_insensitive(self, query_filter: QueryFilter) -> None:
        """Test case-insensitive pattern match."""
        result = {"content": "def Main(): pass"}
        assert query_filter._match_name(result, "pattern", "main*") is True

    def test_match_name_unknown(self, query_filter: QueryFilter) -> None:
        """Test matching unknown method name."""
        name = query_filter._extract_method_name("unknown content")
        assert name == "unknown"


class TestQueryFilterMatchParams:
    """Tests for QueryFilter._match_params method."""

    def test_match_params_zero(self, query_filter: QueryFilter) -> None:
        """Test matching zero parameters."""
        result = {"content": "def main(): pass"}
        assert query_filter._match_params(result, "exact", "0") is True
        assert query_filter._match_params(result, "exact", "1") is False

    def test_match_params_one(self, query_filter: QueryFilter) -> None:
        """Test matching one parameter."""
        result = {"content": "def test(x): pass"}
        assert query_filter._match_params(result, "exact", "1") is True
        assert query_filter._match_params(result, "exact", "0") is False

    def test_match_params_multiple(self, query_filter: QueryFilter) -> None:
        """Test matching multiple parameters."""
        result = {"content": "def func(x, y, z): pass"}
        assert query_filter._match_params(result, "exact", "3") is True

    def test_match_params_invalid(self, query_filter: QueryFilter) -> None:
        """Test matching with invalid parameter count."""
        result = {"content": "def test(x): pass"}
        assert query_filter._match_params(result, "exact", "abc") is False


class TestQueryFilterMatchModifier:
    """Tests for QueryFilter._match_modifier method."""

    def test_match_modifier_static_true(self, query_filter: QueryFilter) -> None:
        """Test matching static modifier true."""
        result = {"content": "public static void main() {}"}
        assert query_filter._match_modifier(result, "static", "true") is True
        assert query_filter._match_modifier(result, "static", "false") is False

    def test_match_modifier_static_false(self, query_filter: QueryFilter) -> None:
        """Test matching static modifier false."""
        result = {"content": "public void main() {}"}
        assert query_filter._match_modifier(result, "static", "false") is True
        assert query_filter._match_modifier(result, "static", "true") is False

    def test_match_modifier_public_true(self, query_filter: QueryFilter) -> None:
        """Test matching public modifier true."""
        result = {"content": "public void main() {}"}
        assert query_filter._match_modifier(result, "public", "true") is True

    def test_match_modifier_public_false(self, query_filter: QueryFilter) -> None:
        """Test matching public modifier false."""
        result = {"content": "private void main() {}"}
        assert query_filter._match_modifier(result, "public", "false") is True

    def test_match_modifier_private_true(self, query_filter: QueryFilter) -> None:
        """Test matching private modifier true."""
        result = {"content": "private void main() {}"}
        assert query_filter._match_modifier(result, "private", "true") is True

    def test_match_modifier_private_false(self, query_filter: QueryFilter) -> None:
        """Test matching private modifier false."""
        result = {"content": "public void main() {}"}
        assert query_filter._match_modifier(result, "private", "false") is True


class TestQueryFilterEdgeCases:
    """Tests for edge cases and error handling."""

    def test_filter_results_empty_list(self, query_filter: QueryFilter) -> None:
        """Test filtering empty results list."""
        results = []
        filtered = query_filter.filter_results(results, "name=main")
        assert len(filtered) == 0

    def test_filter_results_missing_content(self, query_filter: QueryFilter) -> None:
        """Test filtering results without content field."""
        results = [{"name": "main"}]
        filtered = query_filter.filter_results(results, "name=main")
        # Should handle gracefully
        assert isinstance(filtered, list)

    def test_extract_method_name_python(self, query_filter: QueryFilter) -> None:
        """Test extracting method name from Python."""
        name = query_filter._extract_method_name("def my_function(): pass")
        assert name == "my_function"

    def test_extract_method_name_java(self, query_filter: QueryFilter) -> None:
        """Test extracting method name from Java."""
        name = query_filter._extract_method_name("public static void myMethod() {}")
        assert name == "myMethod"

    def test_extract_method_name_javascript(self, query_filter: QueryFilter) -> None:
        """Test extracting method name from JavaScript."""
        name = query_filter._extract_method_name("function myFunc() {}")
        assert name == "myFunc"

    def test_extract_method_name_unknown(self, query_filter: QueryFilter) -> None:
        """Test extracting method name from unknown format."""
        name = query_filter._extract_method_name("some random text")
        assert name == "unknown"

    def test_count_parameters_empty(self, query_filter: QueryFilter) -> None:
        """Test counting parameters with empty list."""
        count = query_filter._count_parameters("def test(): pass")
        assert count == 0

    def test_count_parameters_single(self, query_filter: QueryFilter) -> None:
        """Test counting single parameter."""
        count = query_filter._count_parameters("def test(x): pass")
        assert count == 1

    def test_count_parameters_multiple(self, query_filter: QueryFilter) -> None:
        """Test counting multiple parameters."""
        count = query_filter._count_parameters("def test(x, y, z): pass")
        assert count == 3

    def test_count_parameters_with_spaces(self, query_filter: QueryFilter) -> None:
        """Test counting parameters with spaces."""
        count = query_filter._count_parameters("def test(x, y, z): pass")
        assert count == 3

    def test_get_filter_help(self, query_filter: QueryFilter) -> None:
        """Test getting filter help."""
        help_text = query_filter.get_filter_help()
        assert "Filter Syntax Help" in help_text
        assert "name" in help_text
        assert "params" in help_text
        assert "static" in help_text


# Pytest fixtures
@pytest.fixture
def query_filter() -> QueryFilter:
    """Create a QueryFilter instance for testing."""
    return QueryFilter()
