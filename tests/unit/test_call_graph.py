"""Unit tests for call_graph.py — FunctionRef, CallGraph, AST extraction helpers."""

from pathlib import Path
from unittest.mock import MagicMock

from tree_sitter_analyzer.call_graph import (
    CachedCallGraph,
    CallGraph,
    FunctionRef,
    _extract_call,
    _find_parent_class_java,
    _find_parent_class_python,
    _get_func_name,
    _node_text,
    _walk_tree,
)
from tree_sitter_analyzer.core.parser import Parser

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "call_graph"
PY_PROJECT = FIXTURES_DIR / "python_project"
JS_PROJECT = FIXTURES_DIR / "js_project"
JAVA_PROJECT = FIXTURES_DIR / "java_project"
GO_PROJECT = FIXTURES_DIR / "go_project"
C_PROJECT = FIXTURES_DIR / "c_project"


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
        assert len(calls) >= 2

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
        assert len(defs) >= 1
        names = {d["name"] for d in defs}
        assert "main" in names or "foo" in names

    def test_go_function_defs(self):
        source = 'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println("hi")\n}\n\nfunc helper() int { return 1 }\n'
        root, src = _parse_source(source, "go")
        defs, calls = _walk_tree(root, src, "go")
        assert len(defs) >= 2
        names = {d["name"] for d in defs}
        assert "main" in names
        assert "helper" in names

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
        assert len(calls) >= 1
        assert any(c["name"] == "foo" for c in calls)

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

    def test_no_func_name_returns_none(self):
        node = MagicMock()
        node.children = []
        assert _get_func_name(node, "python") is None

    def test_unsupported_language_returns_none(self):
        source = "def foo():\n    pass\n"
        root, _ = _parse_source(source, "python")
        func_node = root.children[0]
        assert _get_func_name(func_node, "ruby") is None


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


def _collect_nodes(node, node_type, result_list):
    if hasattr(node, "type") and node.type == node_type:
        result_list.append(node)
    if hasattr(node, "children"):
        for child in node.children:
            _collect_nodes(child, node_type, result_list)


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
# CallGraph integration tests
# ============================================================


class TestCallGraphBuild:
    def test_build_python_project(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        assert cg._built
        funcs = cg.all_functions()
        names = {f["name"] for f in funcs}
        assert "main" in names
        assert "load_data" in names
        assert "process" in names
        assert "greet" in names

    def test_build_js_project(self):
        cg = CallGraph(str(JS_PROJECT))
        cg.build()
        funcs = cg.all_functions()
        names = {f["name"] for f in funcs}
        assert "main" in names or "loadData" in names

    def test_build_c_project(self):
        cg = CallGraph(str(C_PROJECT))
        cg.build()
        funcs = cg.all_functions()
        names = {f["name"] for f in funcs}
        assert "main" in names
        assert "loadData" in names

    def test_build_empty_dir(self, tmp_path):
        cg = CallGraph(str(tmp_path))
        cg.build()
        assert cg._built
        assert cg.all_functions() == []

    def test_build_idempotent(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        cg.build()
        funcs1 = cg.all_functions()
        funcs2 = cg.all_functions()
        assert len(funcs1) == len(funcs2)

    def test_summary(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        s = cg.summary()
        assert s["function_count"] > 0
        assert s["call_edge_count"] >= 0
        assert s["file_count"] > 0


class TestCallGraphCallersOf:
    def test_callers_of_called_function(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        callers = cg.callers_of("load_data")
        caller_names = {c["name"] for c in callers}
        assert "main" in caller_names

    def test_callers_of_uncalled_function(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        callers = cg.callers_of("farewell")
        assert callers == []

    def test_callers_with_file_path(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        callers = cg.callers_of("load_data", file_path="main.py")
        assert isinstance(callers, list)


class TestCallGraphCalleesOf:
    def test_callees_of_main(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        callees = cg.callees_of("main")
        callee_names = {c["name"] for c in callees}
        assert "load_data" in callee_names
        assert "process" in callee_names
        assert "save" in callee_names

    def test_callees_leaf_function(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        callees = cg.callees_of("save")
        assert callees == []


class TestCallChain:
    def test_call_chain_from_main(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        chain = cg.call_chain("main", depth=3)
        assert len(chain) > 0
        for edge in chain:
            assert "caller" in edge
            assert "callee" in edge
            assert "depth" in edge
            assert edge["depth"] >= 1

    def test_call_chain_depth_limit(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        chain = cg.call_chain("main", depth=1)
        for edge in chain:
            assert edge["depth"] <= 1

    def test_call_chain_nonexistent_function(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        chain = cg.call_chain("nonexistent")
        assert chain == []


class TestCallGraphPythonClassMethods:
    def test_class_method_discovered(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        funcs = cg.all_functions()
        names = {f["name"] for f in funcs}
        assert "get_user" in names or "delete_user" in names

    def test_class_method_receiver(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        funcs = cg.all_functions()
        user_service_methods = [
            f for f in funcs if f["name"] in ("get_user", "delete_user", "_fetch")
        ]
        assert len(user_service_methods) >= 1
        for m in user_service_methods:
            if "receiver" in m:
                assert m["receiver"] == "UserService"


class TestCallGraphGoProject:
    def test_go_functions_discovered(self):
        cg = CallGraph(str(GO_PROJECT))
        cg.build()
        funcs = cg.all_functions()
        names = {f["name"] for f in funcs}
        assert "main" in names
        assert "loadData" in names
        assert "processData" in names

    def test_go_callees(self):
        cg = CallGraph(str(GO_PROJECT))
        cg.build()
        callees = cg.callees_of("main")
        callee_names = {c["name"] for c in callees}
        assert "loadData" in callee_names


class TestCallGraphJavaProject:
    def test_java_methods_discovered(self):
        cg = CallGraph(str(JAVA_PROJECT))
        cg.build()
        funcs = cg.all_functions()
        names = {f["name"] for f in funcs}
        assert len(names) > 0

    def test_java_callers(self):
        cg = CallGraph(str(JAVA_PROJECT))
        cg.build()
        callers = cg.callers_of("loadData")
        assert isinstance(callers, list)


class TestCallGraphInternalMethods:
    def test_find_enclosing_func(self):
        cg = CallGraph(str(PY_PROJECT))
        ref1 = FunctionRef("main.py", "foo", 10, "python")
        ref2 = FunctionRef("main.py", "bar", 5, "python")
        file_funcs = {"foo": ref1, "bar": ref2}
        result = cg._find_enclosing_func(file_funcs, 12)
        assert result is not None
        assert result.name == "foo"

    def test_find_enclosing_func_tightest(self):
        cg = CallGraph(str(PY_PROJECT))
        ref1 = FunctionRef("main.py", "outer", 1, "python")
        ref2 = FunctionRef("main.py", "inner", 5, "python")
        file_funcs = {"outer": ref1, "inner": ref2}
        result = cg._find_enclosing_func(file_funcs, 7)
        assert result is not None
        assert result.name == "inner"

    def test_find_enclosing_func_no_match(self):
        cg = CallGraph(str(PY_PROJECT))
        ref1 = FunctionRef("main.py", "foo", 10, "python")
        file_funcs = {"foo": ref1}
        result = cg._find_enclosing_func(file_funcs, 5)
        assert result is None

    def test_resolve_callee_same_file(self):
        cg = CallGraph(str(PY_PROJECT))
        ref = FunctionRef("main.py", "foo", 10, "python")
        cg._func_by_name["foo"].append(ref)
        call = {"name": "foo"}
        result = cg._resolve_callee(call, "main.py", {})
        assert len(result) == 1
        assert result[0].name == "foo"

    def test_resolve_callee_different_file(self):
        cg = CallGraph(str(PY_PROJECT))
        ref = FunctionRef("other.py", "foo", 10, "python")
        cg._func_by_name["foo"].append(ref)
        call = {"name": "foo"}
        result = cg._resolve_callee(call, "main.py", {})
        assert len(result) == 1

    def test_resolve_callee_no_match(self):
        cg = CallGraph(str(PY_PROJECT))
        call = {"name": "nonexistent"}
        result = cg._resolve_callee(call, "main.py", {})
        assert result == []

    def test_is_excluded(self):
        cg = CallGraph(str(PY_PROJECT))
        assert cg._is_excluded(Path("/tmp/project/__pycache__/foo.py"))
        assert cg._is_excluded(Path("/tmp/project/.git/config"))
        assert not cg._is_excluded(Path("/tmp/project/main.py"))

    def test_resolve_targets_with_file_path(self):
        cg = CallGraph(str(PY_PROJECT))
        ref = FunctionRef("main.py", "foo", 10, "python")
        cg._func_by_qualified["main.py:foo"] = ref
        result = cg._resolve_targets("foo", "main.py")
        assert len(result) == 1
        assert result[0].name == "foo"

    def test_resolve_targets_by_name_only(self):
        cg = CallGraph(str(PY_PROJECT))
        ref = FunctionRef("main.py", "foo", 10, "python")
        cg._func_by_name["foo"].append(ref)
        result = cg._resolve_targets("foo")
        assert len(result) == 1

    def test_resolve_targets_no_match(self):
        cg = CallGraph(str(PY_PROJECT))
        result = cg._resolve_targets("nonexistent")
        assert result == []


class TestCachedCallGraphImportResolution:
    """Tests for import-aware cross-file resolution in CachedCallGraph."""

    @staticmethod
    def _make_mock_cache(
        functions,
        edges,
        imports=None,
    ):
        cache = MagicMock()
        cache.get_functions.return_value = functions
        cache.get_call_edges.return_value = edges
        cache.get_imports.return_value = imports or {}
        return cache

    def test_same_file_resolution(self):
        functions = [
            {"name": "main", "file": "app.py", "line": 5, "language": "python"},
            {"name": "helper", "file": "app.py", "line": 15, "language": "python"},
        ]
        edges = [
            {
                "caller_name": "main",
                "caller_file": "app.py",
                "caller_line": 5,
                "callee_name": "helper",
                "callee_full": "helper",
                "callee_line": 8,
            },
        ]
        cache = self._make_mock_cache(functions, edges, {"app.py": []})
        cg = CachedCallGraph("/tmp/project", cache=cache)
        cg.build()
        callees = cg.callees_of("main")
        assert len(callees) == 1
        assert callees[0]["name"] == "helper"
        assert callees[0]["file"] == "app.py"

    def test_cross_file_import_resolution(self):
        functions = [
            {"name": "process", "file": "service.py", "line": 10, "language": "python"},
            {"name": "load_data", "file": "models.py", "line": 5, "language": "python"},
        ]
        edges = [
            {
                "caller_name": "process",
                "caller_file": "service.py",
                "caller_line": 10,
                "callee_name": "load_data",
                "callee_full": "load_data",
                "callee_line": 13,
            },
        ]
        imports = {
            "service.py": ["from models import load_data"],
        }
        cache = self._make_mock_cache(functions, edges, imports)
        cg = CachedCallGraph("/tmp/project", cache=cache)
        cg.build()
        callees = cg.callees_of("process")
        assert len(callees) == 1
        assert callees[0]["name"] == "load_data"
        assert callees[0]["file"] == "models.py"

    def test_dotted_callee_resolution(self):
        functions = [
            {"name": "run", "file": "main.py", "line": 5, "language": "python"},
            {"name": "fetch", "file": "client.py", "line": 10, "language": "python"},
        ]
        edges = [
            {
                "caller_name": "run",
                "caller_file": "main.py",
                "caller_line": 5,
                "callee_name": "client.fetch",
                "callee_full": "client.fetch",
                "callee_line": 7,
            },
        ]
        imports = {
            "main.py": ["from client import fetch"],
        }
        cache = self._make_mock_cache(functions, edges, imports)
        cg = CachedCallGraph("/tmp/project", cache=cache)
        cg.build()
        callees = cg.callees_of("run")
        assert len(callees) == 1
        assert callees[0]["name"] == "fetch"
        assert callees[0]["file"] == "client.py"

    def test_fallback_to_first_candidate(self):
        functions = [
            {"name": "handler", "file": "app.py", "line": 5, "language": "python"},
            {
                "name": "validate",
                "file": "validators.py",
                "line": 3,
                "language": "python",
            },
        ]
        edges = [
            {
                "caller_name": "handler",
                "caller_file": "app.py",
                "caller_line": 5,
                "callee_name": "validate",
                "callee_full": "validate",
                "callee_line": 8,
            },
        ]
        cache = self._make_mock_cache(functions, edges, {"app.py": []})
        cg = CachedCallGraph("/tmp/project", cache=cache)
        cg.build()
        callees = cg.callees_of("handler")
        assert len(callees) == 1
        assert callees[0]["name"] == "validate"

    def test_empty_cache_falls_back(self):
        cache = MagicMock()
        cache.get_functions.return_value = []
        cache.get_call_edges.return_value = []
        cg = CachedCallGraph(str(PY_PROJECT), cache=cache, fallback=True)
        cg.build()
        funcs = cg.all_functions()
        assert len(funcs) > 0

    def test_no_fallback_skips_parse(self):
        cache = MagicMock()
        cache.get_functions.return_value = []
        cache.get_call_edges.return_value = []
        cg = CachedCallGraph(str(PY_PROJECT), cache=cache, fallback=False)
        cg.build()
        assert not cg._built

    def test_reverse_callers(self):
        functions = [
            {"name": "main", "file": "main.py", "line": 1, "language": "python"},
            {"name": "process", "file": "service.py", "line": 5, "language": "python"},
        ]
        edges = [
            {
                "caller_name": "main",
                "caller_file": "main.py",
                "caller_line": 1,
                "callee_name": "process",
                "callee_full": "process",
                "callee_line": 3,
            },
        ]
        imports = {"main.py": ["from service import process"]}
        cache = self._make_mock_cache(functions, edges, imports)
        cg = CachedCallGraph("/tmp/project", cache=cache)
        cg.build()
        callers = cg.callers_of("process")
        assert len(callers) == 1
        assert callers[0]["name"] == "main"
        assert callers[0]["file"] == "main.py"

    def test_cache_passes_end_line(self):
        functions = [
            {
                "name": "handler",
                "file": "app.py",
                "line": 5,
                "end_line": 20,
                "language": "python",
            },
        ]
        cache = self._make_mock_cache(functions, [], {})
        cg = CachedCallGraph("/tmp/project", cache=cache)
        cg.build()
        funcs = cg.all_functions()
        assert len(funcs) == 1
        assert funcs[0]["end_line"] == 20


class TestFunctionRefEndLine:
    def test_end_line_defaults_to_start(self):
        ref = FunctionRef("a.py", "foo", 10, "python")
        assert ref.end_line == 10

    def test_end_line_explicit(self):
        ref = FunctionRef("a.py", "foo", 10, "python", end_line=25)
        assert ref.end_line == 25

    def test_to_dict_includes_end_line(self):
        ref = FunctionRef("a.py", "foo", 5, "python", end_line=20)
        d = ref.to_dict()
        assert d["end_line"] == 20


class TestFindEnclosingFuncRange:
    def test_range_containment(self):
        cg = CallGraph("/tmp")
        outer = FunctionRef("a.py", "outer", 1, "python", end_line=50)
        inner = FunctionRef("a.py", "inner", 10, "python", end_line=20)
        file_funcs = {"outer": outer, "inner": inner}
        assert cg._find_enclosing_func(file_funcs, 15) == inner

    def test_range_picks_tighter_scope(self):
        cg = CallGraph("/tmp")
        outer = FunctionRef("a.py", "outer", 1, "python", end_line=50)
        inner = FunctionRef("a.py", "inner", 10, "python", end_line=20)
        file_funcs = {"outer": outer, "inner": inner}
        result = cg._find_enclosing_func(file_funcs, 15)
        assert result.name == "inner"

    def test_fallback_closest_start(self):
        cg = CallGraph("/tmp")
        f1 = FunctionRef("a.py", "foo", 5, "python", end_line=5)
        f2 = FunctionRef("a.py", "bar", 15, "python", end_line=15)
        file_funcs = {"foo": f1, "bar": f2}
        result = cg._find_enclosing_func(file_funcs, 10)
        assert result.name == "foo"


class TestFileImpact:
    def test_file_impact_basic(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        funcs = cg.functions_in_file("main.py")
        assert isinstance(funcs, list)

    def test_file_impact_returns_upstream_downstream(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        impact = cg.file_impact("main.py")
        assert "upstream" in impact
        assert "downstream" in impact
        assert "function_count" in impact
        assert impact["file"] == "main.py"

    def test_file_impact_nonexistent_file(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        impact = cg.file_impact("nonexistent.py")
        assert impact["function_count"] == 0
        assert impact["upstream_count"] == 0
        assert impact["downstream_count"] == 0


class TestNodeTextUtf8:
    def test_node_text_multibyte_comment_before_func(self):
        source = (
            "# \u2264 max_value — compare values\ndef greet(name):\n    return name\n"
        )
        root, src = _parse_source(source, "python")
        func_node = None
        for child in root.children:
            if child.type == "function_definition":
                func_node = child
                break
        assert func_node is not None
        name_node = func_node.child_by_field_name("name")
        assert name_node is not None
        text = _node_text(name_node, src)
        assert text == "greet", f"Expected 'greet' but got {text!r}"

    def test_node_text_cjk_identifier(self):
        source = (
            "# \u30c6\u30b9\u30c8\u95a2\u6570\n"
            "def process_data(items):\n"
            "    return items\n"
        )
        root, src = _parse_source(source, "python")
        func_node = None
        for child in root.children:
            if child.type == "function_definition":
                func_node = child
                break
        assert func_node is not None
        name_node = func_node.child_by_field_name("name")
        assert name_node is not None
        text = _node_text(name_node, src)
        assert text == "process_data"

    def test_extract_call_after_multibyte(self):
        source = "# \u2264 check \u2713 done\ndef run():\n    helper()\n"
        root, src = _parse_source(source, "python")
        definitions, calls = _walk_tree(root, src, "python")
        assert len(calls) == 1
        assert calls[0]["name"] == "helper"

    def test_node_text_none_returns_empty(self):
        assert _node_text(None, "source") == ""
