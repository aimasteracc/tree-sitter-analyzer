from unittest.mock import MagicMock

from tree_sitter_analyzer.formatters._cpp_formatter_helpers import (
    create_cpp_compact_signature,
    format_cpp_class_details,
    format_cpp_compact_table,
    format_cpp_full_table,
    shorten_cpp_type,
)


def _make_formatter():
    fmt = MagicMock()
    fmt.format_class_details.return_value = ["## Foo (1-50)", ""]
    fmt.format_method_row.side_effect = lambda m: (
        f"| {m.get('name', '')} | sig | + | 1-5 | 1 | - |"
    )
    fmt.create_compact_signature.side_effect = lambda m: (
        f"({','.join(str(p.get('type', 'Any')) for p in m.get('parameters', []))})"
    )
    fmt.convert_visibility.side_effect = lambda v: {"public": "+", "private": "-"}.get(
        v, v
    )
    fmt.clean_csv_text.side_effect = lambda t: t
    fmt.extract_doc_summary.side_effect = lambda t: t[:20] if t else ""
    return fmt


def _identity_shorten(t):
    return str(t)


class TestShortenCppType:
    def test_none_returns_void(self):
        assert shorten_cpp_type(None) == "void"

    def test_int(self):
        assert shorten_cpp_type("int") == "i"

    def test_double(self):
        assert shorten_cpp_type("double") == "d"

    def test_float(self):
        assert shorten_cpp_type("float") == "f"

    def test_char(self):
        assert shorten_cpp_type("char") == "c"

    def test_long(self):
        assert shorten_cpp_type("long") == "l"

    def test_short(self):
        assert shorten_cpp_type("short") == "s"

    def test_bool(self):
        assert shorten_cpp_type("bool") == "b"

    def test_void(self):
        assert shorten_cpp_type("void") == "void"

    def test_size_t(self):
        assert shorten_cpp_type("size_t") == "size_t"

    def test_string(self):
        assert shorten_cpp_type("string") == "str"

    def test_unknown_type(self):
        assert shorten_cpp_type("MyClass") == "MyClass"

    def test_pointer_preserved(self):
        assert shorten_cpp_type("int*") == "int*"

    def test_reference_preserved(self):
        assert shorten_cpp_type("int&") == "int&"

    def test_array_preserved(self):
        assert shorten_cpp_type("int[10]") == "int[10]"

    def test_const_stripped(self):
        assert shorten_cpp_type("const int") == "i"

    def test_volatile_stripped(self):
        assert shorten_cpp_type("volatile int") == "i"

    def test_static_stripped(self):
        assert shorten_cpp_type("static int") == "i"

    def test_whitespace_trimmed(self):
        assert shorten_cpp_type("  int  ") == "i"


class TestCreateCppCompactSignature:
    def test_no_params(self):
        method = {"parameters": [], "return_type": "void"}
        result = create_cpp_compact_signature(_identity_shorten, method)
        assert result == "():void"

    def test_single_param(self):
        method = {
            "parameters": [{"type": "int", "name": "x"}],
            "return_type": "void",
        }
        result = create_cpp_compact_signature(_identity_shorten, method)
        assert result == "(int):void"

    def test_multiple_params(self):
        method = {
            "parameters": [
                {"type": "int", "name": "a"},
                {"type": "float", "name": "b"},
            ],
            "return_type": "double",
        }
        result = create_cpp_compact_signature(_identity_shorten, method)
        assert result == "(int,float):double"

    def test_with_shorten(self):
        method = {
            "parameters": [{"type": "int", "name": "x"}],
            "return_type": "int",
        }
        result = create_cpp_compact_signature(shorten_cpp_type, method)
        assert result == "(i):i"

    def test_default_return_type(self):
        method = {"parameters": []}
        result = create_cpp_compact_signature(_identity_shorten, method)
        assert result == "():void"


class TestFormatCppFullTable:
    def test_empty_data(self):
        fmt = _make_formatter()
        result = format_cpp_full_table(fmt, {})
        assert isinstance(result, str)

    def test_file_header(self):
        fmt = _make_formatter()
        data = {
            "file_path": "/src/main.cpp",
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = format_cpp_full_table(fmt, data)
        assert "# main.cpp" in result

    def test_namespace_from_packages(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "packages": [{"name": "std", "line_range": {"start": 1, "end": 5}}],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = format_cpp_full_table(fmt, data)
        assert "## Namespaces" in result
        assert "- `std` (1-5)" in result

    def test_namespace_from_package_name(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "package": {"name": "myns"},
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = format_cpp_full_table(fmt, data)
        assert "## Package" in result
        assert "`myns`" in result

    def test_imports_section(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "imports": [
                {"statement": "#include <iostream>"},
                {"statement": "#include <vector>"},
            ],
            "language": "cpp",
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = format_cpp_full_table(fmt, data)
        assert "## Imports" in result
        assert "```cpp" in result
        assert "#include <iostream>" in result

    def test_imports_skipped_when_empty(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = format_cpp_full_table(fmt, data)
        assert "## Imports" not in result

    def test_classes_overview(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "classes": [
                {
                    "name": "Widget",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 50},
                }
            ],
            "methods": [],
            "fields": [],
        }
        result = format_cpp_full_table(fmt, data)
        assert "## Classes Overview" in result
        assert "| Widget | class | public | 10-50 |" in result

    def test_global_functions(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "classes": [
                {
                    "name": "Inner",
                    "line_range": {"start": 10, "end": 50},
                }
            ],
            "methods": [
                {
                    "name": "globalFunc",
                    "visibility": "public",
                    "line_range": {"start": 3, "end": 8},
                }
            ],
            "fields": [],
        }
        result = format_cpp_full_table(fmt, data)
        assert "## Global Functions" in result
        assert "globalFunc" in result

    def test_global_variables(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "classes": [
                {
                    "name": "Inner",
                    "line_range": {"start": 10, "end": 50},
                }
            ],
            "methods": [],
            "fields": [
                {
                    "name": "g_count",
                    "type": "int",
                    "visibility": "public",
                    "line_range": {"start": 3, "end": 3},
                    "modifiers": [],
                    "javadoc": "",
                }
            ],
        }
        result = format_cpp_full_table(fmt, data)
        assert "## Global Variables" in result
        assert "g_count" in result

    def test_no_trailing_blank_lines(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = format_cpp_full_table(fmt, data)
        assert not result.endswith("\n\n")


class TestFormatCppClassDetails:
    def test_basic_class(self):
        fmt = _make_formatter()
        class_info = {
            "name": "Foo",
            "line_range": {"start": 1, "end": 50},
        }
        data = {
            "methods": [
                {"name": "bar", "line_range": {"start": 10, "end": 20}},
            ],
            "fields": [
                {"name": "x", "line_range": {"start": 5, "end": 5}},
            ],
        }
        result = format_cpp_class_details(fmt, class_info, data)
        assert "## Foo (1-50)" in result

    def test_class_with_no_members(self):
        fmt = _make_formatter()
        class_info = {
            "name": "Empty",
            "line_range": {"start": 1, "end": 10},
        }
        result = format_cpp_class_details(
            fmt, class_info, {"methods": [], "fields": []}
        )
        assert "## Empty (1-10)" in result


class TestFormatCppCompactTable:
    def test_basic(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "methods": [
                {
                    "name": "main",
                    "parameters": [],
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                    "complexity_score": 1,
                    "javadoc": "",
                }
            ],
        }
        result = format_cpp_compact_table(fmt, data)
        assert "# test.cpp" in result
        assert "## Info" in result
        assert "## Methods" in result

    def test_compact_info_cpp_package(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "package": {"name": "myns"},
            "language": "cpp",
            "methods": [],
        }
        result = format_cpp_compact_table(fmt, data)
        assert "| Package | myns |" in result

    def test_compact_info_stats(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "statistics": {"method_count": 10, "field_count": 5},
            "methods": [],
        }
        result = format_cpp_compact_table(fmt, data)
        assert "| Methods | 10 |" in result
        assert "| Fields | 5 |" in result

    def test_no_methods_section_when_empty(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "methods": [],
        }
        result = format_cpp_compact_table(fmt, data)
        assert "## Methods" not in result

    def test_no_trailing_blank_lines(self):
        fmt = _make_formatter()
        data = {
            "file_path": "test.cpp",
            "methods": [],
        }
        result = format_cpp_compact_table(fmt, data)
        assert not result.endswith("\n\n")
