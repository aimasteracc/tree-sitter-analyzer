#!/usr/bin/env python3
"""Comprehensive tests for JavaScript formatter."""

import pytest
from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)


class TestJavaScriptFormatterBasic:
    """Basic functionality tests"""

    def setup_method(self) -> None:
        """Setup test fixtures"""
        self.formatter = JavaScriptTableFormatter()

    def test_format_calls_format_structure(self) -> None:
        """Test format method delegates to format_structure"""
        data = {"file_path": "test.js", "statistics": {}, "functions": []}
        result = self.formatter.format(data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_empty_data(self) -> None:
        """Test formatting empty data"""
        data: dict = {}
        result = self.formatter.format(data)
        assert isinstance(result, str)

    def test_format_minimal_data(self) -> None:
        """Test formatting minimal data"""
        data = {
            "file_path": "app.js",
            "statistics": {},
        }
        result = self.formatter.format(data)
        assert "app" in result


class TestJavaScriptFormatterFullTable:
    """Full table format tests"""

    def setup_method(self) -> None:
        """Setup test fixtures"""
        self.formatter = JavaScriptTableFormatter()

    def test_full_table_basic_module(self) -> None:
        """Test full table for basic module"""
        data = {
            "file_path": "module.js",
            "exports": [{"name": "foo", "is_default": False}],
            "statistics": {"function_count": 1, "variable_count": 2},
            "classes": [],
            "imports": [],
            "functions": [],
            "variables": [],
        }
        result = self.formatter._format_full_table(data)
        assert "# Module: module" in result
        assert "## Module Info" in result
        assert "ES6 Module" in result

    def test_full_table_script_without_exports(self) -> None:
        """Test full table for script without exports"""
        data = {
            "file_path": "script.js",
            "exports": [],
            "statistics": {"function_count": 0, "variable_count": 0},
            "classes": [],
        }
        result = self.formatter._format_full_table(data)
        assert "# Script: script" in result

    def test_full_table_with_imports(self) -> None:
        """Test full table with imports"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "imports": [
                {"statement": "import React from 'react';"},
                {"name": "lodash", "source": "'lodash'", "statement": ""},
            ],
            "statistics": {},
            "classes": [],
        }
        result = self.formatter._format_full_table(data)
        assert "## Imports" in result
        assert "import React from 'react';" in result
        assert "import lodash from 'lodash';" in result

    def test_full_table_with_classes(self) -> None:
        """Test full table with classes"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [
                {
                    "name": "MyClass",
                    "superclass": "BaseClass",
                    "line_range": {"start": 10, "end": 20},
                }
            ],
            "methods": [
                {
                    "name": "method1",
                    "line_range": {"start": 11, "end": 13},
                }
            ],
            "variables": [
                {
                    "name": "prop1",
                    "line_range": {"start": 14, "end": 14},
                }
            ],
        }
        result = self.formatter._format_full_table(data)
        assert "## Classes" in result
        assert "MyClass" in result
        assert "BaseClass" in result
        assert "10-20" in result

    def test_full_table_with_variables(self) -> None:
        """Test full table with variables"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "variables": [
                {
                    "name": "myVar",
                    "initializer": '"hello"',
                    "line_range": {"start": 5, "end": 5},
                    "is_constant": False,
                    "raw_text": "let myVar",
                },
                {
                    "name": "myConst",
                    "initializer": "42",
                    "line_range": {"start": 6, "end": 6},
                    "is_constant": True,
                    "raw_text": "const myConst",
                },
            ],
        }
        result = self.formatter._format_full_table(data)
        assert "## Variables" in result
        assert "myVar" in result
        assert "myConst" in result
        assert "string" in result
        assert "number" in result

    def test_full_table_with_functions(self) -> None:
        """Test full table with regular functions"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "functions": [
                {
                    "name": "regularFunc",
                    "parameters": [{"name": "x", "type": "number"}],
                    "line_range": {"start": 10, "end": 15},
                    "complexity_score": 2,
                    "jsdoc": "A regular function",
                    "is_async": False,
                    "is_method": False,
                }
            ],
        }
        result = self.formatter._format_full_table(data)
        assert "## Functions" in result
        assert "regularFunc" in result

    def test_full_table_with_async_functions(self) -> None:
        """Test full table with async functions"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "functions": [
                {
                    "name": "asyncFunc",
                    "parameters": [],
                    "line_range": {"start": 20, "end": 25},
                    "complexity_score": 1,
                    "jsdoc": "An async function",
                    "is_async": True,
                    "is_method": False,
                }
            ],
        }
        result = self.formatter._format_full_table(data)
        assert "## Async Functions" in result
        assert "asyncFunc" in result

    def test_full_table_with_methods(self) -> None:
        """Test full table with class methods"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "functions": [
                {
                    "name": "myMethod",
                    "parameters": [],
                    "line_range": {"start": 30, "end": 35},
                    "complexity_score": 1,
                    "jsdoc": "A class method",
                    "is_async": False,
                    "is_method": True,
                    "class_name": "MyClass",
                }
            ],
        }
        result = self.formatter._format_full_table(data)
        assert "## Methods" in result
        assert "myMethod" in result
        assert "MyClass" in result

    def test_full_table_with_exports(self) -> None:
        """Test full table with exports"""
        data = {
            "file_path": "test.js",
            "exports": [
                {"name": "defaultExport", "is_default": True},
                {"name": "namedExport", "is_default": False, "is_named": True},
            ],
            "statistics": {},
            "classes": [],
        }
        result = self.formatter._format_full_table(data)
        assert "## Exports" in result
        assert "defaultExport" in result
        assert "namedExport" in result
        assert "✓" in result

    def test_full_table_jsx_file(self) -> None:
        """Test full table with JSX file"""
        data = {
            "file_path": "component.jsx",
            "exports": [],
            "statistics": {},
            "classes": [],
        }
        result = self.formatter._format_full_table(data)
        assert "component" in result

    def test_full_table_mjs_file(self) -> None:
        """Test full table with MJS file"""
        data = {
            "file_path": "module.mjs",
            "exports": [{"name": "test"}],
            "statistics": {},
            "classes": [],
        }
        result = self.formatter._format_full_table(data)
        assert "module" in result


class TestJavaScriptFormatterCompactTable:
    """Compact table format tests"""

    def setup_method(self) -> None:
        """Setup test fixtures"""
        self.formatter = JavaScriptTableFormatter()

    def test_compact_table_basic(self) -> None:
        """Test compact table basic format"""
        data = {
            "file_path": "test.js",
            "statistics": {"function_count": 1, "variable_count": 2},
            "classes": [],
            "exports": [],
        }
        result = self.formatter._format_compact_table(data)
        assert "# test" in result
        assert "## Info" in result

    def test_compact_table_with_functions(self) -> None:
        """Test compact table with functions"""
        data = {
            "file_path": "test.js",
            "statistics": {},
            "classes": [],
            "exports": [],
            "functions": [
                {
                    "name": "func1",
                    "parameters": [{"name": "a"}, {"name": "b"}],
                    "line_range": {"start": 1, "end": 5},
                    "complexity_score": 2,
                    "jsdoc": "Test function",
                    "is_async": False,
                }
            ],
        }
        result = self.formatter._format_compact_table(data)
        assert "## Functions" in result
        assert "func1" in result
        assert "Params" in result


class TestJavaScriptFormatterHelperMethods:
    """Helper method tests"""

    def setup_method(self) -> None:
        """Setup test fixtures"""
        self.formatter = JavaScriptTableFormatter()

    def test_format_function_row(self) -> None:
        """Test formatting function row"""
        func = {
            "name": "testFunc",
            "parameters": [{"name": "x", "type": "number"}],
            "line_range": {"start": 10, "end": 15},
            "complexity_score": 3,
            "jsdoc": "Test function",
            "is_async": False,
        }
        result = self.formatter._format_function_row(func)
        assert "testFunc" in result
        assert "10-15" in result
        assert "3" in result

    def test_format_method_row(self) -> None:
        """Test formatting method row"""
        method = {
            "name": "testMethod",
            "class_name": "TestClass",
            "parameters": [],
            "line_range": {"start": 20, "end": 25},
            "complexity_score": 1,
            "jsdoc": "Test method",
            "is_static": False,
        }
        result = self.formatter._format_method_row(method)
        assert "testMethod" in result
        assert "TestClass" in result

    def test_create_full_params_empty(self) -> None:
        """Test creating full params with no parameters"""
        func = {"parameters": []}
        result = self.formatter._create_full_params(func)
        assert result == "()"

    def test_create_full_params_with_type(self) -> None:
        """Test creating full params with type annotations"""
        func = {
            "parameters": [
                {"name": "x", "type": "number"},
                {"name": "y", "type": "string"},
            ]
        }
        result = self.formatter._create_full_params(func)
        assert "x: number" in result
        assert "y: string" in result

    def test_create_full_params_without_type(self) -> None:
        """Test creating full params without type annotations"""
        func = {"parameters": [{"name": "x"}, {"name": "y"}]}
        result = self.formatter._create_full_params(func)
        assert "x" in result
        assert "y" in result

    def test_create_full_params_string(self) -> None:
        """Test creating full params with string parameters"""
        func = {"parameters": ["x", "y"]}
        result = self.formatter._create_full_params(func)
        assert "x" in result
        assert "y" in result

    def test_create_full_params_truncation(self) -> None:
        """Test parameter truncation for long param lists"""
        func = {
            "parameters": [
                {"name": f"param{i}", "type": "string"} for i in range(20)
            ]
        }
        result = self.formatter._create_full_params(func)
        assert "..." in result
        assert len(result) <= 53

    def test_create_compact_params_few(self) -> None:
        """Test compact params with few parameters"""
        func = {"parameters": [{"name": "x"}, {"name": "y"}]}
        result = self.formatter._create_compact_params(func)
        assert result == "(x,y)"

    def test_create_compact_params_many(self) -> None:
        """Test compact params with many parameters"""
        func = {"parameters": [{"name": f"p{i}"} for i in range(10)]}
        result = self.formatter._create_compact_params(func)
        assert result == "(10 params)"

    def test_create_compact_params_empty(self) -> None:
        """Test compact params with no parameters"""
        func = {"parameters": []}
        result = self.formatter._create_compact_params(func)
        assert result == "()"

    def test_get_function_type_async(self) -> None:
        """Test getting async function type"""
        func = {"is_async": True}
        result = self.formatter._get_function_type(func)
        assert result == "async function"

    def test_get_function_type_generator(self) -> None:
        """Test getting generator function type"""
        func = {"is_async": False, "is_generator": True}
        result = self.formatter._get_function_type(func)
        assert result == "generator"

    def test_get_function_type_arrow(self) -> None:
        """Test getting arrow function type"""
        func = {"is_async": False, "is_generator": False, "is_arrow": True}
        result = self.formatter._get_function_type(func)
        assert result == "arrow"

    def test_get_function_type_constructor(self) -> None:
        """Test getting constructor type"""
        func = {"is_method": True, "is_constructor": True}
        result = self.formatter._get_function_type(func)
        assert result == "constructor"

    def test_get_function_type_getter(self) -> None:
        """Test getting getter type"""
        func = {"is_method": True, "is_getter": True, "is_constructor": False}
        result = self.formatter._get_function_type(func)
        assert result == "getter"

    def test_get_function_type_setter(self) -> None:
        """Test getting setter type"""
        func = {
            "is_method": True,
            "is_setter": True,
            "is_constructor": False,
            "is_getter": False,
        }
        result = self.formatter._get_function_type(func)
        assert result == "setter"

    def test_get_function_type_static_method(self) -> None:
        """Test getting static method type"""
        func = {
            "is_method": True,
            "is_static": True,
            "is_constructor": False,
            "is_getter": False,
            "is_setter": False,
        }
        result = self.formatter._get_function_type(func)
        assert result == "static method"

    def test_get_function_type_method(self) -> None:
        """Test getting regular method type"""
        func = {
            "is_method": True,
            "is_constructor": False,
            "is_getter": False,
            "is_setter": False,
            "is_static": False,
        }
        result = self.formatter._get_function_type(func)
        assert result == "method"

    def test_get_function_type_regular(self) -> None:
        """Test getting regular function type"""
        func = {"is_async": False, "is_generator": False, "is_arrow": False}
        result = self.formatter._get_function_type(func)
        assert result == "function"

    def test_get_function_type_short_async(self) -> None:
        """Test getting short async type"""
        func = {"is_async": True}
        result = self.formatter._get_function_type_short(func)
        assert result == "async"

    def test_get_function_type_short_generator(self) -> None:
        """Test getting short generator type"""
        func = {"is_async": False, "is_generator": True}
        result = self.formatter._get_function_type_short(func)
        assert result == "gen"

    def test_get_function_type_short_arrow(self) -> None:
        """Test getting short arrow type"""
        func = {"is_async": False, "is_generator": False, "is_arrow": True}
        result = self.formatter._get_function_type_short(func)
        assert result == "arrow"

    def test_get_function_type_short_method(self) -> None:
        """Test getting short method type"""
        func = {
            "is_async": False,
            "is_generator": False,
            "is_arrow": False,
            "is_method": True,
        }
        result = self.formatter._get_function_type_short(func)
        assert result == "method"

    def test_get_function_type_short_func(self) -> None:
        """Test getting short function type"""
        func = {
            "is_async": False,
            "is_generator": False,
            "is_arrow": False,
            "is_method": False,
        }
        result = self.formatter._get_function_type_short(func)
        assert result == "func"

    def test_get_method_type_constructor(self) -> None:
        """Test getting constructor method type"""
        method = {"is_constructor": True}
        result = self.formatter._get_method_type(method)
        assert result == "constructor"

    def test_get_method_type_getter(self) -> None:
        """Test getting getter method type"""
        method = {"is_constructor": False, "is_getter": True}
        result = self.formatter._get_method_type(method)
        assert result == "getter"

    def test_get_method_type_setter(self) -> None:
        """Test getting setter method type"""
        method = {"is_constructor": False, "is_getter": False, "is_setter": True}
        result = self.formatter._get_method_type(method)
        assert result == "setter"

    def test_get_method_type_static(self) -> None:
        """Test getting static method type"""
        method = {
            "is_constructor": False,
            "is_getter": False,
            "is_setter": False,
            "is_static": True,
        }
        result = self.formatter._get_method_type(method)
        assert result == "static"

    def test_get_method_type_async(self) -> None:
        """Test getting async method type"""
        method = {
            "is_constructor": False,
            "is_getter": False,
            "is_setter": False,
            "is_static": False,
            "is_async": True,
        }
        result = self.formatter._get_method_type(method)
        assert result == "async"

    def test_get_method_type_regular(self) -> None:
        """Test getting regular method type"""
        method = {
            "is_constructor": False,
            "is_getter": False,
            "is_setter": False,
            "is_static": False,
            "is_async": False,
        }
        result = self.formatter._get_method_type(method)
        assert result == "method"

    def test_is_method_true_by_flag(self) -> None:
        """Test is_method returns True when flag is set"""
        func = {"is_method": True}
        assert self.formatter._is_method(func) is True

    def test_is_method_true_by_class_name(self) -> None:
        """Test is_method returns True when class_name is set"""
        func = {"class_name": "TestClass"}
        assert self.formatter._is_method(func) is True

    def test_is_method_false(self) -> None:
        """Test is_method returns False when neither flag nor class_name is set"""
        func = {}
        assert self.formatter._is_method(func) is False

    def test_get_method_class_with_name(self) -> None:
        """Test getting method class name"""
        method = {"class_name": "MyClass"}
        result = self.formatter._get_method_class(method)
        assert result == "MyClass"

    def test_get_method_class_without_name(self) -> None:
        """Test getting method class name when not set"""
        method = {}
        result = self.formatter._get_method_class(method)
        assert result == "Unknown"

    def test_infer_js_type_undefined(self) -> None:
        """Test inferring undefined type"""
        result = self.formatter._infer_js_type(None)
        assert result == "undefined"

    def test_infer_js_type_string_double_quote(self) -> None:
        """Test inferring string type with double quotes"""
        result = self.formatter._infer_js_type('"hello"')
        assert result == "string"

    def test_infer_js_type_string_single_quote(self) -> None:
        """Test inferring string type with single quotes"""
        result = self.formatter._infer_js_type("'hello'")
        assert result == "string"

    def test_infer_js_type_string_backtick(self) -> None:
        """Test inferring string type with backticks"""
        result = self.formatter._infer_js_type("`hello`")
        assert result == "string"

    def test_infer_js_type_boolean_true(self) -> None:
        """Test inferring boolean type (true)"""
        result = self.formatter._infer_js_type("true")
        assert result == "boolean"

    def test_infer_js_type_boolean_false(self) -> None:
        """Test inferring boolean type (false)"""
        result = self.formatter._infer_js_type("false")
        assert result == "boolean"

    def test_infer_js_type_null(self) -> None:
        """Test inferring null type"""
        result = self.formatter._infer_js_type("null")
        assert result == "null"

    def test_infer_js_type_array(self) -> None:
        """Test inferring array type"""
        result = self.formatter._infer_js_type("[1, 2, 3]")
        assert result == "array"

    def test_infer_js_type_object(self) -> None:
        """Test inferring object type"""
        result = self.formatter._infer_js_type("{a: 1}")
        assert result == "object"

    def test_infer_js_type_function_keyword(self) -> None:
        """Test inferring function type with function keyword"""
        result = self.formatter._infer_js_type("function() {}")
        assert result == "function"

    def test_infer_js_type_function_arrow(self) -> None:
        """Test inferring function type with arrow"""
        result = self.formatter._infer_js_type("() => {}")
        assert result == "function"

    def test_infer_js_type_class(self) -> None:
        """Test inferring class type"""
        result = self.formatter._infer_js_type("class MyClass {}")
        assert result == "class"

    def test_infer_js_type_number_integer(self) -> None:
        """Test inferring number type (integer)"""
        result = self.formatter._infer_js_type("42")
        assert result == "number"

    def test_infer_js_type_number_float(self) -> None:
        """Test inferring number type (float)"""
        result = self.formatter._infer_js_type("3.14")
        assert result == "number"

    def test_infer_js_type_number_negative(self) -> None:
        """Test inferring number type (negative)"""
        result = self.formatter._infer_js_type("-42")
        assert result == "number"

    def test_infer_js_type_unknown(self) -> None:
        """Test inferring unknown type"""
        result = self.formatter._infer_js_type("someIdentifier")
        assert result == "unknown"

    def test_determine_scope_const(self) -> None:
        """Test determining scope for const"""
        var = {"is_constant": True, "raw_text": "const x = 1"}
        result = self.formatter._determine_scope(var)
        assert result == "block"

    def test_determine_scope_let(self) -> None:
        """Test determining scope for let"""
        var = {"is_constant": False, "raw_text": "let x = 1"}
        result = self.formatter._determine_scope(var)
        assert result == "block"

    def test_determine_scope_var(self) -> None:
        """Test determining scope for var"""
        var = {"is_constant": False, "raw_text": "var x = 1"}
        result = self.formatter._determine_scope(var)
        assert result == "function"

    def test_determine_scope_unknown(self) -> None:
        """Test determining scope for unknown"""
        var = {"is_constant": False, "raw_text": "x = 1"}
        result = self.formatter._determine_scope(var)
        assert result == "unknown"

    def test_get_variable_kind_const_by_flag(self) -> None:
        """Test getting variable kind (const by flag)"""
        var = {"is_constant": True}
        result = self.formatter._get_variable_kind(var)
        assert result == "const"

    def test_get_variable_kind_const_by_text(self) -> None:
        """Test getting variable kind (const by text)"""
        var = {"is_constant": False, "raw_text": "const x = 1"}
        result = self.formatter._get_variable_kind(var)
        assert result == "const"

    def test_get_variable_kind_let(self) -> None:
        """Test getting variable kind (let)"""
        var = {"is_constant": False, "raw_text": "let x = 1"}
        result = self.formatter._get_variable_kind(var)
        assert result == "let"

    def test_get_variable_kind_var(self) -> None:
        """Test getting variable kind (var)"""
        var = {"is_constant": False, "raw_text": "var x = 1"}
        result = self.formatter._get_variable_kind(var)
        assert result == "var"

    def test_get_variable_kind_unknown(self) -> None:
        """Test getting variable kind (unknown)"""
        var = {"is_constant": False, "raw_text": ""}
        result = self.formatter._get_variable_kind(var)
        assert result == "unknown"

    def test_get_export_type_default(self) -> None:
        """Test getting export type (default)"""
        export = {"is_default": True}
        result = self.formatter._get_export_type(export)
        assert result == "default"

    def test_get_export_type_named(self) -> None:
        """Test getting export type (named)"""
        export = {"is_default": False, "is_named": True}
        result = self.formatter._get_export_type(export)
        assert result == "named"

    def test_get_export_type_all(self) -> None:
        """Test getting export type (all)"""
        export = {"is_default": False, "is_named": False, "is_all": True}
        result = self.formatter._get_export_type(export)
        assert result == "all"

    def test_get_export_type_unknown(self) -> None:
        """Test getting export type (unknown)"""
        export = {}
        result = self.formatter._get_export_type(export)
        assert result == "unknown"


class TestJavaScriptFormatterEdgeCases:
    """Edge case tests"""

    def setup_method(self) -> None:
        """Setup test fixtures"""
        self.formatter = JavaScriptTableFormatter()

    def test_long_variable_value_truncation(self) -> None:
        """Test variable value truncation"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "variables": [
                {
                    "name": "longValue",
                    "initializer": "x" * 100,
                    "line_range": {"start": 1, "end": 1},
                    "raw_text": "const longValue",
                }
            ],
        }
        result = self.formatter._format_full_table(data)
        assert "..." in result

    def test_variable_value_with_pipe_character(self) -> None:
        """Test variable value with pipe character escaping"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "variables": [
                {
                    "name": "pipeVar",
                    "initializer": "a|b|c",
                    "line_range": {"start": 1, "end": 1},
                    "raw_text": "const pipeVar",
                }
            ],
        }
        result = self.formatter._format_full_table(data)
        assert "\\|" in result

    def test_variable_value_with_newlines(self) -> None:
        """Test variable value with newlines"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "variables": [
                {
                    "name": "multiline",
                    "initializer": "line1\nline2",
                    "line_range": {"start": 1, "end": 1},
                    "raw_text": "const multiline",
                }
            ],
        }
        result = self.formatter._format_full_table(data)
        # Result should contain the variable but newlines in value should be replaced with spaces
        assert "multiline" in result
        assert "line1 line2" in result

    def test_windows_path_handling(self) -> None:
        """Test handling of Windows paths"""
        data = {
            "file_path": "C:\\Users\\test\\file.js",
            "exports": [],
            "statistics": {},
            "classes": [],
        }
        result = self.formatter._format_full_table(data)
        assert "file" in result

    def test_variable_with_value_field(self) -> None:
        """Test variable using value field instead of initializer"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "variables": [
                {
                    "name": "myVar",
                    "value": "123",
                    "line_range": {"start": 1, "end": 1},
                    "raw_text": "const myVar",
                }
            ],
        }
        result = self.formatter._format_full_table(data)
        assert "myVar" in result
        assert "123" in result

    def test_import_without_statement_or_source(self) -> None:
        """Test import without statement or source"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "imports": [{"name": "foo"}],
            "statistics": {},
            "classes": [],
        }
        result = self.formatter._format_full_table(data)
        assert "## Imports" in result

    def test_class_without_superclass(self) -> None:
        """Test class without superclass"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [
                {
                    "name": "SimpleClass",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "methods": [],
            "variables": [],
        }
        result = self.formatter._format_full_table(data)
        assert "SimpleClass" in result
        assert "-" in result

    def test_class_line_range_missing(self) -> None:
        """Test class with missing line range"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [{"name": "MyClass"}],
            "methods": [],
            "variables": [],
        }
        result = self.formatter._format_full_table(data)
        assert "MyClass" in result
        assert "0-0" in result

    def test_function_without_jsdoc(self) -> None:
        """Test function without JSDoc"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "functions": [
                {
                    "name": "noDoc",
                    "parameters": [],
                    "line_range": {"start": 1, "end": 5},
                    "complexity_score": 1,
                    "is_async": False,
                    "is_method": False,
                }
            ],
        }
        result = self.formatter._format_full_table(data)
        assert "noDoc" in result

    def test_empty_functions_list(self) -> None:
        """Test with empty functions list"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "functions": [],
        }
        result = self.formatter._format_full_table(data)
        assert "## Functions" not in result

    def test_empty_variables_list(self) -> None:
        """Test with empty variables list"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
            "variables": [],
        }
        result = self.formatter._format_full_table(data)
        assert "## Variables" not in result

    def test_empty_exports_list(self) -> None:
        """Test with empty exports list"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "statistics": {},
            "classes": [],
        }
        result = self.formatter._format_full_table(data)
        assert "## Exports" not in result

    def test_compact_with_many_items(self) -> None:
        """Test compact format with many items"""
        data = {
            "file_path": "test.js",
            "statistics": {
                "function_count": 100,
                "variable_count": 200,
            },
            "classes": [{"name": f"Class{i}"} for i in range(50)],
            "exports": [{"name": f"export{i}"} for i in range(30)],
            "functions": [
                {
                    "name": f"func{i}",
                    "parameters": [],
                    "line_range": {"start": i, "end": i + 5},
                    "complexity_score": 1,
                    "is_async": False,
                }
                for i in range(10)
            ],
        }
        result = self.formatter._format_compact_table(data)
        assert "100" in result
        assert "200" in result
        assert "50" in result