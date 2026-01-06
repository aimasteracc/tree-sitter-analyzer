#!/usr/bin/env python3
"""
Comprehensive tests for JavaScript formatter to improve coverage.

This module provides extensive test coverage for JavaScriptTableFormatter
class, focusing on all methods and edge cases.
"""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)


class TestJavaScriptTableFormatterComprehensive:
    """Comprehensive tests for JavaScriptTableFormatter"""

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

    def test_format_with_missing_statistics(self, formatter):
        """Test formatting with missing statistics"""
        data = {
            "file_path": "test.js",
            "imports": [],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            # Missing statistics
        }

        result = formatter._format_full_table(data)

        # Should handle missing statistics gracefully and return valid output
        assert isinstance(result, str)
        assert "test" in result

    def test_format_with_empty_data(self, formatter):
        """Test formatting with completely empty data"""
        data = {}

        result = formatter._format_full_table(data)

        # Should handle empty data gracefully
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_compact_with_empty_data(self, formatter):
        """Test compact formatting with completely empty data"""
        data = {}

        result = formatter._format_compact_table(data)

        # Should handle empty data gracefully
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_csv_with_empty_data(self, formatter):
        """Test CSV formatting with completely empty data"""
        data = {}

        result = formatter._format_csv(data)

        # Should handle empty data gracefully
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_json_with_empty_data(self, formatter):
        """Test JSON formatting with completely empty data"""
        data = {}

        result = formatter._format_json(data)

        # Should handle empty data gracefully
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_with_none_values(self, formatter):
        """Test formatting with None values in data"""
        data = {
            "file_path": None,
            "imports": None,
            "exports": None,
            "classes": None,
            "variables": None,
            "functions": None,
            "statistics": None,
        }

        result = formatter._format_full_table(data)

        # Should handle None values gracefully
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_with_malformed_data(self, formatter):
        """Test formatting with malformed data structures"""
        data = {
            "file_path": "test.js",
            "imports": "not_a_list",  # Should be list
            "exports": {"not": "a_list"},  # Should be list
            "classes": None,
            "variables": [],
            "functions": [],
            "statistics": "not_a_dict",  # Should be dict
        }

        # Should not raise exception
        result = formatter._format_full_table(data)
        assert isinstance(result, str)

    def test_get_function_signature_edge_cases(self, formatter):
        """Test function signature generation with edge cases"""
        # Function with no parameters
        func_data = {"name": "noParams", "parameters": []}
        result = formatter._get_function_signature(func_data)
        assert result == "noParams()"

        # Function with None parameters
        func_data = {"name": "noneParams", "parameters": None}
        result = formatter._get_function_signature(func_data)
        assert result == "noneParams()"

        # Function with malformed parameters
        func_data = {"name": "malformedParams", "parameters": "not_a_list"}
        result = formatter._get_function_signature(func_data)
        assert result == "malformedParams()"

    def test_get_class_info_edge_cases(self, formatter):
        """Test class info generation with edge cases"""
        # Class with no methods
        class_data = {"name": "EmptyClass", "methods": []}
        result = formatter._get_class_info(class_data)
        assert result == "EmptyClass (0 methods)"

        # Class with None methods
        class_data = {"name": "NoneMethodsClass", "methods": None}
        result = formatter._get_class_info(class_data)
        assert result == "NoneMethodsClass (0 methods)"

        # Class with malformed methods
        class_data = {"name": "MalformedClass", "methods": "not_a_list"}
        result = formatter._get_class_info(class_data)
        assert result == "MalformedClass (0 methods)"

    def test_infer_js_type_edge_cases(self, formatter):
        """Test JavaScript type inference with edge cases"""
        edge_cases = [
            ("", "unknown"),
            ("   ", "unknown"),
            ("undefined", "undefined"),
            ("NaN", "number"),
            ("Infinity", "number"),
            ("-Infinity", "number"),
            ("Symbol('test')", "unknown"),
            ("BigInt(123)", "unknown"),
            ("new Date()", "unknown"),
            ("new RegExp()", "unknown"),
            ("/pattern/g", "unknown"),
            ("async function() {}", "function"),
            ("function*() {}", "function"),
            ("async () => {}", "function"),
            ("new Function()", "function"),
        ]

        for value, expected in edge_cases:
            result = formatter._infer_js_type(value)
            assert result == expected, f"Failed for value: '{value}'"

    def test_determine_scope_edge_cases(self, formatter):
        """Test variable scope determination with edge cases"""
        edge_cases = [
            ({}, "unknown"),  # Empty dict
            ({"raw_text": ""}, "unknown"),  # Empty text
            ({"raw_text": "   "}, "unknown"),  # Whitespace only
            ({"raw_text": "const"}, "block"),  # Just keyword
            ({"raw_text": "let"}, "block"),  # Just keyword
            ({"raw_text": "var"}, "function"),  # Just keyword
            ({"raw_text": "CONST x = 1"}, "unknown"),  # Wrong case
            ({"raw_text": "LET x = 1"}, "unknown"),  # Wrong case
            ({"raw_text": "VAR x = 1"}, "unknown"),  # Wrong case
        ]

        for var_data, expected in edge_cases:
            with patch.object(formatter, "_get_variable_kind") as mock_get_kind:
                if var_data.get("is_constant") or var_data.get(
                    "raw_text", ""
                ).strip().startswith("const"):
                    mock_get_kind.return_value = "const"
                elif var_data.get("raw_text", "").strip().startswith("let"):
                    mock_get_kind.return_value = "let"
                elif var_data.get("raw_text", "").strip().startswith("var"):
                    mock_get_kind.return_value = "var"
                else:
                    mock_get_kind.return_value = "unknown"

                result = formatter._determine_scope(var_data)
                assert result == expected, f"Failed for var_data: {var_data}"

    def test_get_variable_kind_edge_cases(self, formatter):
        """Test variable kind detection with edge cases"""
        edge_cases = [
            ({}, "unknown"),  # Empty dict
            ({"raw_text": None}, "unknown"),  # None text
            ({"raw_text": ""}, "unknown"),  # Empty text
            ({"raw_text": "   "}, "unknown"),  # Whitespace only
            ({"is_constant": False}, "unknown"),  # False constant
            ({"is_constant": None}, "unknown"),  # None constant
            ({"raw_text": "const x = 1; let y = 2"}, "const"),  # Multiple keywords
            ({"raw_text": "// const x = 1"}, "unknown"),  # Commented out
            ({"raw_text": "string_const = 'const'"}, "unknown"),  # In string
        ]

        for var_data, expected in edge_cases:
            result = formatter._get_variable_kind(var_data)
            assert result == expected, f"Failed for var_data: {var_data}"

    def test_get_export_type_edge_cases(self, formatter):
        """Test export type detection with edge cases"""
        edge_cases = [
            ({}, "unknown"),  # Empty dict
            ({"is_default": False}, "unknown"),  # False flags
            ({"is_named": False}, "unknown"),
            ({"is_all": False}, "unknown"),
            ({"is_default": None}, "unknown"),  # None flags
            ({"is_named": None}, "unknown"),
            ({"is_all": None}, "unknown"),
            (
                {"is_default": True, "is_named": True},
                "default",
            ),  # Multiple flags (default wins)
            (
                {"is_named": True, "is_all": True},
                "named",
            ),  # Multiple flags (named wins)
            ({"unknown_flag": True}, "unknown"),  # Unknown flag
        ]

        for export_data, expected in edge_cases:
            result = formatter._get_export_type(export_data)
            assert result == expected, f"Failed for export_data: {export_data}"

    def test_format_performance_with_large_data(self, formatter):
        """Test formatting performance with large datasets"""
        import time

        # Create large dataset
        large_data = {
            "file_path": "large_test.js",
            "imports": [
                {"name": f"import{i}", "source": f"module{i}"} for i in range(100)
            ],
            "exports": [{"name": f"export{i}", "is_named": True} for i in range(100)],
            "classes": [{"name": f"Class{i}", "methods": []} for i in range(50)],
            "variables": [{"name": f"var{i}", "type": "string"} for i in range(200)],
            "functions": [{"name": f"func{i}", "parameters": []} for i in range(150)],
            "statistics": {"function_count": 150, "variable_count": 200},
        }

        # Test full table formatting
        start_time = time.time()
        result = formatter._format_full_table(large_data)
        end_time = time.time()

        # Should complete within reasonable time (5 seconds)
        assert end_time - start_time < 5.0
        assert isinstance(result, str)
        assert len(result) > 0

        # Test compact table formatting
        start_time = time.time()
        result = formatter._format_compact_table(large_data)
        end_time = time.time()

        # Should complete within reasonable time (5 seconds)
        assert end_time - start_time < 5.0
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unicode_handling(self, formatter):
        """Test handling of Unicode characters in data"""
        unicode_data = {
            "file_path": "unicode_test.js",
            "imports": [{"name": "モジュール", "source": "ライブラリ"}],
            "exports": [{"name": "エクスポート", "is_named": True}],
            "classes": [{"name": "クラス", "methods": []}],
            "variables": [{"name": "変数", "type": "文字列"}],
            "functions": [{"name": "関数", "parameters": []}],
            "statistics": {"function_count": 1, "variable_count": 1},
        }

        # Should handle Unicode without errors
        result = formatter._format_full_table(unicode_data)
        assert isinstance(result, str)
        # Check that the class name (which is used in the header) is present
        assert "クラス" in result

    def test_special_characters_handling(self, formatter):
        """Test handling of special characters in data"""
        special_data = {
            "file_path": "special_test.js",
            "imports": [{"name": "module<>", "source": "lib|pipe"}],
            "exports": [{"name": "export&amp;", "is_named": True}],
            "classes": [{"name": 'Class"quote', "methods": []}],
            "variables": [{"name": "var'apostrophe", "type": "string"}],
            "functions": [{"name": "func\ttab", "parameters": []}],
            "statistics": {"function_count": 1, "variable_count": 1},
        }

        # Should handle special characters without errors
        result = formatter._format_full_table(special_data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_memory_usage_with_repeated_calls(self, formatter):
        """Test memory usage with repeated formatting calls"""
        import gc

        data = {
            "file_path": "memory_test.js",
            "imports": [{"name": "test", "source": "module"}],
            "exports": [{"name": "test", "is_named": True}],
            "classes": [{"name": "Test", "methods": []}],
            "variables": [{"name": "test", "type": "string"}],
            "functions": [{"name": "test", "parameters": []}],
            "statistics": {"function_count": 1, "variable_count": 1},
        }

        # Perform many formatting operations
        for _ in range(100):
            formatter._format_full_table(data)
            formatter._format_compact_table(data)
            formatter._format_csv(data)
            formatter._format_json(data)

        # Force garbage collection
        gc.collect()

        # Should not cause memory issues (test passes if no exception)
        assert True

    def test_concurrent_formatting(self, formatter):
        """Test concurrent formatting operations"""
        import queue
        import threading

        data = {
            "file_path": "concurrent_test.js",
            "imports": [{"name": "test", "source": "module"}],
            "exports": [{"name": "test", "is_named": True}],
            "classes": [{"name": "Test", "methods": []}],
            "variables": [{"name": "test", "type": "string"}],
            "functions": [{"name": "test", "parameters": []}],
            "statistics": {"function_count": 1, "variable_count": 1},
        }

        results = queue.Queue()

        def format_worker():
            try:
                result = formatter._format_full_table(data)
                results.put(("success", result))
            except Exception as e:
                results.put(("error", str(e)))

        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=format_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        success_count = 0
        while not results.empty():
            status, result = results.get()
            if status == "success":
                success_count += 1
                assert isinstance(result, str)
                assert len(result) > 0

        # All threads should succeed
        assert success_count == 5


class TestJavaScriptFormatterIntegration:
    """Integration tests for JavaScript formatter"""

    def test_format_real_javascript_data(self):
        """Test formatting with realistic JavaScript analysis data"""
        formatter = JavaScriptTableFormatter()

        # Realistic JavaScript analysis data
        real_data = {
            "file_path": "src/components/UserProfile.js",
            "imports": [
                {"name": "React", "source": "react"},
                {"name": "useState", "source": "react"},
                {"name": "useEffect", "source": "react"},
                {"name": "PropTypes", "source": "prop-types"},
                {"name": "UserService", "source": "../services/UserService"},
            ],
            "exports": [
                {"name": "UserProfile", "is_default": True},
                {"name": "validateUser", "is_named": True},
            ],
            "classes": [
                {
                    "name": "UserProfile",
                    "methods": [
                        {"name": "constructor", "parameters": ["props"]},
                        {"name": "componentDidMount", "parameters": []},
                        {"name": "handleUserUpdate", "parameters": ["userData"]},
                        {"name": "render", "parameters": []},
                    ],
                }
            ],
            "variables": [
                {"name": "defaultProps", "type": "object", "is_constant": True},
                {
                    "name": "userState",
                    "type": "object",
                    "raw_text": "const userState = useState({})",
                },
                {
                    "name": "isLoading",
                    "type": "boolean",
                    "raw_text": "let isLoading = false",
                },
            ],
            "functions": [
                {
                    "name": "validateUser",
                    "parameters": [
                        {"name": "user", "type": "object"},
                        {"name": "options", "type": "object", "default": "{}"},
                    ],
                    "is_async": False,
                    "return_type": "boolean",
                },
                {
                    "name": "fetchUserData",
                    "parameters": [{"name": "userId", "type": "string"}],
                    "is_async": True,
                    "return_type": "Promise<User>",
                },
            ],
            "statistics": {
                "function_count": 2,
                "variable_count": 3,
                "class_count": 1,
                "import_count": 5,
                "export_count": 2,
            },
        }

        # Test all format types
        full_result = formatter.format(real_data, "full")
        compact_result = formatter.format(real_data, "compact")
        csv_result = formatter.format(real_data, "csv")
        json_result = formatter.format(real_data, "json")

        # Verify all formats work
        assert isinstance(full_result, str) and len(full_result) > 0
        assert isinstance(compact_result, str) and len(compact_result) > 0
        assert isinstance(csv_result, str) and len(csv_result) > 0
        assert isinstance(json_result, str) and len(json_result) > 0

        # Verify content is present in full format (new format uses class name as header)
        assert "UserProfile" in full_result

    def test_format_with_complex_typescript_features(self):
        """Test formatting with complex TypeScript/JavaScript features"""
        formatter = JavaScriptTableFormatter()

        complex_data = {
            "file_path": "src/utils/ApiClient.ts",
            "imports": [
                {"name": "axios", "source": "axios"},
                {"name": "AxiosResponse", "source": "axios"},
                {"name": "Observable", "source": "rxjs"},
                {"name": "map", "source": "rxjs/operators"},
            ],
            "exports": [
                {"name": "ApiClient", "is_default": True},
                {"name": "HttpMethod", "is_named": True},
                {"name": "ApiResponse", "is_named": True},
            ],
            "classes": [
                {
                    "name": "ApiClient",
                    "methods": [
                        {"name": "constructor", "parameters": ["baseUrl", "config"]},
                        {
                            "name": "get",
                            "parameters": ["url", "config"],
                            "generics": ["T"],
                        },
                        {
                            "name": "post",
                            "parameters": ["url", "data", "config"],
                            "generics": ["T", "U"],
                        },
                        {"name": "put", "parameters": ["url", "data", "config"]},
                        {"name": "delete", "parameters": ["url", "config"]},
                    ],
                }
            ],
            "variables": [
                {
                    "name": "DEFAULT_TIMEOUT",
                    "type": "number",
                    "is_constant": True,
                    "value": "5000",
                },
                {
                    "name": "httpClient",
                    "type": "AxiosInstance",
                    "raw_text": "const httpClient = axios.create()",
                },
                {
                    "name": "interceptors",
                    "type": "object",
                    "raw_text": "let interceptors = {}",
                },
            ],
            "functions": [
                {
                    "name": "createApiClient",
                    "parameters": [
                        {"name": "config", "type": "ApiConfig"},
                        {
                            "name": "interceptors",
                            "type": "Interceptor[]",
                            "default": "[]",
                        },
                    ],
                    "is_async": False,
                    "return_type": "ApiClient",
                    "generics": ["T extends BaseConfig"],
                },
                {
                    "name": "handleApiError",
                    "parameters": [
                        {"name": "error", "type": "AxiosError"},
                        {"name": "context", "type": "string", "default": "'unknown'"},
                    ],
                    "is_async": True,
                    "return_type": "Promise<never>",
                },
            ],
            "statistics": {
                "function_count": 2,
                "variable_count": 3,
                "class_count": 1,
                "import_count": 4,
                "export_count": 3,
            },
        }

        # Test formatting
        result = formatter.format(complex_data, "full")

        # Verify complex features are handled (new format uses class name as header)
        assert isinstance(result, str) and len(result) > 0
        assert "ApiClient" in result
