"""Coverage boost tests for mcp/tools/utils/element_extractor.py."""

from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools.utils.element_extractor import (
    extract_elements,
    get_all_exports,
    get_classes,
    get_functions,
    get_functions_in_class,
    get_imports,
    get_structure,
)
from tree_sitter_analyzer.models import AnalysisResult, CodeElement


def _make_element(
    name="test",
    element_type="function",
    start_line=1,
    end_line=10,
    parameters=None,
    is_static=False,
    visibility="public",
    methods=None,
):
    e = MagicMock(spec=CodeElement)
    e.name = name
    e.element_type = element_type
    e.start_line = start_line
    e.end_line = end_line
    e.parameters = parameters or []
    e.is_static = is_static
    e.visibility = visibility
    e.methods = methods or []
    return e


def _make_result(elements):
    result = MagicMock(spec=AnalysisResult)
    result.elements = elements
    return result


class TestExtractElements:
    def test_unsupported_language_returns_none(self, tmp_path):
        f = tmp_path / "readme.txt"
        f.write_text("hello")
        assert extract_elements(str(f)) is None

    def test_binary_file_returns_none(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02")
        assert extract_elements(str(f)) is None

    def test_valid_python_file(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("def hello():\n    pass\n")
        result = extract_elements(str(f))
        if result is not None:
            assert result.elements is not None


class TestGetFunctions:
    def test_extracts_functions(self):
        elems = [
            _make_element("func_a", "function", 1, 5),
            _make_element("func_b", "function", 10, 20),
        ]
        result = _make_result(elems)
        funcs = get_functions(result)
        assert len(funcs) == 2
        assert funcs[0]["name"] == "func_a"
        assert funcs[0]["kind"] == "function"
        assert funcs[0]["lines"] == 5

    def test_skips_non_functions(self):
        elems = [
            _make_element("MyClass", "class", 1, 10),
            _make_element("func_a", "function", 15, 20),
        ]
        result = _make_result(elems)
        funcs = get_functions(result)
        assert len(funcs) == 1
        assert funcs[0]["name"] == "func_a"

    def test_empty_elements(self):
        result = _make_result([])
        assert get_functions(result) == []

    def test_function_attributes(self):
        elem = _make_element(
            "method",
            "function",
            5,
            15,
            parameters=["x", "y"],
            is_static=True,
            visibility="private",
        )
        result = _make_result([elem])
        funcs = get_functions(result)
        assert funcs[0]["parameters"] == ["x", "y"]
        assert funcs[0]["is_static"] is True
        assert funcs[0]["visibility"] == "private"
        assert funcs[0]["parent"] is None


class TestGetClasses:
    def test_extracts_classes_with_methods_attr(self):
        m1 = _make_element("method_a", "function", 3, 8)
        m2 = _make_element("method_b", "function", 10, 15)
        cls_elem = _make_element("MyClass", "class", 1, 20, methods=[m1, m2])
        result = _make_result([cls_elem])
        classes = get_classes(result)
        assert len(classes) == 1
        assert classes[0]["name"] == "MyClass"
        assert classes[0]["method_count"] == 2
        assert "method_a" in classes[0]["method_names"]

    def test_class_without_methods_computes_from_line_range(self):
        func1 = _make_element("m1", "function", 3, 8)
        func2 = _make_element("m2", "function", 10, 15)
        outer_func = _make_element("outer", "function", 25, 30)
        cls_elem = _make_element("MyClass", "class", 1, 20, methods=[])
        result = _make_result([func1, func2, outer_func, cls_elem])
        classes = get_classes(result)
        assert len(classes) == 1
        assert classes[0]["method_count"] == 2
        assert "m1" in classes[0]["method_names"]
        assert "m2" in classes[0]["method_names"]

    def test_no_classes(self):
        elems = [_make_element("func", "function", 1, 5)]
        result = _make_result(elems)
        assert get_classes(result) == []


class TestGetImports:
    def test_extracts_imports(self):
        elems = [
            _make_element("os", "import", 1, 1),
            _make_element("sys", "import", 2, 2),
            _make_element("func", "function", 4, 10),
        ]
        result = _make_result(elems)
        imports = get_imports(result)
        assert imports == ["os", "sys"]

    def test_no_imports(self):
        elems = [_make_element("func", "function", 1, 5)]
        result = _make_result(elems)
        assert get_imports(result) == []


class TestGetAllExports:
    def test_exports_classes_functions_constants(self):
        elems = [
            _make_element(
                "MyClass",
                "class",
                1,
                10,
                methods=[_make_element("m", "function", 2, 5)],
            ),
            _make_element("public_func", "function", 15, 20),
            _make_element("_private_func", "function", 22, 25),
            _make_element("MAX_SIZE", "variable", 12, 12),
            _make_element("regular_var", "variable", 13, 13),
        ]
        result = _make_result(elems)
        exports = get_all_exports(result)
        names = [e["name"] for e in exports]
        assert "MyClass" in names
        assert "public_func" in names
        assert "_private_func" not in names
        assert "MAX_SIZE" in names
        assert "regular_var" not in names

    def test_class_export_has_method_count(self):
        m = _make_element("m1", "function", 3, 5)
        cls = _make_element("MyClass", "class", 1, 10, methods=[m])
        result = _make_result([cls])
        exports = get_all_exports(result)
        assert exports[0]["methods"] == 1

    def test_empty(self):
        result = _make_result([])
        assert get_all_exports(result) == []


class TestGetStructure:
    def test_extracts_structure(self):
        elems = [
            _make_element("MyClass", "class", 1, 50),
            _make_element("func_a", "function", 55, 60),
            _make_element("os", "import", 0, 0),
        ]
        result = _make_result(elems)
        structure = get_structure(result)
        assert len(structure) == 2
        assert structure[0]["kind"] == "class"
        assert structure[1]["kind"] == "function"

    def test_truncates_at_30(self):
        elems = [_make_element(f"func_{i}", "function", i, i + 1) for i in range(50)]
        result = _make_result(elems)
        structure = get_structure(result)
        assert len(structure) == 30

    def test_empty(self):
        result = _make_result([])
        assert get_structure(result) == []


class TestGetFunctionsInClass:
    def test_finds_class_methods(self):
        m1 = _make_element("m1", "function", 3, 8)
        m2 = _make_element("m2", "function", 10, 15)
        cls = _make_element("MyClass", "class", 1, 20, methods=[m1, m2])
        result = _make_result([cls])
        funcs = get_functions_in_class(result, "MyClass")
        assert len(funcs) == 2
        assert funcs[0]["name"] == "m1"

    def test_class_not_found(self):
        cls = _make_element("OtherClass", "class", 1, 10, methods=[])
        result = _make_result([cls])
        assert get_functions_in_class(result, "MyClass") == []

    def test_method_attributes(self):
        m = _make_element("m1", "function", 3, 8)
        m.is_static = True
        cls = _make_element("MyClass", "class", 1, 20, methods=[m])
        result = _make_result([cls])
        funcs = get_functions_in_class(result, "MyClass")
        assert funcs[0]["is_static"] is True
        assert funcs[0]["lines"] == 6
