#!/usr/bin/env python3
"""
Tests for QueryFilter

Comprehensive tests for query result filtering functionality.
"""

import pytest

from tree_sitter_analyzer.core.query_filter import QueryFilter


class TestQueryFilter:
    """Test cases for QueryFilter"""

    def setup_method(self):
        """Set up test fixtures"""
        self.filter = QueryFilter()

        # Sample query results for testing
        self.sample_results = [
            {
                "capture_name": "method",
                "node_type": "method_declaration",
                "start_line": 1,
                "end_line": 5,
                "content": 'public void main(String[] args) {\n    System.out.println("Hello");\n}',
            },
            {
                "capture_name": "method",
                "node_type": "method_declaration",
                "start_line": 7,
                "end_line": 10,
                "content": "private static void helper() {\n    // helper method\n}",
            },
            {
                "capture_name": "method",
                "node_type": "method_declaration",
                "start_line": 12,
                "end_line": 15,
                "content": 'public String authenticate(String user, String pass) {\n    return "token";\n}',
            },
            {
                "capture_name": "method",
                "node_type": "method_declaration",
                "start_line": 17,
                "end_line": 19,
                "content": "protected void initialize() {\n    // init code\n}",
            },
        ]

    def test_filter_results_no_expression(self):
        """Test filtering with no expression returns all results"""
        result = self.filter.filter_results(self.sample_results, "")
        assert result == self.sample_results

        result = self.filter.filter_results(self.sample_results, None)
        assert result == self.sample_results

    def test_filter_by_exact_name_match(self):
        """Test filtering by exact name match"""
        result = self.filter.filter_results(self.sample_results, "name=main")

        assert len(result) == 1
        assert "main" in result[0]["content"]

    def test_filter_by_exact_name_no_match(self):
        """Test filtering by exact name with no matches"""
        result = self.filter.filter_results(self.sample_results, "name=nonexistent")

        assert len(result) == 0

    def test_filter_by_pattern_name_match(self):
        """Test filtering by pattern name match"""
        result = self.filter.filter_results(self.sample_results, "name=~auth*")

        assert len(result) == 1
        assert "authenticate" in result[0]["content"]

    def test_filter_by_pattern_name_multiple_matches(self):
        """Test filtering by pattern with multiple matches"""
        result = self.filter.filter_results(self.sample_results, "name=~*e*")

        # Should match helper, authenticate, initialize
        assert len(result) == 3
        names = [self.filter._extract_method_name(r["content"]) for r in result]
        assert "helper" in names
        assert "authenticate" in names
        assert "initialize" in names

    def test_filter_by_parameter_count(self):
        """Test filtering by parameter count"""
        # Test methods with no parameters
        result = self.filter.filter_results(self.sample_results, "params=0")
        assert len(result) == 2  # helper and initialize

        # Test methods with 1 parameter
        result = self.filter.filter_results(self.sample_results, "params=1")
        assert len(result) == 1  # main

        # Test methods with 2 parameters
        result = self.filter.filter_results(self.sample_results, "params=2")
        assert len(result) == 1  # authenticate

    def test_filter_by_static_modifier(self):
        """Test filtering by static modifier"""
        result = self.filter.filter_results(self.sample_results, "static=true")

        assert len(result) == 1
        assert "static" in result[0]["content"]
        assert "helper" in result[0]["content"]

    def test_filter_by_public_modifier(self):
        """Test filtering by public modifier"""
        result = self.filter.filter_results(self.sample_results, "public=true")

        assert len(result) == 2
        for r in result:
            assert "public" in r["content"]

    def test_filter_by_private_modifier(self):
        """Test filtering by private modifier"""
        result = self.filter.filter_results(self.sample_results, "private=true")

        assert len(result) == 1
        assert "private" in result[0]["content"]

    def test_filter_by_protected_modifier(self):
        """Test filtering by protected modifier"""
        result = self.filter.filter_results(self.sample_results, "protected=true")

        assert len(result) == 1
        assert "protected" in result[0]["content"]

        # Test filtering by protected=false
        result_false = self.filter.filter_results(
            self.sample_results, "protected=false"
        )
        assert len(result_false) == 3  # Should exclude the protected method
        for res in result_false:
            assert "protected" not in res["content"]

    def test_filter_multiple_conditions_and_logic(self):
        """Test filtering with multiple conditions (AND logic)"""
        result = self.filter.filter_results(self.sample_results, "public=true,params=1")

        assert len(result) == 1
        assert "main" in result[0]["content"]

    def test_filter_multiple_conditions_no_match(self):
        """Test filtering with multiple conditions that don't match anything"""
        result = self.filter.filter_results(
            self.sample_results, "static=true,public=true"
        )

        assert len(result) == 0  # No method is both static and public in our sample

    def test_parse_filter_expression_single_exact(self):
        """Test parsing single exact match expression"""
        filters = self.filter._parse_filter_expression("name=main")

        assert "name" in filters
        assert filters["name"]["type"] == "exact"
        assert filters["name"]["value"] == "main"

    def test_parse_filter_expression_single_pattern(self):
        """Test parsing single pattern match expression"""
        filters = self.filter._parse_filter_expression("name=~auth*")

        assert "name" in filters
        assert filters["name"]["type"] == "pattern"
        assert filters["name"]["value"] == "auth*"

    def test_parse_filter_expression_multiple_conditions(self):
        """Test parsing multiple conditions"""
        filters = self.filter._parse_filter_expression("name=main,params=1,static=true")

        assert len(filters) == 3
        assert filters["name"]["type"] == "exact"
        assert filters["name"]["value"] == "main"
        assert filters["params"]["value"] == "1"
        assert filters["static"]["value"] == "true"

    def test_parse_filter_expression_with_spaces(self):
        """Test parsing expression with spaces"""
        filters = self.filter._parse_filter_expression(" name = main , params = 2 ")

        assert "name" in filters
        assert filters["name"]["value"] == "main"
        assert filters["params"]["value"] == "2"

    def test_extract_method_name_java(self):
        """Test extracting method name from Java code"""
        test_cases = [
            ("public void main(String[] args) {", "main"),
            ("private static void helper() {", "helper"),
            ("protected String authenticate(String user) {", "authenticate"),
            ("public static final void initialize() {", "initialize"),
            ("void simpleMethod() {", "simpleMethod"),
        ]

        for content, expected_name in test_cases:
            result = self.filter._extract_method_name(content)
            assert result == expected_name

    def test_extract_method_name_python(self):
        """Test extracting method name from Python code"""
        test_cases = [
            ("def main():", "main"),
            ("def authenticate(user, password):", "authenticate"),
            ("    def helper_method():", "helper_method"),
        ]

        for content, expected_name in test_cases:
            result = self.filter._extract_method_name(content)
            assert result == expected_name

    def test_extract_method_name_javascript(self):
        """Test extracting method name from JavaScript code"""
        test_cases = [
            ("function main() {", "main"),
            ("function authenticate(user, pass) {", "authenticate"),
            ("  function helper() {", "helper"),
        ]

        for content, expected_name in test_cases:
            result = self.filter._extract_method_name(content)
            assert result == expected_name

    def test_extract_method_name_unknown(self):
        """Test extracting method name from unrecognized pattern"""
        result = self.filter._extract_method_name("some random text")
        assert result == "unknown"

    def test_count_parameters_no_params(self):
        """Test counting parameters for methods with no parameters"""
        test_cases = [
            "public void main()",
            "void helper(  )",
            "def method():",
            "function test() {",
        ]

        for content in test_cases:
            result = self.filter._count_parameters(content)
            assert result == 0

    def test_count_parameters_single_param(self):
        """Test counting parameters for methods with one parameter"""
        test_cases = [
            "public void process(String data)",
            "void helper(int value)",
            "def method(self):",
            "function test(param) {",
        ]

        for content in test_cases:
            result = self.filter._count_parameters(content)
            assert result == 1

    def test_count_parameters_multiple_params(self):
        """Test counting parameters for methods with multiple parameters"""
        test_cases = [
            ("public void process(String data, int count)", 2),
            ("void helper(int a, String b, boolean c)", 3),
            ("def method(self, param1, param2):", 3),
            ("function test(a, b, c, d) {", 4),
        ]

        for content, expected_count in test_cases:
            result = self.filter._count_parameters(content)
            assert result == expected_count

    def test_count_parameters_no_parentheses(self):
        """Test counting parameters when no parentheses found"""
        result = self.filter._count_parameters("some text without parentheses")
        assert result == 0

    def test_match_name_exact(self):
        """Test exact name matching"""
        test_result = {"content": "public void main() {}"}

        assert self.filter._match_name(test_result, "exact", "main")
        assert not self.filter._match_name(test_result, "exact", "helper")

    def test_match_name_pattern(self):
        """Test pattern name matching"""
        test_result = {"content": "public void authenticate() {}"}

        assert self.filter._match_name(test_result, "pattern", "auth*")
        assert not self.filter._match_name(test_result, "pattern", "get*")
        assert self.filter._match_name(test_result, "pattern", "*cate")

    def test_match_params(self):
        """Test parameter count matching"""
        test_result = {"content": "public void method(String a, int b) {}"}

        assert self.filter._match_params(test_result, "exact", "2")
        assert not self.filter._match_params(test_result, "exact", "1")
        assert not self.filter._match_params(test_result, "exact", "invalid")

    def test_match_modifier(self):
        """Test modifier matching"""
        test_cases = [
            ("public void method() {}", "public", "true", True),
            ("public void method() {}", "public", "false", False),
            ("private void method() {}", "public", "true", False),
            ("private void method() {}", "private", "true", True),
            ("static void method() {}", "static", "true", True),
            ("void method() {}", "static", "true", False),
        ]

        for content, modifier, value, expected in test_cases:
            test_result = {"content": content}
            result = self.filter._match_modifier(test_result, modifier, value)
            assert result == expected

    def test_get_filter_help(self):
        """Test getting filter help text"""
        help_text = self.filter.get_filter_help()

        assert "Filter Syntax Help" in help_text
        assert "name=" in help_text
        assert "params=" in help_text
        assert "static=" in help_text
        assert "Examples" in help_text


if __name__ == "__main__":
    pytest.main([__file__])
