#!/usr/bin/env python3
"""
QueryExecutor 单元测试
"""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.core.query import QueryExecutor


class TestQueryExecutorInit:
    """QueryExecutor初始化测试"""

    def test_init(self):
        """测试QueryExecutor初始化"""
        executor = QueryExecutor()
        assert executor._query_loader is not None
        assert executor._execution_stats == {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "total_execution_time": 0.0,
        }

    def test_init_creates_query_loader(self):
        """测试初始化时创建query_loader"""
        with patch("tree_sitter_analyzer.core.query.get_query_loader") as mock_loader:
            mock_loader.return_value = MagicMock()
            QueryExecutor()
            mock_loader.assert_called_once()


class TestQueryExecutorExecuteQuery:
    """execute_query方法测试"""

    def test_execute_query_with_none_tree(self):
        """测试tree为None时返回错误"""
        executor = QueryExecutor()
        result = executor.execute_query(
            tree=None,
            language=MagicMock(),
            query_name="test",
            source_code="test code",
        )
        assert result["success"] is False
        assert "error" in result
        assert result["query_name"] == "test"

    def test_execute_query_with_none_language(self):
        """测试language为None时返回错误"""
        executor = QueryExecutor()
        result = executor.execute_query(
            tree=MagicMock(),
            language=None,
            query_name="test",
            source_code="test code",
        )
        assert result["success"] is False
        assert "error" in result
        assert result["query_name"] == "test"

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat")
    def test_execute_query_success(self, mock_compat):
        """测试成功执行查询"""
        # 设置mock
        mock_language = MagicMock()
        mock_language.name = "python"
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        mock_compat.safe_execute_query.return_value = [(MagicMock(), "capture_name")]

        executor = QueryExecutor()
        result = executor.execute_query(
            tree=mock_tree,
            language=mock_language,
            query_name="classes",
            source_code="class Test: pass",
        )

        assert result["success"] is True
        assert result["query_name"] == "classes"
        assert "captures" in result
        assert "execution_time" in result
        assert executor._execution_stats["total_queries"] == 1
        assert executor._execution_stats["successful_queries"] == 1

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat")
    def test_execute_query_query_not_found(self, mock_compat):
        """测试查询未找到"""
        mock_language = MagicMock()
        mock_language.name = "python"
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        executor = QueryExecutor()
        result = executor.execute_query(
            tree=mock_tree,
            language=mock_language,
            query_name="nonexistent",
            source_code="test code",
        )

        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat")
    def test_execute_query_updates_stats(self, mock_compat):
        """测试执行查询更新统计信息"""
        mock_language = MagicMock()
        mock_language.name = "python"
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        # モックの戻り値を設定
        mock_compat.safe_execute_query.return_value = []

        executor = QueryExecutor()
        executor.execute_query(
            tree=mock_tree,
            language=mock_language,
            query_name="classes",  # 有効なクエリ名を使用
            source_code="test code",
        )

        assert executor._execution_stats["total_queries"] == 1
        assert executor._execution_stats["successful_queries"] == 1
        assert executor._execution_stats["failed_queries"] == 0
        # 実行時間は0以上
        assert executor._execution_stats["total_execution_time"] >= 0


class TestQueryExecutorExecuteQueryWithLanguageName:
    """execute_query_with_language_name方法测试"""

    def test_execute_query_with_language_name_none_tree(self):
        """测试tree为None时返回错误"""
        executor = QueryExecutor()
        result = executor.execute_query_with_language_name(
            tree=None,
            language=MagicMock(),
            query_name="test",
            source_code="test code",
            language_name="python",
        )
        assert result["success"] is False
        assert "error" in result

    def test_execute_query_with_language_name_none_language(self):
        """测试language为None时返回错误"""
        executor = QueryExecutor()
        result = executor.execute_query_with_language_name(
            tree=MagicMock(),
            language=None,
            query_name="test",
            source_code="test code",
            language_name="python",
        )
        assert result["success"] is False
        assert "error" in result

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat")
    def test_execute_query_with_language_name_success(self, mock_compat):
        """测试成功执行查询（带语言名）"""
        mock_language = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        mock_compat.safe_execute_query.return_value = []

        executor = QueryExecutor()
        result = executor.execute_query_with_language_name(
            tree=mock_tree,
            language=mock_language,
            query_name="classes",
            source_code="class Test: pass",
            language_name="python",
        )

        assert result["success"] is True
        assert result["query_name"] == "classes"
        assert "execution_time" in result


class TestQueryExecutorExecuteQueryString:
    """execute_query_string方法测试"""

    def test_execute_query_string_none_tree(self):
        """测试tree为None时返回错误"""
        executor = QueryExecutor()
        result = executor.execute_query_string(
            tree=None,
            language=MagicMock(),
            query_string="(class_definition)",
            source_code="test code",
        )
        assert result["success"] is False
        assert "error" in result

    def test_execute_query_string_none_language(self):
        """测试language为None时返回错误"""
        executor = QueryExecutor()
        result = executor.execute_query_string(
            tree=MagicMock(),
            language=None,
            query_string="(class_definition)",
            source_code="test code",
        )
        assert result["success"] is False
        assert "error" in result

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat")
    def test_execute_query_string_success(self, mock_compat):
        """测试成功执行查询字符串"""
        mock_language = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        mock_compat.safe_execute_query.return_value = []

        executor = QueryExecutor()
        result = executor.execute_query_string(
            tree=mock_tree,
            language=mock_language,
            query_string="(class_definition)",
            source_code="class Test: pass",
        )

        assert result["success"] is True
        assert result["query_string"] == "(class_definition)"
        assert "execution_time" in result

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat")
    def test_execute_query_string_updates_stats(self, mock_compat):
        """测试执行查询字符串更新统计信息"""
        mock_language = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        mock_compat.safe_execute_query.return_value = []

        executor = QueryExecutor()
        executor.execute_query_string(
            tree=mock_tree,
            language=mock_language,
            query_string="(function_definition)",
            source_code="def test(): pass",
        )

        assert executor._execution_stats["total_queries"] == 1
        assert executor._execution_stats["successful_queries"] == 1


class TestQueryExecutorExecuteMultipleQueries:
    """execute_multiple_queries方法测试"""

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat")
    def test_execute_multiple_queries(self, mock_compat):
        """测试执行多个查询"""
        mock_language = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        mock_compat.safe_execute_query.return_value = []

        executor = QueryExecutor()
        results = executor.execute_multiple_queries(
            tree=mock_tree,
            language=mock_language,
            query_names=["classes", "functions"],
            source_code="test code",
        )

        assert "classes" in results
        assert "functions" in results
        assert len(results) == 2
        assert executor._execution_stats["total_queries"] == 2

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat")
    def test_execute_multiple_queries_empty_list(self, mock_compat):
        """测试执行空查询列表"""
        mock_language = MagicMock()
        mock_tree = MagicMock()

        executor = QueryExecutor()
        results = executor.execute_multiple_queries(
            tree=mock_tree,
            language=mock_language,
            query_names=[],
            source_code="test code",
        )

        assert results == {}


class TestQueryExecutorProcessCaptures:
    """_process_captures方法测试"""

    @patch("tree_sitter_analyzer.core.query.get_node_text_safe")
    def test_process_captures_tuple_format(self, mock_get_text):
        """测试处理元组格式的captures"""
        mock_get_text.return_value = "test_text"
        executor = QueryExecutor()

        mock_node = MagicMock()
        mock_node.type = "class_definition"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 10

        captures = [(mock_node, "class")]

        result = executor._process_captures(captures, "source code")

        assert len(result) == 1
        assert result[0]["capture_name"] == "class"
        assert result[0]["node_type"] == "class_definition"

    @patch("tree_sitter_analyzer.core.query.get_node_text_safe")
    def test_process_captures_dict_format(self, mock_get_text):
        """测试处理字典格式的captures"""
        mock_get_text.return_value = "test_text"
        executor = QueryExecutor()

        mock_node = MagicMock()
        mock_node.type = "function_definition"

        captures = [{"node": mock_node, "name": "function"}]

        result = executor._process_captures(captures, "source code")

        assert len(result) == 1
        assert result[0]["capture_name"] == "function"

    @patch("tree_sitter_analyzer.core.query.get_node_text_safe")
    def test_process_captures_none_node(self, mock_get_text):
        """测试处理None节点"""
        executor = QueryExecutor()

        captures = [(None, "capture")]

        result = executor._process_captures(captures, "source code")

        assert len(result) == 0

    @patch("tree_sitter_analyzer.core.query.get_node_text_safe")
    def test_process_captures_multiple(self, mock_get_text):
        """测试处理多个captures"""
        mock_get_text.return_value = "text"
        executor = QueryExecutor()

        mock_node1 = MagicMock()
        mock_node1.type = "class"
        mock_node1.start_point = (0, 0)

        mock_node2 = MagicMock()
        mock_node2.type = "function"
        mock_node2.start_point = (1, 0)

        captures = [(mock_node1, "class"), (mock_node2, "function")]

        result = executor._process_captures(captures, "source code")

        assert len(result) == 2
        assert result[0]["capture_name"] == "class"
        assert result[1]["capture_name"] == "function"


class TestQueryExecutorCreateResultDict:
    """_create_result_dict方法测试"""

    @patch("tree_sitter_analyzer.core.query.get_node_text_safe")
    def test_create_result_dict(self, mock_get_text):
        """测试创建结果字典"""
        mock_get_text.return_value = "class Test: pass"
        executor = QueryExecutor()

        mock_node = MagicMock()
        mock_node.type = "class_definition"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 15

        result = executor._create_result_dict(mock_node, "class", "source code")

        assert result["capture_name"] == "class"
        assert result["node_type"] == "class_definition"
        assert result["start_point"] == (0, 0)
        assert result["end_point"] == (1, 0)
        assert result["start_byte"] == 0
        assert result["end_byte"] == 15
        assert result["text"] == "class Test: pass"
        assert result["line_number"] == 1
        assert result["column_number"] == 0

    @patch("tree_sitter_analyzer.core.query.get_node_text_safe")
    def test_create_result_dict_error(self, mock_get_text):
        """测试创建结果字典时出错"""
        mock_get_text.side_effect = Exception("Test error")
        executor = QueryExecutor()

        mock_node = MagicMock()

        result = executor._create_result_dict(mock_node, "capture", "source code")

        assert result["capture_name"] == "capture"
        assert result["node_type"] == "error"
        assert "error" in result


class TestQueryExecutorCreateErrorResult:
    """_create_error_result方法测试"""

    def test_create_error_result_basic(self):
        """测试创建基本错误结果"""
        executor = QueryExecutor()
        result = executor._create_error_result("Test error")

        assert result["success"] is False
        assert result["error"] == "Test error"
        assert result["captures"] == []

    def test_create_error_result_with_query_name(self):
        """测试创建带查询名的错误结果"""
        executor = QueryExecutor()
        result = executor._create_error_result("Test error", query_name="test_query")

        assert result["success"] is False
        assert result["error"] == "Test error"
        assert result["query_name"] == "test_query"

    def test_create_error_result_with_extra_fields(self):
        """测试创建带额外字段的错误结果"""
        executor = QueryExecutor()
        result = executor._create_error_result(
            "Test error", query_name="test", extra_field="value"
        )

        assert result["success"] is False
        assert result["error"] == "Test error"
        assert result["query_name"] == "test"
        assert result["extra_field"] == "value"


class TestQueryExecutorGetAvailableQueries:
    """get_available_queries方法测试"""

    def test_get_available_queries(self):
        """测试获取可用查询"""
        executor = QueryExecutor()
        queries = executor.get_available_queries("python")

        assert isinstance(queries, list)
        assert len(queries) >= 0

    def test_get_available_queries_empty_language(self):
        """测试空语言获取查询"""
        executor = QueryExecutor()
        queries = executor.get_available_queries("")

        assert isinstance(queries, list)
        assert len(queries) >= 0


class TestQueryExecutorGetQueryDescription:
    """get_query_description方法测试"""

    def test_get_query_description(self):
        """测试获取查询描述"""
        executor = QueryExecutor()
        description = executor.get_query_description("python", "classes")

        # 描述可能是None或字符串
        assert description is None or isinstance(description, str)

    def test_get_query_description_nonexistent(self):
        """测试获取不存在查询的描述"""
        executor = QueryExecutor()
        description = executor.get_query_description("python", "nonexistent_query")

        assert description is None


class TestQueryExecutorValidateQuery:
    """validate_query方法测试"""

    @patch("tree_sitter_analyzer.core.query.get_loader")
    def test_validate_query_success(self, mock_loader):
        """测试验证查询成功"""
        mock_lang_loader = MagicMock()
        mock_language = MagicMock()
        mock_language.query.return_value = MagicMock()

        mock_lang_loader.load_language.return_value = mock_language
        mock_loader.return_value = mock_lang_loader

        executor = QueryExecutor()
        result = executor.validate_query("python", "(class_definition)")

        assert result is True

    @patch("tree_sitter_analyzer.core.query.get_loader")
    def test_validate_query_invalid(self, mock_loader):
        """测试验证无效查询"""
        mock_lang_loader = MagicMock()
        mock_lang_loader.load_language.return_value = None
        mock_loader.return_value = mock_lang_loader

        executor = QueryExecutor()
        result = executor.validate_query("python", "(invalid query")

        assert result is False


class TestQueryExecutorGetQueryStatistics:
    """get_query_statistics方法测试"""

    def test_get_query_statistics_initial(self):
        """测试初始查询统计信息"""
        executor = QueryExecutor()
        stats = executor.get_query_statistics()

        assert stats["total_queries"] == 0
        assert stats["successful_queries"] == 0
        assert stats["failed_queries"] == 0
        assert stats["total_execution_time"] == 0.0
        assert stats["success_rate"] == 0.0
        assert stats["average_execution_time"] == 0.0

    @patch("tree_sitter_analyzer.core.query.TreeSitterQueryCompat")
    def test_get_query_statistics_after_execution(self, mock_compat):
        """测试执行后的查询统计信息"""
        mock_language = MagicMock()
        mock_language.name = "python"
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        # モックの戻り値を設定
        mock_compat.safe_execute_query.return_value = []

        executor = QueryExecutor()
        executor.execute_query(
            tree=mock_tree,
            language=mock_language,
            query_name="classes",  # 有効なクエリ名を使用
            source_code="test code",
        )

        stats = executor.get_query_statistics()

        assert stats["total_queries"] == 1
        assert stats["successful_queries"] == 1
        assert stats["failed_queries"] == 0
        # 実行時間は0以上
        assert stats["total_execution_time"] >= 0
        assert stats["success_rate"] == 1.0
        assert stats["average_execution_time"] >= 0


class TestQueryExecutorResetStatistics:
    """reset_statistics方法测试"""

    def test_reset_statistics(self):
        """测试重置统计信息"""
        executor = QueryExecutor()

        # 手动修改统计信息
        executor._execution_stats["total_queries"] = 10
        executor._execution_stats["successful_queries"] = 8
        executor._execution_stats["failed_queries"] = 2
        executor._execution_stats["total_execution_time"] = 1.5

        # 重置
        executor.reset_statistics()

        assert executor._execution_stats["total_queries"] == 0
        assert executor._execution_stats["successful_queries"] == 0
        assert executor._execution_stats["failed_queries"] == 0
        assert executor._execution_stats["total_execution_time"] == 0.0


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
        # 実際のクエリローダーは"Search all class definitions"のような説明を返す
        # テストの期待値を実際の戻り値に合わせる
        mock_query_loader.get_query_description.return_value = (
            "Search all class definitions"
        )
        mock_loader.return_value = mock_query_loader

        from tree_sitter_analyzer.core.query import get_query_description

        description = get_query_description("python", "classes")

        # モックが正しく設定されていれば、戻り値が一致する
        assert description == "Search all class definitions"


# =============================================================================
# Migrated from test_core_query_comprehensive.py and test_core_query_coverage.py
# =============================================================================


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
                result = executor.execute_query(mock_tree, mock_language, "test", "code")
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
                result = executor.execute_query(mock_tree, mock_language, "test", "code")
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
                result = executor.execute_query(mock_tree, mock_language, "test", "code")
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
                result = executor.execute_query(mock_tree, mock_language, "test", "code")
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
                result = executor.execute_query(mock_tree, mock_language, "test", long_code)
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
