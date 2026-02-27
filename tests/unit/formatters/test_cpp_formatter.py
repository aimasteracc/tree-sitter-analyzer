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
