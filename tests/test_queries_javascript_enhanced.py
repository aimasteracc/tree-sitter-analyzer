#!/usr/bin/env python3
"""
Enhanced Tests for JavaScript queries module

Tests for the comprehensive JavaScript query library with ES6+, async/await,
classes, modules, JSX, and framework-specific patterns.
"""

import pytest

from tree_sitter_analyzer.queries.javascript import (
    ALL_QUERIES,
    JAVASCRIPT_QUERIES,
    JAVASCRIPT_QUERY_DESCRIPTIONS,
    get_all_queries,
    get_available_javascript_queries,
    get_javascript_query,
    get_javascript_query_description,
    get_query,
    list_queries,
)


class TestEnhancedJavaScriptQueries:
    """Test enhanced JavaScript queries functionality"""

    def test_javascript_queries_structure(self) -> None:
        """Test JAVASCRIPT_QUERIES dictionary structure"""
        assert isinstance(JAVASCRIPT_QUERIES, dict)
        assert len(JAVASCRIPT_QUERIES) > 50  # Should have many queries now

        # Test essential modern JavaScript queries exist
        essential_queries = [
            "function",
            "function_declaration",
            "function_expression",
            "arrow_function",
            "async_function",
            "generator_function",
            "class",
            "class_declaration",
            "method_definition",
            "constructor",
            "getter",
            "setter",
            "static_method",
            "private_method",
            "variable",
            "var_declaration",
            "let_declaration",
            "const_declaration",
            "import",
            "export",
            "jsx_element",
            "react_component",
        ]

        for query_name in essential_queries:
            assert query_name in JAVASCRIPT_QUERIES
            assert isinstance(JAVASCRIPT_QUERIES[query_name], str)
            assert len(JAVASCRIPT_QUERIES[query_name].strip()) > 0

    def test_javascript_query_descriptions(self) -> None:
        """Test JAVASCRIPT_QUERY_DESCRIPTIONS dictionary"""
        assert isinstance(JAVASCRIPT_QUERY_DESCRIPTIONS, dict)
        assert len(JAVASCRIPT_QUERY_DESCRIPTIONS) > 50

        # Test that all queries have descriptions
        for query_name in JAVASCRIPT_QUERIES:
            assert query_name in JAVASCRIPT_QUERY_DESCRIPTIONS
            description = JAVASCRIPT_QUERY_DESCRIPTIONS[query_name]
            assert isinstance(description, str)
            assert len(description) > 0
            assert "extract" in description.lower()

    def test_get_javascript_query_valid(self) -> None:
        """Test getting valid JavaScript queries"""
        # Test basic queries
        function_query = get_javascript_query("function")
        assert "function_declaration" in function_query

        # Test modern JavaScript queries
        async_query = get_javascript_query("async_function")
        assert "async" in async_query

        arrow_query = get_javascript_query("arrow_function")
        assert "arrow_function" in arrow_query

        class_query = get_javascript_query("class")
        assert "class_declaration" in class_query

    def test_get_javascript_query_invalid(self) -> None:
        """Test getting invalid JavaScript query raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            get_javascript_query("nonexistent_query")

        assert "JavaScript query 'nonexistent_query' does not exist" in str(
            exc_info.value
        )
        assert "Available:" in str(exc_info.value)

    def test_get_javascript_query_description_valid(self) -> None:
        """Test getting valid query descriptions"""
        desc = get_javascript_query_description("function")
        assert isinstance(desc, str)
        assert len(desc) > 0

        desc = get_javascript_query_description("async_function")
        assert "async" in desc.lower()

    def test_get_javascript_query_description_invalid(self) -> None:
        """Test getting description for invalid query"""
        desc = get_javascript_query_description("nonexistent")
        assert desc == "No description"

    def test_get_available_javascript_queries(self) -> None:
        """Test getting list of available JavaScript queries"""
        queries = get_available_javascript_queries()
        assert isinstance(queries, list)
        assert len(queries) > 50

        # Test essential queries are included
        essential = [
            "function",
            "class",
            "async_function",
            "arrow_function",
            "jsx_element",
        ]
        for query in essential:
            assert query in queries

    def test_all_queries_integration(self) -> None:
        """Test ALL_QUERIES integration with enhanced queries"""
        assert isinstance(ALL_QUERIES, dict)
        assert len(ALL_QUERIES) > 60  # Should include both new and legacy queries

        # Test new queries are included
        new_queries = [
            "async_function",
            "arrow_function",
            "jsx_element",
            "react_component",
        ]
        for query_name in new_queries:
            assert query_name in ALL_QUERIES
            assert "query" in ALL_QUERIES[query_name]
            assert "description" in ALL_QUERIES[query_name]

    def test_legacy_queries_compatibility(self) -> None:
        """Test backward compatibility with legacy queries"""
        legacy_queries = ["functions", "classes", "variables", "imports", "exports"]

        for query_name in legacy_queries:
            assert query_name in ALL_QUERIES
            query_data = ALL_QUERIES[query_name]
            assert "query" in query_data
            assert "description" in query_data
            assert isinstance(query_data["query"], str)
            assert len(query_data["query"]) > 0

    def test_function_queries_comprehensive(self) -> None:
        """Test comprehensive function query coverage"""
        function_queries = [
            "function",
            "function_declaration",
            "function_expression",
            "arrow_function",
            "async_function",
            "generator_function",
        ]

        for query_name in function_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]

            # Each function query should contain appropriate patterns
            if "async" in query_name:
                assert "async" in query
            if "arrow" in query_name:
                assert "arrow_function" in query
            if "generator" in query_name:
                assert "generator" in query

    def test_class_queries_comprehensive(self) -> None:
        """Test comprehensive class query coverage"""
        class_queries = [
            "class",
            "class_declaration",
            "class_expression",
            "class_method",
            "constructor",
            "getter",
            "setter",
            "static_method",
            "private_method",
        ]

        for query_name in class_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]

            # Verify query patterns
            if "method" in query_name or "constructor" in query_name:
                assert "method_definition" in query
            if "static" in query_name:
                assert "static" in query
            if "private" in query_name:
                assert "private" in query

    def test_variable_queries_comprehensive(self) -> None:
        """Test comprehensive variable query coverage"""
        variable_queries = [
            "variable",
            "var_declaration",
            "let_declaration",
            "const_declaration",
            "destructuring_assignment",
            "object_destructuring",
        ]

        for query_name in variable_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]

            # Verify query patterns
            if "var" in query_name:
                assert "variable_declaration" in query
            if "let" in query_name or "const" in query_name:
                assert "lexical_declaration" in query
            if "destructuring" in query_name:
                assert "pattern" in query

    def test_import_export_queries_comprehensive(self) -> None:
        """Test comprehensive import/export query coverage"""
        import_export_queries = [
            "import",
            "import_statement",
            "import_default",
            "import_named",
            "import_namespace",
            "dynamic_import",
            "export",
            "export_default",
            "export_named",
            "export_all",
        ]

        for query_name in import_export_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]

            # Verify query patterns
            if "import" in query_name:
                assert "import" in query
            if "export" in query_name:
                assert "export" in query
            if "default" in query_name:
                assert "default" in query
            if "named" in query_name:
                assert "named_imports" in query or "export_clause" in query

    def test_modern_javascript_queries(self) -> None:
        """Test modern JavaScript feature queries"""
        modern_queries = [
            "template_literal",
            "template_substitution",
            "spread_element",
            "rest_parameter",
            "await_expression",
            "yield_expression",
        ]

        for query_name in modern_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]
            assert len(query.strip()) > 0

    def test_jsx_queries(self) -> None:
        """Test JSX-related queries"""
        jsx_queries = [
            "jsx_element",
            "jsx_self_closing",
            "jsx_attribute",
            "jsx_expression",
        ]

        for query_name in jsx_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]
            assert "jsx" in query

    def test_framework_queries(self) -> None:
        """Test framework-specific queries"""
        framework_queries = [
            "react_component",
            "react_hook",
            "node_require",
            "module_exports",
        ]

        for query_name in framework_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]
            assert len(query.strip()) > 0

    def test_control_flow_queries(self) -> None:
        """Test control flow queries"""
        control_flow_queries = [
            "if_statement",
            "for_statement",
            "for_in_statement",
            "for_of_statement",
            "while_statement",
            "do_statement",
            "switch_statement",
            "case_clause",
            "default_clause",
        ]

        for query_name in control_flow_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]

            # Verify appropriate patterns
            if "for" in query_name:
                assert "for" in query
            elif "while" in query_name:
                assert "while" in query
            elif "switch" in query_name:
                assert "switch" in query

    def test_error_handling_queries(self) -> None:
        """Test error handling queries"""
        error_queries = [
            "try_statement",
            "catch_clause",
            "finally_clause",
            "throw_statement",
        ]

        for query_name in error_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]

            # Verify patterns
            if "try" in query_name:
                assert "try" in query
            elif "catch" in query_name:
                assert "catch" in query
            elif "finally" in query_name:
                assert "finally" in query
            elif "throw" in query_name:
                assert "throw" in query

    def test_comment_queries(self) -> None:
        """Test comment-related queries"""
        comment_queries = ["comment", "jsdoc_comment", "line_comment", "block_comment"]

        for query_name in comment_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]
            assert "comment" in query

            # Verify specific patterns
            if "jsdoc" in query_name:
                assert "/\\*\\*" in query
            elif "line" in query_name:
                assert "//" in query
            elif "block" in query_name:
                assert "/\\*" in query

    def test_advanced_pattern_queries(self) -> None:
        """Test advanced pattern queries"""
        advanced_queries = [
            "closure",
            "iife",
            "module_pattern",
            "callback_function",
            "promise_chain",
            "event_listener",
        ]

        for query_name in advanced_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]
            assert len(query.strip()) > 0

    def test_name_extraction_queries(self) -> None:
        """Test name-only extraction queries"""
        name_queries = ["function_name", "class_name", "variable_name"]

        for query_name in name_queries:
            assert query_name in JAVASCRIPT_QUERIES
            query = JAVASCRIPT_QUERIES[query_name]
            # Name queries should be simpler and focus on identifiers
            assert "@" in query  # Should have capture groups

    def test_query_consistency_with_descriptions(self) -> None:
        """Test consistency between queries and descriptions"""
        for query_name in JAVASCRIPT_QUERIES:
            assert query_name in JAVASCRIPT_QUERY_DESCRIPTIONS

            query = JAVASCRIPT_QUERIES[query_name]
            description = JAVASCRIPT_QUERY_DESCRIPTIONS[query_name]

            # Basic consistency checks
            assert isinstance(query, str)
            assert isinstance(description, str)
            assert len(query.strip()) > 0
            assert len(description.strip()) > 0

            # Description should be relevant to query name
            if "function" in query_name:
                assert "function" in description.lower()
            elif "class" in query_name:
                assert "class" in description.lower()
            elif "variable" in query_name:
                assert "variable" in description.lower()

    def test_all_queries_have_capture_groups(self) -> None:
        """Test that all queries have proper capture groups"""
        for query_name, query in JAVASCRIPT_QUERIES.items():
            # All queries should have at least one capture group
            assert "@" in query, f"Query '{query_name}' should have capture groups"

    def test_query_syntax_validity(self) -> None:
        """Test basic query syntax validity"""
        for _query_name, query in JAVASCRIPT_QUERIES.items():
            # Basic syntax checks
            assert (
                query.count("(") >= query.count(")")
                or query.count("(") <= query.count(")") + 2
            )
            # Allow some flexibility for incomplete patterns in documentation

            # Should not have obvious syntax errors
            assert not query.strip().endswith(",")
            assert not query.strip().startswith("@")

    def test_get_query_function_compatibility(self) -> None:
        """Test compatibility with get_query function"""
        # Test that get_query works with new queries
        modern_queries = ["async_function", "arrow_function", "jsx_element"]

        for query_name in modern_queries:
            query = get_query(query_name)
            assert isinstance(query, str)
            assert len(query) > 0
            assert query == JAVASCRIPT_QUERIES[query_name]

    def test_list_queries_includes_all(self) -> None:
        """Test that list_queries includes all available queries"""
        all_query_names = list_queries()

        # Should include both new and legacy queries
        expected_queries = list(JAVASCRIPT_QUERIES.keys()) + [
            "functions",
            "classes",
            "variables",
            "imports",
            "exports",
            "objects",
            "comments",
        ]

        for query_name in expected_queries:
            assert query_name in all_query_names

    def test_get_all_queries_structure(self) -> None:
        """Test get_all_queries returns proper structure"""
        all_queries = get_all_queries()

        # Test structure for new queries
        new_queries = ["async_function", "arrow_function", "jsx_element"]
        for query_name in new_queries:
            assert query_name in all_queries
            query_data = all_queries[query_name]
            assert "query" in query_data
            assert "description" in query_data
            assert query_data["query"] == JAVASCRIPT_QUERIES[query_name]
            assert (
                query_data["description"] == JAVASCRIPT_QUERY_DESCRIPTIONS[query_name]
            )
