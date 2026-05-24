#!/usr/bin/env python3
"""Tests for JavaScriptTableFormatter initialization, params, and type detection methods."""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)


class TestJavaScriptFormatterInit:
    """Tests for JavaScriptTableFormatter initialization."""

    def test_formatter_initialization(self):
        formatter = JavaScriptTableFormatter()
        assert isinstance(formatter, JavaScriptTableFormatter)
        assert formatter.format_type == "full"

    def test_formatter_initialization_with_format_type(self):
        formatter_full = JavaScriptTableFormatter("full")
        assert formatter_full.format_type == "full"

        formatter_compact = JavaScriptTableFormatter("compact")
        assert formatter_compact.format_type == "compact"

        formatter_csv = JavaScriptTableFormatter("csv")
        assert formatter_csv.format_type == "csv"

    def test_format_delegation(self):
        formatter = JavaScriptTableFormatter()
        data = {"some": "data"}
        with patch.object(formatter, "format_structure") as mock_format_structure:
            mock_format_structure.return_value = "test output"
            result = formatter.format(data)
            mock_format_structure.assert_called_once_with(data)
            assert result == "test output"


class TestJavaScriptParamCreation:
    """Tests for parameter creation methods."""

    @pytest.fixture
    def formatter(self) -> JavaScriptTableFormatter:
        return JavaScriptTableFormatter()

    def test_create_full_params_empty(self, formatter):
        func = {"parameters": []}
        result = formatter._create_full_params(func)
        assert result == "()"

    def test_create_full_params_with_types(self, formatter):
        func = {
            "parameters": [
                {"name": "param1", "type": "string"},
                {"name": "param2", "type": "number"},
                {"name": "param3"},
            ]
        }
        result = formatter._create_full_params(func)
        assert "param1: string" in result
        assert "param2: number" in result
        assert "param3" in result

    def test_create_full_params_string_parameters(self, formatter):
        func = {"parameters": ["param1", "param2"]}
        result = formatter._create_full_params(func)
        assert "(param1, param2)" == result

    def test_create_full_params_long_truncation(self, formatter):
        long_params = [f"param{i}" for i in range(20)]
        func = {"parameters": long_params}
        result = formatter._create_full_params(func)
        assert len(result) <= 53
        assert result.endswith("...)")

    def test_create_compact_params_empty(self, formatter):
        func = {"parameters": []}
        result = formatter._create_compact_params(func)
        assert result == "()"

    def test_create_compact_params_few_params(self, formatter):
        func = {
            "parameters": [{"name": "param1"}, {"name": "param2"}, {"name": "param3"}]
        }
        result = formatter._create_compact_params(func)
        assert result == "(param1,param2,param3)"

    def test_create_compact_params_many_params(self, formatter):
        func = {"parameters": [{"name": f"param{i}"} for i in range(5)]}
        result = formatter._create_compact_params(func)
        assert result == "(5 params)"


class TestJavaScriptFunctionTypes:
    """Tests for function/method type detection methods."""

    @pytest.fixture
    def formatter(self) -> JavaScriptTableFormatter:
        return JavaScriptTableFormatter()

    def test_get_function_type_async(self, formatter):
        func = {"is_async": True, "is_generator": False, "is_arrow": False}
        result = formatter._get_function_type(func)
        assert result == "async function"

    def test_get_function_type_generator(self, formatter):
        func = {"is_async": False, "is_generator": True, "is_arrow": False}
        result = formatter._get_function_type(func)
        assert result == "generator"

    def test_get_function_type_arrow(self, formatter):
        func = {"is_async": False, "is_generator": False, "is_arrow": True}
        result = formatter._get_function_type(func)
        assert result == "arrow"

    def test_get_function_type_constructor_method(self, formatter):
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


class TestJavaScriptMethodHelpers:
    """Tests for method detection and class extraction helpers."""

    @pytest.fixture
    def formatter(self) -> JavaScriptTableFormatter:
        return JavaScriptTableFormatter()

    def test_is_method_with_flag(self, formatter):
        func1 = {"is_method": True}
        assert formatter._is_method(func1) is True

    def test_is_method_with_class_name(self, formatter):
        func2 = {"class_name": "TestClass"}
        assert formatter._is_method(func2) is True

    def test_is_method_without_either(self, formatter):
        func3 = {}
        assert formatter._is_method(func3) is False

    def test_get_method_class_present(self, formatter):
        method = {"class_name": "TestClass"}
        result = formatter._get_method_class(method)
        assert result == "TestClass"

    def test_get_method_class_missing(self, formatter):
        method_no_class = {}
        result = formatter._get_method_class(method_no_class)
        assert result == "Unknown"


class TestJavaScriptTypeInference:
    """Tests for JS type inference and variable helpers."""

    @pytest.fixture
    def formatter(self) -> JavaScriptTableFormatter:
        return JavaScriptTableFormatter()

    def test_infer_js_type(self, formatter):
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
        test_cases = [
            ({"is_constant": True}, "block"),
            ({"raw_text": "let x = 1"}, "block"),
            ({"raw_text": "var x = 1"}, "function"),
            ({"raw_text": "unknown x = 1"}, "unknown"),
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
        test_cases = [
            ({"is_default": True}, "default"),
            ({"is_named": True}, "named"),
            ({"is_all": True}, "all"),
            ({}, "unknown"),
        ]
        for export_data, expected in test_cases:
            result = formatter._get_export_type(export_data)
            assert result == expected
