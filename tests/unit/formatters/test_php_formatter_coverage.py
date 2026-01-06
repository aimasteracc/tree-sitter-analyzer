#!/usr/bin/env python3
"""Tests for PHP formatter to improve coverage."""

import pytest

from tree_sitter_analyzer.formatters.php_formatter import PHPTableFormatter


class TestPHPTableFormatterFullTable:
    """Test _format_full_table method."""

    def test_single_class_with_namespace(self):
        """Test single class with namespace via full_qualified_name."""
        formatter = PHPTableFormatter("full")
        data = {
            "file_path": "MyClass.php",
            "classes": [
                {
                    "name": "MyClass",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 50},
                    "full_qualified_name": "MyNamespace\\MyClass",
                }
            ],
            "imports": [{"raw_text": "use Namespace\\OtherClass;"}],
            "methods": [
                {
                    "name": "doSomething",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 10, "end": 15},
                }
            ],
            "fields": [
                {
                    "name": "$field",
                    "variable_type": "int",
                    "visibility": "private",
                    "line_range": {"start": 7, "end": 7},
                }
            ],
            "statistics": {"method_count": 1, "field_count": 1},
        }

        result = formatter.format_structure(data)
        assert "MyClass" in result
        assert "## Imports" in result

    def test_single_class_without_namespace(self):
        """Test single class without namespace."""
        formatter = PHPTableFormatter("full")
        data = {
            "file_path": "MyClass.php",
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
        formatter = PHPTableFormatter("full")
        data = {
            "file_path": "MultipleClasses.php",
            "classes": [
                {
                    "name": "ClassA",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 25},
                    "full_qualified_name": "MyNamespace\\ClassA",
                },
                {
                    "name": "ClassB",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 30, "end": 50},
                },
            ],
            "methods": [
                {
                    "name": "methodA",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 10, "end": 15},
                },
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Classes Overview" in result
        assert "ClassA" in result
        assert "ClassB" in result

    def test_multiple_classes_without_namespace(self):
        """Test multiple classes without namespace."""
        formatter = PHPTableFormatter("full")
        data = {
            "file_path": "NoNamespace.php",
            "classes": [
                {
                    "name": "ClassX",
                    "class_type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                },
                {
                    "name": "ClassY",
                    "class_type": "trait",
                    "visibility": "public",
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

    def test_class_with_trait(self):
        """Test class with trait type."""
        formatter = PHPTableFormatter("full")
        data = {
            "file_path": "MyTrait.php",
            "classes": [
                {
                    "name": "MyTrait",
                    "class_type": "trait",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "methods": [
                {
                    "name": "traitMethod",
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
        assert "MyTrait" in result
        assert "trait" in result.lower()

    def test_interface(self):
        """Test interface type."""
        formatter = PHPTableFormatter("full")
        data = {
            "file_path": "MyInterface.php",
            "classes": [
                {
                    "name": "MyInterface",
                    "class_type": "interface",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "methods": [
                {
                    "name": "doSomething",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 5},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "MyInterface" in result
        assert "interface" in result.lower()

    def test_class_with_methods_and_params(self):
        """Test class with methods having parameters."""
        formatter = PHPTableFormatter("full")
        data = {
            "file_path": "Calculator.php",
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
                    "name": "add",
                    "return_type": "int",
                    "visibility": "public",
                    "parameters": ["int $a", "int $b"],  # String format
                    "line_range": {"start": 5, "end": 10},
                    "is_static": True,
                },
                {
                    "name": "subtract",
                    "return_type": "float",
                    "visibility": "private",
                    "parameters": ["float $x", "float $y"],  # String format
                    "line_range": {"start": 15, "end": 20},
                    "is_static": False,
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
        formatter = PHPTableFormatter("full")
        data = {
            "file_path": "Empty.php",
            "classes": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        # New format uses filename as header when no classes
        assert "Empty.php" in result


class TestPHPTableFormatterCompactTable:
    """Test _format_compact_table method."""

    def test_compact_with_classes(self):
        """Test compact format with classes."""
        formatter = PHPTableFormatter("compact")
        data = {
            "file_path": "MyClass.php",
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
                    "name": "doWork",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": ["string $param"],  # String format
                    "line_range": {"start": 10, "end": 20},
                }
            ],
            "fields": [
                {
                    "name": "$data",
                    "variable_type": "array",
                    "visibility": "private",
                    "line_range": {"start": 5, "end": 5},
                }
            ],
            "statistics": {"method_count": 1, "field_count": 1},
        }

        result = formatter.format_structure(data)
        assert "MyClass" in result

    def test_compact_empty_data(self):
        """Test compact format with empty data."""
        formatter = PHPTableFormatter("compact")
        data = {
            "file_path": "Empty.php",
            "classes": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert isinstance(result, str)

    def test_compact_multiple_classes(self):
        """Test compact format with multiple classes."""
        formatter = PHPTableFormatter("compact")
        data = {
            "file_path": "Multiple.php",
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
                    "visibility": "public",
                    "line_range": {"start": 25, "end": 40},
                },
            ],
            "methods": [
                {
                    "name": "methodA",
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
        # Compact format shows methods, may not list all class names explicitly
        assert "Multiple.php" in result
        assert "methodA" in result


class TestPHPTableFormatterCSV:
    """Test CSV format."""

    def test_csv_format_basic(self):
        """Test basic CSV output."""
        formatter = PHPTableFormatter("csv")
        data = {
            "file_path": "Test.php",
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
                    "name": "method1",
                    "return_type": "string",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 10},
                    "complexity_score": 2,
                }
            ],
            "fields": [
                {
                    "name": "$field1",
                    "type": "int",
                    "visibility": "private",
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
        formatter = PHPTableFormatter("csv")
        data = {
            "file_path": "Empty.php",
            "classes": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Type" in result


class TestPHPTableFormatterHelperMethods:
    """Test helper methods."""

    def test_extract_namespace_with_metadata(self):
        """Test _extract_namespace with metadata namespace."""
        formatter = PHPTableFormatter("full")
        data = {"classes": [{"metadata": {"namespace": "MyNamespace"}}]}
        result = formatter._extract_namespace(data)
        assert result == "MyNamespace"

    def test_extract_namespace_from_method_metadata(self):
        """Test _extract_namespace from method metadata (no longer supported)."""
        formatter = PHPTableFormatter("full")
        data = {
            "classes": [],
            "methods": [{"metadata": {"namespace": "MethodNamespace"}}],
        }
        result = formatter._extract_namespace(data)
        # New implementation only extracts from classes, not methods
        assert result == ""

    def test_extract_namespace_empty(self):
        """Test _extract_namespace with no namespace."""
        formatter = PHPTableFormatter("full")
        data = {}
        result = formatter._extract_namespace(data)
        # New implementation returns empty string instead of "unknown"
        assert result == ""

    def test_get_platform_newline(self):
        """Test _get_platform_newline returns string."""
        formatter = PHPTableFormatter("full")
        result = formatter._get_platform_newline()
        assert result in ["\n", "\r\n"]


class TestPHPTableFormatterEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_format_type(self):
        """Test with invalid format type."""
        formatter = PHPTableFormatter("invalid_format")
        data = {"classes": [], "methods": [], "fields": []}
        with pytest.raises(ValueError, match="Unsupported format type"):
            formatter.format_structure(data)

    def test_abstract_class(self):
        """Test abstract class type."""
        formatter = PHPTableFormatter("full")
        data = {
            "file_path": "AbstractClass.php",
            "classes": [
                {
                    "name": "AbstractClass",
                    "class_type": "abstract class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "methods": [
                {
                    "name": "abstractMethod",
                    "return_type": "void",
                    "visibility": "abstract",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 5},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter.format_structure(data)
        assert "AbstractClass" in result

    def test_static_method(self):
        """Test static method."""
        formatter = PHPTableFormatter("full")
        data = {
            "file_path": "StaticClass.php",
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
                    "name": "staticMethod",
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
        assert "staticMethod" in result


class TestPHPTableFormatterFormatTypeInit:
    """Test format type initialization."""

    def test_full_format_type(self):
        """Test creating formatter with full format type."""
        formatter = PHPTableFormatter("full")
        assert formatter.format_type == "full"

    def test_compact_format_type(self):
        """Test creating formatter with compact format type."""
        formatter = PHPTableFormatter("compact")
        assert formatter.format_type == "compact"

    def test_csv_format_type(self):
        """Test creating formatter with csv format type."""
        formatter = PHPTableFormatter("csv")
        assert formatter.format_type == "csv"

    def test_default_format_type(self):
        """Test creating formatter with default format type."""
        formatter = PHPTableFormatter()
        assert formatter.format_type == "full"
