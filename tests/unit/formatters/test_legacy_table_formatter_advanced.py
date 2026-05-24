#!/usr/bin/env python3
"""
Advanced tests for LegacyTableFormatter covering platform newlines,
edge cases, detailed formatting, language-specific behavior, and
internal helper method branches.
"""

import os
from typing import Any

import pytest

from tree_sitter_analyzer.legacy_table_formatter import LegacyTableFormatter


class TestPlatformNewlines:

    def test_get_platform_newline(self) -> None:
        formatter = LegacyTableFormatter()
        newline = formatter._get_platform_newline()
        assert newline in ("\n", "\r\n")

    def test_convert_to_platform_newlines(self) -> None:
        formatter = LegacyTableFormatter()
        text = "line1\nline2\nline3"
        result = formatter._convert_to_platform_newlines(text)

        if os.name == "nt":
            assert "\r\n" in result or "\n" in result
        else:
            assert result == text

    def test_csv_skips_newline_conversion(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data = {"classes": [{"name": "Test"}]}
        result = formatter.format_structure(data)

        if os.name == "nt":
            assert "\r\r\n" not in result


class TestEdgeCases:

    def test_none_classes(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": None}
        result = formatter.format_structure(data)
        assert "# " in result

    def test_none_methods(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": [{"name": "Test"}], "methods": None}
        result = formatter.format_structure(data)
        assert "## Methods" in result

    def test_none_fields(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": [{"name": "Test"}], "fields": None}
        result = formatter.format_structure(data)
        assert "## Fields" in result

    def test_empty_package_name(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": [{"name": "Test"}], "package": {"name": ""}}
        result = formatter.format_structure(data)
        assert "Test" in result

    def test_unknown_package(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": [{"name": "Test"}], "package": {"name": "unknown"}}
        result = formatter.format_structure(data)
        assert "## Package" not in result or "unknown" in result

    def test_file_path_handling(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = {"classes": [], "file_path": "/path/to/MyClass.java"}
        result = formatter.format_structure(data)
        assert "MyClass" in result

    def test_file_path_with_various_extensions(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")

        data = {"classes": [], "file_path": "/path/to/module.py"}
        result = formatter.format_structure(data)
        assert "module" in result

        data = {"classes": [], "file_path": "/path/to/app.js"}
        result = formatter.format_structure(data)
        assert "app" in result

    def test_method_with_no_parameters(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [{"name": "Test"}],
            "methods": [
                {
                    "name": "noParams",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 10},
                }
            ],
        }
        result = formatter.format_structure(data)
        assert "| noParams |" in result

    def test_parameter_as_plain_string(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [{"name": "Test"}],
            "methods": [
                {
                    "name": "test",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": ["plainParam"],
                    "line_range": {"start": 10},
                }
            ],
        }
        result = formatter.format_structure(data)
        assert "plainParam" in result

    def test_parameter_as_other_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [{"name": "Test"}],
            "methods": [
                {
                    "name": "test",
                    "return_type": "void",
                    "visibility": "public",
                    "parameters": [123],
                    "line_range": {"start": 10},
                }
            ],
        }
        result = formatter.format_structure(data)
        assert "123" in result

    def test_missing_line_range(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [{"name": "Test"}],
            "methods": [
                {
                    "name": "test",
                    "return_type": "void",
                    "visibility": "public",
                }
            ],
        }
        result = formatter.format_structure(data)
        assert "test" in result


class TestDetailedFormatting:

    @pytest.fixture
    def formatter_with_javadoc(self) -> LegacyTableFormatter:
        return LegacyTableFormatter(format_type="full", include_javadoc=True)

    def test_get_class_methods_basic(self) -> None:
        formatter = LegacyTableFormatter()
        data = {
            "classes": [{"line_range": {"start": 1, "end": 50}}],
            "methods": [
                {"name": "m1", "line_range": {"start": 10}},
                {"name": "m2", "line_range": {"start": 60}},
            ],
        }
        class_range = {"start": 1, "end": 50}
        methods = formatter._get_class_methods(data, class_range)
        assert len(methods) == 1
        assert methods[0]["name"] == "m1"

    def test_get_class_fields_basic(self) -> None:
        formatter = LegacyTableFormatter()
        data = {
            "classes": [{"line_range": {"start": 1, "end": 50}}],
            "fields": [
                {"name": "f1", "line_range": {"start": 5}},
                {"name": "f2", "line_range": {"start": 70}},
            ],
        }
        class_range = {"start": 1, "end": 50}
        fields = formatter._get_class_fields(data, class_range)
        assert len(fields) == 1
        assert fields[0]["name"] == "f1"

    def test_get_class_methods_excludes_nested(self) -> None:
        formatter = LegacyTableFormatter()
        data = {
            "classes": [
                {"name": "Outer", "line_range": {"start": 1, "end": 100}},
                {"name": "Inner", "line_range": {"start": 30, "end": 60}},
            ],
            "methods": [
                {"name": "outerMethod", "line_range": {"start": 10}},
                {"name": "innerMethod", "line_range": {"start": 40}},
            ],
        }
        outer_range = {"start": 1, "end": 100}
        methods = formatter._get_class_methods(data, outer_range)

        method_names = [m["name"] for m in methods]
        assert "outerMethod" in method_names
        assert "innerMethod" not in method_names

    def test_get_class_fields_excludes_nested(self) -> None:
        formatter = LegacyTableFormatter()
        data = {
            "classes": [
                {"name": "Outer", "line_range": {"start": 1, "end": 100}},
                {"name": "Inner", "line_range": {"start": 30, "end": 60}},
            ],
            "fields": [
                {"name": "outerField", "line_range": {"start": 5}},
                {"name": "innerField", "line_range": {"start": 35}},
            ],
        }
        outer_range = {"start": 1, "end": 100}
        fields = formatter._get_class_fields(data, outer_range)

        field_names = [f["name"] for f in fields]
        assert "outerField" in field_names
        assert "innerField" not in field_names


class TestLanguageSpecificFormatting:

    def test_python_language_formatting(self) -> None:
        formatter = LegacyTableFormatter(format_type="full", language="python")
        data = {
            "classes": [{"name": "Test"}],
            "imports": [{"statement": "import os"}],
        }
        result = formatter.format_structure(data)
        assert "```python" in result

    def test_java_language_formatting(self) -> None:
        formatter = LegacyTableFormatter(format_type="full", language="java")
        data = {
            "classes": [{"name": "Test"}],
            "imports": [{"statement": "import java.util.*;"}],
        }
        result = formatter.format_structure(data)
        assert "```java" in result

    def test_javascript_language_formatting(self) -> None:
        formatter = LegacyTableFormatter(format_type="full", language="javascript")
        data = {
            "classes": [{"name": "Test"}],
            "imports": [{"statement": "import React from 'react';"}],
        }
        result = formatter.format_structure(data)
        assert "```javascript" in result


class TestFullTableMultiClassParamTypes:

    def _multi_class_data(self, methods: list[dict]) -> dict[str, Any]:
        return {
            "classes": [
                {
                    "name": "Outer",
                    "line_range": {"start": 1, "end": 100},
                    "type": "class",
                    "visibility": "public",
                },
                {
                    "name": "Inner",
                    "line_range": {"start": 40, "end": 60},
                    "type": "class",
                    "visibility": "private",
                },
            ],
            "methods": methods,
        }

    def test_string_param_in_multi_class(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = self._multi_class_data(
            [
                {
                    "name": "foo",
                    "parameters": ["int x", "String y"],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10},
                },
            ]
        )
        result = formatter.format_structure(data)
        assert "int x, String y" in result

    def test_fallback_param_in_multi_class(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        data = self._multi_class_data(
            [
                {
                    "name": "bar",
                    "parameters": [42],
                    "return_type": "int",
                    "visibility": "public",
                    "line_range": {"start": 12},
                },
            ]
        )
        result = formatter.format_structure(data)
        assert "42" in result


class TestCSVFieldAndParamCoverage:

    def test_csv_with_field_rows(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "fields": [
                {
                    "name": "count",
                    "type": "int",
                    "visibility": "private",
                    "modifiers": ["static", "final"],
                    "line_range": {"start": 5},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "field" in result
        assert "count" in result
        assert "true" in result

    def test_csv_method_with_string_params(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "methods": [
                {
                    "name": "hello",
                    "parameters": ["int x"],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "x:int" in result

    def test_csv_method_with_fallback_params(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "methods": [
                {
                    "name": "hello",
                    "parameters": [42],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "42" in result

    def test_csv_method_is_static(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "methods": [
                {
                    "name": "main",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "is_static": True,
                    "line_range": {"start": 10},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "true" in result

    def test_csv_method_is_final(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "methods": [
                {
                    "name": "run",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "is_final": True,
                    "line_range": {"start": 10},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "true" in result

    def test_csv_constructor(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "methods": [
                {
                    "name": "MyClass",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "is_constructor": True,
                    "line_range": {"start": 5},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "constructor" in result

    def test_csv_class_with_final_modifier(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "classes": [
                {
                    "name": "Util",
                    "type": "class",
                    "visibility": "public",
                    "modifiers": ["final"],
                    "line_range": {"start": 1},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "Util" in result
        assert "true" in result

    def test_csv_field_with_is_static_flag(self) -> None:
        formatter = LegacyTableFormatter(format_type="csv")
        data: dict[str, Any] = {
            "fields": [
                {
                    "name": "instance",
                    "type": "Object",
                    "visibility": "public",
                    "is_static": True,
                    "line_range": {"start": 3},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "field" in result
        assert "instance" in result


class TestCreateFullSignatureBranches:

    def test_static_method_signature(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._create_full_signature(
            {
                "name": "main",
                "parameters": [],
                "return_type": "void",
                "is_static": True,
            }
        )
        assert "[static]" in result
        assert "):void" in result

    def test_string_param_signature(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._create_full_signature(
            {
                "name": "foo",
                "parameters": ["String msg"],
                "return_type": "int",
            }
        )
        assert "String msg" in result
        assert ":int" in result

    def test_fallback_param_signature(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._create_full_signature(
            {
                "name": "foo",
                "parameters": [None],
                "return_type": "void",
            }
        )
        assert "None" in result


class TestAbbreviateTypeAdvanced:

    def test_generic_type_map(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        result = formatter._abbreviate_type("Map<String, Object>")
        assert result == "M<S, O>"

    def test_generic_type_custom(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        result = formatter._abbreviate_type("Custom<String>")
        assert result.startswith("C<")

    def test_array_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        result = formatter._abbreviate_type("String[]")
        assert result == "S[]"

    def test_empty_string_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        result = formatter._abbreviate_type("")
        assert result == "?"

    def test_unknown_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        result = formatter._abbreviate_type("CustomType")
        assert result == "C"


class TestCompactTableClassesNone:

    def test_compact_with_none_classes(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        data: dict[str, Any] = {
            "classes": None,
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert "# Unknown" in result

    def test_compact_no_package(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        data: dict[str, Any] = {
            "classes": [{"name": "MyClass"}],
            "methods": [],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert "# MyClass" in result

    def test_compact_with_methods_and_fields(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        data: dict[str, Any] = {
            "package": {"name": "com.example"},
            "classes": [{"name": "Service"}],
            "methods": [
                {
                    "name": "process",
                    "parameters": [
                        {"type": "String", "name": "input"},
                    ],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 20},
                    "complexity_score": 3,
                },
            ],
            "fields": [
                {
                    "name": "name",
                    "type": "String",
                    "visibility": "private",
                    "line_range": {"start": 5},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "## Methods" in result
        assert "## Fields" in result
        assert "process" in result
        assert "name" in result


class TestShortenTypeBranches:

    def test_none_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        assert formatter._shorten_type(None) == "O"

    def test_non_string_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        assert formatter._shorten_type(42) == "42"

    def test_map_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._shorten_type("Map<String,Object>")
        assert result == "M<S,O>"

    def test_list_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._shorten_type("List<String>")
        assert result == "L<S>"

    def test_array_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._shorten_type("String[]")
        assert result == "S[]"

    def test_empty_array_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._shorten_type("[]")
        assert result == "O[]"

    def test_unmapped_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._shorten_type("MyCustomType")
        assert result == "MyCustomType"


class TestDocSummaryAndCSVText:

    def test_extract_doc_with_javadoc(self) -> None:
        formatter = LegacyTableFormatter(include_javadoc=True)
        result = formatter._extract_doc_summary("/**This is a test. More text.*/")
        assert "This is a test" in result

    def test_extract_doc_empty(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._extract_doc_summary("") == "-"

    def test_clean_csv_text_with_newlines(self) -> None:
        formatter = LegacyTableFormatter()
        result = formatter._clean_csv_text("line1\nline2  line3")
        assert "line1 line2 line3" == result

    def test_clean_csv_text_empty(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._clean_csv_text("") == "-"

    def test_clean_csv_text_dash(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._clean_csv_text("-") == "-"

    def test_clean_csv_text_with_quotes(self) -> None:
        formatter = LegacyTableFormatter()
        result = formatter._clean_csv_text('say "hello"')
        assert '""' in result
