"""
Shared fixtures for Query tests.

This module provides shared fixtures used across multiple query test files.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.core.query import QueryExecutor
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
    from tree_sitter_analyzer.core.query_filter import QueryFilter

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
        assert executor is not None
        assert hasattr(executor, '_execution_stats')
        assert executor._execution_stats["total_queries"] == 0
        assert executor._execution_stats["successful_queries"] == 0

    def test_query_executor_alias(self, query_executor):
        """Test that query_executor alias fixture works."""
        assert query_executor is not None

    def test_query_service_initialized(self, query_service):
        """Test that QueryService fixture initializes correctly."""
        assert query_service is not None
        assert query_service.parser is not None
        assert query_service.filter is not None

    def test_query_filter_initialized(self, query_filter):
        """Test that QueryFilter fixture initializes correctly."""
        assert query_filter is not None

    def test_query_filter_noop(self, query_filter):
        """Test QueryFilter.filter_results with no filter returns all results."""
        results = [{"name": "main", "type": "function"}]
        filtered = query_filter.filter_results(results, "")
        assert filtered == results

    def test_temp_project_dir(self, temp_project_dir):
        """Test that temp_project_dir fixture creates a valid path."""
        assert temp_project_dir is not None
        assert temp_project_dir.exists()

    def test_temp_file(self, temp_file):
        """Test that temp_file fixture creates a valid file."""
        assert temp_file is not None
        import os
        assert os.path.exists(temp_file)
