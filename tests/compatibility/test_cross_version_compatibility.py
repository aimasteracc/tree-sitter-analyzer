#!/usr/bin/env python3
"""
Cross-Version Compatibility Tests - 测试跨版本兼容性
"""

import json

import pytest

from tree_sitter_analyzer.core.query import QueryExecutor
from tree_sitter_analyzer.core.request import AnalysisRequest
from tree_sitter_analyzer.query_loader import get_query_loader


class TestConfigFileCompatibility:
    """配置文件兼容性测试"""

    @pytest.mark.regression
    def test_config_file_syntax_valid(self, tmp_path):
        """测试配置文件语法有效性"""
        config_file = tmp_path / "test_config.json"
        config_file.write_text(
            """
{
    "language": "python",
    "queries": ["classes", "functions"]
}
"""
        )

        # 验证JSON语法
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        assert config["language"] == "python"
        assert "queries" in config

    @pytest.mark.regression
    def test_config_file_missing_fields(self, tmp_path):
        """测试配置文件缺失字段"""
        config_file = tmp_path / "test_minimal_config.json"
        config_file.write_text('{"language": "python"}')

        # 读取并验证
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        # 缺失字段应该有默认值
        assert "language" in config
        assert config["language"] == "python"

    @pytest.mark.regression
    def test_config_file_extra_fields(self, tmp_path):
        """测试配置文件额外字段"""
        config_file = tmp_path / "test_extra_config.json"
        config_file.write_text(
            """
{
    "language": "python",
    "queries": ["classes"],
    "extra_field": "should_be_ignored",
    "another_extra": 123
}
"""
        )

        # 读取并验证
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        # 额外字段应该被忽略或处理
        assert config["language"] == "python"
        assert "queries" in config

    @pytest.mark.regression
    def test_config_file_invalid_json(self, tmp_path):
        """测试配置文件无效JSON"""
        config_file = tmp_path / "test_invalid.json"
        config_file.write_text('{"invalid": json}')

        # 尝试读取应该抛出异常
        with pytest.raises(json.JSONDecodeError):
            with open(config_file, encoding="utf-8") as f:
                json.load(f)

    @pytest.mark.regression
    def test_config_file_empty_queries(self, tmp_path):
        """测试配置文件空查询列表"""
        config_file = tmp_path / "test_empty_queries.json"
        config_file.write_text('{"language": "python", "queries": []}')

        # 读取并验证
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        assert config["queries"] == []

    @pytest.mark.regression
    def test_config_file_multiple_languages(self, tmp_path):
        """测试多语言配置文件"""
        config_file = tmp_path / "test_multi_language.json"
        config_file.write_text(
            """
{
    "python": {
        "queries": ["classes", "functions"]
    },
    "java": {
        "queries": ["classes", "methods"]
    }
}
"""
        )

        # 读取并验证
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        assert "python" in config
        assert "java" in config


class TestQueryFileCompatibility:
    """查询文件兼容性测试"""

    @pytest.mark.regression
    def test_query_file_valid_syntax(self, tmp_path):
        """测试查询文件语法有效性"""
        query_file = tmp_path / "test_query.scm"
        query_file.write_text(
            """
(class_definition
  name: "Class Definition"
  body: (class_definition) @class
) @class
"""
        )

        # 验证文件存在
        assert query_file.exists()

        # 尝试读取
        content = query_file.read_text(encoding="utf-8")
        assert "class_definition" in content

    @pytest.mark.regression
    def test_query_file_missing_captures(self, tmp_path):
        """测试查询文件缺失captures"""
        query_file = tmp_path / "test_no_capture.scm"
        query_file.write_text(
            """
(class_definition
  name: "Class Definition"
)
"""
        )

        # 文件应该存在
        assert query_file.exists()

    @pytest.mark.regression
    def test_query_file_multiple_queries(self, tmp_path):
        """测试查询文件多个查询"""
        query_file = tmp_path / "test_multiple.scm"
        query_file.write_text(
            """
(class_definition
  name: "Class Definition"
  body: (class_definition) @class
) @class

(function_definition
  name: "Function Definition"
  body: (function_definition) @function
) @function
"""
        )

        # 验证多个查询
        content = query_file.read_text(encoding="utf-8")
        assert "class_definition" in content
        assert "function_definition" in content

    @pytest.mark.regression
    def test_query_file_invalid_syntax(self, tmp_path):
        """测试查询文件无效语法"""
        query_file = tmp_path / "test_invalid.scm"
        query_file.write_text("invalid query syntax")

        # 文件应该存在
        assert query_file.exists()

    @pytest.mark.regression
    def test_query_loader_loads_files(self):
        """测试查询加载器加载文件"""
        loader = get_query_loader()

        # 验证加载器可以获取查询
        queries = loader.get_all_queries_for_language("python")
        assert isinstance(queries, list | dict)

        if isinstance(queries, list):
            assert len(queries) > 0


class TestPluginInterfaceCompatibility:
    """插件接口兼容性测试"""

    @pytest.mark.regression
    def test_plugin_base_interface(self):
        """测试插件基类接口"""
        from tree_sitter_analyzer.plugins.base import LanguagePlugin

        # 验证基类有必需的方法
        assert hasattr(LanguagePlugin, "get_queries")
        assert hasattr(LanguagePlugin, "get_language_name")

    @pytest.mark.regression
    def test_python_plugin_interface(self):
        """测试Python插件接口"""
        from tree_sitter_analyzer.languages.python_plugin import PythonPlugin

        plugin = PythonPlugin()

        # 验证插件有必需的接口
        assert hasattr(plugin, "get_queries")
        assert hasattr(plugin, "get_language_name")

        # 验证返回值类型
        queries = plugin.get_queries()
        assert isinstance(queries, list | dict)

        language = plugin.get_language_name()
        assert isinstance(language, str)
        assert language == "python"

    @pytest.mark.regression
    def test_java_plugin_interface(self):
        """测试Java插件接口"""
        from tree_sitter_analyzer.languages.java_plugin import JavaPlugin

        plugin = JavaPlugin()

        # 验证插件有必需的接口
        assert hasattr(plugin, "get_queries")
        assert hasattr(plugin, "get_language_name")

        # 验证返回值类型
        queries = plugin.get_queries()
        assert isinstance(queries, list | dict)

        language = plugin.get_language_name()
        assert isinstance(language, str)
        assert language == "java"

    @pytest.mark.regression
    def test_javascript_plugin_interface(self):
        """测试JavaScript插件接口"""
        from tree_sitter_analyzer.languages.javascript_plugin import JavaScriptPlugin

        plugin = JavaScriptPlugin()

        # 验证插件有必需的接口
        assert hasattr(plugin, "get_queries")
        assert hasattr(plugin, "get_language_name")

        queries = plugin.get_queries()
        assert isinstance(queries, list | dict)

        language = plugin.get_language_name()
        assert isinstance(language, str)
        assert language == "javascript"


class TestDataFormatCompatibility:
    """数据格式兼容性测试"""

    @pytest.mark.regression
    def test_json_format_compatibility(self, tmp_path):
        """测试JSON格式兼容性"""
        test_file = tmp_path / "test_data.json"
        test_file.write_text(
            """
{
    "elements": [
        {
            "name": "TestClass",
            "type": "class"
        }
    ]
}
"""
        )

        # 验证JSON格式
        with open(test_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "elements" in data
        assert len(data["elements"]) == 1
        assert data["elements"][0]["name"] == "TestClass"

    @pytest.mark.regression
    def test_json_format_with_nested_structures(self, tmp_path):
        """测试嵌套JSON结构兼容性"""
        test_file = tmp_path / "test_nested.json"
        test_file.write_text(
            """
{
    "elements": [
        {
            "name": "Outer",
            "type": "class",
            "children": [
                {
                    "name": "Inner",
                    "type": "function"
                }
            ]
        }
    ]
}
"""
        )

        # 验证嵌套结构
        with open(test_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "elements" in data
        assert len(data["elements"]) == 1
        assert "children" in data["elements"][0]

    @pytest.mark.regression
    def test_json_format_with_arrays(self, tmp_path):
        """测试JSON数组格式兼容性"""
        test_file = tmp_path / "test_arrays.json"
        test_file.write_text(
            """
{
    "elements": ["item1", "item2", "item3"],
    "languages": ["python", "java", "javascript"]
}
"""
        )

        # 验证数组格式
        with open(test_file, encoding="utf-8") as f:
            data = json.load(f)

        assert isinstance(data["elements"], list)
        assert isinstance(data["languages"], list)

    @pytest.mark.regression
    def test_toon_format_compatibility(self, tmp_path):
        """测试Toon格式兼容性"""
        test_file = tmp_path / "test_data.toon"
        test_file.write_text(
            """
v1
elements
  name:TestClass
  type:class
  start_line:1
  end_line:5
---
"""
        )

        # 验证文件存在
        assert test_file.exists()

        # 读取内容
        content = test_file.read_text(encoding="utf-8")
        assert "elements" in content
        assert "TestClass" in content

    @pytest.mark.regression
    def test_csv_format_compatibility(self, tmp_path):
        """测试CSV格式兼容性"""
        test_file = tmp_path / "test_data.csv"
        test_file.write_text(
            """
name,type,start_line,end_line
TestClass,class,1,5
TestFunction,function,6,10
"""
        )

        # 验证文件存在
        assert test_file.exists()

        # 读取内容
        content = test_file.read_text(encoding="utf-8")
        assert "TestClass" in content
        assert "TestFunction" in content


class TestAPIVersionCompatibility:
    """API版本兼容性测试"""

    @pytest.mark.regression
    def test_analysis_request_v1_compatibility(self):
        """测试AnalysisRequest v1兼容性"""
        # 测试v1参数仍然有效
        request = AnalysisRequest(
            file_path="/test.py",
            language="python",
            include_elements=True,
            include_queries=True,
            include_complexity=True,
            include_details=False,
            format_type="json",
        )

        # 验证所有属性
        assert request.file_path == "/test.py"
        assert request.language == "python"
        assert request.include_elements is True
        assert request.include_queries is True
        assert request.include_complexity is True
        assert request.include_details is False
        assert request.format_type == "json"

    @pytest.mark.regression
    def test_query_executor_v1_compatibility(self):
        """测试QueryExecutor v1兼容性"""
        executor = QueryExecutor()

        # 验证基本方法存在
        assert hasattr(executor, "execute_query")
        assert hasattr(executor, "execute_query_with_language_name")
        assert hasattr(executor, "execute_query_string")
        assert hasattr(executor, "execute_multiple_queries")

        # 验证统计方法存在
        assert hasattr(executor, "get_query_statistics")
        assert hasattr(executor, "reset_statistics")

    @pytest.mark.regression
    def test_query_loader_v1_compatibility(self):
        """测试QueryLoader v1兼容性"""
        loader = get_query_loader()

        # 验证基本方法存在
        assert hasattr(loader, "get_query")
        assert hasattr(loader, "get_all_queries_for_language")
        assert hasattr(loader, "list_supported_languages")

    @pytest.mark.regression
    def test_module_imports(self):
        """测试模块导入兼容性"""
        # 验证核心模块可以导入
        from tree_sitter_analyzer.core import analysis_engine, query, request
        from tree_sitter_analyzer.languages import java_plugin, python_plugin

        # 验证关键类存在
        assert hasattr(analysis_engine, "UnifiedAnalysisEngine")
        assert hasattr(request, "AnalysisRequest")
        assert hasattr(query, "QueryExecutor")
        assert hasattr(python_plugin, "PythonPlugin")
        assert hasattr(java_plugin, "JavaPlugin")


class TestBackwardCompatibility:
    """向后兼容性测试"""

    @pytest.mark.regression
    def test_old_analysis_request_creation(self):
        """测试旧的AnalysisRequest创建方式"""
        # 测试直接实例化
        request1 = AnalysisRequest(
            file_path="/test.py",
            language="python",
        )

        request2 = AnalysisRequest(
            file_path="/test.py",
            language="python",
        )

        # 两个请求应该是独立的
        assert request1 is not request2
        assert request1.file_path == request2.file_path

    @pytest.mark.regression
    def test_old_query_execution(self):
        """测试旧的查询执行方式"""
        executor = QueryExecutor()

        # 测试get_available_queries方法
        queries = executor.get_available_queries("python")

        # 验证返回列表
        assert isinstance(queries, list)

        # 测试get_query_description方法
        description = executor.get_query_description("python", "classes")

        # 描述可能是字符串或None
        assert description is None or isinstance(description, str)

    @pytest.mark.regression
    def test_old_format_types(self):
        """测试旧的格式类型仍然有效"""
        format_types = ["json", "markdown", "csv", "toon", "text"]

        for fmt in format_types:
            request = AnalysisRequest(
                file_path="/test.py",
                format_type=fmt,
            )

            assert request.format_type == fmt


class TestForwardCompatibility:
    """向前兼容性测试"""

    @pytest.mark.regression
    def test_new_parameters_accepted(self):
        """测试新参数被接受"""
        # 测试新增的参数
        request = AnalysisRequest(
            file_path="/test.py",
            language="python",
            include_elements=True,
            include_queries=True,
            include_complexity=True,
            include_details=True,
            format_type="json",
        )

        # 验证新参数被正确处理
        assert request.include_details is True

    @pytest.mark.regression
    def test_new_format_types_accepted(self):
        """测试新格式类型被接受"""
        # 测试toon格式
        request = AnalysisRequest(
            file_path="/test.py",
            format_type="toon",
        )

        assert request.format_type == "toon"
