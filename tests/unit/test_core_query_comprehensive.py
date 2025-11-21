#!/usr/bin/env python3
"""
Comprehensive tests for tree_sitter_analyzer.core.query module.

This module provides comprehensive test coverage for the QueryExecutor class
and related query functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.core.query import (
    QueryExecutor,
    get_all_queries_for_language,
    get_available_queries,
    get_query_description,
)


class TestQueryExecutorInitialization:
    """Test QueryExecutor initialization."""

    def test_init_success(self):
        """Test successful initialization."""
        executor = QueryExecutor()
        assert executor is not None
        assert executor._execution_stats["total_queries"] == 0
        assert executor._execution_stats["successful_queries"] == 0
        assert executor._execution_stats["failed_queries"] == 0
        assert executor._execution_stats["total_execution_time"] == 0.0

    def test_init_sets_query_loader(self):
        """Test that initialization sets the query loader."""
        executor = QueryExecutor()
        assert executor._query_loader is not None


class TestExecuteQuery:
    """Test execute_query method."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    @pytest.fixture
    def mock_tree(self):
        """Create a mock Tree-sitter tree."""
        tree = MagicMock()
        tree.root_node = MagicMock()
        return tree

    @pytest.fixture
    def mock_language(self):
        """Create a mock Language object."""
        lang = MagicMock()
        lang.name = "python"
        return lang

    def test_execute_query_with_none_tree(self, executor):
        """Test execute_query with None tree."""
        result = executor.execute_query(None, MagicMock(), "test_query", "code")
        assert result["success"] is False
        assert "Tree is None" in result["error"]
        assert result["captures"] == []

    def test_execute_query_with_none_language(self, executor, mock_tree):
        """Test execute_query with None language."""
        result = executor.execute_query(mock_tree, None, "test_query", "code")
        assert result["success"] is False
        assert "Language is None" in result["error"]
        assert result["captures"] == []

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query")
    def test_execute_query_success(
        self, mock_safe_execute, executor, mock_tree, mock_language
    ):
        """Test successful query execution."""
        # Setup
        mock_node = MagicMock()
        mock_node.type = "function_definition"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 50
        mock_safe_execute.return_value = [(mock_node, "function")]

        with patch.object(
            executor._query_loader,
            "get_query",
            return_value="(function_definition) @function",
        ):
            result = executor.execute_query(
                mock_tree, mock_language, "functions", "def foo(): pass"
            )

        assert result["success"] is True
        assert "captures" in result
        assert len(result["captures"]) == 1
        assert result["query_name"] == "functions"
        assert "execution_time" in result

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query")
    def test_execute_query_with_language_name_extraction(
        self, mock_safe_execute, executor, mock_tree
    ):
        """Test query execution with language name extraction."""
        # Language without name attribute
        lang = MagicMock(spec=[])
        lang.__class__.__name__ = "Python"
        mock_safe_execute.return_value = []

        with patch.object(executor._query_loader, "get_query", return_value="test"):
            result = executor.execute_query(mock_tree, lang, "test", "code")

        assert result["success"] is True

    def test_execute_query_with_query_not_found(
        self, executor, mock_tree, mock_language
    ):
        """Test execute_query when query is not found."""
        with patch.object(executor._query_loader, "get_query", return_value=None):
            result = executor.execute_query(
                mock_tree, mock_language, "nonexistent", "code"
            )

        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query")
    def test_execute_query_with_execution_error(
        self, mock_safe_execute, executor, mock_tree, mock_language
    ):
        """Test execute_query with query execution error."""
        mock_safe_execute.side_effect = Exception("Query error")

        with patch.object(executor._query_loader, "get_query", return_value="test"):
            result = executor.execute_query(mock_tree, mock_language, "test", "code")

        assert result["success"] is False
        assert "Query execution failed" in result["error"]

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query")
    def test_execute_query_with_capture_processing_error(
        self, mock_safe_execute, executor, mock_tree, mock_language
    ):
        """Test execute_query with capture processing error."""
        # Return invalid captures that will cause processing error
        mock_safe_execute.return_value = [("invalid", "data", "format")]

        with patch.object(executor._query_loader, "get_query", return_value="test"):
            with patch.object(
                executor, "_process_captures", side_effect=Exception("Processing error")
            ):
                result = executor.execute_query(
                    mock_tree, mock_language, "test", "code"
                )

        assert result["success"] is False
        assert "Capture processing failed" in result["error"]

    def test_execute_query_updates_stats(self, executor, mock_tree, mock_language):
        """Test that execute_query updates statistics."""
        initial_total = executor._execution_stats["total_queries"]

        with patch.object(executor._query_loader, "get_query", return_value=None):
            executor.execute_query(mock_tree, mock_language, "test", "code")

        assert executor._execution_stats["total_queries"] == initial_total + 1


class TestExecuteQueryWithLanguageName:
    """Test execute_query_with_language_name method."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    @pytest.fixture
    def mock_tree(self):
        """Create a mock Tree-sitter tree."""
        tree = MagicMock()
        tree.root_node = MagicMock()
        return tree

    @pytest.fixture
    def mock_language(self):
        """Create a mock Language object."""
        return MagicMock()

    def test_execute_with_explicit_language_name(
        self, executor, mock_tree, mock_language
    ):
        """Test query execution with explicit language name."""
        with patch.object(
            executor._query_loader, "get_query", return_value="test"
        ) as mock_get_query:
            with patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                return_value=[],
            ):
                result = executor.execute_query_with_language_name(
                    mock_tree, mock_language, "test", "code", "python"
                )

        mock_get_query.assert_called_once_with("python", "test")
        assert result["success"] is True

    def test_execute_with_language_name_normalization(
        self, executor, mock_tree, mock_language
    ):
        """Test that language name is normalized."""
        with patch.object(
            executor._query_loader, "get_query", return_value="test"
        ) as mock_get_query:
            with patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                return_value=[],
            ):
                executor.execute_query_with_language_name(
                    mock_tree, mock_language, "test", "code", "  PYTHON  "
                )

        mock_get_query.assert_called_once_with("python", "test")

    def test_execute_with_none_tree(self, executor, mock_language):
        """Test with None tree."""
        result = executor.execute_query_with_language_name(
            None, mock_language, "test", "code", "python"
        )
        assert result["success"] is False
        assert "Tree is None" in result["error"]

    def test_execute_with_none_language(self, executor, mock_tree):
        """Test with None language."""
        result = executor.execute_query_with_language_name(
            mock_tree, None, "test", "code", "python"
        )
        assert result["success"] is False
        assert "Language is None" in result["error"]


class TestExecuteQueryString:
    """Test execute_query_string method."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    @pytest.fixture
    def mock_tree(self):
        """Create a mock Tree-sitter tree."""
        tree = MagicMock()
        tree.root_node = MagicMock()
        return tree

    @pytest.fixture
    def mock_language(self):
        """Create a mock Language object."""
        return MagicMock()

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query")
    def test_execute_query_string_success(
        self, mock_safe_execute, executor, mock_tree, mock_language
    ):
        """Test successful query string execution."""
        mock_safe_execute.return_value = []
        query_string = "(function_definition) @func"

        result = executor.execute_query_string(
            mock_tree, mock_language, query_string, "code"
        )

        assert result["success"] is True
        assert result["query_string"] == query_string
        assert "execution_time" in result

    def test_execute_query_string_with_none_tree(self, executor, mock_language):
        """Test execute_query_string with None tree."""
        result = executor.execute_query_string(None, mock_language, "test", "code")
        assert result["success"] is False
        assert "Tree is None" in result["error"]

    def test_execute_query_string_with_none_language(self, executor, mock_tree):
        """Test execute_query_string with None language."""
        result = executor.execute_query_string(mock_tree, None, "test", "code")
        assert result["success"] is False
        assert "Language is None" in result["error"]

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query")
    def test_execute_query_string_with_error(
        self, mock_safe_execute, executor, mock_tree, mock_language
    ):
        """Test execute_query_string with execution error."""
        mock_safe_execute.side_effect = Exception("Execution error")

        result = executor.execute_query_string(mock_tree, mock_language, "test", "code")

        assert result["success"] is False
        assert "Query execution failed" in result["error"]


class TestExecuteMultipleQueries:
    """Test execute_multiple_queries method."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    @pytest.fixture
    def mock_tree(self):
        """Create a mock Tree-sitter tree."""
        tree = MagicMock()
        tree.root_node = MagicMock()
        return tree

    @pytest.fixture
    def mock_language(self):
        """Create a mock Language object."""
        return MagicMock()

    def test_execute_multiple_queries(self, executor, mock_tree, mock_language):
        """Test executing multiple queries."""
        with patch.object(executor, "execute_query") as mock_execute:
            mock_execute.return_value = {"success": True, "captures": []}
            query_names = ["query1", "query2", "query3"]

            results = executor.execute_multiple_queries(
                mock_tree, mock_language, query_names, "code"
            )

        assert len(results) == 3
        assert all(name in results for name in query_names)
        assert mock_execute.call_count == 3

    def test_execute_multiple_queries_empty_list(
        self, executor, mock_tree, mock_language
    ):
        """Test executing multiple queries with empty list."""
        results = executor.execute_multiple_queries(
            mock_tree, mock_language, [], "code"
        )
        assert results == {}


class TestProcessCaptures:
    """Test _process_captures method."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    def test_process_captures_tuple_format(self, executor):
        """Test processing captures in tuple format (modern API)."""
        mock_node = MagicMock()
        mock_node.type = "function"
        mock_node.start_point = (1, 0)
        mock_node.end_point = (5, 0)
        mock_node.start_byte = 10
        mock_node.end_byte = 50

        captures = [(mock_node, "func")]

        with patch(
            "tree_sitter_analyzer.core.query.get_node_text_safe",
            return_value="def foo()",
        ):
            result = executor._process_captures(captures, "source")

        assert len(result) == 1
        assert result[0]["capture_name"] == "func"
        assert result[0]["node_type"] == "function"

    def test_process_captures_dict_format(self, executor):
        """Test processing captures in dict format (legacy API)."""
        mock_node = MagicMock()
        mock_node.type = "class"
        mock_node.start_point = (1, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 5
        mock_node.end_byte = 100

        captures = [{"node": mock_node, "name": "class_def"}]

        with patch(
            "tree_sitter_analyzer.core.query.get_node_text_safe",
            return_value="class Foo",
        ):
            result = executor._process_captures(captures, "source")

        assert len(result) == 1
        assert result[0]["capture_name"] == "class_def"
        assert result[0]["node_type"] == "class"

    def test_process_captures_invalid_format(self, executor):
        """Test processing captures with invalid format."""
        captures = ["invalid", 123, None]
        result = executor._process_captures(captures, "source")
        assert result == []

    def test_process_captures_with_none_node(self, executor):
        """Test processing captures with None node."""
        captures = [(None, "test")]
        result = executor._process_captures(captures, "source")
        assert result == []

    def test_process_captures_with_error(self, executor):
        """Test processing captures when error occurs."""
        mock_node = MagicMock()
        mock_node.type = "test"
        captures = [(mock_node, "test")]

        with patch(
            "tree_sitter_analyzer.core.query.get_node_text_safe",
            side_effect=Exception("Error"),
        ):
            result = executor._process_captures(captures, "source")

        # Should still return results, but may have error info
        assert isinstance(result, list)


class TestCreateResultDict:
    """Test _create_result_dict method."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    def test_create_result_dict_success(self, executor):
        """Test creating result dict successfully."""
        mock_node = MagicMock()
        mock_node.type = "function"
        mock_node.start_point = (5, 4)
        mock_node.end_point = (10, 8)
        mock_node.start_byte = 100
        mock_node.end_byte = 200

        with patch(
            "tree_sitter_analyzer.core.query.get_node_text_safe",
            return_value="def test()",
        ):
            result = executor._create_result_dict(mock_node, "func", "source code")

        assert result["capture_name"] == "func"
        assert result["node_type"] == "function"
        assert result["start_point"] == (5, 4)
        assert result["end_point"] == (10, 8)
        assert result["start_byte"] == 100
        assert result["end_byte"] == 200
        assert result["text"] == "def test()"
        assert result["line_number"] == 6  # 0-indexed + 1
        assert result["column_number"] == 4

    def test_create_result_dict_with_error(self, executor):
        """Test creating result dict when error occurs."""
        mock_node = MagicMock()
        mock_node.type = "test"

        with patch(
            "tree_sitter_analyzer.core.query.get_node_text_safe",
            side_effect=Exception("Error"),
        ):
            result = executor._create_result_dict(mock_node, "test", "source")

        assert result["capture_name"] == "test"
        assert result["node_type"] == "error"
        assert "error" in result


class TestCreateErrorResult:
    """Test _create_error_result method."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    def test_create_error_result_basic(self, executor):
        """Test creating basic error result."""
        result = executor._create_error_result("Test error")
        assert result["success"] is False
        assert result["error"] == "Test error"
        assert result["captures"] == []

    def test_create_error_result_with_query_name(self, executor):
        """Test creating error result with query name."""
        result = executor._create_error_result("Test error", query_name="test_query")
        assert result["query_name"] == "test_query"
        assert result["error"] == "Test error"

    def test_create_error_result_with_additional_fields(self, executor):
        """Test creating error result with additional fields."""
        result = executor._create_error_result(
            "Test error", query_name="test", custom_field="value", another_field=123
        )
        assert result["custom_field"] == "value"
        assert result["another_field"] == 123


class TestGetAvailableQueries:
    """Test get_available_queries method."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    def test_get_available_queries_dict_response(self, executor):
        """Test get_available_queries with dict response."""
        mock_queries = {"query1": "...", "query2": "...", "query3": "..."}

        with patch.object(
            executor._query_loader,
            "get_all_queries_for_language",
            return_value=mock_queries,
        ):
            result = executor.get_available_queries("python")

        assert set(result) == {"query1", "query2", "query3"}

    def test_get_available_queries_list_response(self, executor):
        """Test get_available_queries with list response."""
        mock_queries = ["query1", "query2", "query3"]

        with patch.object(
            executor._query_loader,
            "get_all_queries_for_language",
            return_value=mock_queries,
        ):
            result = executor.get_available_queries("python")

        assert result == mock_queries

    def test_get_available_queries_with_error(self, executor):
        """Test get_available_queries when error occurs."""
        with patch.object(
            executor._query_loader,
            "get_all_queries_for_language",
            side_effect=Exception("Error"),
        ):
            result = executor.get_available_queries("python")

        assert result == []

    def test_get_available_queries_none_response(self, executor):
        """Test get_available_queries with None response."""
        with patch.object(
            executor._query_loader, "get_all_queries_for_language", return_value=None
        ):
            result = executor.get_available_queries("python")

        assert result == []


class TestGetQueryDescription:
    """Test get_query_description method."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    def test_get_query_description_success(self, executor):
        """Test getting query description successfully."""
        expected_desc = "Test description"

        with patch.object(
            executor._query_loader, "get_query_description", return_value=expected_desc
        ):
            result = executor.get_query_description("python", "test_query")

        assert result == expected_desc

    def test_get_query_description_with_error(self, executor):
        """Test get_query_description when error occurs."""
        with patch.object(
            executor._query_loader,
            "get_query_description",
            side_effect=Exception("Error"),
        ):
            result = executor.get_query_description("python", "test_query")

        assert result is None


class TestValidateQuery:
    """Test validate_query method."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    def test_validate_query_success(self, executor):
        """Test successful query validation."""
        # The validate_query method imports get_loader locally
        # We need to patch language_loader.get_loader
        with patch(
            "tree_sitter_analyzer.language_loader.get_loader"
        ) as mock_get_loader:
            mock_loader = MagicMock()
            mock_language = MagicMock()
            mock_language.query = MagicMock(return_value=MagicMock())
            mock_loader.load_language.return_value = mock_language
            mock_get_loader.return_value = mock_loader

            result = executor.validate_query("python", "(function_definition) @func")

            assert result is True
            mock_language.query.assert_called_once_with("(function_definition) @func")

    def test_validate_query_with_invalid_language(self, executor):
        """Test query validation with invalid language."""
        with patch(
            "tree_sitter_analyzer.language_loader.get_loader"
        ) as mock_get_loader:
            mock_loader = MagicMock()
            mock_loader.load_language.return_value = None
            mock_get_loader.return_value = mock_loader

            result = executor.validate_query("invalid", "test")

            assert result is False

    def test_validate_query_with_invalid_query(self, executor):
        """Test query validation with invalid query."""
        with patch(
            "tree_sitter_analyzer.language_loader.get_loader"
        ) as mock_get_loader:
            mock_loader = MagicMock()
            mock_language = MagicMock()
            mock_language.query.side_effect = Exception("Invalid query")
            mock_loader.load_language.return_value = mock_language
            mock_get_loader.return_value = mock_loader

            result = executor.validate_query("python", "invalid query")

            assert result is False


class TestQueryStatistics:
    """Test query statistics methods."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    def test_get_query_statistics_initial(self, executor):
        """Test getting initial statistics."""
        stats = executor.get_query_statistics()

        assert stats["total_queries"] == 0
        assert stats["successful_queries"] == 0
        assert stats["failed_queries"] == 0
        assert stats["total_execution_time"] == 0.0
        assert stats["success_rate"] == 0.0
        assert stats["average_execution_time"] == 0.0

    def test_get_query_statistics_with_data(self, executor):
        """Test getting statistics with data."""
        executor._execution_stats["total_queries"] = 10
        executor._execution_stats["successful_queries"] = 8
        executor._execution_stats["failed_queries"] = 2
        executor._execution_stats["total_execution_time"] = 5.0

        stats = executor.get_query_statistics()

        assert stats["total_queries"] == 10
        assert stats["successful_queries"] == 8
        assert stats["failed_queries"] == 2
        assert stats["success_rate"] == 0.8
        assert stats["average_execution_time"] == 0.5

    def test_reset_statistics(self, executor):
        """Test resetting statistics."""
        executor._execution_stats["total_queries"] = 10
        executor._execution_stats["successful_queries"] = 8
        executor._execution_stats["failed_queries"] = 2
        executor._execution_stats["total_execution_time"] = 5.0

        executor.reset_statistics()

        assert executor._execution_stats["total_queries"] == 0
        assert executor._execution_stats["successful_queries"] == 0
        assert executor._execution_stats["failed_queries"] == 0
        assert executor._execution_stats["total_execution_time"] == 0.0


class TestModuleLevelFunctions:
    """Test module-level functions."""

    @patch("tree_sitter_analyzer.core.query.get_query_loader")
    def test_get_available_queries_with_language(self, mock_get_loader):
        """Test get_available_queries with language."""
        mock_loader = MagicMock()
        mock_loader.list_queries_for_language.return_value = ["query1", "query2"]
        mock_get_loader.return_value = mock_loader

        result = get_available_queries("python")

        assert result == ["query1", "query2"]
        mock_loader.list_queries_for_language.assert_called_once_with("python")

    @patch("tree_sitter_analyzer.core.query.get_query_loader")
    def test_get_available_queries_without_language(self, mock_get_loader):
        """Test get_available_queries without language."""
        mock_loader = MagicMock()
        mock_loader.list_supported_languages.return_value = ["python", "javascript"]
        mock_loader.list_queries_for_language.side_effect = lambda lang: [
            f"{lang}_query1",
            f"{lang}_query2",
        ]
        mock_get_loader.return_value = mock_loader

        result = get_available_queries()

        assert isinstance(result, list)
        assert len(result) > 0

    @patch("tree_sitter_analyzer.core.query.get_query_loader")
    def test_get_available_queries_with_error(self, mock_get_loader):
        """Test get_available_queries with error."""
        mock_get_loader.side_effect = Exception("Error")

        result = get_available_queries("python")

        assert result == []

    def test_get_query_description_module_level(self):
        """Test module-level get_query_description."""
        # The function does `from ..query_loader import get_query_loader` locally
        # so we need to patch query_loader.get_query_loader
        with patch(
            "tree_sitter_analyzer.query_loader.get_query_loader"
        ) as mock_get_loader:
            mock_loader = MagicMock()
            mock_loader.get_query_description.return_value = "Test description"
            mock_get_loader.return_value = mock_loader

            result = get_query_description("python", "test_query")

            assert result == "Test description"

    def test_get_query_description_with_error(self):
        """Test module-level get_query_description with error."""
        with patch(
            "tree_sitter_analyzer.query_loader.get_query_loader",
            side_effect=Exception("Error"),
        ):
            result = get_query_description("python", "test_query")

            assert result is None


class TestDeprecatedFunctions:
    """Test deprecated functions."""

    def test_get_all_queries_for_language_deprecated(self):
        """Test that get_all_queries_for_language shows deprecation warning."""
        with pytest.warns(DeprecationWarning, match="deprecated"):
            result = get_all_queries_for_language("python")

        assert result == []


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor instance."""
        return QueryExecutor()

    def test_execute_query_with_empty_source_code(self, executor):
        """Test executing query with empty source code."""
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_language = MagicMock()
        mock_language.name = "python"

        with patch.object(executor._query_loader, "get_query", return_value="test"):
            with patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                return_value=[],
            ):
                result = executor.execute_query(mock_tree, mock_language, "test", "")

        assert result["success"] is True

    def test_execute_query_with_very_long_source_code(self, executor):
        """Test executing query with very long source code."""
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_language = MagicMock()
        mock_language.name = "python"
        long_code = "x = 1\n" * 100000

        with patch.object(executor._query_loader, "get_query", return_value="test"):
            with patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                return_value=[],
            ):
                result = executor.execute_query(
                    mock_tree, mock_language, "test", long_code
                )

        assert result["success"] is True

    def test_process_captures_with_mixed_formats(self, executor):
        """Test processing captures with mixed tuple and dict formats."""
        mock_node1 = MagicMock()
        mock_node1.type = "function"
        mock_node1.start_point = (1, 0)
        mock_node1.end_point = (5, 0)
        mock_node1.start_byte = 0
        mock_node1.end_byte = 50

        mock_node2 = MagicMock()
        mock_node2.type = "class"
        mock_node2.start_point = (10, 0)
        mock_node2.end_point = (20, 0)
        mock_node2.start_byte = 100
        mock_node2.end_byte = 200

        captures = [(mock_node1, "func"), {"node": mock_node2, "name": "class_def"}]

        with patch(
            "tree_sitter_analyzer.core.query.get_node_text_safe", return_value="test"
        ):
            result = executor._process_captures(captures, "source")

        assert len(result) == 2

    def test_execute_multiple_queries_with_partial_failures(self, executor):
        """Test executing multiple queries where some fail."""
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_language = MagicMock()

        def mock_execute(tree, lang, query_name, code):
            if query_name == "failing":
                return {"success": False, "error": "Failed", "captures": []}
            return {"success": True, "captures": []}

        with patch.object(executor, "execute_query", side_effect=mock_execute):
            results = executor.execute_multiple_queries(
                mock_tree, mock_language, ["query1", "failing", "query3"], "code"
            )

        assert len(results) == 3
        assert results["query1"]["success"] is True
        assert results["failing"]["success"] is False
        assert results["query3"]["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
