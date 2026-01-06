#!/usr/bin/env python3
"""
Comprehensive Tests for Formatters Module

This module provides complete test coverage for the formatters module,
including base formatter, factory, and language-specific formatters.
"""

import pytest

from tree_sitter_analyzer.formatters.base_formatter import BaseTableFormatter
from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter
from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter


class TestBaseTableFormatter:
    """Test the base table formatter functionality."""

    def test_base_formatter_is_abstract(self):
        """Test that BaseTableFormatter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseTableFormatter()

    def test_base_formatter_interface(self):
        """Test that BaseTableFormatter defines the expected interface."""
        # Check that required methods exist
        assert hasattr(BaseTableFormatter, "format_structure")
        assert hasattr(BaseTableFormatter, "_get_platform_newline")
        assert hasattr(BaseTableFormatter, "_convert_to_platform_newlines")
        assert hasattr(BaseTableFormatter, "_format_full_table")
        assert hasattr(BaseTableFormatter, "_format_compact_table")
        assert hasattr(BaseTableFormatter, "_format_csv")

    def test_platform_newline_detection(self):
        """Test platform newline detection."""

        # Create a concrete implementation for testing
        class TestFormatter(BaseTableFormatter):
            def _format_full_table(self, data):
                return "test"

            def _format_compact_table(self, data):
                return "test"

            def _format_csv(self, data):
                return "test"

        formatter = TestFormatter()
        newline = formatter._get_platform_newline()
        assert isinstance(newline, str)
        assert len(newline) > 0

    def test_newline_conversion(self):
        """Test newline conversion functionality."""

        class TestFormatter(BaseTableFormatter):
            def _format_full_table(self, data):
                return "test"

            def _format_compact_table(self, data):
                return "test"

            def _format_csv(self, data):
                return "test"

        formatter = TestFormatter()
        test_text = "line1\nline2\nline3"
        converted = formatter._convert_to_platform_newlines(test_text)
        assert isinstance(converted, str)
        assert "line1" in converted and "line2" in converted

    def test_format_structure_with_invalid_type(self):
        """Test format_structure with invalid format type."""

        class TestFormatter(BaseTableFormatter):
            def _format_full_table(self, data):
                return "test"

            def _format_compact_table(self, data):
                return "test"

            def _format_csv(self, data):
                return "test"

        formatter = TestFormatter("invalid_type")
        with pytest.raises(ValueError, match="Unsupported format type"):
            formatter.format_structure({})


class TestFormatterRegistry:
    """Test the formatter registry functionality."""

    def test_create_formatter_for_java(self):
        """Test creating formatter for Java language."""
        formatter = FormatterRegistry.get_formatter_for_language("java", "full")
        assert formatter is not None

    def test_create_formatter_for_python(self):
        """Test creating formatter for Python language."""
        formatter = FormatterRegistry.get_formatter_for_language("python", "full")
        assert formatter is not None

    def test_create_formatter_for_javascript(self):
        """Test creating formatter for JavaScript language."""
        formatter = FormatterRegistry.get_formatter_for_language("javascript", "full")
        assert formatter is not None

        # Test alias
        formatter_alias = FormatterRegistry.get_formatter_for_language("js", "full")
        assert formatter_alias is not None

    def test_create_formatter_for_typescript(self):
        """Test creating formatter for TypeScript language."""
        formatter = FormatterRegistry.get_formatter_for_language("typescript", "full")
        assert formatter is not None

        # Test alias
        formatter_alias = FormatterRegistry.get_formatter_for_language("ts", "full")
        assert formatter_alias is not None

    def test_create_formatter_case_insensitive(self):
        """Test that formatter registry is case insensitive."""
        formatter1 = FormatterRegistry.get_formatter_for_language("JAVA", "full")
        formatter2 = FormatterRegistry.get_formatter_for_language("java", "full")
        assert type(formatter1) is type(formatter2)

    def test_create_formatter_with_format_type(self):
        """Test creating formatter with specific format type."""
        formatter = FormatterRegistry.get_formatter_for_language("java", "compact")
        assert formatter.format_type == "compact"

    def test_create_formatter_for_unsupported_language(self):
        """Test creating formatter for unsupported language uses default."""
        formatter = FormatterRegistry.get_formatter_for_language("unsupported", "full")
        assert formatter is not None  # Should fall back to default

    def test_get_supported_languages(self):
        """Test getting list of supported languages."""
        languages = FormatterRegistry.get_supported_languages()
        assert isinstance(languages, list)
        assert "java" in languages
        assert "python" in languages
        assert "javascript" in languages or "js" in languages
        assert "typescript" in languages or "ts" in languages

    def test_is_language_supported(self):
        """Test checking if language is supported."""
        supported_languages = FormatterRegistry.get_supported_languages()
        assert "java" in supported_languages
        assert "python" in supported_languages
        assert "javascript" in supported_languages or "js" in supported_languages
        assert "typescript" in supported_languages or "ts" in supported_languages


class TestJavaTableFormatter:
    """Test Java-specific table formatting functionality."""

    def test_java_formatter_creation(self):
        """Test that JavaTableFormatter can be created."""
        formatter = JavaTableFormatter()
        assert formatter is not None
        assert formatter.format_type == "full"

    def test_java_formatter_with_different_format_types(self):
        """Test JavaTableFormatter with different format types."""
        format_types = ["full", "compact", "csv"]
        for format_type in format_types:
            formatter = JavaTableFormatter(format_type)
            assert formatter.format_type == format_type

    def test_format_java_structure_basic(self):
        """Test formatting a basic Java structure."""
        formatter = JavaTableFormatter()

        # Mock basic structure data
        structure_data = {
            "classes": [
                {
                    "name": "TestClass",
                    "type": "class",
                    "modifiers": ["public"],
                    "start_line": 1,
                    "end_line": 10,
                    "methods": [],
                    "fields": [],
                }
            ],
            "package": {"name": "com.example"},
            "file_path": "TestClass.java",
        }

        result = formatter.format_structure(structure_data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_java_structure_with_methods_and_fields(self):
        """Test formatting Java structure with methods and fields."""
        formatter = JavaTableFormatter()

        # Mock complex data structure
        data = {
            "classes": [
                {
                    "name": "ComplexClass",
                    "type": "class",
                    "modifiers": ["public"],
                    "methods": [
                        {
                            "name": "complexMethod",
                            "modifiers": ["public"],
                            "return_type": "int",
                            "parameters": ["String arg1", "int arg2"],
                        }
                    ],
                    "fields": [
                        {
                            "name": "complexField",
                            "modifiers": ["private"],
                            "field_type": "List<String>",
                        }
                    ],
                }
            ],
            "package": {"name": "com.example"},
            "file_path": "ComplexClass.java",
        }

        result = formatter.format_structure(data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_java_structure_compact(self):
        """Test formatting Java structure in compact format."""
        formatter = JavaTableFormatter("compact")

        structure_data = {
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [{"name": "testMethod"}],
                    "fields": [{"name": "testField"}],
                }
            ],
            "package": {"name": "com.example"},
        }

        result = formatter.format_structure(structure_data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_java_structure_csv(self):
        """Test formatting Java structure in CSV format."""
        formatter = JavaTableFormatter("csv")

        structure_data = {
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [{"name": "testMethod"}],
                    "fields": [{"name": "testField"}],
                }
            ]
        }

        result = formatter.format_structure(structure_data)
        assert isinstance(result, str)
        assert len(result) > 0


class TestPythonTableFormatter:
    """Test Python-specific table formatting functionality."""

    def test_python_formatter_creation(self):
        """Test that PythonTableFormatter can be created."""
        formatter = PythonTableFormatter()
        assert formatter is not None
        assert formatter.format_type == "full"

    def test_python_formatter_with_different_format_types(self):
        """Test PythonTableFormatter with different format types."""
        format_types = ["full", "compact", "csv"]
        for format_type in format_types:
            formatter = PythonTableFormatter(format_type)
            assert formatter.format_type == format_type

    def test_format_python_structure_basic(self):
        """Test formatting a basic Python structure."""
        formatter = PythonTableFormatter()

        # Mock basic structure data
        structure_data = {
            "classes": [
                {
                    "name": "TestClass",
                    "type": "class",
                    "base_classes": ["BaseClass"],
                    "start_line": 1,
                    "end_line": 10,
                    "methods": [],
                    "decorators": [],
                }
            ],
            "functions": [],
            "file_path": "test_class.py",
        }

        result = formatter.format_structure(structure_data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_python_structure_with_functions_and_classes(self):
        """Test formatting complex Python structure."""
        formatter = PythonTableFormatter()

        # Mock complex data structure
        data = {
            "classes": [
                {
                    "name": "ComplexClass",
                    "type": "class",
                    "base_classes": ["BaseClass", "Mixin"],
                    "methods": [
                        {
                            "name": "__init__",
                            "parameters": ["self", "arg1"],
                            "decorators": [],
                        },
                        {
                            "name": "complex_method",
                            "parameters": ["self"],
                            "decorators": ["@property"],
                            "is_async": True,
                        },
                    ],
                }
            ],
            "functions": [
                {
                    "name": "standalone_function",
                    "parameters": ["arg1", "arg2=None"],
                    "decorators": ["@staticmethod"],
                }
            ],
            "file_path": "complex_module.py",
        }

        result = formatter.format_structure(data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_python_structure_compact(self):
        """Test formatting Python structure in compact format."""
        formatter = PythonTableFormatter("compact")

        structure_data = {
            "classes": [{"name": "TestClass", "methods": [{"name": "test_method"}]}],
            "functions": [{"name": "test_function"}],
        }

        result = formatter.format_structure(structure_data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_python_structure_csv(self):
        """Test formatting Python structure in CSV format."""
        formatter = PythonTableFormatter("csv")

        structure_data = {
            "classes": [{"name": "TestClass", "methods": [{"name": "test_method"}]}],
            "functions": [{"name": "test_function"}],
        }

        result = formatter.format_structure(structure_data)
        assert isinstance(result, str)
        assert len(result) > 0


class TestFormatterErrorHandling:
    """Test error handling in formatters."""

    def test_formatter_with_none_data(self):
        """Test formatters handle None data gracefully."""
        formatter = JavaTableFormatter()

        # Should handle None gracefully
        try:
            result = formatter.format_structure(None)
            assert isinstance(result, str)
        except (TypeError, AttributeError):
            # These exceptions are acceptable for None input
            pass

    def test_formatter_with_empty_data(self):
        """Test formatters with empty data structures."""
        formatter = PythonTableFormatter()

        empty_data = {
            "classes": [],
            "functions": [],
            "imports": [],
            "file_path": "empty.py",
        }

        result = formatter.format_structure(empty_data)
        assert isinstance(result, str)
        # Empty data should produce some kind of output (even if minimal)

    def test_formatter_with_malformed_data(self):
        """Test formatters with malformed data structures."""
        formatter = JavaTableFormatter()

        malformed_data = {
            "classes": [
                {
                    "name": None,  # Invalid name
                    "methods": "not_a_list",  # Should be list
                }
            ]
        }

        # Should handle malformed data gracefully
        try:
            result = formatter.format_structure(malformed_data)
            assert isinstance(result, str)
        except (TypeError, AttributeError, KeyError):
            # These exceptions are acceptable for malformed input
            pass


class TestFormatterIntegration:
    """Integration tests for formatter functionality."""

    def test_formatter_with_realistic_java_data(self):
        """Test formatters with realistic Java analysis data."""
        # This would typically come from the analysis engine
        java_data = {
            "classes": [
                {
                    "name": "HelloWorld",
                    "type": "class",
                    "modifiers": ["public"],
                    "start_line": 1,
                    "end_line": 10,
                    "methods": [
                        {
                            "name": "main",
                            "modifiers": ["public", "static"],
                            "return_type": "void",
                            "parameters": ["String[] args"],
                            "start_line": 3,
                            "end_line": 6,
                        }
                    ],
                    "fields": [],
                }
            ],
            "package": {"name": "com.example"},
            "file_path": "HelloWorld.java",
            "imports": [{"statement": "java.util.List"}],
        }

        formatter = FormatterRegistry.get_formatter_for_language("java", "full")
        result = formatter.format_structure(java_data)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_all_format_types_produce_output(self):
        """Test that all format types produce valid output."""
        test_data = {
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [{"name": "testMethod"}],
                    "fields": [{"name": "testField"}],
                }
            ]
        }

        format_types = ["full", "compact", "csv"]
        languages = ["java", "python"]

        for language in languages:
            for format_type in format_types:
                formatter = FormatterRegistry.get_formatter_for_language(
                    language, format_type
                )
                result = formatter.format_structure(test_data)

                assert isinstance(result, str)
                assert len(result) >= 0  # Allow empty string for some formats
