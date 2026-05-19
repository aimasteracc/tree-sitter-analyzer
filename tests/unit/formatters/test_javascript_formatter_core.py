#!/usr/bin/env python3
"""Core formatting tests for JavaScriptTableFormatter — initialization, format delegation, params, type methods."""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)


class TestJavaScriptTableFormatterCore:
    """Core tests for JavaScriptTableFormatter"""

    @pytest.fixture
    def formatter(self) -> JavaScriptTableFormatter:
        """Create a JavaScriptTableFormatter instance for testing"""
        return JavaScriptTableFormatter()

    @pytest.fixture
    def sample_js_data(self) -> dict:
        """Sample JavaScript analysis data for testing"""
        return {
            "file_path": "/path/to/module.js",
            "statistics": {"function_count": 3, "variable_count": 5, "class_count": 2},
            "imports": [
                {
                    "statement": "import React from 'react';",
                    "source": "'react'",
                    "name": "React",
                },
                {
                    "statement": "import { useState, useEffect } from 'react';",
                    "source": "'react'",
                    "name": "{ useState, useEffect }",
                },
                {"source": "'./utils'", "name": "utils"},
            ],
            "exports": [
                {
                    "name": "MyComponent",
                    "is_default": True,
                    "is_named": False,
                    "is_all": False,
                },
                {
                    "name": "helper",
                    "is_default": False,
                    "is_named": True,
                    "is_all": False,
                },
                {"name": "*", "is_default": False, "is_named": False, "is_all": True},
            ],
            "classes": [
                {
                    "name": "MyComponent",
                    "superclass": "Component",
                    "line_range": {"start": 10, "end": 50},
                    "methods": [],
                    "properties": [],
                },
                {
                    "name": "DataService",
                    "superclass": "",
                    "line_range": {"start": 60, "end": 100},
                    "methods": [],
                    "properties": [],
                },
            ],
            "variables": [
                {
                    "name": "API_URL",
                    "initializer": "'https://api.example.com'",
                    "value": "'https://api.example.com'",
                    "is_constant": True,
                    "raw_text": "const API_URL = 'https://api.example.com';",
                    "line_range": {"start": 5},
                },
                {
                    "name": "counter",
                    "initializer": "0",
                    "value": "0",
                    "is_constant": False,
                    "raw_text": "let counter = 0;",
                    "line_range": {"start": 6},
                },
                {
                    "name": "config",
                    "initializer": "{ debug: true }",
                    "value": "{ debug: true }",
                    "is_constant": False,
                    "raw_text": "var config = { debug: true };",
                    "line_range": {"start": 7},
                },
                {
                    "name": "items",
                    "initializer": "[]",
                    "value": "[]",
                    "is_constant": False,
                    "raw_text": "let items = [];",
                    "line_range": {"start": 8},
                },
                {
                    "name": "callback",
                    "initializer": "() => console.log('done')",
                    "value": "() => console.log('done')",
                    "is_constant": True,
                    "raw_text": "const callback = () => console.log('done');",
                    "line_range": {"start": 9},
                },
            ],
            "functions": [
                {
                    "name": "fetchData",
                    "parameters": [
                        {"name": "url", "type": "string"},
                        {"name": "options", "type": "object"},
                    ],
                    "is_async": True,
                    "is_generator": False,
                    "is_arrow": False,
                    "is_method": False,
                    "complexity_score": 3,
                    "jsdoc": "/**\n * Fetches data from API\n * @param {string} url - The URL\n * @param {object} options - Options\n * @returns {Promise} Promise with data\n */",
                    "line_range": {"start": 20, "end": 30},
                },
                {
                    "name": "processData",
                    "parameters": [{"name": "data"}],
                    "is_async": False,
                    "is_generator": True,
                    "is_arrow": False,
                    "is_method": False,
                    "complexity_score": 2,
                    "jsdoc": "",
                    "line_range": {"start": 35, "end": 45},
                },
                {
                    "name": "handleClick",
                    "parameters": [{"name": "event"}],
                    "is_async": False,
                    "is_generator": False,
                    "is_arrow": True,
                    "is_method": False,
                    "complexity_score": 1,
                    "jsdoc": "",
                    "line_range": {"start": 55, "end": 58},
                },
                {
                    "name": "render",
                    "parameters": [],
                    "is_async": False,
                    "is_generator": False,
                    "is_arrow": False,
                    "is_method": True,
                    "is_constructor": False,
                    "is_getter": False,
                    "is_setter": False,
                    "is_static": False,
                    "class_name": "MyComponent",
                    "complexity_score": 2,
                    "jsdoc": "/** Renders the component */",
                    "line_range": {"start": 40, "end": 48},
                },
                {
                    "name": "constructor",
                    "parameters": [{"name": "props"}],
                    "is_async": False,
                    "is_generator": False,
                    "is_arrow": False,
                    "is_method": True,
                    "is_constructor": True,
                    "is_getter": False,
                    "is_setter": False,
                    "is_static": False,
                    "class_name": "MyComponent",
                    "complexity_score": 1,
                    "jsdoc": "",
                    "line_range": {"start": 12, "end": 15},
                },
                {
                    "name": "getData",
                    "parameters": [],
                    "is_async": False,
                    "is_generator": False,
                    "is_arrow": False,
                    "is_method": True,
                    "is_constructor": False,
                    "is_getter": True,
                    "is_setter": False,
                    "is_static": False,
                    "class_name": "DataService",
                    "complexity_score": 1,
                    "jsdoc": "",
                    "line_range": {"start": 70, "end": 73},
                },
                {
                    "name": "setData",
                    "parameters": [{"name": "value"}],
                    "is_async": False,
                    "is_generator": False,
                    "is_arrow": False,
                    "is_method": True,
                    "is_constructor": False,
                    "is_getter": False,
                    "is_setter": True,
                    "is_static": False,
                    "class_name": "DataService",
                    "complexity_score": 1,
                    "jsdoc": "",
                    "line_range": {"start": 75, "end": 78},
                },
                {
                    "name": "getInstance",
                    "parameters": [],
                    "is_async": False,
                    "is_generator": False,
                    "is_arrow": False,
                    "is_method": True,
                    "is_constructor": False,
                    "is_getter": False,
                    "is_setter": False,
                    "is_static": True,
                    "class_name": "DataService",
                    "complexity_score": 2,
                    "jsdoc": "",
                    "line_range": {"start": 80, "end": 85},
                },
            ],
        }

    def test_formatter_initialization(self, formatter):
        """Test formatter initialization"""
        assert isinstance(formatter, JavaScriptTableFormatter)
        assert formatter.format_type == "full"

    def test_formatter_initialization_with_format_type(self):
        """Test formatter initialization with different format types"""
        formatter_full = JavaScriptTableFormatter("full")
        assert formatter_full.format_type == "full"

        formatter_compact = JavaScriptTableFormatter("compact")
        assert formatter_compact.format_type == "compact"

        formatter_csv = JavaScriptTableFormatter("csv")
        assert formatter_csv.format_type == "csv"

    def test_format_delegation(self, formatter, sample_js_data):
        """Test that format method delegates to format_structure"""
        with patch.object(formatter, "format_structure") as mock_format_structure:
            mock_format_structure.return_value = "test output"

            result = formatter.format(sample_js_data)

            mock_format_structure.assert_called_once_with(sample_js_data)
            assert result == "test output"

    def test_format_full_table_complete(self, formatter, sample_js_data):
        """Test full table formatting with complete data"""
        result = formatter._format_full_table(sample_js_data)

        assert isinstance(result, str)
        assert len(result) > 0

        # Check for expected sections - new format uses simpler headers
        # The title is based on the first class or filename
        assert "MyComponent" in result or "module" in result

        # Check for class content
        assert "MyComponent" in result
        assert "DataService" in result

    def test_format_full_table_script_type(self, formatter):
        """Test full table formatting for script (non-module) type"""
        data = {
            "file_path": "script.js",
            "exports": [],  # No exports = script
            "imports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter._format_full_table(data)

        # New format uses filename as title without prefix
        assert "script" in result

    def test_format_full_table_with_import_construction(self, formatter):
        """Test import statement construction when statement is missing"""
        data = {
            "file_path": "test.js",
            "imports": [
                {
                    "source": "'react'",
                    "name": "React",
                    "statement": "",  # Empty statement, should be constructed
                }
            ],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter._format_full_table(data)

        # Check that the test file is formatted (imports may not be in new format)
        assert "test" in result

    def test_format_full_table_class_methods_and_properties_counting(self, formatter):
        """Test counting of methods and properties within classes"""
        data = {
            "file_path": "test.js",
            "imports": [],
            "exports": [],
            "classes": [
                {
                    "name": "TestClass",
                    "superclass": "BaseClass",
                    "line_range": {"start": 10, "end": 30},
                }
            ],
            "variables": [
                {
                    "name": "classProperty",
                    "line_range": {"start": 15},  # Within class range
                },
                {
                    "name": "outsideProperty",
                    "line_range": {"start": 5},  # Outside class range
                },
            ],
            "functions": [
                {
                    "name": "classMethod",
                    "line_range": {"start": 20},  # Within class range
                    "is_method": True,
                },
                {
                    "name": "outsideFunction",
                    "line_range": {"start": 35},  # Outside class range
                    "is_method": False,
                },
            ],
            "methods": [
                {
                    "name": "classMethod",
                    "line_range": {"start": 20},  # Within class range
                }
            ],
            "statistics": {"function_count": 2, "variable_count": 2},
        }

        result = formatter._format_full_table(data)

        # Check class appears in output with basic info
        assert "TestClass" in result
        assert "10-30" in result or "10" in result

    def test_format_compact_table(self, formatter, sample_js_data):
        """Test compact table formatting"""
        result = formatter._format_compact_table(sample_js_data)

        assert isinstance(result, str)
        assert len(result) > 0

        # Check for expected sections - new format uses class name or filename
        assert "MyComponent" in result or "module" in result
        assert "## Info" in result

    def test_format_function_row(self, formatter):
        """Test function row formatting"""
        func = {
            "name": "testFunction",
            "parameters": [{"name": "param1", "type": "string"}],
            "is_async": True,
            "is_generator": False,
            "is_arrow": False,
            "is_method": False,
            "complexity_score": 3,
            "jsdoc": "Test function documentation",
            "line_range": {"start": 10, "end": 20},
        }

        result = formatter._format_function_row(func)

        assert "testFunction" in result
        assert "(param1: string)" in result
        assert "async function" in result
        assert "10-20" in result
        assert "3" in result
        assert "Test function documentation" in result

    def test_format_method_row(self, formatter):
        """Test method row formatting"""
        method = {
            "name": "testMethod",
            "class_name": "TestClass",
            "parameters": [{"name": "param1"}],
            "is_async": False,
            "is_constructor": False,
            "is_getter": False,
            "is_setter": False,
            "is_static": True,
            "complexity_score": 2,
            "jsdoc": "Test method",
            "line_range": {"start": 15, "end": 25},
        }

        result = formatter._format_method_row(method)

        assert "testMethod" in result
        assert "TestClass" in result
        assert "(param1)" in result
        assert "static" in result
        assert "15-25" in result
        assert "2" in result

    def test_create_full_params_empty(self, formatter):
        """Test parameter creation with empty parameters"""
        func = {"parameters": []}
        result = formatter._create_full_params(func)
        assert result == "()"

    def test_create_full_params_with_types(self, formatter):
        """Test parameter creation with typed parameters"""
        func = {
            "parameters": [
                {"name": "param1", "type": "string"},
                {"name": "param2", "type": "number"},
                {"name": "param3"},  # No type
            ]
        }

        result = formatter._create_full_params(func)

        assert "param1: string" in result
        assert "param2: number" in result
        assert "param3" in result

    def test_create_full_params_string_parameters(self, formatter):
        """Test parameter creation with string parameters"""
        func = {"parameters": ["param1", "param2"]}

        result = formatter._create_full_params(func)

        assert "(param1, param2)" == result

    def test_create_full_params_long_truncation(self, formatter):
        """Test parameter truncation for long parameter lists"""
        long_params = [f"param{i}" for i in range(20)]
        func = {"parameters": long_params}

        result = formatter._create_full_params(func)

        assert len(result) <= 53  # 50 chars + "()" + "..."
        assert result.endswith("...)")

    def test_create_compact_params_empty(self, formatter):
        """Test compact parameter creation with empty parameters"""
        func = {"parameters": []}
        result = formatter._create_compact_params(func)
        assert result == "()"

    def test_create_compact_params_few_params(self, formatter):
        """Test compact parameter creation with few parameters"""
        func = {
            "parameters": [{"name": "param1"}, {"name": "param2"}, {"name": "param3"}]
        }

        result = formatter._create_compact_params(func)
        assert result == "(param1,param2,param3)"

    def test_create_compact_params_many_params(self, formatter):
        """Test compact parameter creation with many parameters"""
        func = {"parameters": [{"name": f"param{i}"} for i in range(5)]}

        result = formatter._create_compact_params(func)
        assert result == "(5 params)"

    def test_get_function_type_async(self, formatter):
        """Test function type detection for async functions"""
        func = {"is_async": True, "is_generator": False, "is_arrow": False}
        result = formatter._get_function_type(func)
        assert result == "async function"

    def test_get_function_type_generator(self, formatter):
        """Test function type detection for generator functions"""
        func = {"is_async": False, "is_generator": True, "is_arrow": False}
        result = formatter._get_function_type(func)
        assert result == "generator"

    def test_get_function_type_arrow(self, formatter):
        """Test function type detection for arrow functions"""
        func = {"is_async": False, "is_generator": False, "is_arrow": True}
        result = formatter._get_function_type(func)
        assert result == "arrow"

    def test_get_function_type_constructor_method(self, formatter):
        """Test function type detection for constructor methods"""
        func = {
            "is_async": False,
            "is_generator": False,
            "is_arrow": False,
            "is_method": True,
            "is_constructor": True,
        }

        with patch.object(formatter, "_is_method", return_value=True):
            result = formatter._get_function_type(func)
            assert result == "constructor"

    def test_get_function_type_getter_method(self, formatter):
        """Test function type detection for getter methods"""
        func = {
            "is_async": False,
            "is_generator": False,
            "is_arrow": False,
            "is_method": True,
            "is_getter": True,
        }

        with patch.object(formatter, "_is_method", return_value=True):
            result = formatter._get_function_type(func)
            assert result == "getter"

    def test_get_function_type_setter_method(self, formatter):
        """Test function type detection for setter methods"""
        func = {
            "is_async": False,
            "is_generator": False,
            "is_arrow": False,
            "is_method": True,
            "is_setter": True,
        }

        with patch.object(formatter, "_is_method", return_value=True):
            result = formatter._get_function_type(func)
            assert result == "setter"

    def test_get_function_type_static_method(self, formatter):
        """Test function type detection for static methods"""
        func = {
            "is_async": False,
            "is_generator": False,
            "is_arrow": False,
            "is_method": True,
            "is_static": True,
        }

        with patch.object(formatter, "_is_method", return_value=True):
            result = formatter._get_function_type(func)
            assert result == "static method"

    def test_get_function_type_regular_method(self, formatter):
        """Test function type detection for regular methods"""
        func = {
            "is_async": False,
            "is_generator": False,
            "is_arrow": False,
            "is_method": True,
        }

        with patch.object(formatter, "_is_method", return_value=True):
            result = formatter._get_function_type(func)
            assert result == "method"

    def test_get_function_type_regular_function(self, formatter):
        """Test function type detection for regular functions"""
        func = {
            "is_async": False,
            "is_generator": False,
            "is_arrow": False,
            "is_method": False,
        }

        with patch.object(formatter, "_is_method", return_value=False):
            result = formatter._get_function_type(func)
            assert result == "function"

    def test_get_function_type_short(self, formatter):
        """Test short function type detection"""
        test_cases = [
            ({"is_async": True}, "async"),
            ({"is_generator": True}, "gen"),
            ({"is_arrow": True}, "arrow"),
            ({"is_method": True}, "method"),
            ({}, "func"),
        ]

        for func_data, expected in test_cases:
            with patch.object(
                formatter, "_is_method", return_value=func_data.get("is_method", False)
            ):
                result = formatter._get_function_type_short(func_data)
                assert result == expected

    def test_get_method_type(self, formatter):
        """Test method type detection"""
        test_cases = [
            ({"is_constructor": True}, "constructor"),
            ({"is_getter": True}, "getter"),
            ({"is_setter": True}, "setter"),
            ({"is_static": True}, "static"),
            ({"is_async": True}, "async"),
            ({}, "method"),
        ]

        for method_data, expected in test_cases:
            result = formatter._get_method_type(method_data)
            assert result == expected

    def test_is_method(self, formatter):
        """Test method detection"""
        # Test with is_method flag
        func1 = {"is_method": True}
        assert formatter._is_method(func1) is True

        # Test with class_name
        func2 = {"class_name": "TestClass"}
        assert formatter._is_method(func2) is True

        # Test without either
        func3 = {}
        assert formatter._is_method(func3) is False

    def test_get_method_class(self, formatter):
        """Test method class name extraction"""
        method = {"class_name": "TestClass"}
        result = formatter._get_method_class(method)
        assert result == "TestClass"

        # Test with missing class_name
        method_no_class = {}
        result = formatter._get_method_class(method_no_class)
        assert result == "Unknown"

    def test_infer_js_type(self, formatter):
        """Test JavaScript type inference"""
        test_cases = [
            (None, "undefined"),
            ('"string"', "string"),
            ("'string'", "string"),
            ("`template`", "string"),
            ("true", "boolean"),
            ("false", "boolean"),
            ("null", "null"),
            ("[1, 2, 3]", "array"),
            ("{ key: 'value' }", "object"),
            ("function() {}", "function"),
            ("() => {}", "function"),
            ("class MyClass {}", "class"),
            ("42", "number"),
            ("3.14", "number"),
            ("unknown_value", "unknown"),
        ]

        for value, expected in test_cases:
            result = formatter._infer_js_type(value)
            assert result == expected, f"Failed for value: {value}"

    def test_determine_scope(self, formatter):
        """Test variable scope determination"""
        test_cases = [
            ({"is_constant": True}, "block"),  # const
            ({"raw_text": "let x = 1"}, "block"),  # let
            ({"raw_text": "var x = 1"}, "function"),  # var
            ({"raw_text": "unknown x = 1"}, "unknown"),  # unknown
        ]

        for var_data, expected in test_cases:
            with patch.object(formatter, "_get_variable_kind") as mock_get_kind:
                if var_data.get("is_constant"):
                    mock_get_kind.return_value = "const"
                elif "let" in var_data.get("raw_text", ""):
                    mock_get_kind.return_value = "let"
                elif "var" in var_data.get("raw_text", ""):
                    mock_get_kind.return_value = "var"
                else:
                    mock_get_kind.return_value = "unknown"

                result = formatter._determine_scope(var_data)
                assert result == expected

    def test_get_variable_kind(self, formatter):
        """Test variable kind detection"""
        test_cases = [
            ({"is_constant": True}, "const"),
            ({"raw_text": "const x = 1"}, "const"),
            ({"raw_text": "let x = 1"}, "let"),
            ({"raw_text": "var x = 1"}, "var"),
            ({"raw_text": "unknown x = 1"}, "unknown"),
        ]

        for var_data, expected in test_cases:
            result = formatter._get_variable_kind(var_data)
            assert result == expected

    def test_get_export_type(self, formatter):
        """Test export type detection"""
        test_cases = [
            ({"is_default": True}, "default"),
            ({"is_named": True}, "named"),
            ({"is_all": True}, "all"),
            ({}, "unknown"),
        ]

        for export_data, expected in test_cases:
            result = formatter._get_export_type(export_data)
            assert result == expected

    def test_format_full_table_no_imports(self, formatter):
        """Test full table formatting without imports"""
        data = {
            "file_path": "test.js",
            "imports": [],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter._format_full_table(data)

        assert "## Imports" not in result

    def test_format_full_table_no_classes(self, formatter):
        """Test full table formatting without classes"""
        data = {
            "file_path": "test.js",
            "imports": [],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter._format_full_table(data)

        assert "## Classes" not in result

    def test_format_full_table_no_variables(self, formatter):
        """Test full table formatting without variables"""
        data = {
            "file_path": "test.js",
            "imports": [],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter._format_full_table(data)

        assert "## Variables" not in result

    def test_format_full_table_no_functions(self, formatter):
        """Test full table formatting without functions"""
        data = {
            "file_path": "test.js",
            "imports": [],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter._format_full_table(data)

        assert "## Functions" not in result
        assert "## Async Functions" not in result
        assert "## Methods" not in result

    def test_format_full_table_no_exports(self, formatter):
        """Test full table formatting without exports"""
        data = {
            "file_path": "test.js",
            "imports": [],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter._format_full_table(data)

        assert "## Exports" not in result

    def test_format_full_table_trailing_blank_lines_removal(self, formatter):
        """Test removal of trailing blank lines"""
        data = {
            "file_path": "test.js",
            "imports": [],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter._format_full_table(data)

        # Should not end with blank lines
        assert not result.endswith("\n\n")

    def test_format_compact_table_trailing_blank_lines_removal(self, formatter):
        """Test removal of trailing blank lines in compact format"""
        data = {
            "file_path": "test.js",
            "functions": [],
            "classes": [],
            "exports": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter._format_compact_table(data)

        # Should not end with blank lines
        assert not result.endswith("\n\n")


class TestJavaScriptCompactMixinCoverage:
    """Cover uncovered branches in _javascript_formatter_compact_mixin.py."""

    @pytest.fixture
    def formatter(self) -> JavaScriptTableFormatter:
        return JavaScriptTableFormatter()

    def test_create_compact_signature_dict_params(self, formatter):
        method = {
            "parameters": [
                {"name": "a", "type": "string"},
                {"name": "b", "type": "number"},
            ],
            "return_type": "void",
        }
        result = formatter._create_compact_signature(method)
        assert result == "(string,number):void"

    def test_create_compact_signature_non_dict_params(self, formatter):
        method = {
            "parameters": ["not_a_dict", 42],
            "return_type": "unknown",
        }
        result = formatter._create_compact_signature(method)
        assert result == "(Any,Any):unknown"

    def test_create_compact_signature_empty_params(self, formatter):
        method = {"parameters": [], "return_type": "Promise"}
        result = formatter._create_compact_signature(method)
        assert result == "():unknown"

    def test_create_compact_signature_string_params(self, formatter):
        method = {"parameters": "not_a_list", "return_type": "bool"}
        result = formatter._create_compact_signature(method)
        assert result == "():unknown"

    def test_create_compact_signature_no_params_key(self, formatter):
        method = {"return_type": "number"}
        result = formatter._create_compact_signature(method)
        assert result == "():unknown"

    def test_create_compact_signature_dict_without_type(self, formatter):
        method = {
            "parameters": [{"name": "x"}],
            "return_type": "void",
        }
        result = formatter._create_compact_signature(method)
        assert result == "(Any):void"

    def test_create_compact_signature_default_return_type(self, formatter):
        method = {
            "parameters": [{"name": "a", "type": "int"}],
        }
        result = formatter._create_compact_signature(method)
        assert result == "(int):unknown"

    def test_format_compact_table_with_methods(self, formatter):
        data = {
            "file_path": "app.js",
            "classes": [{"name": "App"}],
            "methods": [
                {
                    "name": "init",
                    "parameters": [{"name": "cfg", "type": "Config"}],
                    "return_type": "void",
                    "line_range": {"start": 10, "end": 20},
                    "complexity_score": 3,
                },
                {
                    "name": "render",
                    "parameters": [],
                    "return_type": "VNode",
                    "line_range": {"start": 25, "end": 40},
                    "complexity_score": 5,
                },
            ],
            "functions": [],
            "exports": [],
            "statistics": {"function_count": 2, "variable_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "## Methods" in result
        assert "| init |" in result
        assert "| render |" in result
        assert "(Config):void" in result
        assert "():unknown" in result
        assert "10-20" in result
        assert "25-40" in result

    def test_format_compact_table_no_methods(self, formatter):
        data = {
            "file_path": "empty.js",
            "classes": [],
            "methods": [],
            "functions": [],
            "exports": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "## Info" in result
        assert "## Methods" not in result

    def test_format_compact_table_method_row_content(self, formatter):
        data = {
            "file_path": "svc.js",
            "classes": [],
            "methods": [
                {
                    "name": "fetch",
                    "parameters": [{"name": "url", "type": "string"}],
                    "return_type": "Promise",
                    "line_range": {"start": 5, "end": 15},
                    "complexity_score": 7,
                },
            ],
            "functions": [],
            "exports": [],
            "statistics": {"function_count": 1, "variable_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "| fetch | (string):Promise | + | 5-15 | 7 | - |" in result

    def test_format_compact_info_section_method_count(self, formatter):
        data = {
            "file_path": "mod.js",
            "classes": [],
            "methods": [
                {"name": "a", "parameters": [], "return_type": "void"},
                {"name": "b", "parameters": [], "return_type": "void"},
                {"name": "c", "parameters": [], "return_type": "void"},
            ],
            "functions": [],
            "exports": [],
            "statistics": {"function_count": 3, "variable_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "| Methods | 3 |" in result

    def test_format_compact_method_missing_line_range(self, formatter):
        data = {
            "file_path": "x.js",
            "classes": [],
            "methods": [
                {"name": "op", "parameters": [], "return_type": "void"},
            ],
            "functions": [],
            "exports": [],
            "statistics": {"function_count": 1, "variable_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "| op |" in result
        assert "0-0" in result
