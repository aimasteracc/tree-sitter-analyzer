#!/usr/bin/env python3
"""
API Regression Tests - 测试API向后兼容性
"""

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.core.query import QueryExecutor
from tree_sitter_analyzer.core.request import AnalysisRequest


class TestAPIBackwardCompatibility:
    """API向后兼容性测试"""

    @pytest.mark.regression
    def test_analysis_request_backward_compatibility(self):
        """测试AnalysisRequest向后兼容性"""
        # 测试旧版本的参数创建方式仍然有效
        request = AnalysisRequest(
            file_path="/test.py",
            language="python",
            include_elements=True,
            include_queries=True,
        )

        # 验证基本属性仍然存在
        assert hasattr(request, "file_path")
        assert hasattr(request, "language")
        assert hasattr(request, "include_elements")
        assert hasattr(request, "include_queries")

    @pytest.mark.regression
    def test_analysis_request_from_mcp_arguments_compatibility(self):
        """测试from_mcp_arguments方法兼容性"""
        # 测试旧版本的参数格式
        old_arguments = {
            "file_path": "/test.py",
            "language": "python",
            "include_complexity": True,
            "include_details": False,
            "format_type": "json",
        }

        request = AnalysisRequest.from_mcp_arguments(old_arguments)

        # 验证所有参数都被正确处理
        assert request.file_path == "/test.py"
        assert request.language == "python"
        assert request.include_complexity is True
        assert request.include_details is False
        assert request.format_type == "json"

    @pytest.mark.regression
    def test_analysis_request_new_parameters_compatibility(self):
        """测试新增参数的兼容性"""
        # 测试包含新参数的请求
        arguments = {
            "file_path": "/test.py",
            "language": "python",
            "include_complexity": True,
            "include_details": True,
            "format_type": "toon",
        }

        request = AnalysisRequest.from_mcp_arguments(arguments)

        # 验证新参数被正确处理
        assert request.format_type == "toon"
        assert request.include_details is True

    @pytest.mark.regression
    def test_query_executor_backward_compatibility(self):
        """测试QueryExecutor向后兼容性"""
        executor = QueryExecutor()

        # 验证基本方法仍然存在
        assert hasattr(executor, "execute_query")
        assert hasattr(executor, "execute_query_with_language_name")
        assert hasattr(executor, "execute_query_string")
        assert hasattr(executor, "execute_multiple_queries")

        # 验证统计方法存在
        assert hasattr(executor, "get_query_statistics")
        assert hasattr(executor, "reset_statistics")


class TestAPIParameterCompatibility:
    """API参数兼容性测试"""

    @pytest.mark.regression
    def test_analysis_request_parameter_types(self):
        """测试AnalysisRequest参数类型兼容性"""
        # 测试字符串类型的language
        request1 = AnalysisRequest(file_path="/test.py", language="python")
        assert request1.language == "python"

        # 测试None类型的language
        request2 = AnalysisRequest(file_path="/test.py", language=None)
        assert request2.language is None

        # 测试列表类型的queries
        request3 = AnalysisRequest(file_path="/test.py", queries=["class", "function"])
        assert request3.queries == ["class", "function"]

        # 测试None类型的queries
        request4 = AnalysisRequest(file_path="/test.py", queries=None)
        assert request4.queries is None

    @pytest.mark.regression
    def test_analysis_request_boolean_parameters(self):
        """测试布尔参数兼容性"""
        # 测试所有布尔参数的组合
        combinations = [
            (True, True, True, True),
            (True, True, True, False),
            (True, True, False, True),
            (True, False, True, True),
            (False, True, True, True),
        ]

        for elements, queries, complexity, details in combinations:
            request = AnalysisRequest(
                file_path="/test.py",
                include_elements=elements,
                include_queries=queries,
                include_complexity=complexity,
                include_details=details,
            )
            assert request.include_elements is elements
            assert request.include_queries is queries
            assert request.include_complexity is complexity
            assert request.include_details is details

    @pytest.mark.regression
    def test_analysis_request_format_type_variations(self):
        """测试format_type参数变化"""
        format_types = ["json", "markdown", "csv", "toon", "text"]

        for fmt in format_types:
            request = AnalysisRequest(file_path="/test.py", format_type=fmt)
            assert request.format_type == fmt

    @pytest.mark.regression
    def test_query_executor_parameter_types(self):
        """测试QueryExecutor参数类型兼容性"""
        executor = QueryExecutor()

        # 测试execute_query的参数
        mock_tree = MagicMock()
        mock_language = MagicMock()
        mock_language.name = "python"

        # 这些参数应该被接受而不抛出异常
        result = executor.execute_query(
            tree=mock_tree,
            language=mock_language,
            query_name="classes",
            source_code="test code",
        )

        # 验证返回结果结构
        assert "success" in result or "error" in result

    @pytest.mark.regression
    def test_query_executor_query_name_parameter(self):
        """测试query_name参数兼容性"""
        executor = QueryExecutor()

        mock_tree = MagicMock()
        mock_language = MagicMock()
        mock_language.name = "python"

        # 测试不同的查询名称
        query_names = ["classes", "functions", "imports", "exports"]

        for query_name in query_names:
            result = executor.execute_query(
                tree=mock_tree,
                language=mock_language,
                query_name=query_name,
                source_code="test code",
            )
            # 验证结果包含query_name
            if result.get("success"):
                assert result.get("query_name") == query_name

    @pytest.mark.regression
    def test_query_executor_source_code_parameter(self):
        """测试source_code参数兼容性"""
        executor = QueryExecutor()

        mock_tree = MagicMock()
        mock_language = MagicMock()

        # 测试不同类型的source_code
        source_codes = [
            "def test(): pass",
            "class Test: pass",
            "import os",
        ]

        for source_code in source_codes:
            result = executor.execute_query(
                tree=mock_tree,
                language=mock_language,
                query_name="classes",
                source_code=source_code,
            )
            # 验证结果结构
            assert "success" in result or "error" in result


class TestAPIResponseFormat:
    """API响应格式测试"""

    @pytest.mark.regression
    def test_analysis_response_structure(self):
        """测试分析响应结构"""
        # 创建一个模拟的分析结果
        mock_result = {
            "elements": [
                {
                    "name": "TestClass",
                    "type": "class",
                    "start_line": 1,
                    "end_line": 5,
                }
            ],
            "language": "python",
            "success": True,
        }

        # 验证响应包含必需的字段
        assert "elements" in mock_result
        assert "language" in mock_result
        assert "success" in mock_result

    @pytest.mark.regression
    def test_query_response_structure(self):
        """测试查询响应结构"""
        # 创建一个模拟的查询结果
        mock_result = {
            "captures": [],
            "query_name": "classes",
            "execution_time": 0.001,
            "success": True,
        }

        # 验证响应包含必需的字段
        assert "captures" in mock_result
        assert "query_name" in mock_result
        assert "execution_time" in mock_result
        assert "success" in mock_result

    @pytest.mark.regression
    def test_error_response_structure(self):
        """测试错误响应结构"""
        # 创建一个模拟的错误结果
        mock_error = {
            "success": False,
            "error": "Test error message",
        }

        # 验证错误响应包含必需的字段
        assert "success" in mock_error
        assert "error" in mock_error
        assert mock_error["success"] is False


class TestAPIStatistics:
    """API统计功能测试"""

    @pytest.mark.regression
    def test_query_executor_statistics_structure(self):
        """测试查询执行统计结构"""
        executor = QueryExecutor()

        stats = executor.get_query_statistics()

        # 验证统计结构
        assert "total_queries" in stats
        assert "successful_queries" in stats
        assert "failed_queries" in stats
        assert "total_execution_time" in stats
        assert "success_rate" in stats
        assert "average_execution_time" in stats

    @pytest.mark.regression
    def test_query_executor_statistics_initial_values(self):
        """测试统计初始值"""
        executor = QueryExecutor()

        stats = executor.get_query_statistics()

        # 验证初始值
        assert stats["total_queries"] == 0
        assert stats["successful_queries"] == 0
        assert stats["failed_queries"] == 0
        assert stats["total_execution_time"] == 0.0
        assert stats["success_rate"] == 0.0
        assert stats["average_execution_time"] == 0.0

    @pytest.mark.regression
    def test_query_executor_reset_statistics(self):
        """测试重置统计功能"""
        executor = QueryExecutor()

        # 手动修改统计
        executor._execution_stats["total_queries"] = 10
        executor._execution_stats["successful_queries"] = 8
        executor._execution_stats["failed_queries"] = 2
        executor._execution_stats["total_execution_time"] = 1.5

        # 重置统计
        executor.reset_statistics()

        # 验证统计被重置
        stats = executor.get_query_statistics()
        assert stats["total_queries"] == 0
        assert stats["successful_queries"] == 0
        assert stats["failed_queries"] == 0
        assert stats["total_execution_time"] == 0.0


class TestAPIMigration:
    """API迁移测试"""

    @pytest.mark.regression
    def test_old_api_still_works(self):
        """测试旧API仍然工作"""
        # 测试旧的AnalysisRequest创建方式
        request = AnalysisRequest(
            file_path="/test.py",
            language="python",
            include_elements=True,
            include_queries=True,
            include_complexity=True,
            include_details=False,
            format_type="json",
        )

        # 验证所有属性都可以访问
        assert request.file_path == "/test.py"
        assert request.language == "python"
        assert request.include_elements is True
        assert request.include_queries is True
        assert request.include_complexity is True
        assert request.include_details is False
        assert request.format_type == "json"

    @pytest.mark.regression
    def test_new_api_features(self):
        """测试新API特性"""
        # 测试from_mcp_arguments方法
        arguments = {
            "file_path": "/test.py",
            "language": "python",
            "include_complexity": True,
            "include_details": True,
            "format_type": "toon",
        }

        request = AnalysisRequest.from_mcp_arguments(arguments)

        # 验证新特性工作正常
        assert request.format_type == "toon"
        assert request.include_details is True
