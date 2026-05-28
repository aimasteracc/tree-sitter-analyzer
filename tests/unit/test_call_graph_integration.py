"""Unit tests for call_graph.py — CallGraph integration tests."""

from pathlib import Path

import pytest

from tree_sitter_analyzer.call_graph import (
    CallGraph,
    FunctionRef,
)

# Historical: this marker first gated three call_graph cross-file
# resolution tests as Windows-only. Then we discovered Linux CI fails
# too and broadened the skip to all platforms. The real root cause was
# an iteration-order bug in ``CallGraph.build()`` — def-add and call-
# resolve happened in the same loop, so cross-file edges silently
# dropped whenever the calling file was iterated before its callees.
# The fix is now in place (two-pass build); leaving the alias as a
# no-op marker so existing @_WINDOWS_SKIP_PY_FIXTURE decorators below
# stay syntactically valid but become inert.
_WINDOWS_SKIP_PY_FIXTURE = pytest.mark.skipif(
    False, reason="resolved by two-pass build in call_graph.py"
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "call_graph"
PY_PROJECT = FIXTURES_DIR / "python_project"
JS_PROJECT = FIXTURES_DIR / "js_project"
JAVA_PROJECT = FIXTURES_DIR / "java_project"
GO_PROJECT = FIXTURES_DIR / "go_project"
C_PROJECT = FIXTURES_DIR / "c_project"


# ============================================================
# CallGraph integration tests
# ============================================================


class TestCallGraphBuild:
    def test_build_python_project(self):
        cg = CallGraph(str(PY_PROJECT))
        cg.build()
        assert cg.is_built
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
        assert cg.is_built
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
    @_WINDOWS_SKIP_PY_FIXTURE
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
    @_WINDOWS_SKIP_PY_FIXTURE
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
    @_WINDOWS_SKIP_PY_FIXTURE
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

    def test_go_method_selector_callees(self, tmp_path):
        src = tmp_path / "gin.go"
        src.write_text(
            "package gin\n\n"
            "type Engine struct{}\n\n"
            "func (engine *Engine) ServeHTTP() {\n"
            "\tengine.handleHTTPRequest()\n"
            "}\n\n"
            "func (engine *Engine) handleHTTPRequest() {}\n",
            encoding="utf-8",
        )
        cg = CallGraph(str(tmp_path))
        cg.build()

        callees = cg.callees_of("ServeHTTP", file_path="gin.go")
        assert [callee["name"] for callee in callees] == ["handleHTTPRequest"]


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
        result = cg.find_enclosing_func(file_funcs, 12)
        assert result is not None
        assert result.name == "foo"

    def test_find_enclosing_func_tightest(self):
        cg = CallGraph(str(PY_PROJECT))
        ref1 = FunctionRef("main.py", "outer", 1, "python")
        ref2 = FunctionRef("main.py", "inner", 5, "python")
        file_funcs = {"outer": ref1, "inner": ref2}
        result = cg.find_enclosing_func(file_funcs, 7)
        assert result is not None
        assert result.name == "inner"

    def test_find_enclosing_func_no_match(self):
        cg = CallGraph(str(PY_PROJECT))
        ref1 = FunctionRef("main.py", "foo", 10, "python")
        file_funcs = {"foo": ref1}
        result = cg.find_enclosing_func(file_funcs, 5)
        assert result is None

    def test_resolve_callee_same_file(self):
        cg = CallGraph(str(PY_PROJECT))
        ref = FunctionRef("main.py", "foo", 10, "python")
        cg._func_by_name["foo"].append(ref)
        call = {"name": "foo"}
        result = cg.resolve_callee(call, "main.py", {})
        assert len(result) == 1
        assert result[0].name == "foo"

    def test_resolve_callee_different_file(self):
        cg = CallGraph(str(PY_PROJECT))
        ref = FunctionRef("other.py", "foo", 10, "python")
        cg._func_by_name["foo"].append(ref)
        call = {"name": "foo"}
        result = cg.resolve_callee(call, "main.py", {})
        assert len(result) == 1

    def test_resolve_callee_no_match(self):
        cg = CallGraph(str(PY_PROJECT))
        call = {"name": "nonexistent"}
        result = cg.resolve_callee(call, "main.py", {})
        assert result == []

    def test_is_excluded(self):
        cg = CallGraph(str(PY_PROJECT))
        assert cg.is_excluded(Path("/tmp/project/__pycache__/foo.py"))
        assert cg.is_excluded(Path("/tmp/project/.git/config"))
        assert not cg.is_excluded(Path("/tmp/project/main.py"))

    def test_iter_source_files_prunes_hidden_and_generated_dirs(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n")
        (tmp_path / "node_modules" / "pkg" / "skip.py").write_text(
            "def skip():\n    pass\n"
        )
        (tmp_path / ".hidden" / "skip.py").write_text("def skip():\n    pass\n")
        (tmp_path / ".secret.py").write_text("def skip():\n    pass\n")
        cg = CallGraph(str(tmp_path))

        files = {
            path.relative_to(tmp_path).as_posix()
            for path in cg.iter_source_files({".py"})
        }

        assert files == {"src/main.py"}

    def test_resolve_targets_with_file_path(self):
        cg = CallGraph(str(PY_PROJECT))
        ref = FunctionRef("main.py", "foo", 10, "python")
        cg._func_by_qualified["main.py:foo"] = ref
        result = cg.resolve_targets("foo", "main.py")
        assert len(result) == 1
        assert result[0].name == "foo"

    def test_resolve_targets_by_name_only(self):
        cg = CallGraph(str(PY_PROJECT))
        ref = FunctionRef("main.py", "foo", 10, "python")
        cg._func_by_name["foo"].append(ref)
        result = cg.resolve_targets("foo")
        assert len(result) == 1

    def test_resolve_targets_no_match(self):
        cg = CallGraph(str(PY_PROJECT))
        result = cg.resolve_targets("nonexistent")
        assert result == []


class TestCallGraphAllCallEdges:
    def test_all_call_edges_returns_list(self):
        """all_call_edges() must return a list of 3-tuples."""
        cg = CallGraph(str(PY_PROJECT))
        edges = cg.all_call_edges()
        assert isinstance(edges, list)
        for caller, callee, line in edges:
            assert isinstance(caller, FunctionRef)
            assert isinstance(callee, FunctionRef)
            assert isinstance(line, int)

    def test_all_call_edges_triggers_build(self):
        """all_call_edges() must build the graph if not yet built."""
        cg = CallGraph(str(PY_PROJECT))
        # Graph not yet built — calling all_call_edges() should trigger build.
        # After the call, functions and edges are populated.
        assert len(cg.all_call_edges()) >= 0
        assert len(cg.all_functions()) > 0

    def test_all_call_edges_count_matches_summary(self):
        """all_call_edges() count must match the summary call_edge_count."""
        cg = CallGraph(str(PY_PROJECT))
        edges = cg.all_call_edges()
        summary = cg.summary()
        assert len(edges) == summary["call_edge_count"]

    def test_all_call_edges_returns_copy(self):
        """Mutating the returned list must not affect the internal state."""
        cg = CallGraph(str(PY_PROJECT))
        edges1 = cg.all_call_edges()
        edges1.clear()
        edges2 = cg.all_call_edges()
        assert len(edges2) > 0  # internal list unaffected
