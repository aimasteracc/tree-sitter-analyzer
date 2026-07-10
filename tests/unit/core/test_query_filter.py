#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.core.query_filter module.

This module tests the QueryFilter class.
"""

import pytest

from tree_sitter_analyzer.core.query_filter import QueryFilter


class TestQueryFilterInit:
    """Tests for QueryFilter initialization."""


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


class TestQueryFilterParseExpressionComparison:
    """Tests for comparison operator parsing in _parse_filter_expression."""

    def test_parse_gt_operator(self, query_filter: QueryFilter) -> None:
        """Test parsing '>' operator: complexity>10 → {"complexity": {"type": "gt", "value": 10.0}}"""
        filters = query_filter._parse_filter_expression("complexity>10")
        assert "complexity" in filters
        assert filters["complexity"]["type"] == "gt"
        assert filters["complexity"]["value"] == 10.0

    def test_parse_lt_operator(self, query_filter: QueryFilter) -> None:
        """Test parsing '<' operator: complexity<5 → {"complexity": {"type": "lt", "value": 5.0}}"""
        filters = query_filter._parse_filter_expression("complexity<5")
        assert "complexity" in filters
        assert filters["complexity"]["type"] == "lt"
        assert filters["complexity"]["value"] == 5.0

    def test_parse_gte_operator(self, query_filter: QueryFilter) -> None:
        """Test parsing '>=' operator: line_span>=20 → {"line_span": {"type": "gte", "value": 20.0}}"""
        filters = query_filter._parse_filter_expression("line_span>=20")
        assert "line_span" in filters
        assert filters["line_span"]["type"] == "gte"
        assert filters["line_span"]["value"] == 20.0

    def test_parse_lte_operator(self, query_filter: QueryFilter) -> None:
        """Test parsing '<=' operator: line_span<=50 → {"line_span": {"type": "lte", "value": 50.0}}"""
        filters = query_filter._parse_filter_expression("line_span<=50")
        assert "line_span" in filters
        assert filters["line_span"]["type"] == "lte"
        assert filters["line_span"]["value"] == 50.0

    def test_parse_mixed_eq_and_gt(self, query_filter: QueryFilter) -> None:
        """Test parsing combined eq and gt conditions: both registered."""
        filters = query_filter._parse_filter_expression("public=true,complexity>5")
        assert "public" in filters
        assert filters["public"]["type"] == "exact"
        assert filters["public"]["value"] == "true"
        assert "complexity" in filters
        assert filters["complexity"]["type"] == "gt"
        assert filters["complexity"]["value"] == 5.0

    def test_parse_invalid_rhs_non_numeric(self, query_filter: QueryFilter) -> None:
        """Test parsing non-numeric rhs: complexity>abc → complexity key absent (silent fallback)."""
        filters = query_filter._parse_filter_expression("complexity>abc")
        assert "complexity" not in filters


class TestQueryFilterComplexityFilter:
    """Tests for complexity filtering via _matches_single_filter."""

    def test_complexity_gt_match(self, query_filter: QueryFilter) -> None:
        """complexity_score=15, filter gt 10 → True"""
        result = {"complexity_score": 15, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "complexity", {"type": "gt", "value": 10.0}) is True

    def test_complexity_gt_no_match(self, query_filter: QueryFilter) -> None:
        """complexity_score=5, filter gt 10 → False"""
        result = {"complexity_score": 5, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "complexity", {"type": "gt", "value": 10.0}) is False

    def test_complexity_lt_match(self, query_filter: QueryFilter) -> None:
        """complexity_score=3, filter lt 5 → True"""
        result = {"complexity_score": 3, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "complexity", {"type": "lt", "value": 5.0}) is True

    def test_complexity_lt_no_match(self, query_filter: QueryFilter) -> None:
        """complexity_score=8, filter lt 5 → False"""
        result = {"complexity_score": 8, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "complexity", {"type": "lt", "value": 5.0}) is False

    def test_complexity_gte_boundary(self, query_filter: QueryFilter) -> None:
        """complexity_score=10, filter gte 10 → True (boundary inclusive)"""
        result = {"complexity_score": 10, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "complexity", {"type": "gte", "value": 10.0}) is True

    def test_complexity_lte_boundary(self, query_filter: QueryFilter) -> None:
        """complexity_score=10, filter lte 10 → True (boundary inclusive)"""
        result = {"complexity_score": 10, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "complexity", {"type": "lte", "value": 10.0}) is True

    def test_complexity_missing_field(self, query_filter: QueryFilter) -> None:
        """result without complexity_score, filter gt 5 → False (exclude)"""
        result = {"content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "complexity", {"type": "gt", "value": 5.0}) is False


class TestQueryFilterLineSpanFilter:
    """Tests for line_span filtering via _matches_single_filter."""

    def test_line_span_gt_match(self, query_filter: QueryFilter) -> None:
        """line_span=60, filter gt 50 → True"""
        result = {"line_span": 60, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "line_span", {"type": "gt", "value": 50.0}) is True

    def test_line_span_gt_no_match(self, query_filter: QueryFilter) -> None:
        """line_span=30, filter gt 50 → False"""
        result = {"line_span": 30, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "line_span", {"type": "gt", "value": 50.0}) is False

    def test_line_span_lt_match(self, query_filter: QueryFilter) -> None:
        """line_span=10, filter lt 20 → True"""
        result = {"line_span": 10, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "line_span", {"type": "lt", "value": 20.0}) is True

    def test_line_span_lt_no_match(self, query_filter: QueryFilter) -> None:
        """line_span=25, filter lt 20 → False"""
        result = {"line_span": 25, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "line_span", {"type": "lt", "value": 20.0}) is False

    def test_line_span_gte_boundary(self, query_filter: QueryFilter) -> None:
        """line_span=20, filter gte 20 → True (boundary inclusive)"""
        result = {"line_span": 20, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "line_span", {"type": "gte", "value": 20.0}) is True

    def test_line_span_lte_boundary(self, query_filter: QueryFilter) -> None:
        """line_span=20, filter lte 20 → True (boundary inclusive)"""
        result = {"line_span": 20, "content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "line_span", {"type": "lte", "value": 20.0}) is True

    def test_line_span_missing_field(self, query_filter: QueryFilter) -> None:
        """result without line_span, filter gt 10 → False (exclude)"""
        result = {"content": "void foo() {}"}
        assert query_filter._matches_single_filter(result, "line_span", {"type": "gt", "value": 10.0}) is False


class TestQueryFilterComparisonIntegration:
    """Integration tests for comparison filters through filter_results."""

    def test_filter_complexity_gt_full(self, query_filter: QueryFilter) -> None:
        """3 results with scores 3, 12, 7; filter complexity>10 → 1 result (score=12)"""
        results = [
            {"content": "void a() {}", "complexity_score": 3},
            {"content": "void b() {}", "complexity_score": 12},
            {"content": "void c() {}", "complexity_score": 7},
        ]
        filtered = query_filter.filter_results(results, "complexity>10")
        assert len(filtered) == 1
        assert filtered[0]["complexity_score"] == 12

    def test_filter_line_span_lt_full(self, query_filter: QueryFilter) -> None:
        """3 results with spans 100, 20, 50; filter line_span<50 → 1 result (span=20)"""
        results = [
            {"content": "void a() {}", "line_span": 100},
            {"content": "void b() {}", "line_span": 20},
            {"content": "void c() {}", "line_span": 50},
        ]
        filtered = query_filter.filter_results(results, "line_span<50")
        assert len(filtered) == 1
        assert filtered[0]["line_span"] == 20

    def test_filter_mixed_eq_and_gt(self, query_filter: QueryFilter) -> None:
        """Mixed eq and gt filter applied as AND logic."""
        results = [
            {"content": "public void a() {}", "complexity_score": 10},
            {"content": "public void b() {}", "complexity_score": 3},
            {"content": "private void c() {}", "complexity_score": 10},
        ]
        filtered = query_filter.filter_results(results, "public=true,complexity>5")
        # Should match: public=true AND complexity>5
        # a: public=true, complexity=10>5 → match
        # b: public=true, complexity=3 not >5 → no match
        # c: public=false → no match
        assert len(filtered) == 1
        assert filtered[0]["complexity_score"] == 10
        assert "public" in filtered[0]["content"]
        assert "void a()" in filtered[0]["content"]

    def test_filter_silent_fallback(
        self, query_filter: QueryFilter, capsys: pytest.CaptureFixture
    ) -> None:
        """complexity>abc → all results returned, stderr warning emitted."""
        results = [
            {"content": "void a() {}", "complexity_score": 5},
            {"content": "void b() {}", "complexity_score": 15},
        ]
        filtered = query_filter.filter_results(results, "complexity>abc")
        # All results returned since the condition is skipped
        assert len(filtered) == 2
        captured = capsys.readouterr()
        assert "abc" in captured.err or "complexity" in captured.err


class TestGetFilterHelpContainsComplexity:
    """Tests that get_filter_help includes complexity and line_span entries."""

    def test_get_filter_help_contains_complexity(self, query_filter: QueryFilter) -> None:
        """get_filter_help should mention complexity filter."""
        help_text = query_filter.get_filter_help()
        assert "complexity" in help_text

    def test_get_filter_help_contains_line_span(self, query_filter: QueryFilter) -> None:
        """get_filter_help should mention line_span filter."""
        help_text = query_filter.get_filter_help()
        assert "line_span" in help_text

    def test_get_filter_help_contains_comparison_operators(self, query_filter: QueryFilter) -> None:
        """get_filter_help should show comparison operator examples."""
        help_text = query_filter.get_filter_help()
        assert ">" in help_text


# Pytest fixtures
@pytest.fixture
def query_filter() -> QueryFilter:
    """Create a QueryFilter instance for testing."""
    return QueryFilter()
