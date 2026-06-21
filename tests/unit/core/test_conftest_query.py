"""
Shared fixtures for Query tests.

This module provides shared fixtures used across multiple query test files.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.core.parser import Parser
from tree_sitter_analyzer.core.query import QueryExecutor
from tree_sitter_analyzer.core.query_filter import QueryFilter
from tree_sitter_analyzer.core.query_service import QueryService


@pytest.fixture
def executor():
    """Create a QueryExecutor instance."""
    return QueryExecutor()


@pytest.fixture
def query_executor():
    """Create a QueryExecutor instance (alias)."""
    return QueryExecutor()


@pytest.fixture
def mock_tree():
    """Create a mock Tree-sitter tree."""
    tree = MagicMock()
    tree.root_node = MagicMock()
    return tree


@pytest.fixture
def mock_language():
    """Create a mock Language object."""
    lang = MagicMock()
    lang.name = "python"
    return lang


@pytest.fixture
def query_service():
    """Create a QueryService instance."""
    return QueryService()


@pytest.fixture
def query_filter():
    """Create a QueryFilter instance."""
    return QueryFilter()


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def temp_file():
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def test_function(): pass\n")
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


class TestQueryFixtures:
    """Tests for query fixture functionality."""

    def test_executor_initialized(self, executor):
        """Test that QueryExecutor fixture initializes correctly."""
        assert isinstance(executor, QueryExecutor)
        assert callable(executor.execute_query)
        assert callable(executor.execute_query_string)
        assert executor.execution_stats == {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "total_execution_time": 0.0,
        }

    def test_query_executor_alias(self, query_executor):
        """Test that query_executor alias fixture works."""
        assert isinstance(query_executor, QueryExecutor)
        assert callable(query_executor.execute_multiple_queries)
        assert query_executor.execution_stats == {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "total_execution_time": 0.0,
        }

    def test_query_service_initialized(self, query_service):
        """Test that QueryService fixture initializes correctly."""
        assert isinstance(query_service, QueryService)
        assert query_service.project_root is None
        assert isinstance(query_service.parser, Parser)
        assert isinstance(query_service.filter, QueryFilter)
        assert callable(query_service.execute_query)
        assert callable(query_service.get_available_queries)

    def test_query_filter_initialized(self, query_filter):
        """Test that QueryFilter fixture initializes correctly."""
        assert isinstance(query_filter, QueryFilter)
        assert callable(query_filter.filter_results)
        assert callable(query_filter.get_filter_help)

    def test_query_filter_noop(self, query_filter):
        """Test QueryFilter.filter_results with no filter returns all results."""
        results = [{"name": "main", "type": "function"}]
        filtered = query_filter.filter_results(results, "")
        assert filtered == results

    def test_temp_project_dir(self, temp_project_dir):
        """Test that temp_project_dir fixture creates a valid path."""
        assert isinstance(temp_project_dir, Path)
        assert temp_project_dir.exists()
        assert temp_project_dir.is_dir()

    def test_temp_file(self, temp_file):
        """Test that temp_file fixture creates a valid file."""
        assert isinstance(temp_file, str)
        temp_path = Path(temp_file)
        assert temp_path.exists()
        assert temp_path.is_file()
        assert temp_path.read_text() == "def test_function(): pass\n"
