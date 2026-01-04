#!/usr/bin/env python3
"""
Tests for Kotlin-specific table formatter.
"""

from tree_sitter_analyzer.formatters.kotlin_formatter import KotlinTableFormatter


class TestKotlinFormatterInit:
    """Test KotlinTableFormatter initialization"""

    def test_init_default(self):
        """Test default initialization"""
        formatter = KotlinTableFormatter()
        assert formatter is not None
        assert formatter.format_type == "full"

    def test_init_with_format_type(self):
        """Test initialization with format type"""
        formatter = KotlinTableFormatter(format_type="compact")
        assert formatter.format_type == "compact"


class TestKotlinFormatterFormatFullTable:
    """Test full table format for Kotlin"""

    def test_format_full_with_package(self):
        """Test formatting with package name"""
        formatter = KotlinTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "file_path": "src/main/kotlin/Example.kt",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter._format_full_table(data)
        assert "# com.example.Example.kt" in result

    def test_format_full_without_package(self):
        """Test formatting without package name"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "src/main/kotlin/Example.kt",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter._format_full_table(data)
        assert "# Example.kt" in result

    def test_format_full_with_imports(self):
        """Test formatting with imports"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "Example.kt",
            "imports": [
                {"statement": "import java.util.List"},
                {"statement": "import kotlin.collections.ArrayList"},
            ],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter._format_full_table(data)
        assert "## Imports" in result
        assert "import java.util.List" in result
        assert "import kotlin.collections.ArrayList" in result

    def test_format_full_with_classes(self):
        """Test formatting with classes"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "Example.kt",
            "imports": [],
            "classes": [
                {
                    "name": "MyClass",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 50},
                },
                {
                    "name": "MyObject",
                    "type": "object",
                    "visibility": "public",
                    "line_range": {"start": 55, "end": 80},
                },
            ],
            "methods": [],
            "fields": [],
        }
        result = formatter._format_full_table(data)
        assert "## Classes & Objects" in result
        assert "MyClass" in result
        assert "MyObject" in result
        assert "class" in result
        assert "object" in result

    def test_format_full_with_functions(self):
        """Test formatting with functions"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "Example.kt",
            "imports": [],
            "classes": [],
            "methods": [
                {
                    "name": "main",
                    "parameters": [{"name": "args", "type": "Array<String>"}],
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                    "is_suspend": False,
                    "docstring": "Main function",
                },
                {
                    "name": "suspendFunction",
                    "parameters": [],
                    "visibility": "private",
                    "line_range": {"start": 15, "end": 20},
                    "is_suspend": True,
                    "docstring": "Suspend function",
                },
            ],
            "fields": [],
        }
        result = formatter._format_full_table(data)
        assert "## Functions" in result
        assert "main" in result
        assert "suspendFunction" in result
        assert "Yes" in result  # is_suspend = True
        assert "-" in result  # is_suspend = False

    def test_format_full_with_properties(self):
        """Test formatting with properties"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "Example.kt",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [
                {
                    "name": "myProperty",
                    "type": "String",
                    "visibility": "public",
                    "is_val": True,
                    "line_range": {"start": 10, "end": 10},
                    "docstring": "My property",
                },
                {
                    "name": "myVariable",
                    "type": "Int",
                    "visibility": "private",
                    "is_var": True,
                    "line_range": {"start": 15, "end": 15},
                    "docstring": "My variable",
                },
            ],
        }
        result = formatter._format_full_table(data)
        assert "## Properties" in result
        assert "myProperty" in result
        assert "myVariable" in result
        assert "val" in result
        assert "var" in result


class TestKotlinFormatterFormatCompactTable:
    """Test compact table format for Kotlin"""

    def test_format_compact_with_package(self):
        """Test compact format with package"""
        formatter = KotlinTableFormatter(format_type="compact")
        data = {
            "package": {"name": "com.example"},
            "file_path": "Example.kt",
            "statistics": {"method_count": 5, "field_count": 3},
            "methods": [],
        }
        result = formatter._format_compact_table(data)
        assert "# com.example.Example.kt" in result
        assert "## Info" in result
        assert "Package" in result

    def test_format_compact_with_functions(self):
        """Test compact format with functions"""
        formatter = KotlinTableFormatter(format_type="compact")
        data = {
            "file_path": "Example.kt",
            "methods": [
                {
                    "name": "testFunc",
                    "parameters": [{"name": "x", "type": "Int"}],
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                    "is_suspend": False,
                    "docstring": "Test function",
                },
            ],
        }
        result = formatter._format_compact_table(data)
        assert "## Functions" in result
        assert "testFunc" in result


class TestKotlinFormatterFormatFnRow:
    """Test function row formatting"""

    def test_format_fn_row_with_params(self):
        """Test formatting function with parameters"""
        formatter = KotlinTableFormatter()
        fn = {
            "name": "myFunction",
            "parameters": [
                {"name": "x", "type": "Int"},
                {"name": "y", "type": "String"},
            ],
            "visibility": "public",
            "line_range": {"start": 10, "end": 15},
            "is_suspend": False,
            "docstring": "My function",
        }
        result = formatter._format_fn_row(fn)
        assert "myFunction" in result
        assert "x: Int" in result
        assert "y: String" in result

    def test_format_fn_row_suspend(self):
        """Test formatting suspend function"""
        formatter = KotlinTableFormatter()
        fn = {
            "name": "suspendFunc",
            "parameters": [],
            "visibility": "private",
            "line_range": {"start": 20, "end": 25},
            "is_suspend": True,
            "docstring": "Suspend function",
        }
        result = formatter._format_fn_row(fn)
        assert "Yes" in result


class TestKotlinFormatterFormatPropRow:
    """Test property row formatting"""

    def test_format_prop_row_val(self):
        """Test formatting val property"""
        formatter = KotlinTableFormatter()
        prop = {
            "name": "myVal",
            "type": "String",
            "visibility": "public",
            "is_val": True,
            "line_range": {"start": 5, "end": 5},
            "docstring": "My val",
        }
        result = formatter._format_prop_row(prop)
        assert "myVal" in result
        assert "val" in result

    def test_format_prop_row_var(self):
        """Test formatting var property"""
        formatter = KotlinTableFormatter()
        prop = {
            "name": "myVar",
            "type": "Int",
            "visibility": "private",
            "is_var": True,
            "line_range": {"start": 10, "end": 10},
            "docstring": "My var",
        }
        result = formatter._format_prop_row(prop)
        assert "myVar" in result
        assert "var" in result


class TestKotlinFormatterCreateSignature:
    """Test signature creation"""

    def test_create_full_signature_with_params(self):
        """Test creating full signature with parameters"""
        formatter = KotlinTableFormatter()
        fn = {
            "name": "myFunc",
            "parameters": [
                {"name": "x", "type": "Int"},
                {"name": "y", "type": "String"},
            ],
            "return_type": "Boolean",
        }
        result = formatter._create_full_signature(fn)
        assert "fun(x: Int, y: String): Boolean" in result

    def test_create_full_signature_no_return(self):
        """Test creating full signature without return type"""
        formatter = KotlinTableFormatter()
        fn = {
            "name": "myFunc",
            "parameters": [{"name": "x", "type": "Int"}],
            "return_type": "Unit",
        }
        result = formatter._create_full_signature(fn)
        assert "fun(x: Int)" in result
        assert ": Unit" not in result

    def test_create_compact_signature(self):
        """Test creating compact signature"""
        formatter = KotlinTableFormatter()
        fn = {
            "name": "myFunc",
            "parameters": [
                {"name": "x", "type": "Int"},
                {"name": "y", "type": "String"},
            ],
            "return_type": "Boolean",
        }
        result = formatter._create_compact_signature(fn)
        assert "(2):Boolean" in result


class TestKotlinFormatterConvertVisibility:
    """Test visibility conversion"""

    def test_convert_visibility_public(self):
        """Test converting public visibility"""
        formatter = KotlinTableFormatter()
        result = formatter._convert_visibility("public")
        assert result == "pub"

    def test_convert_visibility_private(self):
        """Test converting private visibility"""
        formatter = KotlinTableFormatter()
        result = formatter._convert_visibility("private")
        assert result == "priv"

    def test_convert_visibility_protected(self):
        """Test converting protected visibility"""
        formatter = KotlinTableFormatter()
        result = formatter._convert_visibility("protected")
        assert result == "prot"

    def test_convert_visibility_internal(self):
        """Test converting internal visibility"""
        formatter = KotlinTableFormatter()
        result = formatter._convert_visibility("internal")
        assert result == "int"

    def test_convert_visibility_unknown(self):
        """Test converting unknown visibility"""
        formatter = KotlinTableFormatter()
        result = formatter._convert_visibility("unknown")
        assert result == "unknown"


class TestKotlinFormatterFormatTable:
    """Test format_table method"""

    def test_format_table_full(self):
        """Test format_table with full type"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "Example.kt",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_table(data, "full")
        assert result is not None
        assert "Example.kt" in result

    def test_format_table_compact(self):
        """Test format_table with compact type"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "Example.kt",
            "methods": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter.format_table(data, "compact")
        assert result is not None
        assert "## Info" in result

    def test_format_table_json(self):
        """Test format_table with JSON type"""
        formatter = KotlinTableFormatter()
        data = {"file_path": "Example.kt", "imports": []}
        result = formatter.format_table(data, "json")
        assert result is not None
        assert "{" in result or "[]" in result


class TestKotlinFormatterFormatSummary:
    """Test format_summary method"""

    def test_format_summary(self):
        """Test format_summary method"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "Example.kt",
            "methods": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter.format_summary(data)
        assert result is not None
        assert "## Info" in result


class TestKotlinFormatterFormatStructure:
    """Test format_structure method"""

    def test_format_structure_full(self):
        """Test format_structure with full type"""
        formatter = KotlinTableFormatter(format_type="full")
        data = {
            "file_path": "Example.kt",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert result is not None
        assert "Example.kt" in result

    def test_format_structure_compact(self):
        """Test format_structure with compact type"""
        formatter = KotlinTableFormatter(format_type="compact")
        data = {
            "file_path": "Example.kt",
            "methods": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter.format_structure(data)
        assert result is not None
        assert "## Info" in result


class TestKotlinFormatterFormatAdvanced:
    """Test format_advanced method"""

    def test_format_advanced_json(self):
        """Test format_advanced with JSON output"""
        formatter = KotlinTableFormatter()
        data = {"file_path": "Example.kt", "imports": []}
        result = formatter.format_advanced(data, "json")
        assert result is not None
        assert "{" in result or "[]" in result

    def test_format_advanced_csv(self):
        """Test format_advanced with CSV output"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "Example.kt",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_advanced(data, "csv")
        assert result is not None

    def test_format_advanced_default(self):
        """Test format_advanced with default output"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "Example.kt",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_advanced(data, "full")
        assert result is not None


class TestKotlinFormatterFormatJson:
    """Test _format_json method"""

    def test_format_json_valid_data(self):
        """Test formatting valid JSON data"""
        formatter = KotlinTableFormatter()
        data = {"file_path": "Example.kt", "imports": []}
        result = formatter._format_json(data)
        assert result is not None
        assert "Example.kt" in result

    def test_format_json_invalid_data(self):
        """Test formatting invalid JSON data"""
        formatter = KotlinTableFormatter()
        # Create data that might cause JSON serialization issues
        data = {"file_path": "Example.kt", "imports": [{"statement": object()}]}
        result = formatter._format_json(data)
        # Should handle the error gracefully
        assert result is not None


class TestKotlinFormatterEdgeCases:
    """Test edge cases"""

    def test_empty_data(self):
        """Test with empty data"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "Example.kt",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert result is not None

    def test_windows_path(self):
        """Test with Windows file path"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "C:\\Projects\\Example.kt",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert "Example.kt" in result

    def test_unix_path(self):
        """Test with Unix file path"""
        formatter = KotlinTableFormatter()
        data = {
            "file_path": "/home/user/projects/Example.kt",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert "Example.kt" in result

    def test_long_function_signature(self):
        """Test with long function signature"""
        formatter = KotlinTableFormatter()
        params = [{"name": f"param{i}", "type": "String"} for i in range(10)]
        fn = {
            "name": "longFunction",
            "parameters": params,
            "visibility": "public",
            "line_range": {"start": 10, "end": 20},
            "is_suspend": False,
            "docstring": "Long function",
        }
        result = formatter._format_fn_row(fn)
        assert "longFunction" in result
        assert "param0" in result
        assert "param9" in result
