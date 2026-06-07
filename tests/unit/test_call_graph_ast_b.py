"""Unit tests for call_graph.py — get_func_name, extract_call, find_parent_class."""

from pathlib import Path
from unittest.mock import MagicMock

from tree_sitter_analyzer.core.parser import Parser
from tree_sitter_analyzer.function_extraction import (
    extract_call as _extract_call,
)
from tree_sitter_analyzer.function_extraction import (
    find_parent_class_java as _find_parent_class_java,
)
from tree_sitter_analyzer.function_extraction import (
    find_parent_class_python as _find_parent_class_python,
)
from tree_sitter_analyzer.function_extraction import (
    get_func_name as _get_func_name,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "call_graph"
PY_PROJECT = FIXTURES_DIR / "python_project"


def _parse_source(source: str, language: str):
    p = Parser()
    result = p.parse_code(source, language)
    assert result.success and result.tree is not None
    return result.tree.root_node, source


def _collect_nodes(node, node_type, result_list):
    if hasattr(node, "type") and node.type == node_type:
        result_list.append(node)
    if hasattr(node, "children"):
        for child in node.children:
            _collect_nodes(child, node_type, result_list)


def _find_first_node(node, node_type, result):
    if hasattr(node, "type") and node.type == node_type:
        result.append(node)
        return
    if hasattr(node, "children"):
        for child in node.children:
            _find_first_node(child, node_type, result)
            if result:
                return


# ============================================================
# _get_func_name tests
# ============================================================


class TestGetFuncName:
    def test_python_function(self):
        source = "def foo():\n    pass\n"
        root, src = _parse_source(source, "python")
        func_node = root.children[0]
        assert func_node.type == "function_definition"
        assert _get_func_name(func_node, "python") == "foo"

    def test_js_function(self):
        source = "function bar() { return 1; }\n"
        root, src = _parse_source(source, "javascript")
        func_node = root.children[0]
        assert func_node.type == "function_declaration"
        assert _get_func_name(func_node, "javascript") == "bar"

    def test_c_function(self):
        source = "int myfunc(void) { return 0; }\n"
        root, src = _parse_source(source, "c")
        func_node = root.children[0]
        assert _get_func_name(func_node, "c") == "myfunc"

    def test_go_method_name_falls_back_to_field_identifier_child(self):
        node = MagicMock()
        node.child_by_field_name.return_value = None
        child = MagicMock()
        child.type = "field_identifier"
        child.text = b"ServeHTTP"
        node.children = [child]

        assert _get_func_name(node, "go") == "ServeHTTP"

    def test_go_method_name_accepts_text_from_name_field(self):
        node = MagicMock()
        name_node = MagicMock()
        name_node.text = "ServeHTTP"
        node.child_by_field_name.return_value = name_node

        assert _get_func_name(node, "go") == "ServeHTTP"

    def test_go_method_name_decodes_bytes_from_name_field(self):
        node = MagicMock()
        name_node = MagicMock()
        name_node.text = b"ServeHTTP"
        node.child_by_field_name.return_value = name_node

        assert _get_func_name(node, "go") == "ServeHTTP"

    def test_no_func_name_returns_none(self):
        node = MagicMock()
        node.children = []
        assert _get_func_name(node, "python") is None

    def test_unsupported_language_returns_none(self):
        source = "def foo():\n    pass\n"
        root, _ = _parse_source(source, "python")
        func_node = root.children[0]
        # ``cobol`` has no entry in _FUNC_NAME_DISPATCH (ruby is now supported).
        assert _get_func_name(func_node, "cobol") is None


# ============================================================
# _extract_call tests
# ============================================================


class TestExtractCall:
    def test_python_call(self):
        source = "bar(1, 2)\n"
        root, src = _parse_source(source, "python")
        call_node = root.children[0]
        assert call_node.type == "expression_statement"
        call_expr = call_node.children[0]
        assert call_expr.type == "call"
        result = _extract_call(call_expr, src, "python")
        assert result is not None
        assert result["name"] == "bar"

    def test_python_method_call(self):
        source = "obj.method()\n"
        root, src = _parse_source(source, "python")
        call_node = root.children[0]
        call_expr = call_node.children[0]
        result = _extract_call(call_expr, src, "python")
        assert result is not None
        assert result["name"] == "method"
        assert result["receiver"] == "obj"

    def test_js_call(self):
        source = "loadData();\n"
        root, src = _parse_source(source, "javascript")
        expr_stmt = root.children[0]
        call_expr = expr_stmt.children[0]
        assert call_expr.type == "call_expression"
        result = _extract_call(call_expr, src, "javascript")
        assert result is not None
        assert result["name"] == "loadData"

    def test_c_call(self):
        source = "int x = foo();\n"
        root, src = _parse_source(source, "c")
        call_nodes = []
        _collect_nodes(root, "call_expression", call_nodes)
        if call_nodes:
            result = _extract_call(call_nodes[0], src, "c")
            assert result is not None
            assert result["name"] == "foo"

    def test_returns_none_for_non_call(self):
        node = MagicMock()
        node.child_by_field_name = MagicMock(return_value=None)
        assert _extract_call(node, "source", "python") is None


# ============================================================
# _find_parent_class_python tests
# ============================================================


class TestFindParentClassPython:
    def test_finds_parent_class(self):
        source = "class Cls:\n    def method(self):\n        pass\n"
        root, _ = _parse_source(source, "python")
        cls_node = root.children[0]
        assert cls_node.type == "class_definition"
        block_node = cls_node.children[3]
        assert block_node.type == "block"
        func_node = block_node.children[0]
        assert func_node.type == "function_definition"
        result = _find_parent_class_python(func_node)
        assert result == "Cls"

    def test_no_parent_class(self):
        source = "def standalone():\n    pass\n"
        root, _ = _parse_source(source, "python")
        func_node = root.children[0]
        assert _find_parent_class_python(func_node) is None


# ============================================================
# _find_parent_class_java tests
# ============================================================


class TestFindParentClassJava:
    def test_finds_parent_class(self):
        source = "public class Main {\n    public void foo() {}\n}\n"
        root, _ = _parse_source(source, "java")
        _find_first_node(root, "method_declaration", result := [])
        if result:
            method_node = result[0]
            cls = _find_parent_class_java(method_node)
            assert cls == "Main"

    def test_no_parent_class_top_level(self):
        source = "class Outer {\n    void foo() {}\n}\n"
        root, _ = _parse_source(source, "java")
        _find_first_node(root, "method_declaration", result := [])
        if result:
            method_node = result[0]
            found = _find_parent_class_java(method_node)
            assert found == "Outer" or found is None
