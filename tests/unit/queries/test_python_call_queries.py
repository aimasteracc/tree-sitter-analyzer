#!/usr/bin/env python3
"""Tests for Python call expression queries (Code Intelligence Graph)."""


class TestPythonCallExpressionQuery:
    """Test call_expression query for extracting function/method calls."""

    def test_simple_function_call(self):
        """CGE-001: Simple function call like print('hello')."""
        from tree_sitter_analyzer.queries.python import PYTHON_QUERIES

        assert "call_expression" in PYTHON_QUERIES
        query = PYTHON_QUERIES["call_expression"]
        assert "callee_name" in query
        assert "@call" in query

    def test_call_query_in_all_queries(self):
        """call_expression should be registered in ALL_QUERIES."""
        from tree_sitter_analyzer.queries.python import ALL_QUERIES

        assert "call_expression" in ALL_QUERIES
        assert "calls" in ALL_QUERIES

    def test_calls_query_exists(self):
        """Simplified calls query should exist."""
        from tree_sitter_analyzer.queries.python import PYTHON_QUERIES

        assert "calls" in PYTHON_QUERIES
        query = PYTHON_QUERIES["calls"]
        assert "@callee" in query
        assert "@call" in query

    def test_call_expression_query_syntax(self):
        """Query should be valid tree-sitter syntax."""
        from tree_sitter_analyzer.queries.python import PYTHON_QUERIES

        query = PYTHON_QUERIES["call_expression"]
        # Should contain call node type
        assert "(call" in query
        # Should capture function name
        assert "(identifier) @callee_name" in query

    def test_method_call_captures(self):
        """CGE-002: Method calls should capture object and method name."""
        from tree_sitter_analyzer.queries.python import PYTHON_QUERIES

        query = PYTHON_QUERIES["call_expression"]
        assert "@callee_object" in query
        assert "@callee_method" in query

    def test_call_expression_descriptions(self):
        """Queries should have descriptions."""
        from tree_sitter_analyzer.queries.python import PYTHON_QUERY_DESCRIPTIONS

        assert "call_expression" in PYTHON_QUERY_DESCRIPTIONS
        assert "calls" in PYTHON_QUERY_DESCRIPTIONS

    def test_get_python_query_call_expression(self):
        """get_python_query should return call_expression."""
        from tree_sitter_analyzer.queries.python import get_python_query

        query = get_python_query("call_expression")
        assert query is not None
        assert len(query) > 0

    def test_call_queries_in_available_list(self):
        """Call queries should appear in available queries list."""
        from tree_sitter_analyzer.queries.python import get_available_python_queries

        available = get_available_python_queries()
        assert "call_expression" in available
        assert "calls" in available
