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
        assert isinstance(filter_obj, QueryFilter)


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


class TestQueryFilterVisibility:
    """Tests for visibility filter."""

    def test_visibility_public(self, query_filter: QueryFilter) -> None:
        result = {"content": "public void run() {}"}
        filtered = query_filter.filter_results([result], "visibility=public")
        assert len(filtered) == 1

    def test_visibility_private(self, query_filter: QueryFilter) -> None:
        result = {"content": "private void run() {}"}
        filtered = query_filter.filter_results([result], "visibility=private")
        assert len(filtered) == 1

    def test_visibility_protected(self, query_filter: QueryFilter) -> None:
        result = {"content": "protected void run() {}"}
        filtered = query_filter.filter_results([result], "visibility=protected")
        assert len(filtered) == 1

    def test_visibility_no_match(self, query_filter: QueryFilter) -> None:
        result = {"content": "private void run() {}"}
        filtered = query_filter.filter_results([result], "visibility=public")
        assert len(filtered) == 0

    def test_visibility_unknown_value(self, query_filter: QueryFilter) -> None:
        result = {"content": "public void run() {}"}
        filtered = query_filter.filter_results([result], "visibility=package")
        assert len(filtered) == 1


class TestQueryFilterAsyncFinalAbstract:
    """Tests for async, final, and abstract modifier filters."""

    def test_async_true(self, query_filter: QueryFilter) -> None:
        result = {"content": "public async Task RunAsync() {}"}
        filtered = query_filter.filter_results([result], "async=true")
        assert len(filtered) == 1

    def test_async_false(self, query_filter: QueryFilter) -> None:
        result = {"content": "public void Run() {}"}
        filtered = query_filter.filter_results([result], "async=false")
        assert len(filtered) == 1

    def test_async_false_when_present(self, query_filter: QueryFilter) -> None:
        result = {"content": "public async Task RunAsync() {}"}
        filtered = query_filter.filter_results([result], "async=false")
        assert len(filtered) == 0

    def test_final_true(self, query_filter: QueryFilter) -> None:
        result = {"content": "public final void finalize() {}"}
        filtered = query_filter.filter_results([result], "final=true")
        assert len(filtered) == 1

    def test_final_false(self, query_filter: QueryFilter) -> None:
        result = {"content": "public void run() {}"}
        filtered = query_filter.filter_results([result], "final=false")
        assert len(filtered) == 1

    def test_abstract_true(self, query_filter: QueryFilter) -> None:
        result = {"content": "public abstract void doWork();"}
        filtered = query_filter.filter_results([result], "abstract=true")
        assert len(filtered) == 1

    def test_abstract_false(self, query_filter: QueryFilter) -> None:
        result = {"content": "public void run() {}"}
        filtered = query_filter.filter_results([result], "abstract=false")
        assert len(filtered) == 1


class TestQueryFilterUnknownKey:
    """Tests for unknown filter key fallback."""

    def test_unknown_filter_key_returns_all(self, query_filter: QueryFilter) -> None:
        results = [{"content": "def main(): pass"}]
        filtered = query_filter.filter_results(results, "unknown_key=value")
        assert len(filtered) == 1


class TestQueryFilterMatchNamePaths:
    """Tests for exact/pattern name match branches."""

    def test_match_name_exact_java(self, query_filter: QueryFilter) -> None:
        result = {"content": "public void myMethod() {}"}
        assert query_filter._match_name(result, "exact", "myMethod") is True
        assert query_filter._match_name(result, "exact", "other") is False

    def test_match_name_pattern_wildcard(self, query_filter: QueryFilter) -> None:
        result = {"content": "def get_name(): pass"}
        assert query_filter._match_name(result, "pattern", "get*") is True
        assert query_filter._match_name(result, "pattern", "set*") is False

    def test_match_name_unknown_type(self, query_filter: QueryFilter) -> None:
        result = {"content": "def main(): pass"}
        assert query_filter._match_name(result, "regex", "main") is False


class TestQueryFilterMatchParamsError:
    """Tests for _match_params ValueError path."""

    def test_match_params_non_numeric(self, query_filter: QueryFilter) -> None:
        result = {"content": "def test(x): pass"}
        assert query_filter._match_params(result, "exact", "abc") is False


class TestQueryFilterMatchModifierEdgeCases:
    """Tests for _match_modifier edge cases."""

    def test_match_modifier_protected_true(self, query_filter: QueryFilter) -> None:
        result = {"content": "protected void doWork() {}"}
        assert query_filter._match_modifier(result, "protected", "true") is True

    def test_match_modifier_case_insensitive_value(
        self, query_filter: QueryFilter
    ) -> None:
        result = {"content": "public static void main() {}"}
        assert query_filter._match_modifier(result, "static", "True") is True

    def test_match_modifier_false_when_present(self, query_filter: QueryFilter) -> None:
        result = {"content": "public static void main() {}"}
        assert query_filter._match_modifier(result, "static", "false") is False

    def test_match_modifier_multiline_content(self, query_filter: QueryFilter) -> None:
        content = "public void run()\n{\n  static x = 1;\n}"
        result = {"content": content}
        assert query_filter._match_modifier(result, "static", "true") is False

    def test_match_modifier_generic_bracket(self, query_filter: QueryFilter) -> None:
        result = {"content": "public abstract <T> void process() {}"}
        assert query_filter._match_modifier(result, "abstract", "true") is True


class TestQueryFilterCountParamsEdgeCases:
    """Tests for _count_parameters edge cases."""

    def test_count_parameters_no_parens(self, query_filter: QueryFilter) -> None:
        assert query_filter._count_parameters("no parens here") == 0

    def test_count_parameters_empty_parens(self, query_filter: QueryFilter) -> None:
        assert query_filter._count_parameters("def test(   ): pass") == 0


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
