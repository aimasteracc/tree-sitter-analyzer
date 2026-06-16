#!/usr/bin/env python3
"""
Comprehensive tests for LegacyTableFormatter to improve coverage to 70%+.

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
from typing import Any

import pytest

from tree_sitter_analyzer.legacy_table_formatter import LegacyTableFormatter


class TestLegacyTableFormatterBasic:
    def test_default_initialization(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter.format_type == "full"
        assert formatter.language == "java"
        assert formatter.include_javadoc is False

    def test_custom_initialization(self) -> None:
        formatter = LegacyTableFormatter(
            format_type="compact", language="python", include_javadoc=True
        )
        assert formatter.format_type == "compact"
        assert formatter.language == "python"
        assert formatter.include_javadoc is True

    def test_invalid_format_type_raises_error(self) -> None:
        formatter = LegacyTableFormatter(format_type="invalid")
        with pytest.raises(ValueError, match="Unsupported format type"):
            formatter.format_structure({})


class TestFullTableFormat:
    @pytest.fixture
    def formatter(self) -> LegacyTableFormatter:
        return LegacyTableFormatter(format_type="full", language="java")

    def test_format_empty_structure(self, formatter: LegacyTableFormatter) -> None:
        data: dict[str, Any] = {}
        result = formatter.format_structure(data)
        assert "# " in result
        assert "## Class Info" in result

    def test_format_single_class(self, formatter: LegacyTableFormatter) -> None:
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
        assert "| - |" in result

    def test_format_with_fields(self, formatter: LegacyTableFormatter) -> None:
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

        assert "true" in result


class TestMultipleClassesFormat:
    @pytest.fixture
    def formatter(self) -> LegacyTableFormatter:
        return LegacyTableFormatter(format_type="full", language="java")

    def test_format_multiple_classes(self, formatter: LegacyTableFormatter) -> None:
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
    @pytest.fixture
    def formatter(self) -> LegacyTableFormatter:
        return LegacyTableFormatter(format_type="compact", language="java")

    def test_compact_format_empty(self, formatter: LegacyTableFormatter) -> None:
        # Bug #778 fixed: empty data must not produce '# Unknown'.
        data: dict[str, Any] = {}
        result = formatter.format_structure(data)

        assert "# Unknown" not in result
        assert "## Info" in result

    def test_compact_format_basic(self, formatter: LegacyTableFormatter) -> None:
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

        assert "| Method | Sig | V | L | Cx | Doc |" in result
        assert "| process |" in result

    def test_compact_format_fields_table(self, formatter: LegacyTableFormatter) -> None:
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

        assert "| Field | Type | V | L |" in result
        assert "| count |" in result


class TestCSVFormat:
    @pytest.fixture
    def formatter(self) -> LegacyTableFormatter:
        return LegacyTableFormatter(format_type="csv", language="java")

    def test_csv_format_header(self, formatter: LegacyTableFormatter) -> None:
        data: dict[str, Any] = {"classes": []}
        result = formatter.format_structure(data)

        lines = result.strip().split("\n")
        assert len(lines) == 1
        header = lines[0]
        assert "Type" in header
        assert "Name" in header
        assert "ReturnType" in header
        assert "Parameters" in header

    def test_csv_format_class_row(self, formatter: LegacyTableFormatter) -> None:
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
        assert len(rows) == 2
        class_row = rows[1]
        assert "class" in class_row
        assert "MyClass" in class_row

    def test_csv_format_method_row(self, formatter: LegacyTableFormatter) -> None:
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
        assert len(rows) == 2
        method_row = rows[1]
        assert "method" in method_row
        assert "process" in method_row
        assert "void" in method_row

    def test_csv_format_constructor_row(self, formatter: LegacyTableFormatter) -> None:
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
        assert len(rows) == 2
        constructor_row = rows[1]
        assert "constructor" in constructor_row

    def test_csv_format_parameters(self, formatter: LegacyTableFormatter) -> None:
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

        assert "a:int" in result
        assert "b:int" in result

    def test_csv_format_string_parameters(
        self, formatter: LegacyTableFormatter
    ) -> None:
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

        assert "input:String" in result
        assert "count:int" in result

    def test_csv_format_static_final(self, formatter: LegacyTableFormatter) -> None:
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

        assert "true" in result
        assert "false" in result
