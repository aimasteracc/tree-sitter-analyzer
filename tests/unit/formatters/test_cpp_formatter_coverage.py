import pytest

from tree_sitter_analyzer.formatters.cpp_formatter import CppTableFormatter
from tree_sitter_analyzer.models import (
    AnalysisResult,
    Class,
    Function,
    Import,
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


def test_cpp_formatter_with_namespace(formatter):
    """Cover namespace/package rendering path."""
    func = Function(
        name="do_work", start_line=10, end_line=12, raw_text="void do_work();"
    )
    cls = Class(name="Helper", start_line=1, end_line=8, raw_text="class Helper {};")
    result = AnalysisResult(
        file_path="src/main.cpp",
        elements=[cls, func],
        language="cpp",
    )
    output = formatter.format_analysis_result(result, "full")
    assert "Helper" in output
    assert "do_work" in output


def test_cpp_formatter_global_functions_only(formatter):
    """Cover pure C-style global functions (no classes)."""
    funcs = [
        Function(name=f"f{i}", start_line=i, end_line=i + 1, raw_text=f"int f{i}();")
        for i in range(3)
    ]
    result = AnalysisResult(file_path="math.c", elements=funcs, language="c")
    output = formatter.format_analysis_result(result, "full")
    assert "Global Functions" in output or any(f"f{i}" in output for i in range(3))


def test_cpp_formatter_compact_format(formatter):
    """Cover compact table path (non-full format)."""
    func = Function(name="main", start_line=1, end_line=3, raw_text="int main() {}")
    result = AnalysisResult(file_path="main.cpp", elements=[func], language="cpp")
    output = formatter.format_analysis_result(result, "compact")
    assert "main" in output


# ============================================================
# Coverage expansion tests — targeting uncovered branches
# ============================================================

# --- packages list → Namespaces section (line 44) ---


def test_packages_list_renders_namespaces_section(formatter):
    """Cover the `packages` list path at line 44."""
    packages = [
        {"name": "std", "line_range": {"start": 1, "end": 10}},
        {"name": "detail", "line_range": {"start": 11, "end": 20}},
    ]
    func = Function(name="f", start_line=21, end_line=22, raw_text="void f();")
    result = AnalysisResult(file_path="ns.cpp", elements=[func], language="cpp")
    # Pre-format via internal path: packages list
    formatted = formatter._convert_analysis_result_to_format(result)
    formatted["packages"] = packages
    output = formatter._format_full_table(formatted)
    assert "## Namespaces" in output
    assert "std" in output
    assert "detail" in output


# --- single package → Package section (line 45-47) ---


def test_single_package_renders_package_section(formatter):
    """Cover the elif branch for single package_name."""
    pkg = Package(name="myapp", start_line=1, end_line=5, raw_text="namespace myapp {}")
    func = Function(name="init", start_line=6, end_line=7, raw_text="void init();")
    result = AnalysisResult(file_path="pkg.cpp", elements=[pkg, func], language="cpp")
    formatted = formatter._convert_analysis_result_to_format(result)
    # Ensure packages is empty so we hit elif package_name
    formatted["packages"] = []
    output = formatter._format_full_table(formatted)
    assert "## Package" in output
    assert "myapp" in output


# --- imports section (lines 52-59) ---


def test_imports_section_rendered(formatter):
    """Cover imports rendering at lines 52-59."""
    imp = Import(
        name="stdio.h",
        start_line=1,
        end_line=1,
        raw_text="#include <stdio.h>",
        module_name="stdio",
    )
    func = Function(name="main", start_line=3, end_line=5, raw_text="int main() {}")
    result = AnalysisResult(file_path="main.c", elements=[imp, func], language="c")
    output = formatter.format_analysis_result(result, "full")
    assert "## Imports" in output
    assert "#include <stdio.h>" in output


# --- global fields not inside classes (lines 129-153) ---


def test_global_fields_rendered(formatter):
    """Cover global variables table at lines 129-153."""
    var = Variable(
        name="global_counter",
        start_line=1,
        end_line=1,
        raw_text="int global_counter = 0;",
        variable_type="int",
        visibility="public",
    )
    func = Function(name="inc", start_line=3, end_line=4, raw_text="void inc();")
    result = AnalysisResult(file_path="glob.cpp", elements=[var, func], language="cpp")
    output = formatter.format_analysis_result(result, "full")
    assert "## Global Variables" in output
    assert "global_counter" in output


# --- _create_compact_signature: string param formats ---


def test_compact_signature_string_params(formatter):
    """Cover _create_compact_signature branches for string-format params."""
    # Dict format already covered; test string formats:
    # "name:type" format
    method_colon = {
        "name": "f1",
        "parameters": ["a:int", "b:float"],
        "return_type": "void",
    }
    sig = formatter._create_compact_signature(method_colon)
    assert "i" in sig or "int" in sig
    assert "f" in sig or "float" in sig
    assert ":void" in sig

    # C-style "type name" with array notation
    method_arr = {
        "name": "f2",
        "parameters": ["int arr[]", "char buf[]"],
        "return_type": "int",
    }
    sig = formatter._create_compact_signature(method_arr)
    assert "[]" in sig  # array notation preserved

    # Pointer notation: "int *ptr"
    method_ptr = {
        "name": "f3",
        "parameters": ["int *ptr", "char *str"],
        "return_type": "void",
    }
    sig = formatter._create_compact_signature(method_ptr)
    assert "*" in sig

    # Single token (type-only, e.g. "void")
    method_single = {
        "name": "f4",
        "parameters": ["void"],
        "return_type": "void",
    }
    sig = formatter._create_compact_signature(method_single)
    assert "void" in sig.lower()


# --- _shorten_type edge cases ---


def test_shorten_type_none(formatter):
    """Cover _shorten_type → None path."""
    assert formatter._shorten_type(None) == "void"


def test_shorten_type_pointers_and_arrays(formatter):
    """Cover _shorten_type pointer/ref/array early return."""
    assert formatter._shorten_type("int*") == "int*"
    assert formatter._shorten_type("int&") == "int&"
    assert formatter._shorten_type("int[]") == "int[]"


def test_shorten_type_qualifier_removal(formatter):
    """Cover _shorten_type const/volatile/static stripping."""
    assert formatter._shorten_type("const int") == "i"
    assert formatter._shorten_type("volatile int") == "i"
    assert formatter._shorten_type("static double") == "d"


def test_shorten_type_map(formatter):
    """Cover _shorten_type type_map dict."""
    mapping = {
        "int": "i",
        "double": "d",
        "float": "f",
        "char": "c",
        "long": "l",
        "short": "s",
        "bool": "b",
        "size_t": "size_t",
        "string": "str",
    }
    for t, expected in mapping.items():
        assert formatter._shorten_type(t) == expected


def test_shorten_type_unknown_passthrough(formatter):
    """Non-primitive types pass through unchanged."""
    assert formatter._shorten_type("MyClass") == "MyClass"
    assert formatter._shorten_type("std::vector") == "std::vector"


# --- format_table: json path ---


def test_format_table_json(formatter):
    """Cover format_table with json type."""
    data = {
        "file_path": "t.cpp",
        "language": "cpp",
        "methods": [{"name": "f", "return_type": "void", "parameters": []}],
    }
    output = formatter.format_table(data, "json")
    assert '"file_path"' in output


# --- format_advanced: csv and full_table paths ---


def test_format_advanced_csv(formatter):
    """Cover format_advanced csv path."""
    data = {
        "file_path": "t.cpp",
        "language": "cpp",
        "methods": [{"name": "f", "return_type": "void", "parameters": []}],
    }
    output = formatter.format_advanced(data, "csv")
    assert output  # csv output produced


def test_format_advanced_full(formatter):
    """Cover format_advanced non-json, non-csv → _format_full_table path."""
    data = {
        "file_path": "t.cpp",
        "language": "cpp",
        "methods": [{"name": "f", "return_type": "void", "parameters": []}],
    }
    output = formatter.format_advanced(data, "full")
    assert output


# --- _convert_function_element: parameter formats ---


def test_convert_function_element_no_space_param(formatter):
    """Cover _convert_function_element with param string having no space."""
    func = Function(
        name="cb",
        start_line=1,
        end_line=1,
        raw_text="void cb();",
        parameters=["callback"],
        return_type="void",
    )
    result = AnalysisResult(file_path="cb.cpp", elements=[func], language="cpp")
    output = formatter.format_analysis_result(result, "full")
    assert "cb" in output


def test_convert_function_element_dict_param(formatter):
    """Cover _convert_function_element with dict-format param."""
    func = Function(
        name="handler",
        start_line=1,
        end_line=1,
        raw_text="void handler();",
        parameters=[{"name": "ev", "type": "Event"}],
        return_type="void",
    )
    result = AnalysisResult(file_path="handler.cpp", elements=[func], language="cpp")
    output = formatter.format_analysis_result(result, "full")
    assert "handler" in output


def test_convert_function_element_non_str_non_dict_param(formatter):
    """Cover _convert_function_element with else-branch (non-str, non-dict param)."""
    func = Function(
        name="weird",
        start_line=1,
        end_line=1,
        raw_text="void weird();",
        parameters=[42],  # non-str, non-dict
        return_type="void",
    )
    result = AnalysisResult(file_path="weird.cpp", elements=[func], language="cpp")
    output = formatter.format_analysis_result(result, "full")
    assert "weird" in output


# --- _convert_import_element: no raw_text fallback ---


def test_convert_import_no_raw_text(formatter):
    """Cover _convert_import_element when raw_text is empty."""
    imp = Import(
        name="vector",
        start_line=1,
        end_line=1,
        raw_text="",  # empty raw_text triggers fallback
        module_name="vector",
    )
    func = Function(name="main", start_line=3, end_line=5, raw_text="int main() {}")
    result = AnalysisResult(
        file_path="fallback.cpp", elements=[imp, func], language="cpp"
    )
    output = formatter.format_analysis_result(result, "full")
    # With empty raw_text, fallback generates "#include vector"
    assert "#include" in output


# --- format_summary (line 446-449) ---


def test_format_summary(formatter):
    """Cover format_summary method."""
    data = {
        "file_path": "t.cpp",
        "language": "cpp",
        "methods": [{"name": "f", "return_type": "void", "parameters": []}],
        "classes": [],
    }
    output = formatter.format_summary(data)
    assert "f" in output


# --- Other Methods section (lines 235-240, 243-248) ---
# Triggered when a method has visibility other than public/private


def test_other_methods_section(formatter):
    """Cover 'Other Methods' rendering for non-public, non-private methods."""
    cls = Class(
        name="Container",
        start_line=1,
        end_line=20,
        raw_text="class Container {};",
    )
    func = Function(
        name="helper",
        start_line=5,
        end_line=7,
        raw_text="void helper();",
        visibility="protected",
        is_public=False,
        is_private=False,
    )
    result = AnalysisResult(file_path="other.cpp", elements=[cls, func], language="cpp")
    output = formatter.format_analysis_result(result, "full")
    assert "### Methods" in output
    assert "helper" in output


# --- _create_compact_signature: dict param with pointer name (*ptr) ---


def test_compact_signature_dict_param_pointer(formatter):
    """Cover dict-format param where name starts with * (pointer)."""
    method = {
        "name": "f",
        "parameters": [{"name": "*ptr", "type": "int"}],
        "return_type": "void",
    }
    sig = formatter._create_compact_signature(method)
    assert "*" in sig


# --- _convert_function_element: string param with fallback ---


def test_convert_function_element_fallback_param(formatter):
    """Cover fallback when param_type or param_name is empty after split."""
    func = Function(
        name="fallback_func",
        start_line=1,
        end_line=1,
        raw_text="void fallback_func();",
        parameters=["  "],  # only spaces → both empty after strip
        return_type="void",
    )
    result = AnalysisResult(file_path="fb.cpp", elements=[func], language="cpp")
    output = formatter.format_analysis_result(result, "full")
    assert "fallback_func" in output


# --- Private Methods section (lines 235-240) ---


def test_private_methods_section(formatter):
    """Cover 'Private Methods' rendering in _format_class_details."""
    cls = Class(
        name="SecureBox",
        start_line=1,
        end_line=20,
        raw_text="class SecureBox {};",
    )
    func = Function(
        name="do_internal",
        start_line=5,
        end_line=7,
        raw_text="void do_internal();",
        visibility="private",
        is_public=False,
        is_private=True,
    )
    result = AnalysisResult(
        file_path="secure.cpp", elements=[cls, func], language="cpp"
    )
    output = formatter.format_analysis_result(result, "full")
    assert "### Private Methods" in output
    assert "do_internal" in output
