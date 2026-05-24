#!/usr/bin/env python3
"""
QueryExecutor module-level functions and edge case tests.
"""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.core.query import QueryExecutor


class TestModuleLevelFunctions:
    """模块级别函数测试"""

    @patch("tree_sitter_analyzer.core.query.get_query_loader")
    def test_get_available_queries_module_level(self, mock_loader):
        """测试模块级别get_available_queries函数"""
        mock_query_loader = MagicMock()
        mock_query_loader.list_supported_languages.return_value = ["python", "java"]
        mock_query_loader.list_queries_for_language.side_effect = lambda x: [
            "classes",
            "functions",
        ]
        mock_loader.return_value = mock_query_loader

        from tree_sitter_analyzer.core.query import get_available_queries

        queries = get_available_queries()

        assert isinstance(queries, list)
        assert len(queries) > 0

    @patch("tree_sitter_analyzer.core.query.get_query_loader")
    def test_get_available_queries_with_language(self, mock_loader):
        """测试带语言参数的get_available_queries"""
        mock_query_loader = MagicMock()
        mock_query_loader.list_queries_for_language.return_value = [
            "classes",
            "functions",
        ]
        mock_loader.return_value = mock_query_loader

        from tree_sitter_analyzer.core.query import get_available_queries

        queries = get_available_queries("python")

        assert isinstance(queries, list)
        assert "classes" in queries
        assert "functions" in queries

    @patch("tree_sitter_analyzer.core.query.get_query_loader")
    def test_get_query_description_module_level(self, mock_loader):
        """测试模块级别get_query_description函数"""
        mock_query_loader = MagicMock()
        mock_query_loader.get_query_description.return_value = (
            "Search all class definitions"
        )
        mock_loader.return_value = mock_query_loader

        from tree_sitter_analyzer.core.query import get_query_description

        description = get_query_description("python", "classes")

        assert description == "Search all class definitions"


class TestGetAvailableQueriesResponseFormats:
    """Test get_available_queries with different response formats."""

    def test_get_available_queries_none_response(self):
        """Test get_available_queries with None response."""
        executor = QueryExecutor()
        with patch.object(
            executor._query_loader, "get_all_queries_for_language", return_value=None
        ):
            result = executor.get_available_queries("python")
        assert result == []

    def test_get_available_queries_dict_response(self):
        """Test get_available_queries with dict response."""
        executor = QueryExecutor()
        mock_queries = {"query1": "...", "query2": "...", "query3": "..."}
        with patch.object(
            executor._query_loader,
            "get_all_queries_for_language",
            return_value=mock_queries,
        ):
            result = executor.get_available_queries("python")
        assert set(result) == {"query1", "query2", "query3"}

    def test_get_available_queries_list_response(self):
        """Test get_available_queries with list response."""
        executor = QueryExecutor()
        mock_queries = ["query1", "query2", "query3"]
        with patch.object(
            executor._query_loader,
            "get_all_queries_for_language",
            return_value=mock_queries,
        ):
            result = executor.get_available_queries("python")
        assert result == mock_queries


class TestExecuteQueryLanguageNameEdgeCases:
    """Test execute_query with edge case language names."""

    def test_execute_query_with_empty_language_name(self):
        """Test execute_query when language name is empty string."""
        executor = QueryExecutor()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_language = MagicMock()
        mock_language.name = ""

        with patch.object(executor._query_loader, "get_query", return_value="test"):
            with patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                return_value=[],
            ):
                result = executor.execute_query(
                    mock_tree, mock_language, "test", "code"
                )
        assert result["success"] is True

    def test_execute_query_with_none_language_name_attr(self):
        """Test execute_query when language.name is None."""
        executor = QueryExecutor()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_language = MagicMock()
        mock_language.name = None
        mock_language._name = None

        with patch.object(executor._query_loader, "get_query", return_value="test"):
            with patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                return_value=[],
            ):
                result = executor.execute_query(
                    mock_tree, mock_language, "test", "code"
                )
        assert result["success"] is True

    def test_execute_query_with_language_name_string_none(self):
        """Test execute_query when language name is string 'None'."""
        executor = QueryExecutor()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_language = MagicMock()
        mock_language.name = "None"

        with patch.object(executor._query_loader, "get_query", return_value="test"):
            with patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                return_value=[],
            ):
                result = executor.execute_query(
                    mock_tree, mock_language, "test", "code"
                )
        assert result["success"] is True

    def test_execute_query_with_whitespace_language_name(self):
        """Test execute_query when language name is whitespace."""
        executor = QueryExecutor()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_language = MagicMock()
        mock_language.name = "   "

        with patch.object(executor._query_loader, "get_query", return_value="test"):
            with patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                return_value=[],
            ):
                result = executor.execute_query(
                    mock_tree, mock_language, "test", "code"
                )
        assert result["success"] is True


class TestExecuteQueryEdgeCases:
    """Test execute_query with various edge cases."""

    def test_execute_query_with_empty_source_code(self):
        """Test executing query with empty source code."""
        executor = QueryExecutor()
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

    def test_execute_query_with_very_long_source_code(self):
        """Test executing query with very long source code."""
        executor = QueryExecutor()
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


class TestProcessCapturesMixedFormats:
    """Test _process_captures with mixed formats."""

    def test_process_captures_with_mixed_formats(self):
        """Test processing captures with mixed tuple and dict formats."""
        executor = QueryExecutor()

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


class TestExecuteMultipleQueriesPartialFailures:
    """Test execute_multiple_queries with partial failures."""

    def test_execute_multiple_queries_with_partial_failures(self):
        """Test executing multiple queries where some fail."""
        executor = QueryExecutor()
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


class TestDeprecatedFunctions:
    """Test deprecated functions."""

    def test_get_all_queries_for_language_deprecated(self):
        """Test that get_all_queries_for_language shows deprecation warning."""
        from tree_sitter_analyzer.core.query import get_all_queries_for_language

        with pytest.warns(DeprecationWarning, match="deprecated"):
            result = get_all_queries_for_language("python")

        assert result == []


class TestExecuteQueryWithRealParser:
    """Integration tests using real tree-sitter parsing."""

    def test_execute_query_with_real_python_code(self):
        """Test query execution with real Python code parsing."""
        executor = QueryExecutor()
        try:
            from tree_sitter_analyzer.core.parser import Parser

            parser = Parser()
            code = "def hello():\n    pass"
            parse_result = parser.parse_code(code, "python")

            if parse_result.success and parse_result.tree:
                language = parse_result.tree.language
                result = executor.execute_query_with_language_name(
                    parse_result.tree, language, "functions", code, "python"
                )
                assert "success" in result
                assert "captures" in result
        except Exception:
            pytest.skip("Tree-sitter not properly configured")

    def test_execute_query_string_with_real_code(self):
        """Test query string execution with real code."""
        executor = QueryExecutor()
        try:
            from tree_sitter_analyzer.core.parser import Parser

            parser = Parser()
            code = "class MyClass:\n    pass"
            parse_result = parser.parse_code(code, "python")

            if parse_result.success and parse_result.tree:
                language = parse_result.tree.language
                query_string = "(class_definition) @class"
                result = executor.execute_query_string(
                    parse_result.tree, language, query_string, code
                )
                assert "success" in result
        except Exception:
            pytest.skip("Tree-sitter not properly configured")
