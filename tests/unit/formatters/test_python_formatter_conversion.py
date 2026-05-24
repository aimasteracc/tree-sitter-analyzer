"""Tests for formatters._python_formatter_conversion — element conversion helpers."""

from dataclasses import dataclass

from tree_sitter_analyzer.constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
)
from tree_sitter_analyzer.formatters._python_formatter_conversion import (
    convert_analysis_result_to_python_format,
    convert_class_element_for_python,
    convert_function_element_for_python,
    convert_import_element_for_python,
    convert_variable_element_for_python,
    process_python_parameters,
)


@dataclass
class FakeElement:
    name: str = "test"
    element_type: str = "function"
    start_line: int = 1
    end_line: int = 5
    raw_text: str = ""
    parameters: list | str | None = None
    return_type: str = "None"
    visibility: str = "public"
    is_constructor: bool = False
    is_static: bool = False
    is_async: bool = False
    complexity_score: int = 1
    docstring: str = ""
    decorators: list | None = None
    modifiers: list | None = None
    variable_type: str = ""
    field_type: str = ""
    class_type: str = "class"
    module_name: str = ""


@dataclass
class FakeAnalysisResult:
    file_path: str = "test.py"
    language: str = "python"
    line_count: int = 50
    elements: list | None = None


class FakeFormatter:
    def _convert_class_element_for_python(self, element):
        return convert_class_element_for_python(element)

    def _convert_function_element_for_python(self, element):
        return convert_function_element_for_python(self, element)

    def _convert_variable_element_for_python(self, element):
        return convert_variable_element_for_python(element)

    def _convert_import_element_for_python(self, element):
        return convert_import_element_for_python(element)

    def _process_python_parameters(self, params):
        return process_python_parameters(params)


def _make_element(**kwargs):
    return FakeElement(**kwargs)


class TestConvertAnalysisResultToPythonFormat:
    def test_empty_elements(self):
        result_obj = FakeAnalysisResult(elements=[])
        formatter = FakeFormatter()
        result = convert_analysis_result_to_python_format(formatter, result_obj)
        assert result["file_path"] == "test.py"
        assert result["language"] == "python"
        assert result["statistics"]["method_count"] == 0
        assert result["package"]["name"] == "unknown"

    def test_mixed_element_types(self):
        elements = [
            _make_element(element_type=ELEMENT_TYPE_PACKAGE, name="mypackage"),
            _make_element(element_type=ELEMENT_TYPE_CLASS, name="MyClass"),
            _make_element(element_type=ELEMENT_TYPE_FUNCTION, name="my_func"),
            _make_element(element_type=ELEMENT_TYPE_VARIABLE, name="x"),
            _make_element(element_type=ELEMENT_TYPE_IMPORT, name="os"),
        ]
        result_obj = FakeAnalysisResult(elements=elements)
        formatter = FakeFormatter()
        result = convert_analysis_result_to_python_format(formatter, result_obj)
        assert result["package"]["name"] == "mypackage"
        assert len(result["classes"]) == 1
        assert len(result["methods"]) == 1
        assert len(result["fields"]) == 1
        assert len(result["imports"]) == 1


class TestConvertClassElementForPython:
    def test_basic_class(self):
        el = _make_element(element_type=ELEMENT_TYPE_CLASS, name="Foo")
        result = convert_class_element_for_python(el)
        assert result["name"] == "Foo"
        assert result["type"] == "class"
        assert result["visibility"] == "public"

    def test_class_with_no_name(self):
        el = _make_element(element_type=ELEMENT_TYPE_CLASS, name=None)
        result = convert_class_element_for_python(el)
        assert result["name"] == "UnknownClass"


class TestConvertFunctionElementForPython:
    def test_basic_function(self):
        formatter = FakeFormatter()
        el = _make_element(
            element_type=ELEMENT_TYPE_FUNCTION, name="do_stuff", parameters=[]
        )
        result = convert_function_element_for_python(formatter, el)
        assert result["name"] == "do_stuff"
        assert result["is_async"] is False

    def test_async_function_with_params(self):
        formatter = FakeFormatter()
        el = _make_element(
            element_type=ELEMENT_TYPE_FUNCTION,
            name="fetch",
            parameters=["url: str", "timeout: int"],
            is_async=True,
            docstring="Fetch data",
        )
        result = convert_function_element_for_python(formatter, el)
        assert result["is_async"] is True
        assert result["docstring"] == "Fetch data"
        assert len(result["parameters"]) == 2


class TestConvertVariableElementForPython:
    def test_basic_variable(self):
        el = _make_element(
            element_type=ELEMENT_TYPE_VARIABLE, name="count", variable_type="int"
        )
        result = convert_variable_element_for_python(el)
        assert result["name"] == "count"
        assert result["type"] == "int"

    def test_variable_with_field_type_fallback(self):
        el = _make_element(
            element_type=ELEMENT_TYPE_VARIABLE,
            name="data",
            variable_type="",
            field_type="str",
        )
        result = convert_variable_element_for_python(el)
        assert result["type"] == "str"


class TestConvertImportElementForPython:
    def test_import_with_raw_text(self):
        el = _make_element(element_type=ELEMENT_TYPE_IMPORT, raw_text="import os.path")
        result = convert_import_element_for_python(el)
        assert result["statement"] == "import os.path"

    def test_import_without_raw_text(self):
        el = _make_element(element_type=ELEMENT_TYPE_IMPORT, name="os", raw_text="")
        result = convert_import_element_for_python(el)
        assert result["statement"] == "import os"


class TestProcessPythonParameters:
    def test_string_params(self):
        result = process_python_parameters("a, b, c")
        assert len(result) == 3
        assert result[0] == {"name": "a", "type": "Any"}

    def test_empty_string(self):
        result = process_python_parameters("  ")
        assert result == []

    def test_list_of_strings(self):
        result = process_python_parameters(["x: int", "y"])
        assert result[0] == {"name": "x", "type": "int"}
        assert result[1] == {"name": "y", "type": "Any"}

    def test_list_of_dicts(self):
        params = [{"name": "a", "type": "int"}]
        result = process_python_parameters(params)
        assert result == params

    def test_unknown_type_returns_any(self):
        result = process_python_parameters([42])
        assert result == [{"name": "42", "type": "Any"}]

    def test_non_string_non_list_returns_empty(self):
        result = process_python_parameters(42)
        assert result == []
