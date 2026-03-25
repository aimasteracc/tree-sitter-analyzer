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
