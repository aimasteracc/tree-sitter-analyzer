#!/usr/bin/env python3
"""Tests for Ruby formatter to improve coverage."""

import pytest

from tree_sitter_analyzer.formatters.ruby_formatter import RubyTableFormatter


class TestRubyTableFormatterFullTable:
    """Test _format_full_table method."""

    def test_single_class(self):
        """Test single class."""
        formatter = RubyTableFormatter("full")
        data = {
            "file_path": "my_class.rb",
            "classes": [
                {
                    "name": "MyClass",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "imports": [{"raw_text": "require 'json'"}],
            "methods": [
                {
                    "name": "do_something",
                    "return_type": None,
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                }
            ],
            "fields": [
                {
                    "name": "@field",
                    "variable_type": None,
                    "visibility": "private",
                    "is_constant": False,
                    "line_range": {"start": 3, "end": 3},
                }
            ],
            "statistics": {"method_count": 1, "field_count": 1},
        }

        result = formatter.format_structure(data)
        assert "MyClass" in result
        assert "## Imports" in result

    def test_multiple_classes(self):
        """Test multiple classes."""
        formatter = RubyTableFormatter("full")
        data = {
            "file_path": "multiple_classes.rb",
            "classes": [
                {
                    "name": "ClassA",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 20},
                },
                {
                    "name": "ClassB",
                    "class_type": "class",
                    "line_range": {"start": 25, "end": 45},
                },
            ],
            "methods": [
                {
                    "name": "method_a",
                    "return_type": None,
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                },
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Classes Overview" in result
        assert "ClassA" in result
        assert "ClassB" in result

    def test_module(self):
        """Test module type."""
        formatter = RubyTableFormatter("full")
        data = {
            "file_path": "my_module.rb",
            "classes": [
                {
                    "name": "MyModule",
                    "class_type": "module",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "methods": [
                {
                    "name": "module_method",
                    "return_type": None,
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                    "is_module_function": True,
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "MyModule" in result
        assert "module" in result.lower()

    def test_class_with_constants(self):
        """Test class with constants."""
        formatter = RubyTableFormatter("full")
        data = {
            "file_path": "constants.rb",
            "classes": [
                {
                    "name": "ConstantClass",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "methods": [],
            "fields": [
                {
                    "name": "CONSTANT_VALUE",
                    "variable_type": None,
                    "visibility": "public",
                    "is_constant": True,
                    "line_range": {"start": 3, "end": 3},
                },
                {
                    "name": "@instance_var",
                    "variable_type": None,
                    "visibility": "private",
                    "is_constant": False,
                    "line_range": {"start": 4, "end": 4},
                },
            ],
            "statistics": {"method_count": 0, "field_count": 2},
        }

        result = formatter.format_structure(data)
        assert "ConstantClass" in result

    def test_class_with_methods_and_params(self):
        """Test class with methods having parameters."""
        formatter = RubyTableFormatter("full")
        data = {
            "file_path": "calculator.rb",
            "classes": [
                {
                    "name": "Calculator",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "methods": [
                {
                    "name": "add",
                    "return_type": None,
                    "visibility": "public",
                    "parameters": ["a", "b"],  # String format
                    "line_range": {"start": 5, "end": 10},
                },
                {
                    "name": "subtract",
                    "return_type": None,
                    "visibility": "private",
                    "parameters": ["x", "y"],  # String format
                    "line_range": {"start": 15, "end": 20},
                },
            ],
            "fields": [],
            "statistics": {"method_count": 2, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "add" in result
        assert "subtract" in result

    def test_empty_classes(self):
        """Test data with no classes."""
        formatter = RubyTableFormatter("full")
        data = {
            "file_path": "empty.rb",
            "classes": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Unknown" in result

    def test_singleton_class(self):
        """Test singleton class."""
        formatter = RubyTableFormatter("full")
        data = {
            "file_path": "singleton.rb",
            "classes": [
                {
                    "name": "SingletonClass",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "methods": [
                {
                    "name": "instance",
                    "return_type": None,
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                    "is_class_method": True,
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "SingletonClass" in result


class TestRubyTableFormatterCompactTable:
    """Test _format_compact_table method."""

    def test_compact_with_classes(self):
        """Test compact format with classes."""
        formatter = RubyTableFormatter("compact")
        data = {
            "file_path": "my_class.rb",
            "classes": [
                {
                    "name": "MyClass",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "methods": [
                {
                    "name": "do_work",
                    "return_type": None,
                    "visibility": "public",
                    "parameters": ["param"],  # String format
                    "line_range": {"start": 10, "end": 20},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "MyClass" in result

    def test_compact_empty_data(self):
        """Test compact format with empty data."""
        formatter = RubyTableFormatter("compact")
        data = {
            "file_path": "empty.rb",
            "classes": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert isinstance(result, str)

    def test_compact_multiple_classes(self):
        """Test compact format with multiple classes."""
        formatter = RubyTableFormatter("compact")
        data = {
            "file_path": "multiple.rb",
            "classes": [
                {
                    "name": "ClassA",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 20},
                },
                {
                    "name": "ClassB",
                    "class_type": "module",
                    "line_range": {"start": 25, "end": 40},
                },
            ],
            "methods": [
                {
                    "name": "method_a",
                    "return_type": None,
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "ClassA" in result


class TestRubyTableFormatterCSV:
    """Test CSV format."""

    def test_csv_format_basic(self):
        """Test basic CSV output."""
        formatter = RubyTableFormatter("csv")
        data = {
            "file_path": "test.rb",
            "classes": [
                {
                    "name": "TestClass",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "methods": [
                {
                    "name": "method1",
                    "return_type": None,
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                    "complexity_score": 2,
                }
            ],
            "fields": [
                {
                    "name": "@field1",
                    "type": None,
                    "visibility": "private",
                    "is_constant": False,
                    "line_range": {"start": 3, "end": 3},
                }
            ],
            "statistics": {"method_count": 1, "field_count": 1},
        }

        result = formatter.format_structure(data)
        assert "Type" in result
        assert "Name" in result

    def test_csv_format_empty(self):
        """Test CSV with no methods or fields."""
        formatter = RubyTableFormatter("csv")
        data = {
            "file_path": "empty.rb",
            "classes": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Type" in result


class TestRubyTableFormatterHelperMethods:
    """Test helper methods."""

    def test_get_platform_newline(self):
        """Test _get_platform_newline returns string."""
        formatter = RubyTableFormatter("full")
        result = formatter._get_platform_newline()
        assert result in ["\n", "\r\n"]

    def test_convert_to_platform_newlines(self):
        """Test _convert_to_platform_newlines."""
        formatter = RubyTableFormatter("full")
        text = "line1\nline2\nline3"
        result = formatter._convert_to_platform_newlines(text)
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result


class TestRubyTableFormatterEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_format_type(self):
        """Test with invalid format type."""
        formatter = RubyTableFormatter("invalid_format")
        data = {"classes": [], "methods": [], "fields": []}
        with pytest.raises(ValueError, match="Unsupported format type"):
            formatter.format_structure(data)

    def test_method_with_block(self):
        """Test method with block parameter."""
        formatter = RubyTableFormatter("full")
        data = {
            "file_path": "block_method.rb",
            "classes": [
                {
                    "name": "BlockHandler",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "methods": [
                {
                    "name": "each_item",
                    "return_type": None,
                    "visibility": "public",
                    "parameters": ["&block"],  # String format
                    "line_range": {"start": 5, "end": 15},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "each_item" in result

    def test_method_with_splat(self):
        """Test method with splat parameter."""
        formatter = RubyTableFormatter("full")
        data = {
            "file_path": "splat_method.rb",
            "classes": [
                {
                    "name": "SplatHandler",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "methods": [
                {
                    "name": "variadic_method",
                    "return_type": None,
                    "visibility": "public",
                    "parameters": ["*args"],  # String format
                    "line_range": {"start": 5, "end": 15},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "variadic_method" in result

    def test_class_with_inheritance(self):
        """Test class with inheritance."""
        formatter = RubyTableFormatter("full")
        data = {
            "file_path": "derived.rb",
            "classes": [
                {
                    "name": "DerivedClass",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 30},
                    "base_classes": ["BaseClass"],
                }
            ],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "DerivedClass" in result


class TestRubyTableFormatterFormatTypeInit:
    """Test format type initialization."""

    def test_full_format_type(self):
        """Test creating formatter with full format type."""
        formatter = RubyTableFormatter("full")
        assert formatter.format_type == "full"

    def test_compact_format_type(self):
        """Test creating formatter with compact format type."""
        formatter = RubyTableFormatter("compact")
        assert formatter.format_type == "compact"

    def test_csv_format_type(self):
        """Test creating formatter with csv format type."""
        formatter = RubyTableFormatter("csv")
        assert formatter.format_type == "csv"

    def test_default_format_type(self):
        """Test creating formatter with default format type."""
        formatter = RubyTableFormatter()
        assert formatter.format_type == "full"
