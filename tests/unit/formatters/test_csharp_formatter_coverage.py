#!/usr/bin/env python3
"""Tests for C# formatter to improve coverage."""

import pytest

from tree_sitter_analyzer.formatters.csharp_formatter import CSharpTableFormatter


class TestCSharpTableFormatterFullTable:
    """Test _format_full_table method."""

    def test_single_class_with_namespace(self):
        """Test single class with namespace via full_qualified_name."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "MyClass.cs",
            "classes": [
                {
                    "name": "MyClass",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 50},
                    "full_qualified_name": "MyNamespace.MyClass",
                }
            ],
            "imports": [{"raw_text": "using System;"}],
            "methods": [
                {
                    "name": "DoSomething",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 10, "end": 15},
                }
            ],
            "fields": [
                {
                    "name": "_field",
                    "variable_type": "int",
                    "visibility": "private",
                    "line_range": {"start": 7, "end": 7},
                }
            ],
            "statistics": {"method_count": 1, "field_count": 1},
        }

        result = formatter.format_structure(data)
        assert "MyNamespace.MyClass" in result
        assert "## Imports" in result
        assert "using System;" in result

    def test_single_class_without_namespace(self):
        """Test single class without namespace."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "MyClass.cs",
            "classes": [
                {
                    "name": "MyClass",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "MyClass" in result

    def test_multiple_classes_with_namespace(self):
        """Test multiple classes with namespace."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "MultipleClasses.cs",
            "classes": [
                {
                    "name": "ClassA",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 25},
                    "full_qualified_name": "MyNamespace.ClassA",
                },
                {
                    "name": "ClassB",
                    "class_type": "class",
                    "visibility": "internal",
                    "line_range": {"start": 30, "end": 50},
                },
            ],
            "methods": [
                {
                    "name": "MethodA",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 10, "end": 15},
                },
                {
                    "name": "MethodB",
                    "return_type": "int",
                    "visibility": "private",
                    "parameters": ["int x"],  # String format
                    "line_range": {"start": 35, "end": 40},
                },
            ],
            "fields": [],
            "statistics": {"method_count": 2, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Classes Overview" in result
        assert "ClassA" in result
        assert "ClassB" in result

    def test_multiple_classes_without_namespace(self):
        """Test multiple classes without namespace."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "NoNamespace.cs",
            "classes": [
                {
                    "name": "ClassX",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                },
                {
                    "name": "ClassY",
                    "class_type": "struct",
                    "visibility": "internal",
                    "line_range": {"start": 25, "end": 40},
                },
            ],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "ClassX" in result
        assert "ClassY" in result

    def test_class_with_methods_having_parameters(self):
        """Test class with methods having parameters."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "Calculator.cs",
            "classes": [
                {
                    "name": "Calculator",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 100},
                }
            ],
            "methods": [
                {
                    "name": "Add",
                    "return_type": "int",
                    "visibility": "public",
                    "parameters": ["int a", "int b"],  # String format
                    "line_range": {"start": 5, "end": 10},
                    "is_static": True,
                    "complexity_score": 1,
                },
                {
                    "name": "Subtract",
                    "return_type": "double",
                    "visibility": "private",
                    "parameters": ["double x", "double y"],  # String format
                    "line_range": {"start": 15, "end": 20},
                    "is_static": False,
                    "complexity_score": 3,
                },
            ],
            "fields": [],
            "statistics": {"method_count": 2, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Add" in result
        assert "Subtract" in result

    def test_empty_classes(self):
        """Test data with no classes."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "Empty.cs",
            "classes": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Unknown" in result


class TestCSharpTableFormatterCompactTable:
    """Test _format_compact_table method."""

    def test_compact_with_classes(self):
        """Test compact format with classes."""
        formatter = CSharpTableFormatter("compact")
        data = {
            "file_path": "MyClass.cs",
            "classes": [
                {
                    "name": "MyClass",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "methods": [
                {
                    "name": "DoWork",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": ["string param"],  # String format
                    "line_range": {"start": 10, "end": 20},
                }
            ],
            "fields": [
                {
                    "name": "_data",
                    "variable_type": "List<int>",
                    "visibility": "private",
                    "line_range": {"start": 5, "end": 5},
                }
            ],
            "statistics": {"method_count": 1, "field_count": 1},
        }

        result = formatter.format_structure(data)
        # Compact should have summary structure
        assert "MyClass" in result

    def test_compact_empty_data(self):
        """Test compact format with empty data."""
        formatter = CSharpTableFormatter("compact")
        data = {
            "file_path": "Empty.cs",
            "classes": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert isinstance(result, str)

    def test_compact_multiple_classes(self):
        """Test compact format with multiple classes."""
        formatter = CSharpTableFormatter("compact")
        data = {
            "file_path": "Multiple.cs",
            "classes": [
                {
                    "name": "ClassA",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                },
                {
                    "name": "ClassB",
                    "class_type": "interface",
                    "visibility": "internal",
                    "line_range": {"start": 25, "end": 40},
                },
            ],
            "methods": [
                {
                    "name": "MethodA",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        # Compact format shows method info, not class names
        assert "MethodA" in result


class TestCSharpTableFormatterCSV:
    """Test CSV format."""

    def test_csv_format_basic(self):
        """Test basic CSV output."""
        formatter = CSharpTableFormatter("csv")
        data = {
            "file_path": "Test.cs",
            "classes": [
                {
                    "name": "TestClass",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "methods": [
                {
                    "name": "Method1",
                    "return_type": "string",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                    "complexity_score": 2,
                }
            ],
            "fields": [
                {
                    "name": "Field1",
                    "type": "int",
                    "visibility": "private",
                    "line_range": {"start": 3, "end": 3},
                }
            ],
            "statistics": {"method_count": 1, "field_count": 1},
        }

        result = formatter.format_structure(data)
        # Check CSV has header and rows
        assert "Type" in result
        assert "Name" in result

    def test_csv_format_empty(self):
        """Test CSV with no methods or fields."""
        formatter = CSharpTableFormatter("csv")
        data = {
            "file_path": "Empty.cs",
            "classes": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        # CSV should at least have header
        assert "Type" in result


class TestCSharpTableFormatterHelperMethods:
    """Test helper methods."""

    def test_extract_namespace_with_full_qualified_name(self):
        """Test _extract_namespace with full_qualified_name."""
        formatter = CSharpTableFormatter("full")
        data = {"classes": [{"full_qualified_name": "MyNamespace.SubNS.MyClass"}]}
        result = formatter._extract_namespace(data)
        assert result == "MyNamespace.SubNS"

    def test_extract_namespace_without_dot(self):
        """Test _extract_namespace with no dot in name."""
        formatter = CSharpTableFormatter("full")
        data = {"classes": [{"full_qualified_name": "MyClass"}]}
        result = formatter._extract_namespace(data)
        assert result == "unknown"

    def test_extract_namespace_empty(self):
        """Test _extract_namespace with no namespace."""
        formatter = CSharpTableFormatter("full")
        data = {}
        result = formatter._extract_namespace(data)
        assert result == "unknown"

    def test_get_platform_newline(self):
        """Test _get_platform_newline returns string."""
        formatter = CSharpTableFormatter("full")
        result = formatter._get_platform_newline()
        assert result in ["\n", "\r\n"]

    def test_convert_to_platform_newlines(self):
        """Test _convert_to_platform_newlines."""
        formatter = CSharpTableFormatter("full")
        text = "line1\nline2\nline3"
        result = formatter._convert_to_platform_newlines(text)
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    def test_format_parameter(self):
        """Test _format_parameter method."""
        formatter = CSharpTableFormatter("full")
        result = formatter._format_parameter("int x")
        assert result == "int x"

    def test_format_param_type(self):
        """Test _format_param_type method."""
        formatter = CSharpTableFormatter("full")
        result = formatter._format_param_type("int x")
        assert result == "int"

    def test_format_param_type_empty(self):
        """Test _format_param_type with empty string."""
        formatter = CSharpTableFormatter("full")
        result = formatter._format_param_type("")
        assert result == "?"

    def test_abbreviate_type_simple(self):
        """Test _abbreviate_type with simple types."""
        formatter = CSharpTableFormatter("full")
        assert formatter._abbreviate_type("String") == "string"
        assert formatter._abbreviate_type("Int32") == "int"
        assert formatter._abbreviate_type("Boolean") == "bool"

    def test_abbreviate_type_with_namespace(self):
        """Test _abbreviate_type removes namespace."""
        formatter = CSharpTableFormatter("full")
        result = formatter._abbreviate_type("System.String")
        assert result == "string"

    def test_get_visibility_symbol(self):
        """Test _get_visibility_symbol method."""
        formatter = CSharpTableFormatter("full")
        assert formatter._get_visibility_symbol("public") == "+"
        assert formatter._get_visibility_symbol("private") == "-"
        assert formatter._get_visibility_symbol("protected") == "#"
        assert formatter._get_visibility_symbol("internal") == "~"


class TestCSharpTableFormatterEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_format_type(self):
        """Test with invalid format type."""
        formatter = CSharpTableFormatter("invalid_format")
        data = {"classes": [], "methods": [], "fields": []}
        with pytest.raises(ValueError, match="Unsupported format type"):
            formatter.format_structure(data)

    def test_method_with_no_parameters(self):
        """Test method with empty parameters list."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "Test.cs",
            "classes": [
                {
                    "name": "TestClass",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "methods": [
                {
                    "name": "NoParams",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "NoParams" in result

    def test_class_with_static_methods(self):
        """Test class with static methods."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "StaticClass.cs",
            "classes": [
                {
                    "name": "StaticHelper",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "methods": [
                {
                    "name": "StaticMethod",
                    "return_type": "int",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                    "is_static": True,
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "StaticMethod" in result

    def test_class_with_constructor(self):
        """Test class with constructor."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "WithCtor.cs",
            "classes": [
                {
                    "name": "WithCtor",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "methods": [
                {
                    "name": ".ctor",
                    "return_type": "",
                    "visibility": "public",
                    "parameters": ["int value"],  # String format
                    "line_range": {"start": 5, "end": 10},
                    "is_constructor": True,
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert ".ctor" in result or "WithCtor" in result

    def test_interface_class_type(self):
        """Test interface as class type."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "IMyInterface.cs",
            "classes": [
                {
                    "name": "IMyInterface",
                    "class_type": "interface",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "methods": [
                {
                    "name": "DoSomething",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 3, "end": 3},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "IMyInterface" in result
        assert "interface" in result.lower()

    def test_struct_class_type(self):
        """Test struct as class type."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "MyStruct.cs",
            "classes": [
                {
                    "name": "MyStruct",
                    "class_type": "struct",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "methods": [],
            "fields": [
                {
                    "name": "Value",
                    "variable_type": "int",
                    "visibility": "public",
                    "line_range": {"start": 3, "end": 3},
                }
            ],
            "statistics": {"method_count": 0, "field_count": 1},
        }

        result = formatter.format_structure(data)
        assert "MyStruct" in result
        assert "struct" in result.lower()

    def test_method_with_documentation(self):
        """Test method with documentation."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "Documented.cs",
            "classes": [
                {
                    "name": "Documented",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "methods": [
                {
                    "name": "DocumentedMethod",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 15},
                    "documentation": "This is a documented method.",
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "DocumentedMethod" in result

    def test_field_with_modifiers(self):
        """Test field with modifiers."""
        formatter = CSharpTableFormatter("full")
        data = {
            "file_path": "Modifiers.cs",
            "classes": [
                {
                    "name": "Modifiers",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "methods": [],
            "fields": [
                {
                    "name": "_items",
                    "variable_type": "Dictionary<string, List<int>>",
                    "visibility": "private",
                    "line_range": {"start": 3, "end": 3},
                    "modifiers": ["readonly", "static"],
                }
            ],
            "statistics": {"method_count": 0, "field_count": 1},
        }

        result = formatter.format_structure(data)
        assert "_items" in result


class TestCSharpTableFormatterFormatTypeInit:
    """Test format type initialization."""

    def test_full_format_type(self):
        """Test creating formatter with full format type."""
        formatter = CSharpTableFormatter("full")
        assert formatter.format_type == "full"

    def test_compact_format_type(self):
        """Test creating formatter with compact format type."""
        formatter = CSharpTableFormatter("compact")
        assert formatter.format_type == "compact"

    def test_csv_format_type(self):
        """Test creating formatter with csv format type."""
        formatter = CSharpTableFormatter("csv")
        assert formatter.format_type == "csv"

    def test_default_format_type(self):
        """Test creating formatter with default format type."""
        formatter = CSharpTableFormatter()
        assert formatter.format_type == "full"
