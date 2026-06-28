"""
All Java formatter output tests.

Consolidates: test_java_formatter_basic, test_java_formatter_advanced,
test_java_formatter_coverage, test_java_formatter_signatures.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tree_sitter_analyzer.default_table_formatter import DefaultTableFormatter
from tree_sitter_analyzer.formatters._java_formatter_signatures_mixin import (
    _method_sig_line,
    _shorten_return_type,
)
from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
from tree_sitter_analyzer.formatters.go_formatter import GoTableFormatter
from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    _validate_format_type,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FMT = JavaTableFormatter()

_BASE_CLASS: dict[str, Any] = {
    "name": "Test",
    "type": "class",
    "visibility": "public",
    "line_range": {"start": 1, "end": 10},
}

_BASE_DATA: dict[str, Any] = {
    "package": {"name": "com.example"},
    "classes": [_BASE_CLASS],
    "imports": [],
    "methods": [],
    "fields": [],
    "statistics": {"method_count": 0, "field_count": 0},
}


def _data(**overrides: Any) -> dict[str, Any]:
    return {**_BASE_DATA, **overrides}


def _make_simple_data(
    *,
    package: str = "com.example",
    class_name: str = "MyClass",
    n_methods: int = 3,
    n_fields: int = 2,
) -> dict:
    cls = {
        "name": class_name,
        "type": "class",
        "visibility": "public",
        "line_range": {"start": 1, "end": 100},
    }
    methods = [
        {
            "name": f"method{i}",
            "return_type": "void" if i % 2 == 0 else "int",
            "parameters": [{"name": "p", "type": "String"}] * (i % 3),
            "is_constructor": False,
            "is_static": False,
            "complexity_score": 1,
            "line_range": {"start": 10 + i * 5, "end": 14 + i * 5},
            "javadoc": "",
        }
        for i in range(n_methods)
    ]
    fields = [
        {
            "name": f"field{i}",
            "type": "int",
            "visibility": "private",
            "line_range": {"start": 5 + i, "end": 5 + i},
        }
        for i in range(n_fields)
    ]
    return {
        "file_path": f"src/{class_name}.java",
        "language": "java",
        "line_count": 100,
        "package": {"name": package},
        "classes": [cls],
        "methods": methods,
        "fields": fields,
        "imports": [],
        "statistics": {"method_count": n_methods, "field_count": n_fields},
    }


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestInstantiation:
    def test_create_formatter(self):
        assert isinstance(JavaTableFormatter(), JavaTableFormatter)

    def test_formatter_with_full_format_type(self):
        fmt = JavaTableFormatter(format_type="full")
        assert fmt.format_type == "full"

    def test_formatter_with_compact_format_type(self):
        fmt = JavaTableFormatter(format_type="compact")
        assert fmt.format_type == "compact"

    def test_formatter_inherits_from_base(self):
        from tree_sitter_analyzer.formatters.base_formatter import BaseTableFormatter

        assert isinstance(JavaTableFormatter(), BaseTableFormatter)


# ---------------------------------------------------------------------------
# Full table formatting
# ---------------------------------------------------------------------------


class TestFormatFullTable:
    def test_simple_class_header(self):
        result = _FMT._format_full_table(
            _data(
                classes=[
                    {
                        "name": "TestClass",
                        "type": "class",
                        "visibility": "public",
                        "line_range": {"start": 1, "end": 10},
                    }
                ]
            )
        )
        assert "# com.example.TestClass" in result
        assert "## Class Info" in result

    def test_class_with_package(self):
        result = _FMT._format_full_table(
            _data(
                package={"name": "com.example.test"},
                classes=[
                    {
                        "name": "MyClass",
                        "type": "class",
                        "visibility": "public",
                        "line_range": {"start": 5, "end": 50},
                    }
                ],
            )
        )
        assert "com.example.test.MyClass" in result

    def test_class_with_imports(self):
        result = _FMT._format_full_table(
            _data(
                imports=[
                    {"statement": "import java.util.List;"},
                    {"statement": "import java.util.Map;"},
                ]
            )
        )
        assert "## Imports" in result
        assert "java.util.List" in result
        assert "java.util.Map" in result

    def test_class_with_fields(self):
        result = _FMT._format_full_table(
            _data(
                fields=[
                    {
                        "name": "name",
                        "type": "String",
                        "visibility": "private",
                        "modifiers": [],
                        "line_range": {"start": 5, "end": 5},
                        "javadoc": "",
                    },
                    {
                        "name": "age",
                        "type": "int",
                        "visibility": "private",
                        "modifiers": [],
                        "line_range": {"start": 6, "end": 6},
                        "javadoc": "",
                    },
                ],
                statistics={"method_count": 0, "field_count": 2},
            )
        )
        assert "## Fields" in result
        assert "name" in result
        assert "String" in result
        assert "age" in result
        assert "int" in result

    def test_class_with_public_methods(self):
        result = _FMT._format_full_table(
            _data(
                methods=[
                    {
                        "name": "getName",
                        "visibility": "public",
                        "return_type": "String",
                        "parameters": [],
                        "is_constructor": False,
                        "line_range": {"start": 10, "end": 12},
                        "complexity_score": 1,
                        "javadoc": "",
                    }
                ],
                statistics={"method_count": 1, "field_count": 0},
            )
        )
        assert "## Public Methods" in result
        assert "getName" in result

    def test_constructor_gets_constructor_section(self):
        result = _FMT._format_full_table(
            _data(
                methods=[
                    {
                        "name": "TestClass",
                        "visibility": "public",
                        "return_type": None,
                        "parameters": [{"type": "String", "name": "param"}],
                        "is_constructor": True,
                        "line_range": {"start": 5, "end": 7},
                        "complexity_score": 1,
                        "javadoc": "",
                    }
                ],
                statistics={"method_count": 1, "field_count": 0},
            )
        )
        assert "## Constructor" in result
        assert "TestClass" in result

    def test_enum_class_type_shown(self):
        result = _FMT._format_full_table(
            _data(
                classes=[
                    {
                        "name": "Status",
                        "type": "enum",
                        "visibility": "public",
                        "line_range": {"start": 1, "end": 10},
                        "constants": ["ACTIVE", "INACTIVE"],
                    }
                ]
            )
        )
        assert "enum" in result

    def test_multiple_classes_table_header(self):
        result = _FMT._format_full_table(
            _data(
                file_path="Test.java",
                classes=[
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
            )
        )
        assert "## Classes" in result
        assert "ClassA" in result
        assert "ClassB" in result

    def test_private_methods_section(self):
        result = _FMT._format_full_table(
            _data(
                classes=[
                    {
                        "name": "TestClass",
                        "type": "class",
                        "visibility": "public",
                        "line_range": {"start": 1, "end": 30},
                    }
                ],
                methods=[
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
                statistics={"method_count": 1, "field_count": 0},
            )
        )
        assert "## Private Methods" in result
        assert "privateHelper" in result

    def test_mixed_visibility_methods(self):
        result = _FMT._format_full_table(
            _data(
                classes=[
                    {
                        "name": "TestClass",
                        "type": "class",
                        "visibility": "public",
                        "line_range": {"start": 1, "end": 50},
                    }
                ],
                methods=[
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
                statistics={"method_count": 2, "field_count": 0},
            )
        )
        assert "## Public Methods" in result
        assert "## Private Methods" in result
        assert "publicMethod" in result
        assert "privateMethod" in result

    def test_multiple_classes_with_package_methods_fields_counts(self):
        data = {
            "package": {"name": "com.example"},
            "file_path": "path/to/MyFile.java",
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
                    "visibility": "package",
                    "line_range": {"start": 11, "end": 20},
                },
            ],
            "methods": [
                {"name": "methodA", "line_range": {"start": 2, "end": 3}},
                {"name": "methodB", "line_range": {"start": 12, "end": 13}},
            ],
            "fields": [
                {"name": "fieldA", "line_range": {"start": 4, "end": 4}},
                {"name": "fieldB", "line_range": {"start": 14, "end": 14}},
            ],
        }
        result = _FMT._format_full_table(data)
        assert "# com.example.MyFile" in result
        assert "| Class | Type | Visibility | Lines | Methods | Fields |" in result
        assert "| ClassA | class | public | 1-10 | 1 | 1 |" in result
        assert "| ClassB | class | package | 11-20 | 1 | 1 |" in result

    def test_multiple_classes_no_package_uses_filename(self):
        data = {
            "file_path": "path/to/MyFile.java",
            "classes": [
                {"name": "A", "type": "class", "line_range": {"start": 1, "end": 10}},
                {"name": "B", "type": "class", "line_range": {"start": 11, "end": 20}},
            ],
        }
        result = _FMT._format_full_table(data)
        assert "# MyFile" in result

    def test_single_class_no_package_uses_class_name(self):
        data = {
            "classes": [
                {"name": "A", "type": "class", "line_range": {"start": 1, "end": 10}}
            ]
        }
        result = _FMT._format_full_table(data)
        assert "# A" in result

    def test_enum_details_field_method_shown(self):
        data = {
            "classes": [
                {
                    "name": "MyEnum",
                    "type": "enum",
                    "line_range": {"start": 1, "end": 20},
                    "constants": ["A", "B"],
                }
            ],
            "fields": [
                {
                    "name": "value",
                    "type": "int",
                    "visibility": "private",
                    "line_range": {"start": 5, "end": 5},
                    "modifiers": ["final"],
                }
            ],
            "methods": [
                {
                    "name": "getValue",
                    "visibility": "public",
                    "return_type": "int",
                    "line_range": {"start": 10, "end": 12},
                    "parameters": [],
                }
            ],
        }
        result = _FMT._format_full_table(data)
        assert "## MyEnum" in result
        assert "| Type | enum |" in result
        assert "### Fields" in result
        assert "| value | int | - | final | 5 | - |" in result
        assert "Public Methods" in result
        assert "getValue" in result

    def test_empty_data_returns_string(self):
        result = _FMT._format_full_table(_data(package={}, classes=[], statistics={}))
        assert isinstance(result, str)

    def test_missing_package_returns_string(self):
        result = _FMT._format_full_table(_data(package=None))
        assert isinstance(result, str)

    def test_none_values_return_string(self):
        result = _FMT._format_full_table(
            {
                "package": None,
                "classes": [],
                "imports": [],
                "methods": [],
                "fields": [],
                "statistics": None,
            }
        )
        assert isinstance(result, str)

    def test_javadoc_in_output(self):
        result = _FMT._format_full_table(
            _data(
                methods=[
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
                statistics={"method_count": 1, "field_count": 0},
            )
        )
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Compact table formatting
# ---------------------------------------------------------------------------


class TestFormatCompactTable:
    def test_compact_basic_header(self):
        result = _FMT._format_compact_table(_data())
        assert "# com.example.Test" in result
        assert "## Info" in result

    def test_compact_with_methods(self):
        result = _FMT._format_compact_table(
            _data(
                methods=[
                    {
                        "name": "test",
                        "visibility": "public",
                        "return_type": "void",
                        "parameters": [],
                        "is_constructor": False,
                        "line_range": {"start": 10, "end": 12},
                        "complexity_score": 1,
                        "javadoc": "",
                    }
                ],
                statistics={"method_count": 1, "field_count": 0},
            )
        )
        assert "## Methods" in result
        assert "test" in result

    def test_compact_multiple_classes_with_package(self):
        result = _FMT._format_compact_table(
            _data(
                file_path="path/to/MultiClass.java",
                classes=[
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
            )
        )
        assert "com.example.MultiClass" in result
        assert "## Info" in result

    def test_compact_multiple_classes_no_package(self):
        result = _FMT._format_compact_table(
            _data(
                file_path="path/to/MultiClass.java",
                package={},
                classes=[
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
            )
        )
        assert "MultiClass" in result
        assert "## Info" in result

    def test_compact_single_class_no_package(self):
        result = _FMT._format_compact_table(
            _data(
                package={},
                classes=[
                    {
                        "name": "SingleClass",
                        "type": "class",
                        "visibility": "public",
                        "line_range": {"start": 1, "end": 20},
                    }
                ],
            )
        )
        assert "# SingleClass" in result
        assert "## Info" in result


# ---------------------------------------------------------------------------
# Method row formatting
# ---------------------------------------------------------------------------


class TestMethodFormatting:
    def test_format_method_row_contains_name_and_complexity(self):
        method = {
            "name": "testMethod",
            "visibility": "public",
            "return_type": "String",
            "parameters": [{"type": "int", "name": "x"}],
            "line_range": {"start": 10, "end": 15},
            "complexity_score": 2,
            "javadoc": "Test method",
        }
        result = _FMT._format_method_row(method)
        assert "testMethod" in result
        assert "2" in result

    def test_format_method_row_javadoc_first_line_only(self):
        method = {"name": "test", "javadoc": "Line 1\nLine 2"}
        row = _FMT._format_method_row(method)
        assert "Line 1" in row

    def test_create_compact_signature_abbreviates_types(self):
        method = {
            "parameters": [
                {"type": "String", "name": "s"},
                {"type": "int", "name": "n"},
            ],
            "return_type": "boolean",
        }
        result = _FMT._create_compact_signature(method)
        assert "S" in result
        assert "i" in result
        assert "b" in result

    def test_create_full_signature_includes_types(self):
        method = {
            "parameters": [{"type": "String", "name": "text"}],
            "return_type": "void",
        }
        result = _FMT._create_full_signature(method)
        assert "String" in result
        assert "void" in result


# ---------------------------------------------------------------------------
# Type shortening
# ---------------------------------------------------------------------------


class TestTypeShortening:
    def test_primitive_types(self):
        assert _FMT._shorten_type("int") == "i"
        assert _FMT._shorten_type("long") == "l"
        assert _FMT._shorten_type("double") == "d"
        assert _FMT._shorten_type("boolean") == "b"
        assert _FMT._shorten_type("void") == "void"

    def test_common_object_types(self):
        assert _FMT._shorten_type("String") == "S"
        assert _FMT._shorten_type("Object") == "O"
        assert _FMT._shorten_type("Exception") == "E"

    def test_collection_types(self):
        assert _FMT._shorten_type("List<String>") == "L<S>"
        assert _FMT._shorten_type("Map<String,Object>") == "M<S,O>"

    def test_array_types(self):
        assert _FMT._shorten_type("String[]") == "S[]"
        assert _FMT._shorten_type("Object[]") == "O[]"
        assert _FMT._shorten_type("int[]") == "i[]"
        assert _FMT._shorten_type("Unknown[]") == "U[]"

    def test_none_type_returns_O(self):
        assert _FMT._shorten_type(None) == "O"

    def test_unknown_type_returns_itself(self):
        assert _FMT._shorten_type("CustomType") == "CustomType"

    def test_empty_array_type(self):
        assert _FMT._shorten_type("[]") == "O[]"

    def test_exception_abbreviations(self):
        assert _FMT._shorten_type("RuntimeException") == "RE"
        assert _FMT._shorten_type("SQLException") == "SE"
        assert _FMT._shorten_type("IllegalArgumentException") == "IAE"

    def test_non_string_input(self):
        assert _FMT._shorten_type(123) == "123"


# ---------------------------------------------------------------------------
# Visibility conversion
# ---------------------------------------------------------------------------


class TestVisibilityConversion:
    def test_public_visibility(self):
        result = _FMT._convert_visibility("public")
        assert result in ["+", "public", "pub"]

    def test_private_visibility(self):
        result = _FMT._convert_visibility("private")
        assert result in ["-", "private", "priv"]

    def test_protected_visibility(self):
        result = _FMT._convert_visibility("protected")
        assert result in ["#", "protected", "prot"]


# ---------------------------------------------------------------------------
# format_table / format_summary / format_structure / format_advanced
# ---------------------------------------------------------------------------


class TestFormatDispatch:
    def test_format_table_json_parseable(self):
        result = _FMT.format_table(
            {
                "package": {"name": "com.example"},
                "classes": [{"name": "Test", "type": "class"}],
            },
            table_type="json",
        )
        assert isinstance(result, str)
        assert json.loads(result) is not None

    def test_format_summary_contains_package(self):
        result = _FMT.format_summary(_data())
        assert isinstance(result, str)
        assert "com.example" in result

    def test_format_structure_returns_string(self):
        result = _FMT.format_structure(_data())
        assert isinstance(result, str)
        assert result

    def test_format_advanced_csv_returns_string(self):
        result = _FMT.format_advanced(_data(), output_format="csv")
        assert isinstance(result, str)

    def test_format_advanced_json_returns_parseable(self):
        data = {"classes": [{"name": "Test"}]}
        result = _FMT.format_advanced(data, "json")
        assert '"name": "Test"' in result

    def test_format_advanced_unknown_format_uses_full(self):
        data = {"classes": [{"name": "Test"}]}
        result = _FMT.format_advanced(data, "unknown")
        assert "# Test" in result

    def test_format_table_restores_format_type(self):
        fmt = JavaTableFormatter()
        fmt.format_type = "compact"
        fmt.format_table({"classes": [{"name": "Test"}]}, "json")
        assert fmt.format_type == "compact"

    def test_format_json_unserializable_returns_error_string(self):
        class Unserializable:
            pass

        result = _FMT._format_json({"key": Unserializable()})
        assert "# JSON serialization error:" in result


# ---------------------------------------------------------------------------
# Signatures mode — _method_sig_line helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, expected_contains",
    [
        (
            {
                "name": "init",
                "return_type": "void",
                "parameters": [],
                "line_range": {"start": 10, "end": 15},
            },
            ["init", "→void(0p)", "10-15"],
        ),
        (
            {
                "name": "createSession",
                "return_type": "String",
                "parameters": [{"name": "a"}, {"name": "b"}],
                "line_range": {"start": 100, "end": 120},
            },
            ["createSession", "→String(2p)", "100-120"],
        ),
        (
            {
                "name": "isAlive",
                "return_type": "boolean",
                "parameters": [],
                "line_range": {"start": 50, "end": 52},
            },
            ["isAlive", "→bool(0p)", "50-52"],
        ),
        (
            {
                "name": "getMap",
                "return_type": "Map<String, Object>",
                "parameters": [{"name": "k"}],
                "line_range": {"start": 200, "end": 205},
            },
            ["getMap", "(1p)", "200-205"],
        ),
    ],
)
def test_method_sig_line_shape(method: dict, expected_contains: list[str]) -> None:
    line = _method_sig_line(method)
    for fragment in expected_contains:
        assert fragment in line, f"Expected {fragment!r} in {line!r}"


@pytest.mark.parametrize(
    "return_type, expected",
    [
        ("void", "void"),
        ("boolean", "bool"),
        ("Boolean", "bool"),
        ("int", "int"),
        ("Integer", "int"),
        ("long", "long"),
        ("String", "String"),
        ("Object", "Object"),
        ("SomeCustomType", "SomeCustomType"),
        ("", "void"),
        ("java.util.List", "List"),
    ],
)
def test_shorten_return_type(return_type: str, expected: str) -> None:
    assert _shorten_return_type(return_type) == expected


# ---------------------------------------------------------------------------
# Signatures mode — JavaTableFormatterSignaturesMixin via JavaTableFormatter
# ---------------------------------------------------------------------------


class TestJavaSignaturesMode:
    def test_header_contains_signatures_marker(self):
        fmt = JavaTableFormatter(format_type="signatures")
        assert "[signatures]" in fmt.format_structure(_make_simple_data())

    def test_method_arrow_lines_present(self):
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data(n_methods=3))
        assert "→void" in output or "→int" in output

    def test_param_count_not_full_types(self):
        fmt = JavaTableFormatter(format_type="signatures")
        data = _make_simple_data(n_methods=2)
        data["methods"][0]["parameters"] = [
            {"name": "req", "type": "HttpServletRequest"}
        ]
        output = fmt.format_structure(data)
        assert "(1p)" in output
        assert "HttpServletRequest" not in output

    def test_class_group_header_present(self):
        fmt = JavaTableFormatter(format_type="signatures")
        assert "## FooBar" in fmt.format_structure(
            _make_simple_data(class_name="FooBar")
        )

    def test_line_range_in_method_output(self):
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data(n_methods=1))
        assert "10-14" in output

    def test_next_step_hint_present(self):
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data())
        assert "next_step" in output
        assert "--partial-read" in output

    def test_fields_shown_when_few(self):
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data(n_fields=2))
        assert "fields:" in output
        assert "field0" in output

    def test_signatures_output_shorter_than_full(self):
        full_fmt = JavaTableFormatter(format_type="full")
        sig_fmt = JavaTableFormatter(format_type="signatures")
        data = _make_simple_data(n_methods=20, n_fields=5)
        full_output = full_fmt.format_structure(data)
        sig_output = sig_fmt.format_structure(data)
        assert len(sig_output) < len(full_output), (
            f"signatures ({len(sig_output)}) should be shorter than full ({len(full_output)})"
        )

    def test_multi_class_grouping(self):
        fmt = JavaTableFormatter(format_type="signatures")
        data = _make_simple_data(n_methods=0, n_fields=0)
        data["classes"].append(
            {
                "name": "HelperClass",
                "type": "class",
                "visibility": "public",
                "line_range": {"start": 110, "end": 200},
            }
        )
        output = fmt.format_structure(data)
        assert "## MyClass" in output
        assert "## HelperClass" in output

    def test_package_line_in_output(self):
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data(package="org.apache.lucene"))
        assert "org.apache.lucene" in output


# ---------------------------------------------------------------------------
# BaseTableFormatter dispatch
# ---------------------------------------------------------------------------


def test_base_formatter_signatures_dispatch_does_not_raise():
    fmt = JavaTableFormatter(format_type="signatures")
    output = fmt.format_structure(_make_simple_data())
    assert isinstance(output, str)
    assert output


def test_base_formatter_signatures_raises_for_go_formatter():
    fmt = GoTableFormatter(format_type="signatures")
    with pytest.raises((ValueError, AttributeError)):
        fmt.format_structure(
            {"package": {}, "classes": [], "methods": [], "fields": []}
        )


# ---------------------------------------------------------------------------
# DefaultTableFormatter dispatch
# ---------------------------------------------------------------------------


def test_default_formatter_signatures_dispatch():
    fmt = DefaultTableFormatter(format_type="signatures")
    output = fmt.format_structure(_make_simple_data())
    assert "[signatures]" in output
    assert "next_step" in output


# ---------------------------------------------------------------------------
# FormatterRegistry
# ---------------------------------------------------------------------------


def test_formatter_registry_returns_formatter_for_signatures():
    # Ensure registry is initialized (conftest may reset singletons between tests)
    from tree_sitter_analyzer.formatters.formatter_registry import (
        register_builtin_formatters,
    )

    register_builtin_formatters()
    fmt = FormatterRegistry.get_formatter_for_language("java", "signatures")
    assert fmt is not None
    assert "[signatures]" in fmt.format_structure(_make_simple_data())


# ---------------------------------------------------------------------------
# analyze_code_structure_tool: _validate_format_type
# ---------------------------------------------------------------------------


def test_validate_format_type_accepts_signatures():
    _validate_format_type({"format_type": "signatures"})


def test_validate_format_type_rejects_unknown():
    with pytest.raises(ValueError, match="Invalid format_type"):
        _validate_format_type({"format_type": "unknown_mode"})
