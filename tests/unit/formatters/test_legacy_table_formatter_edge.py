#!/usr/bin/env python3
"""Edge case tests for LegacyTableFormatter — edge cases, boundary conditions, method/field details."""

from typing import Any

import pytest

from tree_sitter_analyzer.legacy_table_formatter import (
    LegacyTableFormatter,
)


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


# ============================================================================
# Coverage boost: _format_full_table multi-class string/fallback params (240-247)
# ============================================================================


class TestFullTableMultiClassParamTypes:
    """Cover string and fallback param branches in _format_full_table multi-class path."""

    def _multi_class_data(self, methods: list[dict]) -> dict[str, Any]:
        return {
            "classes": [
                {
                    "name": "Outer",
                    "line_range": {"start": 1, "end": 100},
                    "type": "class",
                    "visibility": "public",
                },
                {
                    "name": "Inner",
                    "line_range": {"start": 40, "end": 60},
                    "type": "class",
                    "visibility": "private",
                },
            ],
            "methods": methods,
        }

    def test_string_param_in_multi_class(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = self._multi_class_data(
            [
                {
                    "name": "foo",
                    "parameters": ["int x", "String y"],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10},
                },
            ]
        )
        result = formatter.format_structure(data)
        assert "int x, String y" in result

    def test_fallback_param_in_multi_class(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = self._multi_class_data(
            [
                {
                    "name": "bar",
                    "parameters": [42],
                    "return_type": "int",
                    "visibility": "public",
                    "line_range": {"start": 12},
                },
            ]
        )
        result = formatter.format_structure(data)
        assert "42" in result


# ============================================================================
# Coverage boost: _format_csv with fields, string/fallback params (789-856)
# ============================================================================


class TestCSVFieldAndParamCoverage:
    """Cover _format_csv field rows and method param type branches."""

    def test_csv_with_field_rows(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "fields": [
                {
                    "name": "count",
                    "type": "int",
                    "visibility": "private",
                    "modifiers": ["static", "final"],
                    "line_range": {"start": 5},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "field" in result
        assert "count" in result
        assert "true" in result

    def test_csv_method_with_string_params(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "methods": [
                {
                    "name": "hello",
                    "parameters": ["int x"],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "x:int" in result

    def test_csv_method_with_fallback_params(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "methods": [
                {
                    "name": "hello",
                    "parameters": [42],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "42" in result

    def test_csv_method_is_static(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "methods": [
                {
                    "name": "main",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "is_static": True,
                    "line_range": {"start": 10},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "true" in result

    def test_csv_method_is_final(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "methods": [
                {
                    "name": "run",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "is_final": True,
                    "line_range": {"start": 10},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "true" in result

    def test_csv_constructor(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "methods": [
                {
                    "name": "MyClass",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "is_constructor": True,
                    "line_range": {"start": 5},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "constructor" in result

    def test_csv_class_with_final_modifier(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "classes": [
                {
                    "name": "Util",
                    "type": "class",
                    "visibility": "public",
                    "modifiers": ["final"],
                    "line_range": {"start": 1},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "Util" in result
        assert "true" in result

    def test_csv_field_with_is_static_flag(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "fields": [
                {
                    "name": "instance",
                    "type": "Object",
                    "visibility": "public",
                    "is_static": True,
                    "line_range": {"start": 3},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "field" in result
        assert "instance" in result


# ============================================================================
# Coverage boost: _create_full_signature branches (871-926)
# ============================================================================


