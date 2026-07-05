#!/usr/bin/env python3
"""Tests for JavaScriptTableFormatter full/compact table formatting output."""

import pytest

from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)


def _sample_js_data() -> dict:
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


class TestJavaScriptFullTableFormatting:
    """Tests for full table formatting output."""

    @pytest.fixture
    def formatter(self) -> JavaScriptTableFormatter:
        return JavaScriptTableFormatter()

    @pytest.fixture
    def sample_js_data(self) -> dict:
        return _sample_js_data()

    def test_format_full_table_complete(self, formatter, sample_js_data):
        result = formatter._format_full_table(sample_js_data)
        assert isinstance(result, str)
        assert result
        assert "MyComponent" in result or "module" in result
        assert "MyComponent" in result
        assert "DataService" in result

    def test_format_full_table_script_type(self, formatter):
        data = {
            "file_path": "script.js",
            "exports": [],
            "imports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }
        result = formatter._format_full_table(data)
        assert "script" in result

    def test_format_full_table_with_import_construction(self, formatter):
        data = {
            "file_path": "test.js",
            "imports": [
                {
                    "source": "'react'",
                    "name": "React",
                    "statement": "",
                }
            ],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }
        result = formatter._format_full_table(data)
        assert "test" in result

    def test_format_full_table_class_methods_and_properties_counting(self, formatter):
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
                    "line_range": {"start": 15},
                },
                {
                    "name": "outsideProperty",
                    "line_range": {"start": 5},
                },
            ],
            "functions": [
                {
                    "name": "classMethod",
                    "line_range": {"start": 20},
                    "is_method": True,
                },
                {
                    "name": "outsideFunction",
                    "line_range": {"start": 35},
                    "is_method": False,
                },
            ],
            "methods": [
                {
                    "name": "classMethod",
                    "line_range": {"start": 20},
                }
            ],
            "statistics": {"function_count": 2, "variable_count": 2},
        }
        result = formatter._format_full_table(data)
        assert "TestClass" in result
        assert "10-30" in result or "10" in result

    def test_format_function_row(self, formatter):
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


class TestJavaScriptSectionAbsence:
    """Tests verifying sections are omitted when data is empty."""

    @pytest.fixture
    def formatter(self) -> JavaScriptTableFormatter:
        return JavaScriptTableFormatter()

    def _empty_data(self) -> dict:
        return {
            "file_path": "test.js",
            "imports": [],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

    def test_format_full_table_no_imports(self, formatter):
        result = formatter._format_full_table(self._empty_data())
        assert "## Imports" not in result

    def test_format_full_table_no_classes(self, formatter):
        result = formatter._format_full_table(self._empty_data())
        assert "## Classes" not in result

    def test_format_full_table_no_variables(self, formatter):
        result = formatter._format_full_table(self._empty_data())
        assert "## Variables" not in result

    def test_format_full_table_no_functions(self, formatter):
        result = formatter._format_full_table(self._empty_data())
        assert "## Functions" not in result
        assert "## Async Functions" not in result
        assert "## Methods" not in result

    def test_format_full_table_no_exports(self, formatter):
        result = formatter._format_full_table(self._empty_data())
        assert "## Exports" not in result

    def test_format_full_table_trailing_blank_lines_removal(self, formatter):
        result = formatter._format_full_table(self._empty_data())
        assert not result.endswith("\n\n")

    def test_format_compact_table_trailing_blank_lines_removal(self, formatter):
        data = {
            "file_path": "test.js",
            "functions": [],
            "classes": [],
            "exports": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert not result.endswith("\n\n")


class TestJavaScriptCompactTableFormatting:
    """Tests for compact table formatting output."""

    @pytest.fixture
    def formatter(self) -> JavaScriptTableFormatter:
        return JavaScriptTableFormatter()

    @pytest.fixture
    def sample_js_data(self) -> dict:
        return _sample_js_data()

    def test_format_compact_table(self, formatter, sample_js_data):
        result = formatter._format_compact_table(sample_js_data)
        assert isinstance(result, str)
        assert result
        assert "MyComponent" in result or "module" in result
        assert "## Info" in result

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


class TestJavaScriptCompactSignatureMixin:
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
