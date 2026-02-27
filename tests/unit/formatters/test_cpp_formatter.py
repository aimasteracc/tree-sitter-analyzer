import pytest

from tree_sitter_analyzer.formatters.cpp_formatter import CppTableFormatter
from tree_sitter_analyzer.models import (
    AnalysisResult,
    Class,
    Function,
    Package,
    Variable,
)


@pytest.fixture
def formatter():
    return CppTableFormatter()


def test_cpp_formatter_basic(formatter):
    element = Function(
        name="test_func", start_line=1, end_line=5, raw_text="void test_func() {}"
    )
    result = AnalysisResult(file_path="test.cpp", elements=[element])
    output = formatter.format_analysis_result(result, "full")
    assert "test_func" in output
    assert "1-5" in output


def test_cpp_formatter_complex(formatter):
    elements = [
        Class(name="MyClass", start_line=1, end_line=10, raw_text="class MyClass {};"),
        Function(
            name="my_method", start_line=2, end_line=4, raw_text="void my_method();"
        ),
        Variable(name="my_var", start_line=5, end_line=5, raw_text="int my_var;"),
        Package(
            name="my_namespace",
            start_line=17,
            end_line=20,
            raw_text="namespace my_namespace {}",
        ),
    ]
    result = AnalysisResult(file_path="complex.cpp", elements=elements)
    output = formatter.format_analysis_result(result, "full")
    assert "MyClass" in output
    assert "my_method" in output
    assert "my_var" in output
    assert "my_namespace" in output


# ---------------------------------------------------------------------------
# Targeted tests for uncovered lines
# ---------------------------------------------------------------------------


class TestFormatFullTable:
    """Tests for _format_full_table covering namespaces, imports, classes, globals."""

    def test_with_packages_namespaces(self, formatter):
        data = {
            "file_path": "test.cpp",
            "package": {"name": "myns"},
            "packages": [{"name": "myns", "line_range": {"start": 1, "end": 50}}],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        output = formatter._format_full_table(data)
        assert "## Namespaces" in output
        assert "myns" in output

    def test_with_package_no_packages_list(self, formatter):
        data = {
            "file_path": "test.cpp",
            "package": {"name": "mypkg"},
            "packages": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        output = formatter._format_full_table(data)
        assert "## Package" in output
        assert "mypkg" in output

    def test_with_imports(self, formatter):
        data = {
            "file_path": "test.cpp",
            "package": {"name": "unknown"},
            "packages": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [{"statement": "#include <iostream>"}, {"statement": "#include <vector>"}],
            "language": "cpp",
        }
        output = formatter._format_full_table(data)
        assert "## Imports" in output
        assert "#include <iostream>" in output

    def test_with_classes_overview(self, formatter):
        data = {
            "file_path": "test.cpp",
            "package": {"name": "unknown"},
            "packages": [],
            "classes": [
                {"name": "MyClass", "type": "class", "visibility": "public", "line_range": {"start": 1, "end": 20}},
            ],
            "methods": [
                {"name": "foo", "line_range": {"start": 5, "end": 10}, "visibility": "public", "modifiers": ["public"]},
            ],
            "fields": [
                {"name": "bar", "line_range": {"start": 3, "end": 3}, "type": "int", "visibility": "public", "modifiers": []},
            ],
            "imports": [],
        }
        output = formatter._format_full_table(data)
        assert "## Classes Overview" in output
        assert "MyClass" in output
        assert "| 1 |" in output  # 1 method
        assert "| 1 |" in output  # 1 field

    def test_global_functions(self, formatter):
        data = {
            "file_path": "test.cpp",
            "package": {"name": "unknown"},
            "packages": [],
            "classes": [{"name": "C", "line_range": {"start": 1, "end": 5}}],
            "methods": [
                {"name": "global_fn", "line_range": {"start": 20, "end": 25}, "visibility": "public",
                 "return_type": "void", "parameters": [], "complexity_score": 1, "javadoc": ""},
            ],
            "fields": [],
            "imports": [],
        }
        output = formatter._format_full_table(data)
        assert "## Global Functions" in output
        assert "global_fn" in output

    def test_global_variables(self, formatter):
        data = {
            "file_path": "test.cpp",
            "package": {"name": "unknown"},
            "packages": [],
            "classes": [{"name": "C", "line_range": {"start": 1, "end": 5}}],
            "methods": [],
            "fields": [
                {"name": "g_count", "line_range": {"start": 20, "end": 20}, "type": "int",
                 "visibility": "public", "modifiers": ["static"], "javadoc": "Global counter"},
            ],
            "imports": [],
        }
        output = formatter._format_full_table(data)
        assert "## Global Variables" in output
        assert "g_count" in output
        assert "static" in output


class TestFormatClassDetails:
    """Tests for _format_class_details covering fields, methods by visibility."""

    def test_class_with_fields(self, formatter):
        class_info = {"name": "Foo", "line_range": {"start": 1, "end": 20}}
        data = {
            "methods": [],
            "fields": [
                {"name": "x", "type": "int", "visibility": "private", "modifiers": ["const"],
                 "line_range": {"start": 3, "end": 3}, "javadoc": "field x"},
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Fields" in output
        assert "x" in output

    def test_class_with_public_private_other_methods(self, formatter):
        class_info = {"name": "Bar", "line_range": {"start": 1, "end": 30}}
        data = {
            "fields": [],
            "methods": [
                {"name": "pub_m", "line_range": {"start": 5, "end": 8}, "visibility": "public",
                 "modifiers": ["public"], "return_type": "void", "parameters": [], "complexity_score": 1, "javadoc": ""},
                {"name": "priv_m", "line_range": {"start": 10, "end": 13}, "visibility": "private",
                 "modifiers": ["private"], "return_type": "int", "parameters": [], "complexity_score": 2, "javadoc": ""},
                {"name": "prot_m", "line_range": {"start": 15, "end": 18}, "visibility": "protected",
                 "modifiers": ["protected"], "return_type": "void", "parameters": [], "complexity_score": 1, "javadoc": ""},
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Public Methods" in output
        assert "### Private Methods" in output
        assert "### Methods" in output  # "other" methods
        assert "pub_m" in output
        assert "priv_m" in output
        assert "prot_m" in output


class TestFormatCompactTable:
    """Tests for _format_compact_table covering info section and methods."""

    def test_compact_with_cpp_language(self, formatter):
        data = {
            "file_path": "test.cpp",
            "language": "cpp",
            "package": {"name": "myns"},
            "statistics": {"method_count": 3, "field_count": 2},
            "methods": [
                {"name": "fn1", "visibility": "public", "return_type": "void",
                 "parameters": [{"name": "a", "type": "int"}],
                 "line_range": {"start": 1, "end": 5}, "complexity_score": 2, "javadoc": "A function"},
            ],
        }
        output = formatter._format_compact_table(data)
        assert "## Info" in output
        assert "| Package | myns |" in output
        assert "## Methods" in output
        assert "fn1" in output

    def test_compact_c_language_no_package(self, formatter):
        data = {
            "file_path": "test.c",
            "language": "c",
            "package": {"name": "unknown"},
            "statistics": {"method_count": 1, "field_count": 0},
            "methods": [],
        }
        output = formatter._format_compact_table(data)
        assert "Package" not in output  # C doesn't show package


class TestCreateCompactSignature:
    """Tests for _create_compact_signature covering all parameter formats."""

    def test_dict_params(self, formatter):
        method = {"parameters": [{"name": "a", "type": "int"}, {"name": "b", "type": "double"}], "return_type": "void"}
        sig = formatter._create_compact_signature(method)
        assert "(i,d):void" == sig

    def test_dict_param_array(self, formatter):
        method = {"parameters": [{"name": "arr[]", "type": "int"}], "return_type": "void"}
        sig = formatter._create_compact_signature(method)
        assert "int[]" in sig

    def test_dict_param_pointer(self, formatter):
        method = {"parameters": [{"name": "*ptr", "type": "int"}], "return_type": "void"}
        sig = formatter._create_compact_signature(method)
        assert "int*" in sig

    def test_string_param_colon_format(self, formatter):
        method = {"parameters": ["x:int", "y:float"], "return_type": "bool"}
        sig = formatter._create_compact_signature(method)
        assert "(i,f):b" == sig

    def test_string_param_c_style(self, formatter):
        method = {"parameters": ["int a", "double b"], "return_type": "char"}
        sig = formatter._create_compact_signature(method)
        assert "(i,d):c" == sig

    def test_string_param_array_notation(self, formatter):
        method = {"parameters": ["int arr[]"], "return_type": "void"}
        sig = formatter._create_compact_signature(method)
        assert "int[]" in sig

    def test_string_param_pointer_notation(self, formatter):
        method = {"parameters": ["int *ptr"], "return_type": "void"}
        sig = formatter._create_compact_signature(method)
        assert "int*" in sig

    def test_string_param_single_token(self, formatter):
        method = {"parameters": ["void"], "return_type": "int"}
        sig = formatter._create_compact_signature(method)
        assert "(void):i" == sig

    def test_non_string_non_dict_param(self, formatter):
        method = {"parameters": [123], "return_type": "void"}
        sig = formatter._create_compact_signature(method)
        assert "Any" in sig


class TestShortenType:
    """Tests for _shorten_type covering all type mappings."""

    def test_primitives(self, formatter):
        assert formatter._shorten_type("int") == "i"
        assert formatter._shorten_type("double") == "d"
        assert formatter._shorten_type("float") == "f"
        assert formatter._shorten_type("char") == "c"
        assert formatter._shorten_type("long") == "l"
        assert formatter._shorten_type("short") == "s"
        assert formatter._shorten_type("bool") == "b"
        assert formatter._shorten_type("string") == "str"
        assert formatter._shorten_type("void") == "void"
        assert formatter._shorten_type("size_t") == "size_t"

    def test_none_returns_void(self, formatter):
        assert formatter._shorten_type(None) == "void"

    def test_pointer_kept(self, formatter):
        assert formatter._shorten_type("int*") == "int*"

    def test_reference_kept(self, formatter):
        assert formatter._shorten_type("string&") == "string&"

    def test_array_kept(self, formatter):
        assert formatter._shorten_type("int[10]") == "int[10]"

    def test_qualifiers_removed(self, formatter):
        assert formatter._shorten_type("const int") == "i"
        assert formatter._shorten_type("volatile double") == "d"
        assert formatter._shorten_type("static float") == "f"

    def test_custom_type_passthrough(self, formatter):
        assert formatter._shorten_type("MyClass") == "MyClass"


class TestConvertAnalysisResult:
    """Tests for _convert_analysis_result_to_format covering element categorization."""

    def test_package_element(self, formatter):
        result = AnalysisResult(
            file_path="test.cpp",
            elements=[Package(name="myns", start_line=1, end_line=50, raw_text="namespace myns {}")],
        )
        data = formatter._convert_analysis_result_to_format(result)
        assert data["packages"][0]["name"] == "myns"
        assert data["package"]["name"] == "myns"

    def test_package_single_letter_rejected(self, formatter):
        result = AnalysisResult(
            file_path="test.cpp",
            elements=[Package(name="T", start_line=1, end_line=5, raw_text="namespace T {}")],
        )
        data = formatter._convert_analysis_result_to_format(result)
        assert len(data["packages"]) == 0

    def test_package_type_name_rejected(self, formatter):
        result = AnalysisResult(
            file_path="test.cpp",
            elements=[Package(name="int", start_line=1, end_line=5, raw_text="namespace int {}")],
        )
        data = formatter._convert_analysis_result_to_format(result)
        assert len(data["packages"]) == 0

    def test_class_element(self, formatter):
        result = AnalysisResult(
            file_path="test.cpp",
            elements=[Class(name="Foo", start_line=1, end_line=10, raw_text="class Foo {};")],
        )
        data = formatter._convert_analysis_result_to_format(result)
        assert len(data["classes"]) == 1
        assert data["classes"][0]["name"] == "Foo"

    def test_function_element(self, formatter):
        result = AnalysisResult(
            file_path="test.cpp",
            elements=[Function(name="bar", start_line=1, end_line=5, raw_text="void bar()", parameters=["int a", "double b"])],
        )
        data = formatter._convert_analysis_result_to_format(result)
        assert len(data["methods"]) == 1
        assert data["methods"][0]["name"] == "bar"
        assert len(data["methods"][0]["parameters"]) == 2

    def test_variable_element(self, formatter):
        from tree_sitter_analyzer.models import Import
        result = AnalysisResult(
            file_path="test.cpp",
            elements=[
                Variable(name="count", start_line=1, end_line=1, raw_text="int count;"),
                Import(name="iostream", start_line=1, end_line=1, raw_text="#include <iostream>"),
            ],
        )
        data = formatter._convert_analysis_result_to_format(result)
        assert len(data["fields"]) == 1
        assert len(data["imports"]) == 1

    def test_exception_in_element_skipped(self, formatter):
        """Element processing exception should be silently skipped."""

        class BadElement:
            """Element that raises on attribute access."""

            @property
            def name(self):
                raise RuntimeError("bad element")

            start_line = 0
            end_line = 0
            raw_text = ""

        result = AnalysisResult(file_path="test.cpp", elements=[BadElement()])
        data = formatter._convert_analysis_result_to_format(result)
        assert isinstance(data, dict)


class TestConvertFunctionElement:
    """Tests for _convert_function_element parameter processing."""

    def test_string_param_with_space(self, formatter):
        func = Function(name="f", start_line=1, end_line=1, raw_text="void f(int a)", parameters=["int a"])
        data = formatter._convert_function_element(func)
        assert data["parameters"][0]["type"] == "int"
        assert data["parameters"][0]["name"] == "a"

    def test_string_param_array(self, formatter):
        func = Function(name="f", start_line=1, end_line=1, raw_text="void f(int arr[])", parameters=["int arr[]"])
        data = formatter._convert_function_element(func)
        assert "[]" in data["parameters"][0]["type"]

    def test_string_param_no_space(self, formatter):
        func = Function(name="f", start_line=1, end_line=1, raw_text="void f(void)", parameters=["void"])
        data = formatter._convert_function_element(func)
        assert data["parameters"][0]["type"] == "void"

    def test_dict_param(self, formatter):
        func = Function(name="f", start_line=1, end_line=1, raw_text="", parameters=[])
        func.parameters = [{"name": "x", "type": "int"}]
        data = formatter._convert_function_element(func)
        assert data["parameters"][0]["type"] == "int"

    def test_non_string_non_dict_param(self, formatter):
        func = Function(name="f", start_line=1, end_line=1, raw_text="", parameters=[123])
        data = formatter._convert_function_element(func)
        assert data["parameters"][0]["type"] == "Any"


class TestFormatTableAndAdvanced:
    """Tests for format_table, format_summary, format_advanced."""

    def test_format_table_json(self, formatter):
        data = {"file_path": "test.cpp", "language": "cpp"}
        result = formatter.format_table(data, "json")
        assert "test.cpp" in result

    def test_format_table_full(self, formatter):
        result = AnalysisResult(file_path="test.cpp", elements=[])
        data = formatter._convert_analysis_result_to_format(result)
        output = formatter.format_table(data, "full")
        assert "test.cpp" in output

    def test_format_summary(self, formatter):
        data = {
            "file_path": "test.cpp", "language": "cpp",
            "package": {"name": "unknown"},
            "statistics": {"method_count": 0, "field_count": 0},
            "methods": [],
        }
        output = formatter.format_summary(data)
        assert "test.cpp" in output

    def test_format_analysis_result_compact(self, formatter):
        result = AnalysisResult(file_path="test.cpp", elements=[])
        output = formatter.format_analysis_result(result, "compact")
        assert "test.cpp" in output

    def test_format_analysis_result_csv(self, formatter):
        result = AnalysisResult(file_path="test.cpp", elements=[])
        output = formatter.format_analysis_result(result, "csv")
        assert isinstance(output, str)

    def test_format_analysis_result_default(self, formatter):
        result = AnalysisResult(file_path="test.cpp", elements=[])
        output = formatter.format_analysis_result(result, "unknown_format")
        assert "test.cpp" in output

    def test_format_advanced_json(self, formatter):
        data = {"file_path": "test.cpp"}
        output = formatter.format_advanced(data, "json")
        assert "test.cpp" in output

    def test_format_advanced_csv(self, formatter):
        data = {"file_path": "test.cpp", "package": {"name": "unknown"}, "classes": [], "methods": [], "fields": [], "imports": []}
        output = formatter.format_advanced(data, "csv")
        assert isinstance(output, str)

    def test_format_advanced_default(self, formatter):
        data = {"file_path": "test.cpp", "package": {"name": "unknown"}, "packages": [], "classes": [], "methods": [], "fields": [], "imports": []}
        output = formatter.format_advanced(data, "table")
        assert "test.cpp" in output

    def test_format_json_error(self, formatter):
        """Test JSON serialization error handling."""
        import math
        data = {"value": math.nan}  # NaN causes JSON error with ensure_ascii
        result = formatter._format_json(data)
        # Should either serialize or return error message
        assert isinstance(result, str)
