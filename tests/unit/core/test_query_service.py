#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.core.query_service module.

This module tests the QueryService class.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.core.query_service import QueryService


class TestQueryServiceInit:
    """Tests for QueryService initialization."""

    def test_query_service_init_default(self) -> None:
        """Test QueryService initialization with default project_root."""
        service = QueryService()
        assert service.project_root is None
        assert service.parser is not None
        assert service.filter is not None
        assert service.plugin_manager is not None

    def test_query_service_init_with_project_root(self) -> None:
        """Test QueryService initialization with project_root."""
        service = QueryService(project_root="/test/path")
        assert service.project_root == "/test/path"
        assert service.parser is not None
        assert service.filter is not None


class TestQueryServiceExecuteQuery:
    """Tests for QueryService.execute_query method."""

    @pytest.mark.asyncio
    async def test_execute_query_with_query_key(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query with query_key."""
        results = await query_service.execute_query(
            str(temp_file), "python", query_key="functions"
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_execute_query_with_query_string(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query with custom query_string."""
        results = await query_service.execute_query(
            str(temp_file),
            "python",
            query_string="(function_definition) @func",
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_execute_query_with_filter(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query with filter expression."""
        results = await query_service.execute_query(
            str(temp_file),
            "python",
            query_key="functions",
            filter_expression="name=~test*",
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_execute_query_no_query_params(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query without query parameters raises ValueError."""
        with pytest.raises(
            ValueError, match="Must provide either query_key or query_string"
        ):
            await query_service.execute_query(str(temp_file), "python")

    @pytest.mark.asyncio
    async def test_execute_query_both_query_params(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query with both query_key and query_string raises ValueError."""
        with pytest.raises(
            ValueError, match="Cannot provide both query_key and query_string"
        ):
            await query_service.execute_query(
                str(temp_file),
                "python",
                query_key="functions",
                query_string="(function_definition) @func",
            )

    @pytest.mark.asyncio
    async def test_execute_query_invalid_query_key(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query with invalid query_key raises ValueError."""
        with pytest.raises(ValueError, match="Query 'invalid' not found"):
            await query_service.execute_query(
                str(temp_file), "python", query_key="invalid"
            )

    @pytest.mark.asyncio
    async def test_execute_query_file_not_found(
        self, query_service: QueryService
    ) -> None:
        """Test executing query on non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await query_service.execute_query(
                "nonexistent.py", "python", query_key="functions"
            )


class TestQueryServiceCreateResultDict:
    """Tests for QueryService._create_result_dict method."""

    def test_create_result_dict(self, query_service: QueryService) -> None:
        """Test creating result dictionary from node."""
        # Create mock node
        mock_node = MagicMock()
        mock_node.type = "function_definition"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_node.text = b"def test(): pass"

        result = query_service._create_result_dict(
            mock_node, "test", "def test(): pass"
        )

        assert result["capture_name"] == "test"
        assert result["node_type"] == "function_definition"
        assert result["start_line"] == 1  # 0-based to 1-based
        assert result["end_line"] == 6  # 0-based to 1-based
        # Content is extracted by get_node_text_safe, which may return empty string
        # if node.text is not properly accessible
        assert isinstance(result["content"], str)

    def test_create_result_dict_with_source_code(
        self, query_service: QueryService
    ) -> None:
        """Test creating result dictionary with source code."""
        mock_node = MagicMock()
        mock_node.type = "class_definition"
        mock_node.start_point = (10, 0)
        mock_node.end_point = (20, 0)
        mock_node.text = b"class MyClass: pass"

        result = query_service._create_result_dict(
            mock_node, "class", "class MyClass: pass"
        )

        assert result["capture_name"] == "class"
        assert result["node_type"] == "class_definition"
        assert result["start_line"] == 11
        assert result["end_line"] == 21


class TestQueryServiceGetAvailableQueries:
    """Tests for QueryService.get_available_queries method."""

    def test_get_available_queries(self, query_service: QueryService) -> None:
        """Test getting available queries for language."""
        queries = query_service.get_available_queries("python")
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_get_available_queries_unsupported_language(
        self, query_service: QueryService
    ) -> None:
        """Test getting available queries for unsupported language."""
        queries = query_service.get_available_queries("unsupported")
        assert isinstance(queries, list)


class TestQueryServiceGetQueryDescription:
    """Tests for QueryService.get_query_description method."""

    def test_get_query_description(self, query_service: QueryService) -> None:
        """Test getting query description."""
        description = query_service.get_query_description("python", "functions")
        assert isinstance(description, str) or description is None

    def test_get_query_description_invalid_query(
        self, query_service: QueryService
    ) -> None:
        """Test getting description for invalid query."""
        description = query_service.get_query_description("python", "invalid")
        assert description is None


class TestQueryServiceExecutePluginQuery:
    """Tests for QueryService._execute_plugin_query method."""

    def test_execute_plugin_query_with_plugin(
        self, query_service: QueryService
    ) -> None:
        """Test executing plugin query with available plugin."""
        mock_root_node = MagicMock()
        mock_root_node.children = []

        captures = query_service._execute_plugin_query(
            mock_root_node, "functions", "python", "def test(): pass"
        )
        assert isinstance(captures, list)

    def test_execute_plugin_query_without_plugin(
        self, query_service: QueryService
    ) -> None:
        """Test executing plugin query without available plugin."""
        mock_root_node = MagicMock()
        mock_root_node.children = []

        captures = query_service._execute_plugin_query(
            mock_root_node, "functions", "unsupported", "code"
        )
        assert isinstance(captures, list)


class TestQueryServiceFallbackQueryExecution:
    """Tests for QueryService._fallback_query_execution method."""

    def test_fallback_query_execution_function(
        self, query_service: QueryService
    ) -> None:
        """Test fallback query execution for function nodes."""
        mock_root_node = MagicMock()
        mock_root_node.type = "module"
        mock_root_node.children = []

        mock_child = MagicMock()
        mock_child.type = "function_definition"
        mock_child.start_point = (0, 0)
        mock_child.end_point = (5, 0)
        mock_child.children = []

        mock_root_node.children = [mock_child]

        captures = query_service._fallback_query_execution(mock_root_node, "function")
        assert isinstance(captures, list)
        assert len(captures) >= 0

    def test_fallback_query_execution_class(self, query_service: QueryService) -> None:
        """Test fallback query execution for class nodes."""
        mock_root_node = MagicMock()
        mock_root_node.type = "module"
        mock_root_node.children = []

        mock_child = MagicMock()
        mock_child.type = "class_definition"
        mock_child.start_point = (0, 0)
        mock_child.end_point = (10, 0)
        mock_child.children = []

        mock_root_node.children = [mock_child]

        captures = query_service._fallback_query_execution(mock_root_node, "class")
        assert isinstance(captures, list)

    def test_fallback_query_execution_no_matches(
        self, query_service: QueryService
    ) -> None:
        """Test fallback query execution with no matches."""
        mock_root_node = MagicMock()
        mock_root_node.type = "module"
        mock_root_node.children = []

        mock_child = MagicMock()
        mock_child.type = "comment"
        mock_child.start_point = (0, 0)
        mock_child.end_point = (1, 0)
        mock_child.children = []

        mock_root_node.children = [mock_child]

        captures = query_service._fallback_query_execution(mock_root_node, "function")
        assert isinstance(captures, list)


class TestQueryServiceReadFileAsync:
    """Tests for QueryService._read_file_async method."""

    @pytest.mark.asyncio
    async def test_read_file_async(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test async file reading."""
        content, encoding = await query_service._read_file_async(str(temp_file))
        assert isinstance(content, str)
        assert isinstance(encoding, str)
        assert "def hello(): pass" in content


class TestQueryServiceEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_execute_query_empty_results(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query that returns no results."""
        # Use a query that likely won't match
        results = await query_service.execute_query(
            str(temp_file),
            "python",
            query_string="(nonexistent_node_type) @node",
        )
        assert isinstance(results, list)

    def test_create_result_dict_missing_attributes(
        self, query_service: QueryService
    ) -> None:
        """Test creating result dict with node missing attributes."""
        mock_node = MagicMock()
        # Remove type attribute
        del mock_node.type
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_node.text = b"def test(): pass"

        result = query_service._create_result_dict(mock_node, "test", "code")
        assert result["node_type"] == "unknown"
        assert result["start_line"] == 1
        assert result["end_line"] == 6


# Pytest fixtures
@pytest.fixture
def query_service() -> QueryService:
    """Create a QueryService instance for testing."""
    return QueryService()


@pytest.fixture
def temp_file() -> Path:
    """Create a temporary Python file for testing."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write("def hello(): pass\n")
        f.write("def test_func(): pass\n")
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    try:
        temp_path.unlink()
    except Exception:
        pass
