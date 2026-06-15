"""Unit tests for call_graph.py — FunctionRef, node_text, walk_tree."""

from pathlib import Path
from unittest.mock import MagicMock

from tree_sitter_analyzer.call_graph import (
    FunctionRef,
)
from tree_sitter_analyzer.core.parser import Parser
from tree_sitter_analyzer.function_extraction import (
    find_receiver_type_go as _find_receiver_type_go,
)
from tree_sitter_analyzer.function_extraction import (
    node_text as _node_text,
)
from tree_sitter_analyzer.function_extraction import (
    walk_tree as _walk_tree,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "call_graph"
PY_PROJECT = FIXTURES_DIR / "python_project"


def _parse_source(source: str, language: str):
    p = Parser()
    result = p.parse_code(source, language)
    assert result.success and result.tree is not None
    return result.tree.root_node, source


# ============================================================
# FunctionRef tests
# ============================================================


class TestFunctionRef:
    def test_basic_creation(self):
        ref = FunctionRef("main.py", "foo", 10, "python")
        assert ref.file_path == "main.py"
        assert ref.name == "foo"
        assert ref.start_line == 10
        assert ref.language == "python"
        assert ref.receiver is None

    def test_creation_with_receiver(self):
        ref = FunctionRef("main.py", "method", 5, "python", receiver="MyClass")
        assert ref.receiver == "MyClass"

    def test_qualified_name_without_receiver(self):
        ref = FunctionRef("main.py", "foo", 10, "python")
        assert ref.qualified_name() == "main.py:foo"

    def test_qualified_name_with_receiver(self):
        ref = FunctionRef("main.py", "method", 5, "python", receiver="MyClass")
        assert ref.qualified_name() == "main.py:MyClass.method"

    def test_equality_same_fields(self):
        a = FunctionRef("main.py", "foo", 10, "python")
        b = FunctionRef("main.py", "foo", 10, "python")
        assert a == b

    def test_equality_different_line(self):
        a = FunctionRef("main.py", "foo", 10, "python")
        b = FunctionRef("main.py", "foo", 20, "python")
        assert a != b

    def test_equality_different_name(self):
        a = FunctionRef("main.py", "foo", 10, "python")
        b = FunctionRef("main.py", "bar", 10, "python")
        assert a != b

    def test_equality_not_functionref(self):
        ref = FunctionRef("main.py", "foo", 10, "python")
        assert ref != "not a FunctionRef"
        assert ref.__eq__("string") is NotImplemented

    def test_hash_same_equal(self):
        a = FunctionRef("main.py", "foo", 10, "python")
        b = FunctionRef("main.py", "foo", 10, "python")
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    def test_hash_different(self):
        a = FunctionRef("main.py", "foo", 10, "python")
        b = FunctionRef("main.py", "bar", 10, "python")
        assert hash(a) != hash(b)

    def test_to_dict_no_receiver(self):
        ref = FunctionRef("main.py", "foo", 10, "python")
        d = ref.to_dict()
        assert d["file"] == "main.py"
        assert d["name"] == "foo"
        assert d["line"] == 10
        assert d["end_line"] == 10
        assert d["language"] == "python"
        assert "receiver" not in d

    def test_to_dict_with_receiver(self):
        ref = FunctionRef("main.py", "method", 5, "python", receiver="Cls")
        d = ref.to_dict()
        assert d["receiver"] == "Cls"

    def test_slots(self):
        ref = FunctionRef("a.py", "f", 1, "python")
        assert not hasattr(ref, "__dict__")


# ============================================================
# _node_text tests
# ============================================================


class TestNodeText:
    def test_extracts_text_from_node(self):
        source = "hello world"
        node = MagicMock()
        node.start_byte = 0
        node.end_byte = 5
        assert _node_text(node, source) == "hello"

    def test_extracts_text_from_middle(self):
        source = "hello world"
        node = MagicMock()
        node.start_byte = 6
        node.end_byte = 11
        assert _node_text(node, source) == "world"

    def test_fallback_to_text_attribute_bytes(self):
        node = MagicMock()
        node.start_byte = property(lambda s: (_ for _ in ()).throw(Exception("nope")))
        del node.start_byte
        node.text = b"fallback"
        assert _node_text(node, "source") == "fallback"

    def test_fallback_to_text_attribute_str(self):
        node = MagicMock()
        del node.start_byte
        node.text = "fallback"
        assert _node_text(node, "source") == "fallback"

    def test_fallback_to_text_attribute_unicode(self):
        node = MagicMock()
        del node.start_byte
        node.text = "日本語"
        assert _node_text(node, "src") == "日本語"


# ============================================================
# _walk_tree / _extract_recursive tests
# ============================================================


class TestWalkTree:
    def test_python_function_defs(self):
        source = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        root, src = _parse_source(source, "python")
        defs, calls = _walk_tree(root, src, "python")
        assert len(defs) == 2
        names = {d["name"] for d in defs}
        assert names == {"foo", "bar"}

    def test_python_class_method(self):
        source = "class Cls:\n    def method(self):\n        pass\n"
        root, src = _parse_source(source, "python")
        defs, calls = _walk_tree(root, src, "python")
        assert len(defs) == 1
        assert defs[0]["name"] == "method"
        assert defs[0]["class"] == "Cls"

    def test_python_calls(self):
        source = "def foo():\n    bar()\n    baz(1)\n"
        root, src = _parse_source(source, "python")
        defs, calls = _walk_tree(root, src, "python")
        assert len(defs) == 1
        assert len(calls) == 2
        names = {c["name"] for c in calls}
        assert names == {"bar", "baz"}

    def test_python_method_call(self):
        source = "def foo():\n    obj.method()\n"
        root, src = _parse_source(source, "python")
        defs, calls = _walk_tree(root, src, "python")
        assert len(calls) == 1
        assert calls[0]["name"] == "method"
        assert calls[0]["receiver"] == "obj"

    def test_python_nested_class(self):
        source = "class Outer:\n    class Inner:\n        def method(self):\n            pass\n"
        root, src = _parse_source(source, "python")
        defs, calls = _walk_tree(root, src, "python")
        assert len(defs) == 1
        assert defs[0]["class"] is not None

    def test_js_function_defs(self):
        source = "function foo() { return 1; }\nfunction bar() { return 2; }\n"
        root, src = _parse_source(source, "javascript")
        defs, calls = _walk_tree(root, src, "javascript")
        assert len(defs) == 2
        names = {d["name"] for d in defs}
        assert names == {"foo", "bar"}

    def test_js_calls(self):
        source = "function main() { loadData(); processData(); }\n"
        root, src = _parse_source(source, "javascript")
        defs, calls = _walk_tree(root, src, "javascript")
        assert len(defs) == 1
        assert len(calls) == 2

    def test_java_method_defs(self):
        source = (
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            "        foo();\n"
            "    }\n"
            "    private static void foo() {}\n"
            "}\n"
        )
        root, src = _parse_source(source, "java")
        defs, calls = _walk_tree(root, src, "java")
        assert len(defs) == 2
        names = {d["name"] for d in defs}
        assert names == {"main", "foo"}

    def test_go_function_defs(self):
        source = 'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println("hi")\n}\n\nfunc helper() int { return 1 }\n'
        root, src = _parse_source(source, "go")
        defs, calls = _walk_tree(root, src, "go")
        assert len(defs) == 2
        names = {d["name"] for d in defs}
        assert "main" in names
        assert "helper" in names

    def test_go_method_defs_and_selector_calls(self):
        source = (
            "package main\n\n"
            "type Engine struct{}\n\n"
            "func (engine *Engine) ServeHTTP() {\n"
            "\tengine.handleHTTPRequest()\n"
            "}\n\n"
            "func (engine *Engine) handleHTTPRequest() {}\n"
        )
        root, src = _parse_source(source, "go")
        defs, calls = _walk_tree(root, src, "go")

        assert {d["name"] for d in defs} == {"ServeHTTP", "handleHTTPRequest"}
        assert calls == [
            {
                "name": "handleHTTPRequest",
                "full_name": "engine.handleHTTPRequest",
                "line": 6,
                "col": 1,
                "receiver": "engine",
            }
        ]

    def test_go_method_receiver_type_extracted(self):
        source = (
            "package main\n\n"
            "type Engine struct{}\n\n"
            "func (e *Engine) ServeHTTP() {}\n"
            "func (e Engine) Handle() {}\n"
        )
        root, src = _parse_source(source, "go")
        defs, _ = _walk_tree(root, src, "go")
        serve = next(d for d in defs if d["name"] == "ServeHTTP")
        handle = next(d for d in defs if d["name"] == "Handle")
        assert serve["class"] == "Engine"
        assert handle["class"] == "Engine"

    def test_go_function_no_receiver(self):
        source = "package main\n\nfunc helper() int { return 1 }\n"
        root, src = _parse_source(source, "go")
        defs, _ = _walk_tree(root, src, "go")
        assert defs[0]["class"] is None

    def test_find_receiver_type_go_pointer(self):
        source = "package main\n\nfunc (e *Engine) Run() {}\n"
        root, src = _parse_source(source, "go")
        method_node = None
        for child in root.children:
            if child.type == "method_declaration":
                method_node = child
                break
        assert method_node is not None
        assert _find_receiver_type_go(method_node) == "Engine"

    def test_find_receiver_type_go_value_receiver(self):
        source = "package main\n\nfunc (e Engine) Run() {}\n"
        root, src = _parse_source(source, "go")
        method_node = next(c for c in root.children if c.type == "method_declaration")
        assert _find_receiver_type_go(method_node) == "Engine"

    def test_find_receiver_type_go_none_for_non_method(self):
        assert _find_receiver_type_go(None) is None

    def test_find_receiver_type_go_wrong_node_type(self):
        source = "package main\n\nfunc helper() {}\n"
        root, src = _parse_source(source, "go")
        func_node = next(c for c in root.children if c.type == "function_declaration")
        assert _find_receiver_type_go(func_node) is None

    def test_c_function_defs(self):
        source = "int foo(void) { return 1; }\nint bar(void) { return foo(); }\n"
        root, src = _parse_source(source, "c")
        defs, calls = _walk_tree(root, src, "c")
        assert len(defs) == 2
        names = {d["name"] for d in defs}
        assert names == {"foo", "bar"}

    def test_c_calls(self):
        source = "int main(void) { return foo(); }\nint foo(void) { return 1; }\n"
        root, src = _parse_source(source, "c")
        defs, calls = _walk_tree(root, src, "c")
        assert len(calls) == 1
        assert calls[0]["name"] == "foo"

    def test_unsupported_language(self):
        source = "def foo():\n    pass\n"
        root, src = _parse_source(source, "python")
        defs, calls = _walk_tree(root, src, "brainfuck")
        assert defs == []
        assert calls == []

    def test_empty_source(self):
        source = "\n"
        root, src = _parse_source(source, "python")
        defs, calls = _walk_tree(root, src, "python")
        assert defs == []
        assert calls == []
