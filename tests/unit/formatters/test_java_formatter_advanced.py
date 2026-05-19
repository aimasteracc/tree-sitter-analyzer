#!/usr/bin/env python3
"""
Tests for JavaTableFormatter — structure, advanced, javadoc, private methods,
compact multiple classes, edge cases.
"""

import json

import pytest

from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter


class TestFormatStructure:
    """Test format_structure method"""

    def test_format_structure(self):
        """Test structure formatting"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": "Test",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_structure(data)

        assert isinstance(result, str)
        assert len(result) > 0


class TestFormatAdvanced:
    """Test format_advanced method"""

    def test_format_advanced_json(self):
        """Test advanced formatting with JSON"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Test", "type": "class"}],
        }

        result = formatter.format_advanced(data, output_format="json")

        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed is not None

    def test_format_advanced_csv(self):
        """Test advanced formatting with CSV"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": "Test",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_advanced(data, output_format="csv")

        assert isinstance(result, str)

    def test_format_advanced_default(self):
        """Test advanced formatting with default format"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": "Test",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter.format_advanced(data, output_format="other")

        assert isinstance(result, str)


class TestJavaDocHandling:
    """Test JavaDoc comment handling"""

    def test_format_with_javadoc(self):
        """Test formatting with JavaDoc comments"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": "Test",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "imports": [],
            "methods": [
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
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter._format_full_table(data)

        assert isinstance(result, str)


class TestPrivateMethods:
    """Test private method formatting"""

    def test_format_private_methods(self):
        """Test formatting class with private methods"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": "TestClass",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "imports": [],
            "methods": [
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
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }

        result = formatter._format_full_table(data)

        assert "## Private Methods" in result
        assert "privateHelper" in result

    def test_format_mixed_visibility_methods(self):
        """Test formatting class with both public and private methods"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": "TestClass",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "imports": [],
            "methods": [
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
            "fields": [],
            "statistics": {"method_count": 2, "field_count": 0},
        }

        result = formatter._format_full_table(data)

        assert "## Public Methods" in result
        assert "## Private Methods" in result
        assert "publicMethod" in result
        assert "privateMethod" in result


class TestCompactTableMultipleClasses:
    """Test compact table formatting with multiple classes"""

    def test_format_compact_multiple_classes_with_package(self):
        """Test compact format with multiple classes and package"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "file_path": "path/to/MultiClass.java",
            "classes": [
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
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter._format_compact_table(data)

        assert "com.example.MultiClass" in result
        assert "## Info" in result

    def test_format_compact_multiple_classes_no_package(self):
        """Test compact format with multiple classes without package"""
        formatter = JavaTableFormatter()
        data = {
            "file_path": "path/to/MultiClass.java",
            "classes": [
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
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter._format_compact_table(data)

        assert "MultiClass" in result
        assert "## Info" in result

    def test_format_compact_single_class_no_package(self):
        """Test compact format with single class without package"""
        formatter = JavaTableFormatter()
        data = {
            "classes": [
                {
                    "name": "SingleClass",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter._format_compact_table(data)

        assert "# SingleClass" in result
        assert "## Info" in result


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_format_empty_data(self):
        """Test formatting empty data"""
        formatter = JavaTableFormatter()
        data = {
            "package": {},
            "classes": [],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {},
        }

        result = formatter._format_full_table(data)

        assert isinstance(result, str)

    def test_format_missing_package(self):
        """Test formatting with missing package"""
        formatter = JavaTableFormatter()
        data = {
            "classes": [
                {
                    "name": "Test",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }

        result = formatter._format_full_table(data)

        assert isinstance(result, str)
        assert "unknown" in result.lower() or "Test" in result

    def test_format_missing_statistics(self):
        """Test formatting with missing statistics"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": "Test",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "imports": [],
            "methods": [],
            "fields": [],
        }

        result = formatter._format_full_table(data)

        assert isinstance(result, str)

    def test_format_none_values(self):
        """Test formatting with None values"""
        formatter = JavaTableFormatter()
        data = {
            "package": None,
            "classes": [],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": None,
        }

        result = formatter._format_full_table(data)

        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
