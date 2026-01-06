#!/usr/bin/env python3
"""
Unit tests for formatter_factory module.

Tests for TableFormatterFactory class and create_table_formatter function.
"""

from tree_sitter_analyzer.formatters.base_formatter import BaseTableFormatter
from tree_sitter_analyzer.formatters.formatter_factory import (
    TableFormatterFactory,
    create_table_formatter,
)
from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter
from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)
from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter
from tree_sitter_analyzer.formatters.typescript_formatter import (
    TypeScriptTableFormatter,
)


class TestTableFormatterFactory:
    """测试 TableFormatterFactory 类"""

    def test_get_supported_languages(self):
        """测试获取支持的语言列表"""
        languages = TableFormatterFactory.get_supported_languages()

        # Should include the supported languages
        assert "java" in languages
        assert "javascript" in languages
        assert "js" in languages  # Alias
        assert "python" in languages
        assert "typescript" in languages
        assert "ts" in languages  # Alias

    def test_create_formatter_java(self):
        """测试创建Java格式化器"""
        formatter = TableFormatterFactory.create_formatter("java", "full")

        assert isinstance(formatter, JavaTableFormatter)
        assert formatter.format_type == "full"

    def test_create_formatter_javascript(self):
        """测试创建JavaScript格式化器"""
        formatter = TableFormatterFactory.create_formatter("javascript", "compact")

        assert isinstance(formatter, JavaScriptTableFormatter)
        assert formatter.format_type == "compact"

    def test_create_formatter_js_alias(self):
        """测试创建JavaScript格式化器（js别名）"""
        formatter = TableFormatterFactory.create_formatter("js", "full")

        assert isinstance(formatter, JavaScriptTableFormatter)
        assert formatter.format_type == "full"

    def test_create_formatter_python(self):
        """测试创建Python格式化器"""
        formatter = TableFormatterFactory.create_formatter("python", "csv")

        assert isinstance(formatter, PythonTableFormatter)
        assert formatter.format_type == "csv"

    def test_create_formatter_typescript(self):
        """测试创建TypeScript格式化器"""
        formatter = TableFormatterFactory.create_formatter("typescript", "full")

        assert isinstance(formatter, TypeScriptTableFormatter)
        assert formatter.format_type == "full"

    def test_create_formatter_ts_alias(self):
        """测试创建TypeScript格式化器（ts别名）"""
        formatter = TableFormatterFactory.create_formatter("ts", "compact")

        assert isinstance(formatter, TypeScriptTableFormatter)
        assert formatter.format_type == "compact"

    def test_create_formatter_case_insensitive(self):
        """测试创建格式化器（大小写不敏感）"""
        formatter1 = TableFormatterFactory.create_formatter("Java", "full")
        formatter2 = TableFormatterFactory.create_formatter("JAVA", "full")
        formatter3 = TableFormatterFactory.create_formatter("java", "full")

        # All should create Java formatter
        assert isinstance(formatter1, JavaTableFormatter)
        assert isinstance(formatter2, JavaTableFormatter)
        assert isinstance(formatter3, JavaTableFormatter)

    def test_create_formatter_unsupported_language(self):
        """测试创建不支持的语言（默认使用Java）"""
        formatter = TableFormatterFactory.create_formatter("unknown", "full")

        # Should default to Java formatter
        assert isinstance(formatter, JavaTableFormatter)
        assert formatter.format_type == "full"

    def test_create_formatter_default_format_type(self):
        """测试创建格式化器（默认格式类型）"""
        formatter = TableFormatterFactory.create_formatter("python")

        assert isinstance(formatter, PythonTableFormatter)
        # Should use default format_type "full"
        assert formatter.format_type == "full"

    def test_create_formatter_csv_format(self):
        """测试创建CSV格式化器"""
        formatter = TableFormatterFactory.create_formatter("java", "csv")

        assert isinstance(formatter, JavaTableFormatter)
        assert formatter.format_type == "csv"

    def test_register_formatter(self):
        """测试注册新格式化器"""

        # Create a custom formatter class
        class CustomFormatter(BaseTableFormatter):
            def _format_full_table(self, data):
                return "Custom full"

            def _format_compact_table(self, data):
                return "Custom compact"

        # Register it
        TableFormatterFactory.register_formatter("custom", CustomFormatter)

        # Try to create it
        formatter = TableFormatterFactory.create_formatter("custom", "full")

        assert isinstance(formatter, CustomFormatter)
        assert formatter.format_type == "full"

    def test_register_formatter_case_insensitive(self):
        """测试注册格式化器（大小写不敏感）"""

        class CustomFormatter(BaseTableFormatter):
            def _format_full_table(self, data):
                return "Custom full"

            def _format_compact_table(self, data):
                return "Custom compact"

        # Register with uppercase
        TableFormatterFactory.register_formatter("CUSTOM2", CustomFormatter)

        # Should be able to create with lowercase
        formatter = TableFormatterFactory.create_formatter("custom2", "full")

        assert isinstance(formatter, CustomFormatter)

    def test_register_formatter_overwrites_existing(self):
        """测试注册格式化器覆盖已存在的"""

        # Register a custom formatter for an existing language
        class CustomJavaFormatter(BaseTableFormatter):
            def _format_full_table(self, data):
                return "Custom Java full"

            def _format_compact_table(self, data):
                return "Custom Java compact"

        TableFormatterFactory.register_formatter("java", CustomJavaFormatter)

        # Should create the custom formatter instead of JavaTableFormatter
        formatter = TableFormatterFactory.create_formatter("java", "full")

        assert isinstance(formatter, CustomJavaFormatter)
        assert not isinstance(formatter, JavaTableFormatter)

    def test_get_supported_languages_includes_registered(self):
        """测试获取支持的语言列表（包括已注册的）"""

        class CustomFormatter(BaseTableFormatter):
            def _format_full_table(self, data):
                return "Custom full"

            def _format_compact_table(self, data):
                return "Custom compact"

        # Register a new language
        TableFormatterFactory.register_formatter("customlang", CustomFormatter)

        # Get supported languages
        languages = TableFormatterFactory.get_supported_languages()

        # Should include the newly registered language
        assert "customlang" in languages


class TestCreateTableFormatter:
    """测试 create_table_formatter 函数"""

    def test_create_table_formatter_default(self):
        """测试创建表格格式化器（默认参数）"""
        formatter = create_table_formatter("full")

        # Should default to Java language
        assert isinstance(formatter, JavaTableFormatter)
        assert formatter.format_type == "full"

    def test_create_table_formatter_with_language(self):
        """测试创建表格格式化器（指定语言）"""
        formatter = create_table_formatter("compact", "python")

        assert isinstance(formatter, PythonTableFormatter)
        assert formatter.format_type == "compact"

    def test_create_table_formatter_full(self):
        """测试创建完整表格格式化器"""
        formatter = create_table_formatter("full", "javascript")

        assert isinstance(formatter, JavaScriptTableFormatter)
        assert formatter.format_type == "full"

    def test_create_table_formatter_compact(self):
        """测试创建紧凑表格格式化器"""
        formatter = create_table_formatter("compact", "typescript")

        assert isinstance(formatter, TypeScriptTableFormatter)
        assert formatter.format_type == "compact"

    def test_create_table_formatter_csv(self):
        """测试创建CSV表格格式化器"""
        formatter = create_table_formatter("csv", "python")

        assert isinstance(formatter, PythonTableFormatter)
        assert formatter.format_type == "csv"

    def test_create_table_formatter_unsupported_language(self):
        """测试创建表格格式化器（不支持的语言）"""
        formatter = create_table_formatter("full", "unknown")

        # Should default to Java
        assert isinstance(formatter, JavaTableFormatter)
        assert formatter.format_type == "full"

    def test_create_table_formatter_case_insensitive(self):
        """测试创建表格格式化器（大小写不敏感）"""
        formatter = create_table_formatter("full", "PYTHON")

        assert isinstance(formatter, PythonTableFormatter)


class TestIntegration:
    """测试集成场景"""

    def test_full_workflow(self):
        """测试完整工作流"""
        # Get supported languages
        languages = TableFormatterFactory.get_supported_languages()
        assert len(languages) > 0

        # Create formatters for each language
        for language in ["java", "python", "javascript", "typescript"]:
            formatter = TableFormatterFactory.create_formatter(language, "full")
            assert isinstance(formatter, BaseTableFormatter)
            assert formatter.format_type == "full"

    def test_multiple_format_types(self):
        """测试多种格式类型"""
        for format_type in ["full", "compact", "csv"]:
            formatter = TableFormatterFactory.create_formatter("java", format_type)
            assert formatter.format_type == format_type

    def test_function_wrapper_consistency(self):
        """测试函数包装器一致性"""
        # Both should create the same type of formatter
        formatter1 = TableFormatterFactory.create_formatter("python", "full")
        formatter2 = create_table_formatter("full", "python")

        assert type(formatter1) is type(formatter2)
        assert formatter1.format_type == formatter2.format_type
