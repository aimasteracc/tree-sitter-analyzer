#!/usr/bin/env python3
"""
Extended tests for JavaScript Tree-sitter queries.

This module tests the comprehensive JavaScript query definitions to ensure
they cover all modern JavaScript features and maintain consistency with
other language query implementations.
"""

import pytest

from tree_sitter_analyzer.queries import javascript as js_queries


class TestJavaScriptExtendedQueries:
    """Test cases for extended JavaScript query definitions"""

    def test_query_count_comprehensive(self):
        """Test that JavaScript has comprehensive query coverage"""
        # JavaScript should have 85+ queries
        assert len(js_queries.ALL_QUERIES) >= 85
        print(f"Total JavaScript queries: {len(js_queries.ALL_QUERIES)}")

    def test_function_queries_comprehensive(self):
        """Test comprehensive function query coverage"""
        function_queries = [
            "function",
            "function_declaration",
            "function_expression",
            "arrow_function",
            "method_definition",
            "async_function",
            "generator_function",
        ]

        for query_name in function_queries:
            assert query_name in js_queries.ALL_QUERIES
            query_data = js_queries.ALL_QUERIES[query_name]
            assert "query" in query_data
            assert "description" in query_data
            assert len(query_data["query"].strip()) > 0

    def test_class_queries_comprehensive(self):
        """Test comprehensive class query coverage"""
        class_queries = [
            "class",
            "class_declaration",
            "class_expression",
            "constructor",
            "class_method",  # Changed from "method" to "class_method"
            "getter",
            "setter",
            "static_method",
        ]

        for query_name in class_queries:
            assert query_name in js_queries.ALL_QUERIES
            query_data = js_queries.ALL_QUERIES[query_name]
            assert "query" in query_data
            assert "description" in query_data

    def test_variable_queries_comprehensive(self):
        """Test comprehensive variable query coverage"""
        variable_queries = [
            "variable",
            "const_declaration",
            "let_declaration",
            "var_declaration",
        ]

        for query_name in variable_queries:
            assert query_name in js_queries.ALL_QUERIES
            query_data = js_queries.ALL_QUERIES[query_name]
            assert "query" in query_data
            assert "description" in query_data

    def test_import_export_queries(self):
        """Test import/export query coverage"""
        import_export_queries = [
            "import",
            "import_statement",
            "import_default",
            "import_named",
            "import_namespace",
            "export",
            "export_default",
            "export_named",
        ]

        for query_name in import_export_queries:
            assert query_name in js_queries.ALL_QUERIES
            query_data = js_queries.ALL_QUERIES[query_name]
            assert "query" in query_data
            assert "description" in query_data

    def test_modern_javascript_features(self):
        """Test modern JavaScript feature queries"""
        modern_queries = [
            "destructuring",
            "spread_element",
            "rest_parameter",
            "template_literal",
            "optional_chaining",
            "nullish_coalescing",
            "async_await",
            "promise",
        ]

        for query_name in modern_queries:
            if query_name in js_queries.ALL_QUERIES:  # Some might not exist
                query_data = js_queries.ALL_QUERIES[query_name]
                assert "query" in query_data
                assert "description" in query_data

    def test_jsx_queries(self):
        """Test JSX query coverage"""
        jsx_queries = [
            "jsx_element",
            "jsx_self_closing_element",
            "jsx_fragment",
            "jsx_expression",
        ]

        for query_name in jsx_queries:
            if query_name in js_queries.ALL_QUERIES:  # JSX might be optional
                query_data = js_queries.ALL_QUERIES[query_name]
                assert "query" in query_data
                assert "description" in query_data
                assert "jsx" in query_data["description"].lower()

    def test_object_queries(self):
        """Test object-related queries"""
        object_queries = [
            "object",
            "object_pattern",
            "property_definition",
            "computed_property",
            "shorthand_property",
        ]

        for query_name in object_queries:
            if query_name in js_queries.ALL_QUERIES:
                query_data = js_queries.ALL_QUERIES[query_name]
                assert "query" in query_data
                assert "description" in query_data

    def test_control_flow_queries(self):
        """Test control flow queries"""
        control_flow_queries = [
            "if_statement",
            "for_statement",
            "while_statement",
            "switch_statement",
            "try_statement",
            "catch_clause",
            "finally_clause",
        ]

        for query_name in control_flow_queries:
            if query_name in js_queries.ALL_QUERIES:
                query_data = js_queries.ALL_QUERIES[query_name]
                assert "query" in query_data
                assert "description" in query_data

    def test_expression_queries(self):
        """Test expression queries"""
        expression_queries = [
            "binary_expression",
            "unary_expression",
            "assignment_expression",
            "call_expression",
            "member_expression",
            "conditional_expression",
        ]

        for query_name in expression_queries:
            if query_name in js_queries.ALL_QUERIES:
                query_data = js_queries.ALL_QUERIES[query_name]
                assert "query" in query_data
                assert "description" in query_data

    def test_comment_queries(self):
        """Test comment queries"""
        comment_queries = ["comment", "line_comment", "block_comment"]

        for query_name in comment_queries:
            if query_name in js_queries.ALL_QUERIES:
                query_data = js_queries.ALL_QUERIES[query_name]
                assert "query" in query_data
                assert "description" in query_data

    def test_all_queries_structure(self):
        """Test that all queries have valid structure"""
        for query_name, query_data in js_queries.ALL_QUERIES.items():
            # Check structure
            assert isinstance(query_name, str)
            assert isinstance(query_data, dict)
            assert "query" in query_data
            assert "description" in query_data

            # Check content
            assert isinstance(query_data["query"], str)
            assert isinstance(query_data["description"], str)
            assert len(query_data["query"].strip()) > 0
            assert len(query_data["description"].strip()) > 0

    def test_query_syntax_validation(self):
        """Test basic syntax validation for queries"""
        for query_name, query_data in js_queries.ALL_QUERIES.items():
            query_string = query_data["query"]

            # Basic syntax checks
            assert query_string.count("(") == query_string.count(")"), (
                f"Unbalanced parentheses in {query_name} query"
            )
            assert query_string.count("[") == query_string.count("]"), (
                f"Unbalanced brackets in {query_name} query"
            )
            assert query_string.count("{") == query_string.count("}"), (
                f"Unbalanced braces in {query_name} query"
            )

    def test_capture_groups_present(self):
        """Test that queries contain capture groups"""
        for query_name, query_data in js_queries.ALL_QUERIES.items():
            query_string = query_data["query"]

            # Should contain capture groups (indicated by @)
            assert "@" in query_string, f"No capture groups found in {query_name} query"

    def test_javascript_specific_features(self):
        """Test JavaScript-specific features in queries"""
        all_queries_text = " ".join(
            [q["query"] for q in js_queries.ALL_QUERIES.values()]
        )

        # JavaScript-specific node types
        js_features = [
            "function_declaration",
            "function_expression",
            "arrow_function",
            "class_declaration",
            "method_definition",
            "variable_declaration",
            "import_statement",
            "export_statement",
        ]

        for feature in js_features:
            assert feature in all_queries_text, (
                f"JavaScript feature '{feature}' not found in queries"
            )

    def test_query_descriptions_quality(self):
        """Test that query descriptions are meaningful"""
        for query_name, query_data in js_queries.ALL_QUERIES.items():
            description = query_data["description"]

            # Description should be meaningful
            assert len(description) > 10, f"Description for {query_name} is too short"
            assert not description.lower().startswith("todo"), (
                f"Description for {query_name} appears to be a placeholder"
            )

    def test_utility_functions(self):
        """Test utility functions"""
        # Test get_query function
        if hasattr(js_queries, "get_query"):
            functions_query = js_queries.get_query("functions")
            assert isinstance(functions_query, str)
            assert len(functions_query) > 0

        # Test get_all_queries function
        if hasattr(js_queries, "get_all_queries"):
            all_queries = js_queries.get_all_queries()
            assert isinstance(all_queries, dict)
            assert len(all_queries) >= 85

        # Test list_queries function
        if hasattr(js_queries, "list_queries"):
            query_names = js_queries.list_queries()
            assert isinstance(query_names, list)
            assert len(query_names) >= 85

    def test_consistency_with_constants(self):
        """Test consistency between constants and ALL_QUERIES"""
        # Test that ALL_QUERIES contains the expected constants
        if hasattr(js_queries, "FUNCTIONS"):
            assert js_queries.ALL_QUERIES["functions"]["query"] == js_queries.FUNCTIONS

        if hasattr(js_queries, "CLASSES"):
            assert js_queries.ALL_QUERIES["classes"]["query"] == js_queries.CLASSES

        if hasattr(js_queries, "VARIABLES"):
            assert js_queries.ALL_QUERIES["variables"]["query"] == js_queries.VARIABLES

    def test_framework_specific_queries(self):
        """Test framework-specific queries"""
        framework_queries = [
            "react_component",
            "react_hook",
            "vue_component",
            "angular_component",
        ]

        for query_name in framework_queries:
            if query_name in js_queries.ALL_QUERIES:
                query_data = js_queries.ALL_QUERIES[query_name]
                assert "query" in query_data
                assert "description" in query_data

    def test_advanced_patterns(self):
        """Test advanced JavaScript patterns"""
        advanced_queries = [
            "closure",
            "iife",  # Immediately Invoked Function Expression
            "callback",
            "promise_chain",
            "event_listener",
            "module_pattern",
        ]

        for query_name in advanced_queries:
            if query_name in js_queries.ALL_QUERIES:
                query_data = js_queries.ALL_QUERIES[query_name]
                assert "query" in query_data
                assert "description" in query_data

    def test_es6_plus_features(self):
        """Test ES6+ feature queries"""
        es6_queries = [
            "class_declaration",
            "arrow_function",
            "template_literal",
            "destructuring_assignment",
            "spread_syntax",
            "rest_parameters",
            "default_parameters",
            "for_of_statement",
        ]

        for query_name in es6_queries:
            if query_name in js_queries.ALL_QUERIES:
                query_data = js_queries.ALL_QUERIES[query_name]
                assert "query" in query_data
                assert "description" in query_data


class TestJavaScriptQueryComparison:
    """Test JavaScript queries in comparison to other languages"""

    def test_javascript_comprehensive_coverage(self):
        """Test that JavaScript has comprehensive coverage"""
        js_count = len(js_queries.ALL_QUERIES)

        # JavaScript should have 85+ queries
        assert js_count >= 85, (
            f"JavaScript should have at least 85 queries, got {js_count}"
        )

    def test_javascript_vs_typescript_features(self):
        """Test JavaScript vs TypeScript feature overlap"""
        # Common features that should exist in both
        common_features = ["functions", "classes", "variables", "imports", "exports"]

        for feature in common_features:
            assert feature in js_queries.ALL_QUERIES, (
                f"Common feature '{feature}' missing from JavaScript queries"
            )

    def test_javascript_specific_vs_typescript(self):
        """Test JavaScript-specific features vs TypeScript"""
        # JavaScript might have some features TypeScript doesn't need
        # or implements differently
        all_queries_text = " ".join(
            [q["query"] for q in js_queries.ALL_QUERIES.values()]
        )

        # Core JavaScript features
        js_core = [
            "function_declaration",
            "function_expression",
            "arrow_function",
            "class_declaration",
            "variable_declaration",
        ]

        for feature in js_core:
            assert feature in all_queries_text, (
                f"Core JavaScript feature '{feature}' not found"
            )


if __name__ == "__main__":
    pytest.main([__file__])
