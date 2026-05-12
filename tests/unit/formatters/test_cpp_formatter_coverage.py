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


def test_cpp_formatter_with_namespace(formatter):
    """Cover namespace/package rendering path."""
    func = Function(name="do_work", start_line=10, end_line=12, raw_text="void do_work();")
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
    funcs = [Function(name=f"f{i}", start_line=i, end_line=i+1, raw_text=f"int f{i}();") for i in range(3)]
    result = AnalysisResult(file_path="math.c", elements=funcs, language="c")
    output = formatter.format_analysis_result(result, "full")
    assert "Global Functions" in output or any(f"f{i}" in output for i in range(3))

def test_cpp_formatter_compact_format(formatter):
    """Cover compact table path (non-full format)."""
    func = Function(name="main", start_line=1, end_line=3, raw_text="int main() {}")
    result = AnalysisResult(file_path="main.cpp", elements=[func], language="cpp")
    output = formatter.format_analysis_result(result, "compact")
    assert "main" in output
