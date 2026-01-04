#!/usr/bin/env python3
"""
Analysis Request 单元测试
"""

import pytest

from tree_sitter_analyzer.core.request import AnalysisRequest


class TestAnalysisRequest:
    """AnalysisRequest测试类"""

    def test_init_with_all_parameters(self):
        """测试使用所有参数初始化"""
        request = AnalysisRequest(
            file_path="/path/to/file.py",
            language="python",
            queries=["classes", "functions"],
            include_elements=True,
            include_queries=True,
            include_complexity=True,
            include_details=True,
            format_type="json",
        )
        assert request.file_path == "/path/to/file.py"
        assert request.language == "python"
        assert request.queries == ["classes", "functions"]
        assert request.include_elements is True
        assert request.include_queries is True
        assert request.include_complexity is True
        assert request.include_details is True
        assert request.format_type == "json"

    def test_init_with_defaults(self):
        """测试使用默认参数初始化"""
        request = AnalysisRequest(file_path="/path/to/file.py")
        assert request.file_path == "/path/to/file.py"
        assert request.language is None
        assert request.queries is None
        assert request.include_elements is True  # 默认值
        assert request.include_queries is True  # 默认值
        assert request.include_complexity is True  # 默认值
        assert request.include_details is False  # 默认值
        assert request.format_type == "json"  # 默认值

    def test_init_with_partial_parameters(self):
        """测试使用部分参数初始化"""
        request = AnalysisRequest(
            file_path="/path/to/file.py",
            language="java",
            include_complexity=False,
        )
        assert request.file_path == "/path/to/file.py"
        assert request.language == "java"
        assert request.queries is None
        assert request.include_elements is True
        assert request.include_queries is True
        assert request.include_complexity is False
        assert request.include_details is False
        assert request.format_type == "json"

    def test_dataclass_not_frozen(self):
        """测试dataclass不是frozen的"""
        request = AnalysisRequest(file_path="/test.py")
        request.file_path = "/new/path.py"
        assert request.file_path == "/new/path.py"

    def test_from_mcp_arguments_all_fields(self):
        """测试从MCP参数创建请求（所有字段）"""
        arguments = {
            "file_path": "/path/to/file.py",
            "language": "python",
            "include_complexity": False,
            "include_details": True,
            "format_type": "markdown",
        }
        request = AnalysisRequest.from_mcp_arguments(arguments)
        assert request.file_path == "/path/to/file.py"
        assert request.language == "python"
        assert request.include_complexity is False
        assert request.include_details is True
        assert request.format_type == "markdown"

    def test_from_mcp_arguments_minimal(self):
        """测试从MCP参数创建请求（最小参数）"""
        arguments = {"file_path": "/path/to/file.py"}
        request = AnalysisRequest.from_mcp_arguments(arguments)
        assert request.file_path == "/path/to/file.py"
        assert request.language is None
        assert request.include_complexity is True  # 默认值
        assert request.include_details is False  # 默认值
        assert request.format_type == "json"  # 默认值

    def test_from_mcp_arguments_empty(self):
        """测试从空MCP参数创建请求"""
        arguments = {}
        request = AnalysisRequest.from_mcp_arguments(arguments)
        assert request.file_path == ""  # get默认值
        assert request.language is None
        assert request.include_complexity is True
        assert request.include_details is False
        assert request.format_type == "json"

    def test_from_mcp_arguments_extra_fields(self):
        """测试从包含额外字段的MCP参数创建请求"""
        arguments = {
            "file_path": "/path/to/file.py",
            "language": "javascript",
            "extra_field": "ignored",
            "another_field": 123,
        }
        request = AnalysisRequest.from_mcp_arguments(arguments)
        assert request.file_path == "/path/to/file.py"
        assert request.language == "javascript"
        # 额外字段应该被忽略
        assert not hasattr(request, "extra_field")
        assert not hasattr(request, "another_field")

    def test_from_mcp_arguments_none_values(self):
        """测试从包含None值的MCP参数创建请求"""
        arguments = {
            "file_path": "/path/to/file.py",
            "language": None,
            "include_complexity": None,
            "include_details": None,
            "format_type": None,
        }
        request = AnalysisRequest.from_mcp_arguments(arguments)
        assert request.file_path == "/path/to/file.py"
        assert request.language is None
        # None值会被传递
        assert request.include_complexity is None
        assert request.include_details is None
        assert request.format_type is None

    def test_from_mcp_arguments_type_coercion(self):
        """测试MCP参数类型强制转换"""
        arguments = {
            "file_path": "/path/to/file.py",
            "include_complexity": "true",  # 字符串
            "include_details": 1,  # 整数
            "format_type": "json",
        }
        request = AnalysisRequest.from_mcp_arguments(arguments)
        assert request.file_path == "/path/to/file.py"
        # 类型不会被自动转换
        assert request.include_complexity == "true"
        assert request.include_details == 1

    def test_file_path_required(self):
        """测试file_path是必需的"""
        # 在dataclass中file_path没有默认值，所以必须提供
        with pytest.raises(TypeError):
            AnalysisRequest()  # type: ignore

    def test_format_type_variations(self):
        """测试不同的format_type值"""
        formats = ["json", "markdown", "csv", "toon", "text"]
        for fmt in formats:
            request = AnalysisRequest(file_path="/test.py", format_type=fmt)
            assert request.format_type == fmt

    def test_boolean_flags_combinations(self):
        """测试布尔标志的不同组合"""
        combinations = [
            (True, True, True, True),
            (True, True, True, False),
            (True, True, False, True),
            (True, False, True, True),
            (False, True, True, True),
            (False, False, False, False),
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

    def test_queries_list(self):
        """测试queries列表参数"""
        queries_list = ["classes", "functions", "imports", "exports"]
        request = AnalysisRequest(
            file_path="/test.py",
            queries=queries_list,
        )
        assert request.queries == queries_list
        assert isinstance(request.queries, list)

    def test_queries_empty_list(self):
        """测试空的queries列表"""
        request = AnalysisRequest(
            file_path="/test.py",
            queries=[],
        )
        assert request.queries == []
        assert isinstance(request.queries, list)

    def test_language_variations(self):
        """测试不同的language值"""
        languages = ["python", "java", "javascript", "typescript", "go", "rust"]
        for lang in languages:
            request = AnalysisRequest(file_path="/test.py", language=lang)
            assert request.language == lang

    def test_request_immutability_check(self):
        """测试请求对象的可变性（dataclass不是frozen）"""
        request = AnalysisRequest(file_path="/test.py", language="python")
        original_path = request.file_path
        original_language = request.language

        # 修改属性
        request.file_path = "/new/path.py"
        request.language = "java"

        # 验证修改成功
        assert request.file_path != original_path
        assert request.language != original_language
        assert request.file_path == "/new/path.py"
        assert request.language == "java"

    def test_from_mcp_arguments_preserves_defaults(self):
        """测试from_mcp_arguments保留未提供字段的默认值"""
        arguments = {"file_path": "/test.py"}
        request = AnalysisRequest.from_mcp_arguments(arguments)
        assert request.include_elements is True  # 未在from_mcp_arguments中设置
        assert request.include_queries is True  # 未在from_mcp_arguments中设置
        assert request.include_complexity is True  # 默认值
        assert request.include_details is False  # 默认值
        assert request.format_type == "json"  # 默认值

    def test_multiple_from_mcp_calls(self):
        """测试多次调用from_mcp_arguments"""
        args1 = {"file_path": "/test1.py", "language": "python"}
        args2 = {"file_path": "/test2.py", "language": "java"}

        request1 = AnalysisRequest.from_mcp_arguments(args1)
        request2 = AnalysisRequest.from_mcp_arguments(args2)

        assert request1.file_path == "/test1.py"
        assert request1.language == "python"
        assert request2.file_path == "/test2.py"
        assert request2.language == "java"

    def test_from_mcp_arguments_with_special_characters(self):
        """测试MCP参数中的特殊字符"""
        arguments = {
            "file_path": "/path/to/file with spaces.py",
            "language": "python",
        }
        request = AnalysisRequest.from_mcp_arguments(arguments)
        assert request.file_path == "/path/to/file with spaces.py"
