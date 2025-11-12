#!/usr/bin/env python3
"""
Comprehensive tests for JavaTableFormatter.

Tests Java class/method formatting, annotation handling, package declarations,
and various output formats.
"""

import json

import pytest

from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter


class TestJavaTableFormatterInstantiation:
    """Test JavaTableFormatter creation and basic properties"""

    def test_create_formatter(self):
        """Test creating a JavaTableFormatter instance"""
        formatter = JavaTableFormatter()
        assert formatter is not None

    def test_formatter_with_format_type(self):
        """Test creating formatter with specific format type"""
        formatter = JavaTableFormatter(format_type="full")
        assert formatter.format_type == "full"

    def test_formatter_with_compact_format(self):
        """Test creating formatter with compact format"""
        formatter = JavaTableFormatter(format_type="compact")
        assert formatter.format_type == "compact"

    def test_formatter_inheritance(self):
        """Test that JavaTableFormatter inherits from BaseTableFormatter"""
        from tree_sitter_analyzer.formatters.base_formatter import BaseTableFormatter
        
        formatter = JavaTableFormatter()
        assert isinstance(formatter, BaseTableFormatter)


class TestFormatFullTable:
    """Test full table formatting"""

    def test_format_simple_class(self):
        """Test formatting a simple Java class"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "TestClass", "type": "class", "visibility": "public", 
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter._format_full_table(data)
        
        assert "# com.example.TestClass" in result
        assert "## Class Info" in result

    def test_format_class_with_package(self):
        """Test formatting class with package name"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example.test"},
            "classes": [{"name": "MyClass", "type": "class", "visibility": "public",
                        "line_range": {"start": 5, "end": 50}}],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter._format_full_table(data)
        
        assert "com.example.test.MyClass" in result

    def test_format_class_with_imports(self):
        """Test formatting class with imports"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "TestClass", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [
                {"statement": "import java.util.List;"},
                {"statement": "import java.util.Map;"}
            ],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter._format_full_table(data)
        
        assert "## Imports" in result
        assert "java.util.List" in result
        assert "java.util.Map" in result

    def test_format_class_with_fields(self):
        """Test formatting class with fields"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "TestClass", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 20}}],
            "imports": [],
            "methods": [],
            "fields": [
                {"name": "name", "type": "String", "visibility": "private", 
                 "modifiers": [], "line_range": {"start": 5, "end": 5}, "javadoc": ""},
                {"name": "age", "type": "int", "visibility": "private",
                 "modifiers": [], "line_range": {"start": 6, "end": 6}, "javadoc": ""}
            ],
            "statistics": {"method_count": 0, "field_count": 2}
        }
        
        result = formatter._format_full_table(data)
        
        assert "## Fields" in result
        assert "name" in result
        assert "String" in result
        assert "age" in result
        assert "int" in result

    def test_format_class_with_methods(self):
        """Test formatting class with methods"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "TestClass", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 30}}],
            "imports": [],
            "methods": [
                {"name": "getName", "visibility": "public", "return_type": "String",
                 "parameters": [], "is_constructor": False,
                 "line_range": {"start": 10, "end": 12}, "complexity_score": 1, "javadoc": ""}
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0}
        }
        
        result = formatter._format_full_table(data)
        
        assert "## Public Methods" in result
        assert "getName" in result

    def test_format_constructor(self):
        """Test formatting constructor method"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "TestClass", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 20}}],
            "imports": [],
            "methods": [
                {"name": "TestClass", "visibility": "public", "return_type": None,
                 "parameters": [{"type": "String", "name": "param"}], "is_constructor": True,
                 "line_range": {"start": 5, "end": 7}, "complexity_score": 1, "javadoc": ""}
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0}
        }
        
        result = formatter._format_full_table(data)
        
        assert "## Constructor" in result
        assert "TestClass" in result

    def test_format_enum_class(self):
        """Test formatting enum class"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {"name": "Status", "type": "enum", "visibility": "public",
                 "line_range": {"start": 1, "end": 10}, 
                 "constants": ["ACTIVE", "INACTIVE"]}
            ],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter._format_full_table(data)
        
        assert "## Status" in result
        assert "enum" in result
        assert "ACTIVE" in result or "INACTIVE" in result

    def test_format_multiple_classes(self):
        """Test formatting file with multiple classes"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "file_path": "Test.java",
            "classes": [
                {"name": "ClassA", "type": "class", "visibility": "public",
                 "line_range": {"start": 1, "end": 10}},
                {"name": "ClassB", "type": "class", "visibility": "public",
                 "line_range": {"start": 11, "end": 20}}
            ],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter._format_full_table(data)
        
        assert "## Classes" in result
        assert "ClassA" in result
        assert "ClassB" in result


class TestFormatCompactTable:
    """Test compact table formatting"""

    def test_format_compact_basic(self):
        """Test basic compact formatting"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "TestClass", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter._format_compact_table(data)
        
        assert "# com.example.TestClass" in result
        assert "## Info" in result

    def test_format_compact_with_methods(self):
        """Test compact format with methods"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "TestClass", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 20}}],
            "imports": [],
            "methods": [
                {"name": "test", "visibility": "public", "return_type": "void",
                 "parameters": [], "is_constructor": False,
                 "line_range": {"start": 10, "end": 12}, "complexity_score": 1, "javadoc": ""}
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0}
        }
        
        result = formatter._format_compact_table(data)
        
        assert "## Methods" in result
        assert "test" in result


class TestMethodFormatting:
    """Test method signature formatting"""

    def test_format_method_row(self):
        """Test formatting a method row"""
        formatter = JavaTableFormatter()
        method = {
            "name": "testMethod",
            "visibility": "public",
            "return_type": "String",
            "parameters": [{"type": "int", "name": "x"}],
            "line_range": {"start": 10, "end": 15},
            "complexity_score": 2,
            "javadoc": "Test method"
        }
        
        result = formatter._format_method_row(method)
        
        assert "testMethod" in result
        assert "public" in result or "+" in result
        assert "2" in result  # complexity

    def test_create_compact_signature(self):
        """Test creating compact method signature"""
        formatter = JavaTableFormatter()
        method = {
            "parameters": [{"type": "String", "name": "s"}, {"type": "int", "name": "n"}],
            "return_type": "boolean"
        }
        
        result = formatter._create_compact_signature(method)
        
        assert "S" in result  # String -> S
        assert "i" in result  # int -> i
        assert "b" in result  # boolean -> b

    def test_create_full_signature(self):
        """Test creating full method signature"""
        formatter = JavaTableFormatter()
        method = {
            "parameters": [{"type": "String", "name": "text"}],
            "return_type": "void"
        }
        
        result = formatter._create_full_signature(method)
        
        assert "String" in result
        assert "void" in result


class TestTypeShortening:
    """Test type name shortening"""

    def test_shorten_primitive_types(self):
        """Test shortening primitive types"""
        formatter = JavaTableFormatter()
        
        assert formatter._shorten_type("int") == "i"
        assert formatter._shorten_type("long") == "l"
        assert formatter._shorten_type("double") == "d"
        assert formatter._shorten_type("boolean") == "b"
        assert formatter._shorten_type("void") == "void"

    def test_shorten_common_types(self):
        """Test shortening common object types"""
        formatter = JavaTableFormatter()
        
        assert formatter._shorten_type("String") == "S"
        assert formatter._shorten_type("Object") == "O"
        assert formatter._shorten_type("Exception") == "E"

    def test_shorten_collection_types(self):
        """Test shortening collection types"""
        formatter = JavaTableFormatter()
        
        result = formatter._shorten_type("List<String>")
        assert "L<" in result
        assert "S" in result

    def test_shorten_map_types(self):
        """Test shortening map types"""
        formatter = JavaTableFormatter()
        
        result = formatter._shorten_type("Map<String,Object>")
        assert "M<" in result

    def test_shorten_array_types(self):
        """Test shortening array types"""
        formatter = JavaTableFormatter()
        
        result = formatter._shorten_type("String[]")
        assert "S[]" in result

    def test_shorten_none_type(self):
        """Test shortening None type"""
        formatter = JavaTableFormatter()
        
        result = formatter._shorten_type(None)
        assert result == "O"

    def test_shorten_unknown_type(self):
        """Test shortening unknown type"""
        formatter = JavaTableFormatter()
        
        result = formatter._shorten_type("CustomType")
        assert result == "CustomType"


class TestVisibilityConversion:
    """Test visibility indicator conversion"""

    def test_convert_visibility(self):
        """Test converting visibility to indicators"""
        formatter = JavaTableFormatter()
        
        # Should convert to symbols or keep as-is
        public = formatter._convert_visibility("public")
        assert public in ["+", "public", "pub"]
        
        private = formatter._convert_visibility("private")
        assert private in ["-", "private", "priv"]
        
        protected = formatter._convert_visibility("protected")
        assert protected in ["#", "protected", "prot"]


class TestFormatTable:
    """Test format_table method"""

    def test_format_table_full(self):
        """Test format_table with full type"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Test", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter.format_table(data, table_type="full")
        
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_table_compact(self):
        """Test format_table with compact type"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Test", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter.format_table(data, table_type="compact")
        
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_table_json(self):
        """Test format_table with json type"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Test", "type": "class"}]
        }
        
        result = formatter.format_table(data, table_type="json")
        
        assert isinstance(result, str)
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed is not None


class TestFormatSummary:
    """Test format_summary method"""

    def test_format_summary_basic(self):
        """Test basic summary formatting"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Test", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter.format_summary(data)
        
        assert isinstance(result, str)
        assert "com.example" in result


class TestFormatStructure:
    """Test format_structure method"""

    def test_format_structure(self):
        """Test structure formatting"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Test", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
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
            "classes": [{"name": "Test", "type": "class"}]
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
            "classes": [{"name": "Test", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter.format_advanced(data, output_format="csv")
        
        assert isinstance(result, str)

    def test_format_advanced_default(self):
        """Test advanced formatting with default format"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Test", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
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
            "classes": [{"name": "Test", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 20}}],
            "imports": [],
            "methods": [
                {"name": "test", "visibility": "public", "return_type": "void",
                 "parameters": [], "is_constructor": False,
                 "line_range": {"start": 10, "end": 12}, "complexity_score": 1,
                 "javadoc": "This is a test method"}
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0}
        }
        
        result = formatter._format_full_table(data)
        
        assert isinstance(result, str)


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
            "statistics": {}
        }
        
        result = formatter._format_full_table(data)
        
        assert isinstance(result, str)

    def test_format_missing_package(self):
        """Test formatting with missing package"""
        formatter = JavaTableFormatter()
        data = {
            "classes": [{"name": "Test", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0}
        }
        
        result = formatter._format_full_table(data)
        
        assert isinstance(result, str)
        assert "unknown" in result.lower() or "Test" in result

    def test_format_missing_statistics(self):
        """Test formatting with missing statistics"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Test", "type": "class", "visibility": "public",
                        "line_range": {"start": 1, "end": 10}}],
            "imports": [],
            "methods": [],
            "fields": []
        }
        
        result = formatter._format_full_table(data)
        
        assert isinstance(result, str)

    def test_format_none_values(self):
        """Test formatting with None values"""
        formatter = JavaTableFormatter()
        data = {
            "package": None,
            "classes": [],  # Use empty list instead of None
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": None
        }
        
        # Should handle gracefully without crashing
        result = formatter._format_full_table(data)
        
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
