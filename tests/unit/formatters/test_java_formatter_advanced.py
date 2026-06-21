#!/usr/bin/env python3
"""
Tests for JavaTableFormatter — structure, advanced, javadoc, private methods,
compact multiple classes, edge cases.
"""

from typing import Any

import pytest

from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter

_FMT = JavaTableFormatter()

_BASE_CLASS = {
    "name": "Test",
    "type": "class",
    "visibility": "public",
    "line_range": {"start": 1, "end": 10},
}
_BASE_DATA: dict[str, Any] = {
    "package": {"name": "com.example"},
    "classes": [_BASE_CLASS],
    "imports": [],
    "methods": [],
    "fields": [],
    "statistics": {"method_count": 0, "field_count": 0},
}


def _data(**overrides: Any) -> dict[str, Any]:
    """Return a copy of _BASE_DATA with top-level keys overridden."""
    return {**_BASE_DATA, **overrides}


class TestFormatStructure:
    """Test format_structure method"""

    def test_format_structure(self):
        """Test structure formatting"""
        result = _FMT.format_structure(_data())
        assert isinstance(result, str)
        assert result


class TestFormatAdvanced:
    """Test format_advanced method"""

    def test_format_advanced_csv(self):
        """Test advanced formatting with CSV"""
        result = _FMT.format_advanced(_data(), output_format="csv")
        assert isinstance(result, str)

    def test_format_advanced_default(self):
        """Test advanced formatting with default format"""
        result = _FMT.format_advanced(_data(), output_format="other")

        assert isinstance(result, str)


class TestJavaDocHandling:
    """Test JavaDoc comment handling"""

    def test_format_with_javadoc(self):
        """Test formatting with JavaDoc comments"""
        data = _data(
            classes=[
                {
                    "name": "Test",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            methods=[
                {
                    "name": "test",
                    "visibility": "public",
                    "return_type": "void",
                    "parameters": [],
                    "is_constructor": False,
                    "line_range": {"start": 10, "end": 12},
                    "complexity_score": 1,
                    "javadoc": "This is a test method",
                }
            ],
            statistics={"method_count": 1, "field_count": 0},
        )

        result = _FMT._format_full_table(data)

        assert isinstance(result, str)


class TestPrivateMethods:
    """Test private method formatting"""

    def test_format_private_methods(self):
        """Test formatting class with private methods"""
        data = _data(
            classes=[
                {
                    "name": "TestClass",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            methods=[
                {
                    "name": "privateHelper",
                    "visibility": "private",
                    "return_type": "void",
                    "parameters": [],
                    "is_constructor": False,
                    "line_range": {"start": 15, "end": 20},
                    "complexity_score": 2,
                    "javadoc": "Private helper method",
                }
            ],
            statistics={"method_count": 1, "field_count": 0},
        )
        result = _FMT._format_full_table(data)
        assert "## Private Methods" in result
        assert "privateHelper" in result

    def test_format_mixed_visibility_methods(self):
        """Test formatting class with both public and private methods"""
        data = _data(
            classes=[
                {
                    "name": "TestClass",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            methods=[
                {
                    "name": "publicMethod",
                    "visibility": "public",
                    "return_type": "String",
                    "parameters": [],
                    "is_constructor": False,
                    "line_range": {"start": 10, "end": 15},
                    "complexity_score": 1,
                    "javadoc": "",
                },
                {
                    "name": "privateMethod",
                    "visibility": "private",
                    "return_type": "void",
                    "parameters": [{"type": "int", "name": "x"}],
                    "is_constructor": False,
                    "line_range": {"start": 20, "end": 25},
                    "complexity_score": 3,
                    "javadoc": "",
                },
            ],
            statistics={"method_count": 2, "field_count": 0},
        )
        result = _FMT._format_full_table(data)
        assert "## Public Methods" in result
        assert "## Private Methods" in result
        assert "publicMethod" in result
        assert "privateMethod" in result


class TestCompactTableMultipleClasses:
    """Test compact table formatting with multiple classes"""

    def test_format_compact_multiple_classes_with_package(self):
        """Test compact format with multiple classes and package"""
        data = _data(
            file_path="path/to/MultiClass.java",
            classes=[
                {
                    "name": "ClassA",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                },
                {
                    "name": "ClassB",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 11, "end": 20},
                },
            ],
        )
        result = _FMT._format_compact_table(data)
        assert "com.example.MultiClass" in result
        assert "## Info" in result

    def test_format_compact_multiple_classes_no_package(self):
        """Test compact format with multiple classes without package"""
        data = _data(
            file_path="path/to/MultiClass.java",
            package={},
            classes=[
                {
                    "name": "ClassA",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                },
                {
                    "name": "ClassB",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 11, "end": 20},
                },
            ],
        )
        result = _FMT._format_compact_table(data)
        assert "MultiClass" in result
        assert "## Info" in result

    def test_format_compact_single_class_no_package(self):
        """Test compact format with single class without package"""
        data = _data(
            package={},
            classes=[
                {
                    "name": "SingleClass",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
        )
        result = _FMT._format_compact_table(data)
        assert "# SingleClass" in result
        assert "## Info" in result


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_format_empty_data(self):
        """Test formatting empty data"""
        result = _FMT._format_full_table(_data(package={}, classes=[], statistics={}))
        assert isinstance(result, str)

    def test_format_missing_package(self):
        """Test formatting with missing package"""
        result = _FMT._format_full_table(_data(package=None))
        assert isinstance(result, str)
        assert "unknown" in result.lower() or "Test" in result

    def test_format_missing_statistics(self):
        """Test formatting with missing statistics"""
        d = _data()
        d.pop("statistics", None)
        result = _FMT._format_full_table(d)
        assert isinstance(result, str)

    def test_format_none_values(self):
        """Test formatting with None values"""
        result = _FMT._format_full_table(
            {
                "package": None,
                "classes": [],
                "imports": [],
                "methods": [],
                "fields": [],
                "statistics": None,
            }
        )
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
