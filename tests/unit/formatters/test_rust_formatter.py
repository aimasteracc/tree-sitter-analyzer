#!/usr/bin/env python3
"""
Tests for Rust-specific table formatter.
"""

import pytest

from tree_sitter_analyzer.formatters.rust_formatter import RustTableFormatter


class TestRustFormatterSignaturesUnsupported:
    """Rust does not support the signatures directory mode; it must raise the
    same enumerable error as the base/Go formatter, not silently render the
    full table (regression: it fell through to _format_full_table)."""

    def test_format_structure_signatures_raises_enumerable(self):
        formatter = RustTableFormatter(format_type="signatures")
        data = {
            "file_path": "lib.rs",
            "methods": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        with pytest.raises(ValueError, match="signatures format not supported"):
            formatter.format_structure(data)


class TestRustFormatterInit:
    """Test RustTableFormatter initialization"""

    def test_init_default(self):
        """Test default initialization"""
        formatter = RustTableFormatter()
        assert formatter is not None
        assert formatter.format_type == "full"

    def test_init_with_format_type(self):
        """Test initialization with format type"""
        formatter = RustTableFormatter(format_type="compact")
        assert formatter.format_type == "compact"


class TestRustFormatterFormatFullTable:
    """Test full table format for Rust"""

    def test_format_full_with_modules(self):
        """Test formatting with modules"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/main.rs",
            "modules": [
                {
                    "name": "my_module",
                    "visibility": "pub",
                    "line_range": {"start": 1, "end": 100},
                },
            ],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter._format_full_table(data)
        assert "## Modules" in result
        assert "my_module" in result

    def test_format_full_with_structs(self):
        """Test formatting with structs"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/main.rs",
            "modules": [],
            "classes": [
                {
                    "name": "MyStruct",
                    "type": "struct",
                    "visibility": "pub",
                    "line_range": {"start": 10, "end": 50},
                },
                {
                    "name": "MyEnum",
                    "type": "enum",
                    "visibility": "pub",
                    "line_range": {"start": 55, "end": 80},
                },
            ],
            "methods": [],
            "fields": [],
        }
        result = formatter._format_full_table(data)
        assert "## Structs" in result
        assert "MyStruct" in result
        assert "MyEnum" in result
        assert "struct" in result
        assert "enum" in result

    def test_format_full_with_impls(self):
        """Test formatting with impl blocks"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/main.rs",
            "modules": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "impls": [
                {
                    "type": "MyStruct",
                    "trait": "MyTrait",
                    "line_range": {"start": 100, "end": 150},
                },
                {
                    "type": "AnotherStruct",
                    "trait": "-",
                    "line_range": {"start": 155, "end": 200},
                },
            ],
        }
        result = formatter._format_full_table(data)
        assert "## Implementations" in result
        assert "MyStruct" in result
        assert "MyTrait" in result

    def test_format_full_with_functions(self):
        """Test formatting with functions"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/main.rs",
            "modules": [],
            "classes": [],
            "methods": [
                {
                    "name": "main",
                    "parameters": [],
                    "visibility": "pub",
                    "line_range": {"start": 5, "end": 10},
                    "is_async": False,
                    "docstring": "Main function",
                },
                {
                    "name": "async_function",
                    "parameters": [],
                    "visibility": "pub",
                    "line_range": {"start": 15, "end": 20},
                    "is_async": True,
                    "docstring": "Async function",
                },
            ],
            "fields": [],
        }
        result = formatter._format_full_table(data)
        assert "## Functions" in result
        assert "main" in result
        assert "async_function" in result
        assert "Yes" in result  # is_async = True
        assert "-" in result  # is_async = False

    def test_full_table_has_complexity_column(self):
        """The full Functions table must expose a Cx column with the computed
        complexity (parity with the Go full table; Rust complexity is computed
        as of the always-1 fix but was not surfaced in the markdown table)."""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/lib.rs",
            "modules": [],
            "classes": [],
            "methods": [
                {
                    "name": "binary_search",
                    "parameters": [],
                    "visibility": "pub",
                    "line_range": {"start": 1, "end": 14},
                    "is_async": False,
                    "docstring": "",
                    "complexity_score": 4,
                }
            ],
            "fields": [],
        }
        result = formatter._format_full_table(data)
        header = next(line for line in result.splitlines() if "| Function " in line)
        assert "Cx" in header
        row = next(line for line in result.splitlines() if "binary_search" in line)
        assert "| 4 |" in row


class TestRustFormatterFormatCompactTable:
    """Test compact table format for Rust"""

    def test_format_compact_with_modules(self):
        """Test compact format with modules"""
        formatter = RustTableFormatter(format_type="compact")
        data = {
            "file_path": "src/main.rs",
            "modules": [],
            "statistics": {"method_count": 5, "lines": 100},
            "methods": [],
        }
        result = formatter._format_compact_table(data)
        assert "# main.rs" in result
        assert "## Info" in result
        assert "Structs" in result

    def test_format_compact_with_functions(self):
        """Test compact format with functions"""
        formatter = RustTableFormatter(format_type="compact")
        data = {
            "file_path": "src/main.rs",
            "methods": [
                {
                    "name": "test_func",
                    "parameters": [],
                    "visibility": "pub",
                    "line_range": {"start": 5, "end": 10},
                    "is_async": False,
                    "docstring": "Test function",
                },
            ],
        }
        result = formatter._format_compact_table(data)
        assert "## Functions" in result
        assert "test_func" in result


class TestRustFormatterFormatFnRow:
    """Test function row formatting"""

    def test_format_fn_row_with_params(self):
        """Test formatting function with parameters"""
        formatter = RustTableFormatter()
        fn = {
            "name": "my_function",
            "parameters": ["x: i32", "y: String"],
            "visibility": "pub",
            "line_range": {"start": 10, "end": 15},
            "is_async": False,
            "docstring": "My function",
        }
        result = formatter._format_fn_row(fn)
        assert "my_function" in result
        assert "x: i32" in result
        assert "y: String" in result

    def test_format_fn_row_async(self):
        """Test formatting async function"""
        formatter = RustTableFormatter()
        fn = {
            "name": "async_fn",
            "parameters": [],
            "visibility": "pub",
            "line_range": {"start": 20, "end": 25},
            "is_async": True,
            "docstring": "Async function",
        }
        result = formatter._format_fn_row(fn)
        assert "Yes" in result


class TestRustFormatterCreateSignature:
    """Test signature creation"""

    def test_create_full_signature_with_params(self):
        """Test creating full signature with parameters"""
        formatter = RustTableFormatter()
        fn = {
            "name": "my_func",
            "parameters": ["x: i32", "y: String"],
            "return_type": "bool",
        }
        result = formatter._create_full_signature(fn)
        assert "fn(x: i32, y: String) -> bool" in result

    def test_create_full_signature_no_return(self):
        """Test creating full signature without return type"""
        formatter = RustTableFormatter()
        fn = {
            "name": "my_func",
            "parameters": ["x: i32"],
            "return_type": "()",
        }
        result = formatter._create_full_signature(fn)
        assert "fn(x: i32)" in result
        assert "-> ()" not in result

    def test_create_compact_signature(self):
        """Test creating compact signature"""
        formatter = RustTableFormatter()
        fn = {
            "name": "my_func",
            "parameters": ["x: i32", "y: String"],
            "return_type": "bool",
        }
        result = formatter._create_compact_signature(fn)
        assert "(2)->bool" in result


class TestRustFormatterConvertVisibility:
    """Test visibility conversion"""

    def test_convert_visibility_pub(self):
        """Test converting pub visibility"""
        formatter = RustTableFormatter()
        result = formatter._convert_visibility("pub")
        assert result == "pub"

    def test_convert_visibility_pub_crate(self):
        """Test converting pub(crate) visibility"""
        formatter = RustTableFormatter()
        result = formatter._convert_visibility("pub(crate)")
        assert result == "crate"

    def test_convert_visibility_private(self):
        """Test converting private visibility"""
        formatter = RustTableFormatter()
        result = formatter._convert_visibility("private")
        assert result == "priv"

    def test_convert_visibility_unknown(self):
        """Test converting unknown visibility"""
        formatter = RustTableFormatter()
        result = formatter._convert_visibility("unknown")
        assert result == "unknown"


class TestRustFormatterFormatTable:
    """Test format_table method"""

    def test_format_table_full(self):
        """Test format_table with full type"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/main.rs",
            "modules": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_table(data, "full")
        assert result is not None
        assert "# main.rs" in result

    def test_format_table_compact(self):
        """Test format_table with compact type"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/main.rs",
            "methods": [],
            "statistics": {"method_count": 0, "lines": 0},
        }
        result = formatter.format_table(data, "compact")
        assert result is not None
        assert "## Info" in result

    def test_format_table_json(self):
        """Test format_table with JSON type"""
        formatter = RustTableFormatter()
        data = {"file_path": "src/main.rs", "modules": []}
        result = formatter.format_table(data, "json")
        assert result is not None
        assert "{" in result or "[]" in result


class TestRustFormatterFormatSummary:
    """Test format_summary method"""

    def test_format_summary(self):
        """Test format_summary method"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/main.rs",
            "methods": [],
            "statistics": {"method_count": 0, "lines": 0},
        }
        result = formatter.format_summary(data)
        assert result is not None
        assert "## Info" in result


class TestRustFormatterFormatStructure:
    """Test format_structure method"""

    def test_format_structure_full(self):
        """Test format_structure with full type"""
        formatter = RustTableFormatter(format_type="full")
        data = {
            "file_path": "src/main.rs",
            "modules": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert result is not None
        assert "# main.rs" in result

    def test_format_structure_compact(self):
        """Test format_structure with compact type"""
        formatter = RustTableFormatter(format_type="compact")
        data = {
            "file_path": "src/main.rs",
            "methods": [],
            "statistics": {"method_count": 0, "lines": 0},
        }
        result = formatter.format_structure(data)
        assert result is not None
        assert "## Info" in result


class TestRustFormatterFormatAdvanced:
    """Test format_advanced method"""

    def test_format_advanced_json(self):
        """Test format_advanced with JSON output"""
        formatter = RustTableFormatter()
        data = {"file_path": "src/main.rs", "modules": []}
        result = formatter.format_advanced(data, "json")
        assert result is not None
        assert "{" in result or "[]" in result

    def test_format_advanced_csv(self):
        """Test format_advanced with CSV output"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/main.rs",
            "modules": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_advanced(data, "csv")
        assert result is not None

    def test_format_advanced_default(self):
        """Test format_advanced with default output"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/main.rs",
            "modules": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_advanced(data, "full")
        assert result is not None


class TestRustFormatterFormatJson:
    """Test _format_json method"""

    def test_format_json_valid_data(self):
        """Test formatting valid JSON data"""
        formatter = RustTableFormatter()
        data = {"file_path": "src/main.rs", "modules": []}
        result = formatter._format_json(data)
        assert result is not None
        assert "src/main.rs" in result

    def test_format_json_invalid_data(self):
        """Test formatting invalid JSON data"""
        formatter = RustTableFormatter()
        # Create data that might cause JSON serialization issues
        data = {"file_path": "src/main.rs", "modules": [{"statement": object()}]}
        result = formatter._format_json(data)
        # Should handle error gracefully
        assert result is not None


class TestRustFormatterParamDictLeak:
    """Regression tests: parameters must never render as raw Python dicts.

    Before the fix, parameters provided as dicts (e.g. from the Rust extractor)
    were coerced via ``str(p)`` which produced the ugly
    ``{'name': 'self', 'type': 'Any'}`` literal in the signature column.
    """

    def test_format_rust_param_dict_self(self):
        """self param as dict renders as bare 'self' (Rust convention)."""
        formatter = RustTableFormatter()
        result = formatter._format_rust_param({"name": "self", "type": "Any"})
        assert result == "self"
        assert "{'name'" not in result

    def test_format_rust_param_dict_ref_self(self):
        """&self param as dict renders as '&self'."""
        formatter = RustTableFormatter()
        result = formatter._format_rust_param({"name": "&self", "type": "Any"})
        assert result == "&self"
        assert "{'name'" not in result

    def test_format_rust_param_dict_mut_self(self):
        """&mut self param as dict renders as '&mut self'."""
        formatter = RustTableFormatter()
        result = formatter._format_rust_param({"name": "&mut self", "type": "Any"})
        assert result == "&mut self"
        assert "{'name'" not in result

    def test_format_rust_param_dict_typed(self):
        """Typed param renders as 'name: type'."""
        formatter = RustTableFormatter()
        result = formatter._format_rust_param({"name": "value", "type": "&T"})
        assert result == "value: &T"
        assert "{'name'" not in result

    def test_format_rust_param_dict_i32(self):
        """Typed param with primitive type renders correctly."""
        formatter = RustTableFormatter()
        result = formatter._format_rust_param({"name": "a", "type": "i32"})
        assert result == "a: i32"
        assert "{'name'" not in result

    def test_format_rust_param_string(self):
        """String params (already formatted) pass through unchanged."""
        formatter = RustTableFormatter()
        assert formatter._format_rust_param("x: i32") == "x: i32"
        assert formatter._format_rust_param("&self") == "&self"

    def test_create_full_signature_dict_params_no_leak(self):
        """Full signature with dict params must not contain literal braces."""
        formatter = RustTableFormatter()
        fn = {
            "name": "search",
            "parameters": [
                {"name": "self", "type": "Any"},
                {"name": "value", "type": "&T"},
            ],
            "return_type": "bool",
        }
        result = formatter._create_full_signature(fn)
        assert result == "fn(self, value: &T) -> bool"
        assert "{'name'" not in result

    def test_create_full_signature_add_dict_params(self):
        """fn(a: i32, b: i32) -> i32 from dict params."""
        formatter = RustTableFormatter()
        fn = {
            "name": "add",
            "parameters": [
                {"name": "a", "type": "i32"},
                {"name": "b", "type": "i32"},
            ],
            "return_type": "i32",
        }
        result = formatter._create_full_signature(fn)
        assert result == "fn(a: i32, b: i32) -> i32"
        assert "{'name'" not in result

    def test_format_full_table_dict_params_no_leak(self):
        """Full table output must not contain raw dict reprs in any row."""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/lib.rs",
            "modules": [],
            "classes": [],
            "methods": [
                {
                    "name": "search",
                    "parameters": [
                        {"name": "self", "type": "Any"},
                        {"name": "value", "type": "&T"},
                    ],
                    "visibility": "pub",
                    "return_type": "bool",
                    "line_range": {"start": 10, "end": 15},
                    "is_async": False,
                    "docstring": "",
                },
                {
                    "name": "new",
                    "parameters": [],
                    "visibility": "pub",
                    "return_type": "Self",
                    "line_range": {"start": 20, "end": 25},
                    "is_async": False,
                    "docstring": "",
                },
            ],
            "fields": [],
        }
        result = formatter._format_full_table(data)
        assert "{'name'" not in result
        assert "search" in result
        assert "fn(self, value: &T) -> bool" in result
        assert "fn() -> Self" in result


class TestRustFormatterEdgeCases:
    """Test edge cases"""

    def test_empty_data(self):
        """Test with empty data"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "src/main.rs",
            "modules": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert result is not None

    def test_windows_path(self):
        """Test with Windows file path"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "C:\\Projects\\src\\main.rs",
            "modules": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert "main.rs" in result

    def test_unix_path(self):
        """Test with Unix file path"""
        formatter = RustTableFormatter()
        data = {
            "file_path": "/home/user/projects/src/main.rs",
            "modules": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert "main.rs" in result

    def test_long_function_signature(self):
        """Test with long function signature"""
        formatter = RustTableFormatter()
        params = [f"param{i}: i32" for i in range(10)]
        fn = {
            "name": "long_function",
            "parameters": params,
            "visibility": "pub",
            "line_range": {"start": 10, "end": 20},
            "is_async": False,
            "docstring": "Long function",
        }
        result = formatter._format_fn_row(fn)
        assert "long_function" in result
        assert "param0" in result
        assert "param9" in result
