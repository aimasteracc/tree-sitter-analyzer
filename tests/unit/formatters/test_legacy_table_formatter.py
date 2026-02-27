#!/usr/bin/env python3
"""
Tests for LegacyTableFormatter.

Tests cover:
- Full table format
- Compact table format
- CSV format
- Multiple classes handling
- Methods and fields extraction
- Platform-specific newlines
- Edge cases and error handling
"""

import csv
import io
import os
from typing import Any

import pytest

from tree_sitter_analyzer.legacy_table_formatter import LegacyTableFormatter


class TestLegacyTableFormatterBasic:
    """Basic tests for LegacyTableFormatter initialization and attributes."""

    def test_default_initialization(self) -> None:
        """Test default initialization values."""
        formatter = LegacyTableFormatter()
        assert formatter.format_type == "full"
        assert formatter.language == "java"
        assert formatter.include_javadoc is False

    def test_custom_initialization(self) -> None:
        """Test custom initialization values."""
        formatter = LegacyTableFormatter(
            format_type="compact", language="python", include_javadoc=True
        )
        assert formatter.format_type == "compact"
        assert formatter.language == "python"
        assert formatter.include_javadoc is True

    def test_invalid_format_type_raises_error(self) -> None:
        """Test that invalid format type raises ValueError."""
        formatter = LegacyTableFormatter(format_type="invalid")
        with pytest.raises(ValueError, match="Unsupported format type"):
            formatter.format_structure({})


class TestFullTableFormat:
    """Tests for full table format output."""

    @pytest.fixture
    def formatter(self) -> LegacyTableFormatter:
        """Create a full format formatter."""
        return LegacyTableFormatter(format_type="full", language="java")

    def test_format_empty_structure(self, formatter: LegacyTableFormatter) -> None:
        """Test formatting empty structure."""
        data: dict[str, Any] = {}
        result = formatter.format_structure(data)
        assert "# " in result  # Should have header
        assert "## Class Info" in result

    def test_format_single_class(self, formatter: LegacyTableFormatter) -> None:
        """Test formatting single class."""
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": "User",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
        }
        result = formatter.format_structure(data)

        assert "# com.example.User" in result
        assert "## Class Info" in result
        assert "| Name | User |" in result
        assert "| Package | com.example |" in result

    def test_format_class_with_extends(self, formatter: LegacyTableFormatter) -> None:
        """Test formatting class with extends."""
        data = {
            "classes": [
                {
                    "name": "Employee",
                    "type": "class",
                    "visibility": "public",
                    "extends": "Person",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
        }
        result = formatter.format_structure(data)

        assert "| Extends | Person |" in result

    def test_format_class_with_implements(
        self, formatter: LegacyTableFormatter
    ) -> None:
        """Test formatting class with implements."""
        data = {
            "classes": [
                {
                    "name": "MyClass",
                    "type": "class",
                    "visibility": "public",
                    "implements": ["Serializable", "Comparable"],
                    "line_range": {"start": 1, "end": 50},
                }
            ],
        }
        result = formatter.format_structure(data)

        assert "| Implements | Serializable, Comparable |" in result

    def test_format_with_imports(self, formatter: LegacyTableFormatter) -> None:
        """Test formatting with imports section."""
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Test", "line_range": {"start": 1, "end": 10}}],
            "imports": [
                {"statement": "import java.util.List;"},
                {"statement": "import java.util.Map;"},
            ],
        }
        result = formatter.format_structure(data)

        assert "## Imports" in result
        assert "import java.util.List;" in result
        assert "import java.util.Map;" in result

    def test_format_with_methods(self, formatter: LegacyTableFormatter) -> None:
        """Test formatting with methods."""
        data = {
            "classes": [{"name": "Test", "line_range": {"start": 1, "end": 50}}],
            "methods": [
                {
                    "name": "getName",
                    "return_type": "String",
                    "visibility": "public",
                    "parameters": [{"type": "int", "name": "id"}],
                    "line_range": {"start": 10, "end": 15},
                },
                {
                    "name": "setName",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [{"type": "String", "name": "name"}],
                    "line_range": {"start": 20, "end": 25},
                },
            ],
        }
        result = formatter.format_structure(data)

        assert "## Methods" in result
        assert "| getName |" in result
        assert "| setName |" in result
        assert "int id" in result
        assert "String name" in result

    def test_format_with_constructor(self, formatter: LegacyTableFormatter) -> None:
        """Test formatting constructor (no return type)."""
        data = {
            "classes": [{"name": "Test", "line_range": {"start": 1, "end": 50}}],
            "methods": [
                {
                    "name": "Test",
                    "is_constructor": True,
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 8},
                }
            ],
        }
        result = formatter.format_structure(data)

        assert "| Test |" in result
        # Constructor should have "-" as return type
        assert "| - |" in result

    def test_format_with_fields(self, formatter: LegacyTableFormatter) -> None:
        """Test formatting with fields."""
        data = {
            "classes": [{"name": "Test", "line_range": {"start": 1, "end": 50}}],
            "fields": [
                {
                    "name": "id",
                    "type": "int",
                    "visibility": "private",
                    "modifiers": [],
                    "line_range": {"start": 3, "end": 3},
                },
                {
                    "name": "name",
                    "type": "String",
                    "visibility": "private",
                    "modifiers": ["final"],
                    "line_range": {"start": 4, "end": 4},
                },
            ],
        }
        result = formatter.format_structure(data)

        assert "## Fields" in result
        assert "| id |" in result
        assert "| name |" in result

    def test_format_static_final_fields(self, formatter: LegacyTableFormatter) -> None:
        """Test formatting static and final field modifiers."""
        data = {
            "classes": [{"name": "Test", "line_range": {"start": 1, "end": 50}}],
            "fields": [
                {
                    "name": "MAX_SIZE",
                    "type": "int",
                    "visibility": "public",
                    "modifiers": ["static", "final"],
                    "line_range": {"start": 3, "end": 3},
                },
                {
                    "name": "instance",
                    "type": "Test",
                    "visibility": "private",
                    "is_static": True,
                    "line_range": {"start": 4, "end": 4},
                },
            ],
        }
        result = formatter.format_structure(data)

        assert "true" in result  # Should have static or final as true


class TestMultipleClassesFormat:
    """Tests for formatting multiple classes."""

    @pytest.fixture
    def formatter(self) -> LegacyTableFormatter:
        """Create a full format formatter."""
        return LegacyTableFormatter(format_type="full", language="java")

    def test_format_multiple_classes(self, formatter: LegacyTableFormatter) -> None:
        """Test formatting multiple classes with overview table."""
        data = {
            "classes": [
                {
                    "name": "Person",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                },
                {
                    "name": "Employee",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 25, "end": 50},
                },
            ],
            "methods": [
                {
                    "name": "getName",
                    "return_type": "String",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 8},
                },
                {
                    "name": "getSalary",
                    "return_type": "double",
                    "visibility": "public",
                    "line_range": {"start": 30, "end": 35},
                },
            ],
            "fields": [
                {
                    "name": "name",
                    "type": "String",
                    "visibility": "private",
                    "line_range": {"start": 3, "end": 3},
                },
                {
                    "name": "salary",
                    "type": "double",
                    "visibility": "private",
                    "line_range": {"start": 27, "end": 27},
                },
            ],
        }
        result = formatter.format_structure(data)

        assert "## Classes Overview" in result
        assert "| Person |" in result
        assert "| Employee |" in result

    def test_format_nested_classes(self, formatter: LegacyTableFormatter) -> None:
        """Test that nested class methods/fields are excluded from parent."""
        data = {
            "classes": [
                {
                    "name": "Outer",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                },
                {
                    "name": "Inner",
                    "type": "class",
                    "visibility": "private",
                    "line_range": {"start": 20, "end": 40},
                },
            ],
            "methods": [
                {
                    "name": "outerMethod",
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                },
                {
                    "name": "innerMethod",
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 25, "end": 30},
                },
            ],
        }
        result = formatter.format_structure(data)

        assert "## Outer" in result
        assert "## Inner" in result


class TestCompactTableFormat:
    """Tests for compact table format output."""

    @pytest.fixture
    def formatter(self) -> LegacyTableFormatter:
        """Create a compact format formatter."""
        return LegacyTableFormatter(format_type="compact", language="java")

    def test_compact_format_empty(self, formatter: LegacyTableFormatter) -> None:
        """Test compact format with empty data."""
        data: dict[str, Any] = {}
        result = formatter.format_structure(data)

        assert "# Unknown" in result
        assert "## Info" in result

    def test_compact_format_basic(self, formatter: LegacyTableFormatter) -> None:
        """Test basic compact format."""
        data = {
            "classes": [
                {
                    "name": "TestClass",
                    "type": "class",
                }
            ],
            "methods": [
                {
                    "name": "test1",
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10},
                },
                {
                    "name": "test2",
                    "return_type": "String",
                    "visibility": "private",
                    "line_range": {"start": 20},
                },
            ],
            "fields": [
                {
                    "name": "field1",
                    "type": "int",
                    "visibility": "private",
                    "line_range": {"start": 5},
                },
            ],
        }
        result = formatter.format_structure(data)

        assert "# TestClass" in result
        assert "| Methods | 2 |" in result
        assert "| Fields | 1 |" in result

    def test_compact_format_methods_table(
        self, formatter: LegacyTableFormatter
    ) -> None:
        """Test compact format methods table (simplified)."""
        data = {
            "classes": [{"name": "Test"}],
            "methods": [
                {
                    "name": "process",
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 15},
                }
            ],
        }
        result = formatter.format_structure(data)

        # Compact format now uses abbreviated headers
        assert "| Method | Sig | V | L | Cx | Doc |" in result
        assert "| process |" in result

    def test_compact_format_fields_table(self, formatter: LegacyTableFormatter) -> None:
        """Test compact format fields table (simplified)."""
        data = {
            "classes": [{"name": "Test"}],
            "fields": [
                {
                    "name": "count",
                    "type": "int",
                    "visibility": "private",
                    "line_range": {"start": 5},
                }
            ],
        }
        result = formatter.format_structure(data)

        # Compact format now uses abbreviated headers
        assert "| Field | Type | V | L |" in result
        assert "| count |" in result


class TestCSVFormat:
    """Tests for CSV format output."""

    @pytest.fixture
    def formatter(self) -> LegacyTableFormatter:
        """Create a CSV format formatter."""
        return LegacyTableFormatter(format_type="csv", language="java")

    def test_csv_format_header(self, formatter: LegacyTableFormatter) -> None:
        """Test CSV format has correct header."""
        data: dict[str, Any] = {"classes": []}
        result = formatter.format_structure(data)

        lines = result.strip().split("\n")
        assert len(lines) >= 1
        header = lines[0]
        assert "Type" in header
        assert "Name" in header
        assert "ReturnType" in header
        assert "Parameters" in header

    def test_csv_format_class_row(self, formatter: LegacyTableFormatter) -> None:
        """Test CSV format class row."""
        data = {
            "classes": [
                {
                    "name": "MyClass",
                    "type": "class",
                    "visibility": "public",
                    "modifiers": [],
                    "line_range": {"start": 1},
                }
            ],
        }
        result = formatter.format_structure(data)

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) >= 2
        class_row = rows[1]
        assert "class" in class_row
        assert "MyClass" in class_row

    def test_csv_format_method_row(self, formatter: LegacyTableFormatter) -> None:
        """Test CSV format method row."""
        data = {
            "classes": [],
            "methods": [
                {
                    "name": "process",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [{"type": "String", "name": "input"}],
                    "modifiers": ["static"],
                    "line_range": {"start": 10},
                }
            ],
        }
        result = formatter.format_structure(data)

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) >= 2
        method_row = rows[1]
        assert "method" in method_row
        assert "process" in method_row
        assert "void" in method_row

    def test_csv_format_constructor_row(self, formatter: LegacyTableFormatter) -> None:
        """Test CSV format constructor row."""
        data = {
            "classes": [],
            "methods": [
                {
                    "name": "MyClass",
                    "is_constructor": True,
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 5},
                }
            ],
        }
        result = formatter.format_structure(data)

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) >= 2
        constructor_row = rows[1]
        assert "constructor" in constructor_row

    def test_csv_format_parameters(self, formatter: LegacyTableFormatter) -> None:
        """Test CSV format parameter formatting."""
        data = {
            "classes": [],
            "methods": [
                {
                    "name": "calculate",
                    "return_type": "int",
                    "visibility": "public",
                    "parameters": [
                        {"type": "int", "name": "a"},
                        {"type": "int", "name": "b"},
                    ],
                    "line_range": {"start": 10},
                }
            ],
        }
        result = formatter.format_structure(data)

        # Parameters should be in format "param:type;param:type"
        assert "a:int" in result
        assert "b:int" in result

    def test_csv_format_string_parameters(
        self, formatter: LegacyTableFormatter
    ) -> None:
        """Test CSV format with string-style parameters."""
        data = {
            "classes": [],
            "methods": [
                {
                    "name": "test",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": ["String input", "int count"],
                    "line_range": {"start": 10},
                }
            ],
        }
        result = formatter.format_structure(data)

        # String parameters should be converted
        assert "input:String" in result
        assert "count:int" in result

    def test_csv_format_static_final(self, formatter: LegacyTableFormatter) -> None:
        """Test CSV format static and final columns."""
        data = {
            "classes": [],
            "methods": [
                {
                    "name": "staticMethod",
                    "return_type": "void",
                    "visibility": "public",
                    "modifiers": ["static", "final"],
                    "line_range": {"start": 10},
                },
                {
                    "name": "normalMethod",
                    "return_type": "void",
                    "visibility": "public",
                    "modifiers": [],
                    "line_range": {"start": 20},
                },
            ],
        }
        result = formatter.format_structure(data)

        # Should contain true and false for static/final
        assert "true" in result
        assert "false" in result


class TestPlatformNewlines:
    """Tests for platform-specific newline handling."""

    def test_get_platform_newline(self) -> None:
        """Test platform newline detection."""
        formatter = LegacyTableFormatter()
        newline = formatter._get_platform_newline()
        # Should be either \n or \r\n depending on platform
        assert newline in ("\n", "\r\n")

    def test_convert_to_platform_newlines(self) -> None:
        """Test newline conversion."""
        formatter = LegacyTableFormatter()
        text = "line1\nline2\nline3"
        result = formatter._convert_to_platform_newlines(text)

        # Result should have consistent newlines for the platform
        if os.name == "nt":
            assert "\r\n" in result or "\n" in result
        else:
            assert result == text

    def test_csv_skips_newline_conversion(self) -> None:
        """Test that CSV format skips newline conversion."""
        formatter = LegacyTableFormatter(format_type="csv")
        data = {"classes": [{"name": "Test"}]}
        result = formatter.format_structure(data)

        # CSV should use standard newlines
        if os.name == "nt":
            # On Windows, CSV should NOT have \r\n converted
            assert "\r\r\n" not in result


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_none_classes(self) -> None:
        """Test handling of None classes list."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": None}
        result = formatter.format_structure(data)
        assert "# " in result  # Should have header

    def test_none_methods(self) -> None:
        """Test handling of None methods list."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": [{"name": "Test"}], "methods": None}
        result = formatter.format_structure(data)
        assert "## Methods" in result

    def test_none_fields(self) -> None:
        """Test handling of None fields list."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": [{"name": "Test"}], "fields": None}
        result = formatter.format_structure(data)
        assert "## Fields" in result

    def test_empty_package_name(self) -> None:
        """Test handling of empty package name."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": [{"name": "Test"}], "package": {"name": ""}}
        result = formatter.format_structure(data)
        assert "Test" in result

    def test_unknown_package(self) -> None:
        """Test handling of unknown package."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": [{"name": "Test"}], "package": {"name": "unknown"}}
        result = formatter.format_structure(data)
        # unknown package should not be displayed
        assert "## Package" not in result or "unknown" in result

    def test_file_path_handling(self) -> None:
        """Test file path extraction for header."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": [], "file_path": "/path/to/MyClass.java"}
        result = formatter.format_structure(data)
        assert "MyClass" in result

    def test_file_path_with_various_extensions(self) -> None:
        """Test file path handling with different extensions."""
        formatter = LegacyTableFormatter(format_type="full")

        # Python file
        data = {"classes": [], "file_path": "/path/to/module.py"}
        result = formatter.format_structure(data)
        assert "module" in result

        # JavaScript file
        data = {"classes": [], "file_path": "/path/to/app.js"}
        result = formatter.format_structure(data)
        assert "app" in result

    def test_method_with_no_parameters(self) -> None:
        """Test method with empty parameters list."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [{"name": "Test"}],
            "methods": [
                {
                    "name": "noParams",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 10},
                }
            ],
        }
        result = formatter.format_structure(data)
        assert "| noParams |" in result

    def test_parameter_as_plain_string(self) -> None:
        """Test parameter handling when it's just a string."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [{"name": "Test"}],
            "methods": [
                {
                    "name": "test",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": ["plainParam"],
                    "line_range": {"start": 10},
                }
            ],
        }
        result = formatter.format_structure(data)
        assert "plainParam" in result

    def test_parameter_as_other_type(self) -> None:
        """Test parameter handling when it's an unexpected type."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [{"name": "Test"}],
            "methods": [
                {
                    "name": "test",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [123],  # Unexpected type
                    "line_range": {"start": 10},
                }
            ],
        }
        result = formatter.format_structure(data)
        assert "123" in result

    def test_missing_line_range(self) -> None:
        """Test handling of missing line range."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [{"name": "Test"}],
            "methods": [
                {
                    "name": "test",
                    "return_type": "void",
                    "visibility": "public",
                }
            ],
        }
        result = formatter.format_structure(data)
        # Should handle missing line_range gracefully
        assert "test" in result


class TestDetailedFormatting:
    """Tests for detailed formatting methods."""

    @pytest.fixture
    def formatter_with_javadoc(self) -> LegacyTableFormatter:
        """Create formatter with javadoc enabled."""
        return LegacyTableFormatter(format_type="full", include_javadoc=True)

    def test_get_class_methods_basic(self) -> None:
        """Test _get_class_methods method."""
        formatter = LegacyTableFormatter()
        data = {
            "classes": [{"line_range": {"start": 1, "end": 50}}],
            "methods": [
                {"name": "m1", "line_range": {"start": 10}},
                {"name": "m2", "line_range": {"start": 60}},  # Outside class
            ],
        }
        class_range = {"start": 1, "end": 50}
        methods = formatter._get_class_methods(data, class_range)
        assert len(methods) == 1
        assert methods[0]["name"] == "m1"

    def test_get_class_fields_basic(self) -> None:
        """Test _get_class_fields method."""
        formatter = LegacyTableFormatter()
        data = {
            "classes": [{"line_range": {"start": 1, "end": 50}}],
            "fields": [
                {"name": "f1", "line_range": {"start": 5}},
                {"name": "f2", "line_range": {"start": 70}},  # Outside class
            ],
        }
        class_range = {"start": 1, "end": 50}
        fields = formatter._get_class_fields(data, class_range)
        assert len(fields) == 1
        assert fields[0]["name"] == "f1"

    def test_get_class_methods_excludes_nested(self) -> None:
        """Test that nested class methods are excluded."""
        formatter = LegacyTableFormatter()
        data = {
            "classes": [
                {"name": "Outer", "line_range": {"start": 1, "end": 100}},
                {"name": "Inner", "line_range": {"start": 30, "end": 60}},
            ],
            "methods": [
                {"name": "outerMethod", "line_range": {"start": 10}},
                {"name": "innerMethod", "line_range": {"start": 40}},
            ],
        }
        outer_range = {"start": 1, "end": 100}
        methods = formatter._get_class_methods(data, outer_range)

        # innerMethod should be excluded because it's in nested class
        method_names = [m["name"] for m in methods]
        assert "outerMethod" in method_names
        assert "innerMethod" not in method_names

    def test_get_class_fields_excludes_nested(self) -> None:
        """Test that nested class fields are excluded."""
        formatter = LegacyTableFormatter()
        data = {
            "classes": [
                {"name": "Outer", "line_range": {"start": 1, "end": 100}},
                {"name": "Inner", "line_range": {"start": 30, "end": 60}},
            ],
            "fields": [
                {"name": "outerField", "line_range": {"start": 5}},
                {"name": "innerField", "line_range": {"start": 35}},
            ],
        }
        outer_range = {"start": 1, "end": 100}
        fields = formatter._get_class_fields(data, outer_range)

        # innerField should be excluded
        field_names = [f["name"] for f in fields]
        assert "outerField" in field_names
        assert "innerField" not in field_names


class TestFormatClassDetails:
    """Tests for _format_class_details method (covers lines 449-534)."""

    @pytest.fixture
    def formatter_no_javadoc(self) -> LegacyTableFormatter:
        """Create formatter without javadoc."""
        return LegacyTableFormatter(format_type="full", include_javadoc=False)

    @pytest.fixture
    def formatter_with_javadoc(self) -> LegacyTableFormatter:
        """Create formatter with javadoc enabled."""
        return LegacyTableFormatter(format_type="full", include_javadoc=True)

    def test_format_class_details_basic(self, formatter_no_javadoc: LegacyTableFormatter) -> None:
        """Test basic class detail formatting."""
        class_info = {
            "name": "UserService",
            "line_range": {"start": 10, "end": 100},
        }
        data = {
            "classes": [class_info],
            "methods": [
                {
                    "name": "getUser",
                    "return_type": "User",
                    "visibility": "public",
                    "is_constructor": False,
                    "parameters": [{"type": "int", "name": "id"}],
                    "line_range": {"start": 20, "end": 30},
                    "complexity_score": 2,
                    "javadoc": "",
                },
            ],
            "fields": [
                {
                    "name": "userDao",
                    "type": "UserDao",
                    "visibility": "private",
                    "modifiers": [],
                    "line_range": {"start": 12, "end": 12},
                    "javadoc": "",
                },
            ],
        }
        lines = formatter_no_javadoc._format_class_details(class_info, data)
        result = "\n".join(lines)

        assert "## UserService (10-100)" in result
        assert "### Fields" in result
        assert "| userDao |" in result
        assert "### Public Methods" in result
        assert "| getUser |" in result

    def test_format_class_details_with_constructors(self, formatter_no_javadoc: LegacyTableFormatter) -> None:
        """Test class details with constructors."""
        class_info = {
            "name": "Person",
            "line_range": {"start": 1, "end": 50},
        }
        data = {
            "classes": [class_info],
            "methods": [
                {
                    "name": "Person",
                    "is_constructor": True,
                    "visibility": "public",
                    "parameters": [{"type": "String", "name": "name"}],
                    "line_range": {"start": 5, "end": 10},
                    "complexity_score": 1,
                    "javadoc": "",
                },
            ],
            "fields": [],
        }
        lines = formatter_no_javadoc._format_class_details(class_info, data)
        result = "\n".join(lines)

        assert "### Constructors" in result
        assert "| Person |" in result

    def test_format_class_details_methods_by_visibility(self, formatter_no_javadoc: LegacyTableFormatter) -> None:
        """Test class details organizes methods by visibility."""
        class_info = {
            "name": "TestClass",
            "line_range": {"start": 1, "end": 100},
        }
        data = {
            "classes": [class_info],
            "methods": [
                {"name": "pubMethod", "visibility": "public", "is_constructor": False,
                 "line_range": {"start": 10, "end": 15}, "parameters": [], "complexity_score": 1, "javadoc": ""},
                {"name": "protMethod", "visibility": "protected", "is_constructor": False,
                 "line_range": {"start": 20, "end": 25}, "parameters": [], "complexity_score": 1, "javadoc": ""},
                {"name": "pkgMethod", "visibility": "package", "is_constructor": False,
                 "line_range": {"start": 30, "end": 35}, "parameters": [], "complexity_score": 1, "javadoc": ""},
                {"name": "privMethod", "visibility": "private", "is_constructor": False,
                 "line_range": {"start": 40, "end": 45}, "parameters": [], "complexity_score": 1, "javadoc": ""},
            ],
            "fields": [],
        }
        lines = formatter_no_javadoc._format_class_details(class_info, data)
        result = "\n".join(lines)

        assert "### Public Methods" in result
        assert "### Protected Methods" in result
        assert "### Package Methods" in result
        assert "### Private Methods" in result
        assert "| pubMethod |" in result
        assert "| protMethod |" in result
        assert "| pkgMethod |" in result
        assert "| privMethod |" in result

    def test_format_class_details_with_javadoc(self, formatter_with_javadoc: LegacyTableFormatter) -> None:
        """Test class details with javadoc enabled."""
        class_info = {
            "name": "DocClass",
            "line_range": {"start": 1, "end": 50},
        }
        data = {
            "classes": [class_info],
            "methods": [
                {"name": "documented", "visibility": "public", "is_constructor": False,
                 "line_range": {"start": 10, "end": 20}, "parameters": [],
                 "complexity_score": 1, "javadoc": "/** Gets the user name. */"},
            ],
            "fields": [
                {"name": "name", "type": "String", "visibility": "private",
                 "modifiers": [], "line_range": {"start": 3, "end": 3},
                 "javadoc": "/** The user name. */"},
            ],
        }
        lines = formatter_with_javadoc._format_class_details(class_info, data)
        result = "\n".join(lines)

        # Javadoc should be extracted, not "-"
        assert "Gets the user name" in result
        assert "The user name" in result

    def test_format_class_details_no_methods_no_fields(self, formatter_no_javadoc: LegacyTableFormatter) -> None:
        """Test class details with no methods or fields."""
        class_info = {
            "name": "EmptyClass",
            "line_range": {"start": 1, "end": 5},
        }
        data = {
            "classes": [class_info],
            "methods": [],
            "fields": [],
        }
        lines = formatter_no_javadoc._format_class_details(class_info, data)
        result = "\n".join(lines)

        assert "## EmptyClass (1-5)" in result
        # No methods or fields sections
        assert "### Fields" not in result
        assert "### Public Methods" not in result


class TestFormatMethodRowDetailed:
    """Tests for _format_method_row_detailed (covers lines 536-550)."""

    def test_method_row_basic(self) -> None:
        """Test basic method row formatting."""
        formatter = LegacyTableFormatter(include_javadoc=False)
        method = {
            "name": "process",
            "return_type": "void",
            "visibility": "public",
            "is_static": False,
            "parameters": [{"type": "String", "name": "input"}],
            "line_range": {"start": 10, "end": 20},
            "complexity_score": 3,
            "javadoc": "",
        }
        result = formatter._format_method_row_detailed(method)
        assert "| process |" in result
        assert "| + |" in result or "+ |" in result
        assert "10-20" in result
        assert "3" in result

    def test_method_row_static(self) -> None:
        """Test static method row formatting."""
        formatter = LegacyTableFormatter(include_javadoc=False)
        method = {
            "name": "staticMethod",
            "return_type": "int",
            "visibility": "public",
            "is_static": True,
            "parameters": [],
            "line_range": {"start": 5, "end": 8},
            "complexity_score": 1,
            "javadoc": "",
        }
        result = formatter._format_method_row_detailed(method)
        assert "[static]" in result

    def test_method_row_with_javadoc(self) -> None:
        """Test method row with javadoc enabled."""
        formatter = LegacyTableFormatter(include_javadoc=True)
        method = {
            "name": "getData",
            "return_type": "List",
            "visibility": "public",
            "is_static": False,
            "parameters": [],
            "line_range": {"start": 15, "end": 25},
            "complexity_score": 2,
            "javadoc": "/** Retrieves all data from the database. */",
        }
        result = formatter._format_method_row_detailed(method)
        assert "Retrieves all data from the database" in result


class TestCompactMethodRow:
    """Tests for _format_compact_method_row (covers lines 552-564)."""

    def test_compact_method_row_basic(self) -> None:
        """Test basic compact method row."""
        formatter = LegacyTableFormatter()
        method = {
            "name": "calculate",
            "return_type": "double",
            "visibility": "public",
            "parameters": [{"type": "int", "name": "a"}, {"type": "int", "name": "b"}],
            "line_range": {"start": 10, "end": 20},
            "complexity_score": 3,
        }
        result = formatter._format_compact_method_row(method)
        assert "| calculate |" in result
        assert "| + |" in result or "+ |" in result

    def test_compact_method_row_same_start_end(self) -> None:
        """Test compact method row where start equals end."""
        formatter = LegacyTableFormatter()
        method = {
            "name": "getter",
            "return_type": "String",
            "visibility": "private",
            "parameters": [],
            "line_range": {"start": 10, "end": 10},
            "complexity_score": 1,
        }
        result = formatter._format_compact_method_row(method)
        assert "| 10 |" in result or "10" in result


class TestCreateCompactSignature:
    """Tests for _create_compact_signature (covers lines 566-580)."""

    def test_compact_signature_basic(self) -> None:
        """Test basic compact signature creation."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [{"type": "String", "name": "name"}, {"type": "int", "name": "age"}],
            "return_type": "boolean",
        }
        result = formatter._create_compact_signature(method)
        assert result == "(S,i):b"

    def test_compact_signature_no_params(self) -> None:
        """Test compact signature with no parameters."""
        formatter = LegacyTableFormatter()
        method = {"parameters": [], "return_type": "void"}
        result = formatter._create_compact_signature(method)
        assert result == "():void"


class TestAbbreviateType:
    """Tests for _abbreviate_type (covers lines 582-620)."""

    def test_abbreviate_basic_types(self) -> None:
        """Test abbreviation of basic types."""
        formatter = LegacyTableFormatter()
        assert formatter._abbreviate_type("String") == "S"
        assert formatter._abbreviate_type("int") == "i"
        assert formatter._abbreviate_type("boolean") == "b"
        assert formatter._abbreviate_type("void") == "void"
        assert formatter._abbreviate_type("Object") == "O"
        assert formatter._abbreviate_type("long") == "l"
        assert formatter._abbreviate_type("double") == "d"
        assert formatter._abbreviate_type("float") == "f"
        assert formatter._abbreviate_type("List") == "L"
        assert formatter._abbreviate_type("Map") == "M"
        assert formatter._abbreviate_type("Set") == "St"
        assert formatter._abbreviate_type("Collection") == "C"

    def test_abbreviate_generic_type(self) -> None:
        """Test abbreviation of generic types like Map<String, Object>."""
        formatter = LegacyTableFormatter()
        result = formatter._abbreviate_type("Map<String, Object>")
        assert "M<" in result
        assert "S" in result
        assert "O" in result

    def test_abbreviate_array_type(self) -> None:
        """Test abbreviation of array types."""
        formatter = LegacyTableFormatter()
        result = formatter._abbreviate_type("String[]")
        assert result == "S[]"

    def test_abbreviate_unknown_type(self) -> None:
        """Test abbreviation of unknown type (first letter uppercase)."""
        formatter = LegacyTableFormatter()
        result = formatter._abbreviate_type("CustomType")
        assert result == "C"

    def test_abbreviate_empty_type(self) -> None:
        """Test abbreviation of empty type string."""
        formatter = LegacyTableFormatter()
        result = formatter._abbreviate_type("")
        assert result == "?"


class TestGetVisibilitySymbol:
    """Tests for _get_visibility_symbol (covers lines 622-631)."""

    def test_visibility_symbols(self) -> None:
        """Test all visibility symbol conversions."""
        formatter = LegacyTableFormatter()
        assert formatter._get_visibility_symbol("public") == "+"
        assert formatter._get_visibility_symbol("private") == "-"
        assert formatter._get_visibility_symbol("protected") == "#"
        assert formatter._get_visibility_symbol("package") == "~"
        assert formatter._get_visibility_symbol("internal") == "~"

    def test_visibility_unknown(self) -> None:
        """Test unknown visibility defaults to +."""
        formatter = LegacyTableFormatter()
        assert formatter._get_visibility_symbol("unknown") == "+"

    def test_visibility_case_sensitivity(self) -> None:
        """Test that case conversion works for visibility."""
        formatter = LegacyTableFormatter()
        assert formatter._get_visibility_symbol("PUBLIC") == "+"  # lowered


class TestShortenType:
    """Tests for _shorten_type (covers lines 847-890)."""

    def test_shorten_basic_types(self) -> None:
        """Test shortening of basic types."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type("String") == "S"
        assert formatter._shorten_type("int") == "i"
        assert formatter._shorten_type("void") == "void"
        assert formatter._shorten_type("boolean") == "b"
        assert formatter._shorten_type("Object") == "O"

    def test_shorten_none_type(self) -> None:
        """Test shortening of None type."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type(None) == "O"

    def test_shorten_non_string_type(self) -> None:
        """Test shortening of non-string type."""
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type(42)
        assert isinstance(result, str)

    def test_shorten_map_type(self) -> None:
        """Test shortening Map generic type."""
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type("Map<String,Object>")
        assert "M<" in result
        assert "S" in result

    def test_shorten_list_type(self) -> None:
        """Test shortening List generic type."""
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type("List<String>")
        assert "L<" in result
        assert "S" in result

    def test_shorten_array_type(self) -> None:
        """Test shortening array type."""
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type("String[]")
        assert result == "S[]"

    def test_shorten_empty_array_type(self) -> None:
        """Test shortening empty base array type."""
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type("[]")
        assert result == "O[]"

    def test_shorten_exception_types(self) -> None:
        """Test shortening exception types."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type("Exception") == "E"
        assert formatter._shorten_type("SQLException") == "SE"
        assert formatter._shorten_type("IllegalArgumentException") == "IAE"
        assert formatter._shorten_type("RuntimeException") == "RE"


class TestConvertVisibility:
    """Tests for _convert_visibility (covers lines 892-895)."""

    def test_convert_all_visibilities(self) -> None:
        """Test all visibility conversions."""
        formatter = LegacyTableFormatter()
        assert formatter._convert_visibility("public") == "+"
        assert formatter._convert_visibility("private") == "-"
        assert formatter._convert_visibility("protected") == "#"
        assert formatter._convert_visibility("package") == "~"

    def test_convert_unknown_visibility(self) -> None:
        """Test unknown visibility returns as-is."""
        formatter = LegacyTableFormatter()
        assert formatter._convert_visibility("internal") == "internal"


class TestExtractDocSummary:
    """Tests for _extract_doc_summary (covers lines 897-913)."""

    def test_extract_empty_doc(self) -> None:
        """Test extracting summary from empty doc."""
        formatter = LegacyTableFormatter()
        assert formatter._extract_doc_summary("") == "-"

    def test_extract_javadoc_summary(self) -> None:
        """Test extracting summary from JavaDoc comment."""
        formatter = LegacyTableFormatter()
        result = formatter._extract_doc_summary("/** Gets the user name. */")
        assert "Gets the user name" in result

    def test_extract_javadoc_first_sentence(self) -> None:
        """Test extracting first sentence from multi-sentence JavaDoc."""
        formatter = LegacyTableFormatter()
        result = formatter._extract_doc_summary(
            "/** First sentence. Second sentence with details. */"
        )
        assert "First sentence" in result


class TestCleanCsvText:
    """Tests for _clean_csv_text (covers lines 915-926)."""

    def test_clean_empty_text(self) -> None:
        """Test cleaning empty text."""
        formatter = LegacyTableFormatter()
        assert formatter._clean_csv_text("") == "-"
        assert formatter._clean_csv_text("-") == "-"

    def test_clean_text_with_newlines(self) -> None:
        """Test cleaning text with newlines."""
        formatter = LegacyTableFormatter()
        result = formatter._clean_csv_text("line1\nline2\nline3")
        assert "\n" not in result
        assert "line1 line2 line3" == result

    def test_clean_text_with_quotes(self) -> None:
        """Test cleaning text with double quotes."""
        formatter = LegacyTableFormatter()
        result = formatter._clean_csv_text('text with "quotes"')
        assert '""' in result

    def test_clean_text_with_extra_whitespace(self) -> None:
        """Test cleaning text with extra whitespace."""
        formatter = LegacyTableFormatter()
        result = formatter._clean_csv_text("  extra   spaces  ")
        assert result == "extra spaces"


class TestCreateFullSignature:
    """Tests for _create_full_signature (covers lines 815-845)."""

    def test_full_signature_basic(self) -> None:
        """Test basic full signature creation."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [{"type": "String", "name": "name"}],
            "return_type": "void",
        }
        result = formatter._create_full_signature(method)
        assert result == "(name:String):void"

    def test_full_signature_static(self) -> None:
        """Test full signature with static modifier."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [],
            "return_type": "int",
            "is_static": True,
        }
        result = formatter._create_full_signature(method)
        assert "[static]" in result
        assert "():int" in result

    def test_full_signature_string_param(self) -> None:
        """Test full signature with string-format parameters."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": ["String name", "int age"],
            "return_type": "void",
        }
        result = formatter._create_full_signature(method)
        assert "String name" in result
        assert "int age" in result

    def test_full_signature_other_param_type(self) -> None:
        """Test full signature with non-standard parameter types."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [123, True],
            "return_type": "void",
        }
        result = formatter._create_full_signature(method)
        assert "123" in result
        assert "True" in result


class TestMultipleClassesMethodRows:
    """Tests for multiple-class method row formatting (covers lines 226-256)."""

    def test_multiple_classes_method_parameters(self) -> None:
        """Test method parameter formatting in multi-class mode."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [
                {"name": "ClassA", "type": "class", "visibility": "public",
                 "line_range": {"start": 1, "end": 30}},
                {"name": "ClassB", "type": "class", "visibility": "public",
                 "line_range": {"start": 35, "end": 60}},
            ],
            "methods": [
                {"name": "methodA", "return_type": "void", "visibility": "public",
                 "is_constructor": False,
                 "parameters": [
                     {"type": "String", "name": "input"},
                     {"type": "int", "name": "count"},
                 ],
                 "line_range": {"start": 10, "end": 15}},
                {"name": "ConstructorB", "return_type": "void", "visibility": "public",
                 "is_constructor": True,
                 "parameters": ["plainParam"],
                 "line_range": {"start": 40, "end": 45}},
            ],
            "fields": [
                {"name": "field1", "type": "int", "visibility": "private",
                 "modifiers": ["static", "final"],
                 "line_range": {"start": 3, "end": 3}},
            ],
        }
        result = formatter.format_structure(data)

        assert "## ClassA" in result
        assert "## ClassB" in result
        assert "String input" in result
        assert "int count" in result
        assert "| - |" in result  # Constructor return type


class TestFullTableFilePathVariants:
    """Tests for file_path handling in _format_full_table (covers lines 102-122)."""

    def test_file_path_no_classes_with_package(self) -> None:
        """Test header when no classes but package name exists."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "package": {"name": "com.example"},
            "classes": [],
            "file_path": "/path/to/Utils.java",
        }
        result = formatter.format_structure(data)
        assert "com.example.Utils" in result

    def test_file_path_no_package_no_classes(self) -> None:
        """Test header with no package and no classes uses default."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": []}
        result = formatter.format_structure(data)
        assert "unknown.Unknown" in result

    def test_file_path_package_no_file(self) -> None:
        """Test header with package but no file path and no classes."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {"package": {"name": "org.test"}, "classes": []}
        result = formatter.format_structure(data)
        assert "org.test.Unknown" in result

    def test_none_package(self) -> None:
        """Test handling of None package dict."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {"package": None, "classes": [{"name": "Test"}]}
        result = formatter.format_structure(data)
        assert "Test" in result

    def test_compact_format_with_package(self) -> None:
        """Test compact format with package name."""
        formatter = LegacyTableFormatter(format_type="compact")
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Service"}],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert "# com.example.Service" in result
        assert "| Package | com.example |" in result


class TestCSVEdgeCases:
    """Additional CSV format tests (covers lines 744-813)."""

    def test_csv_field_rows(self) -> None:
        """Test CSV format with field rows."""
        formatter = LegacyTableFormatter(format_type="csv")
        data = {
            "classes": [],
            "methods": [],
            "fields": [
                {"name": "count", "type": "int", "visibility": "private",
                 "modifiers": ["static", "final"], "line_range": {"start": 5}},
                {"name": "name", "type": "String", "visibility": "public",
                 "modifiers": [], "is_static": False, "line_range": {"start": 6}},
            ],
        }
        result = formatter.format_structure(data)
        assert "field" in result
        assert "count" in result
        assert "name" in result
        # Static field
        assert "true" in result

    def test_csv_class_with_final_modifier(self) -> None:
        """Test CSV class row with final modifier."""
        formatter = LegacyTableFormatter(format_type="csv")
        data = {
            "classes": [
                {"name": "FinalClass", "type": "class", "visibility": "public",
                 "modifiers": ["final"], "line_range": {"start": 1}},
            ],
        }
        result = formatter.format_structure(data)
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        class_row = rows[1]
        # Final should be true
        assert "true" in class_row

    def test_csv_single_part_string_parameter(self) -> None:
        """Test CSV with single-part string parameter."""
        formatter = LegacyTableFormatter(format_type="csv")
        data = {
            "classes": [],
            "methods": [
                {"name": "test", "return_type": "void", "visibility": "public",
                 "parameters": ["args"],  # Single part parameter
                 "line_range": {"start": 10}},
            ],
        }
        result = formatter.format_structure(data)
        assert "args" in result


class TestLanguageSpecificFormatting:
    """Tests for language-specific formatting."""

    def test_python_language_formatting(self) -> None:
        """Test Python language code block formatting."""
        formatter = LegacyTableFormatter(format_type="full", language="python")
        data = {
            "classes": [{"name": "Test"}],
            "imports": [{"statement": "import os"}],
        }
        result = formatter.format_structure(data)
        assert "```python" in result

    def test_java_language_formatting(self) -> None:
        """Test Java language code block formatting."""
        formatter = LegacyTableFormatter(format_type="full", language="java")
        data = {
            "classes": [{"name": "Test"}],
            "imports": [{"statement": "import java.util.*;"}],
        }
        result = formatter.format_structure(data)
        assert "```java" in result

    def test_javascript_language_formatting(self) -> None:
        """Test JavaScript language code block formatting."""
        formatter = LegacyTableFormatter(format_type="full", language="javascript")
        data = {
            "classes": [{"name": "Test"}],
            "imports": [{"statement": "import React from 'react';"}],
        }
        result = formatter.format_structure(data)
        assert "```javascript" in result
