#!/usr/bin/env python3
"""
Standardized and consolidated tests for QueryExecutor and QueryLoader.
Optimized to remove redundancy while maintaining functional coverage.
"""

from unittest.mock import MagicMock, patch

import pytest
from tree_sitter import Language, Tree

from tree_sitter_analyzer.core.query import (
    QueryExecutor,
    get_query_description,
)
from tree_sitter_analyzer.query_loader import QueryLoader
from tree_sitter_analyzer.utils.tree_sitter_compat import TreeSitterQueryCompat


@pytest.fixture
def mock_language():
    lang = MagicMock(spec=Language)
    lang.name = "python"
    return lang


@pytest.fixture
def mock_tree():
    tree = MagicMock(spec=Tree)
    tree.root_node = MagicMock()
    return tree


class TestQueryExecutor:
    """Tests for QueryExecutor functionality including stats and execution."""

    def test_executor_initialization(self):
        executor = QueryExecutor()
        assert executor._query_loader is not None
        assert executor._execution_stats["total_queries"] == 0

    def test_execute_query_validation(self):
        executor = QueryExecutor()
        # Test None inputs
        res1 = executor.execute_query(None, MagicMock(), "q", "code")
        assert res1["success"] is False
        assert "Tree is None" in res1["error"]

        res2 = executor.execute_query(MagicMock(), None, "q", "code")
        assert res2["success"] is False
        assert "Language is None" in res2["error"]

    @patch.object(QueryLoader, "get_query")
    def test_execute_query_missing_query(self, mock_get_query):
        mock_get_query.return_value = None
        executor = QueryExecutor()
        res = executor.execute_query(MagicMock(), MagicMock(), "nonexistent", "code")
        assert res["success"] is False
        assert "not found" in res["error"].lower()

    @patch.object(QueryLoader, "get_query")
    @patch.object(TreeSitterQueryCompat, "safe_execute_query")
    def test_execute_query_success(
        self, mock_safe_exec, mock_get_query, mock_tree, mock_language
    ):
        mock_get_query.return_value = "(node) @cap"
        mock_safe_exec.return_value = [(MagicMock(), "cap")]

        executor = QueryExecutor()
        res = executor.execute_query(mock_tree, mock_language, "test_q", "code")

        assert res["success"] is True
        assert res["query_name"] == "test_q"
        assert executor._execution_stats["successful_queries"] == 1

    def test_statistics_and_reset(self, mock_tree, mock_language):
        executor = QueryExecutor()
        with patch.object(TreeSitterQueryCompat, "safe_execute_query", return_value=[]):
            executor.execute_query(mock_tree, mock_language, "classes", "code")

        stats = executor.get_query_statistics()
        assert stats["total_queries"] == 1
        assert stats["success_rate"] == 1.0

        executor.reset_statistics()
        assert executor._execution_stats["total_queries"] == 0

    def test_normalize_language_name(self):
        executor = QueryExecutor()
        lang = MagicMock()
        lang.name = "Python"
        assert executor._normalize_language_name(lang) == "python"

        lang.name = None
        lang._name = "Java"
        assert executor._normalize_language_name(lang) == "java"


class TestQueryLoaderAndModuleFunctions:
    """Tests for QueryLoader pattern management and helper functions."""

    def test_get_builtin_queries(self):
        loader = QueryLoader()
        q = loader.get_query("python", "functions")
        assert q is not None
        assert "@function" in q

    @patch("tree_sitter_analyzer.query_loader.get_query_loader")
    def test_module_level_helpers(self, mock_get_loader):
        mock_loader = MagicMock()
        mock_loader.list_queries_for_language.return_value = ["q1", "q2"]
        mock_loader.get_query_description.return_value = "desc"
        mock_get_loader.return_value = mock_loader

        # Test directly against module level functions
        assert get_query_description("python", "q1") == "desc"
