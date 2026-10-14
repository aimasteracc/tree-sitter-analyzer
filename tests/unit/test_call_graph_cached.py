"""Unit tests for call_graph.py — CachedCallGraph, FunctionRef end_line, file impact, node_text UTF-8."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.call_graph import (
    CachedCallGraph,
    CallGraph,
    FunctionRef,
)
from tree_sitter_analyzer.core.parser import Parser
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
# CachedCallGraph import resolution tests
# ============================================================


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
        assert funcs

    def test_no_fallback_skips_parse(self):
        cache = MagicMock()
        cache.get_functions.return_value = []
        cache.get_call_edges.return_value = []
        cg = CachedCallGraph(str(PY_PROJECT), cache=cache, fallback=False)
        cg.build()
        assert not cg.is_built

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


_TWO_PUBLISH_FUNCTIONS = [
    {"name": "run", "file": "app.py", "line": 1, "language": "python"},
    {
        "name": "publish",
        "file": "gen.py",
        "line": 2,
        "language": "python",
        "class": "GenerationStore",
    },
    {
        "name": "publish",
        "file": "reg.py",
        "line": 2,
        "language": "python",
        "class": "Registry",
    },
]


def _publish_edge(callee_full: str, **resolution: str) -> dict:
    return {
        "caller_name": "run",
        "caller_file": "app.py",
        "caller_line": 1,
        "callee_name": "publish",
        "callee_full": callee_full,
        "callee_line": 3,
        **resolution,
    }


class TestCachedCallGraphNoBareNameFanout:
    """#1559/#1560：缓存边优先采用持久化解析，模糊裸名不扇出成边。"""

    @staticmethod
    def _graph(functions, edges) -> CachedCallGraph:
        cache = MagicMock()
        cache.get_functions.return_value = functions
        cache.get_call_edges.return_value = edges
        cache.get_imports.return_value = {}
        cg = CachedCallGraph("/tmp/project", cache=cache)
        cg.build()
        return cg

    def test_persisted_resolution_binds_only_its_file(self):
        # #1559：持久化解析到 gen.py 的边只挂到 GenerationStore.publish。
        edge = _publish_edge(
            "store.publish",
            callee_resolution="project",
            callee_resolved_file="gen.py",
        )
        cg = self._graph(_TWO_PUBLISH_FUNCTIONS, [edge])
        assert [(c["file"], c["line"]) for c in cg.callees_of("run")] == [("gen.py", 2)]

    def test_ambiguous_global_match_creates_no_edge(self):
        # #1559：接收者未知且有两个同名候选时不猜测。
        edge = _publish_edge("target.publish", callee_resolution="unknown")
        cg = self._graph(_TWO_PUBLISH_FUNCTIONS, [edge])
        assert cg.callees_of("run") == []

    def test_ambiguous_candidates_stay_reachable_for_dead_code(self):
        # #1559：模糊候选不成为边，但死代码分析仍视其为可达。
        edge = _publish_edge("target.publish", callee_resolution="unknown")
        cg = self._graph(_TWO_PUBLISH_FUNCTIONS, [edge])
        run = next(f for f in cg.function_refs() if f.name == "run")
        assert sorted(f.file_path for f in cg.reachable_callee_refs_of(run)) == [
            "gen.py",
            "reg.py",
        ]

    def test_class_qualified_call_binds_its_receiver(self):
        # #1559：`Registry.publish(...)` 的接收者就是类名，可以唯一确定。
        edge = _publish_edge("Registry.publish")
        cg = self._graph(_TWO_PUBLISH_FUNCTIONS, [edge])
        assert [c["file"] for c in cg.callees_of("run")] == ["reg.py"]

    def test_builtin_resolution_is_not_a_project_callee(self):
        # #1560：持久化为 stdlib 的 `dataclasses.replace` 不能挂到项目的 replace。
        functions = [
            {"name": "run", "file": "app.py", "line": 1, "language": "python"},
            {"name": "replace", "file": "plan.py", "line": 4, "language": "python"},
        ]
        edge = {
            **_publish_edge("dataclasses.replace", callee_resolution="stdlib"),
            "callee_name": "replace",
        }
        cg = self._graph(functions, [edge])
        assert cg.callees_of("run") == []

    def test_unknown_receiver_skips_unique_global_candidate(self):
        # #1560：项目里只有一个 `get`，`d.get(...)` 也不能断定调用的是它。
        functions = [
            {"name": "run", "file": "app.py", "line": 1, "language": "python"},
            {
                "name": "get",
                "file": "box.py",
                "line": 2,
                "language": "python",
                "class": "Box",
            },
        ]
        edge = {**_publish_edge("d.get"), "callee_name": "get"}
        cg = self._graph(functions, [edge])
        assert cg.callees_of("run") == []

    def test_self_call_binds_unique_mixin_method(self):
        # #1559：`self.helper()` 指向唯一的 mixin 方法时仍然绑定。
        functions = [
            {"name": "run", "file": "app.py", "line": 1, "language": "python"},
            {
                "name": "helper",
                "file": "mixins.py",
                "line": 7,
                "language": "python",
                "class": "HelperMixin",
            },
        ]
        edge = {**_publish_edge("self.helper"), "callee_name": "helper"}
        cg = self._graph(functions, [edge])
        assert [c["file"] for c in cg.callees_of("run")] == ["mixins.py"]


# ============================================================
# FunctionRef end_line tests
# ============================================================


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


# ============================================================
# _find_enclosing_func range tests
# ============================================================


class TestFindEnclosingFuncRange:
    def test_range_containment(self):
        cg = CallGraph("/tmp")
        outer = FunctionRef("a.py", "outer", 1, "python", end_line=50)
        inner = FunctionRef("a.py", "inner", 10, "python", end_line=20)
        file_funcs = {"outer": outer, "inner": inner}
        assert cg.find_enclosing_func(file_funcs, 15) == inner

    def test_range_picks_tighter_scope(self):
        cg = CallGraph("/tmp")
        outer = FunctionRef("a.py", "outer", 1, "python", end_line=50)
        inner = FunctionRef("a.py", "inner", 10, "python", end_line=20)
        file_funcs = {"outer": outer, "inner": inner}
        result = cg.find_enclosing_func(file_funcs, 15)
        assert result.name == "inner"

    def test_module_level_gap_returns_none(self):
        """A call between two non-overlapping functions has no enclosing function.

        Before #648: the fallback returned the nearest preceding function (foo).
        After #648: returns None — the call is module-level and must not be
        attributed to any function (mirrors the SQL tier's counted-exclusion).
        """
        cg = CallGraph("/tmp")
        f1 = FunctionRef("a.py", "foo", 5, "python", end_line=5)
        f2 = FunctionRef("a.py", "bar", 15, "python", end_line=15)
        file_funcs = {"foo": f1, "bar": f2}
        result = cg.find_enclosing_func(file_funcs, 10)
        assert result is None


# ============================================================
# File impact tests
# ============================================================


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


# ============================================================
# node_text UTF-8 tests
# ============================================================


class TestNodeTextUtf8:
    def test_node_text_multibyte_comment_before_func(self):
        source = "# ≤ max_value — compare values\ndef greet(name):\n    return name\n"
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
        source = "# テスト関数\ndef process_data(items):\n    return items\n"
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
        source = "# ≤ check ✓ done\ndef run():\n    helper()\n"
        root, src = _parse_source(source, "python")
        definitions, calls = _walk_tree(root, src, "python")
        assert len(calls) == 1
        assert calls[0]["name"] == "helper"

    def test_node_text_none_returns_empty(self):
        assert _node_text(None, "source") == ""


# ============================================================
# CallGraph.call_edges() public accessor (TDD — added to replace
# direct access to private _call_edges in codegraph_metrics_tool)
# ============================================================


class TestCallEdgesPublicAccessor:
    """call_edges() must expose the same data as the private _call_edges."""

    @staticmethod
    def _make_mock_cache(functions, edges):
        cache = MagicMock()
        cache.get_functions.return_value = functions
        cache.get_call_edges.return_value = edges
        cache.get_imports.return_value = {}
        return cache

    def test_call_edges_returns_list(self):
        """call_edges() must return a list (not None)."""
        cg = CallGraph.__new__(CallGraph)  # avoid filesystem scan
        # Write to private attrs here to bootstrap test state without build().
        # This is test-only setup — not production code.
        cg._built = True  # noqa: SLF001
        cg._functions = []  # noqa: SLF001
        cg._call_edges = []  # noqa: SLF001
        cg._func_by_name = {}  # noqa: SLF001
        result = cg.call_edges()
        assert isinstance(result, list)

    def test_call_edges_matches_private_attribute(self):
        """call_edges() must return the edges that were built (data contract)."""
        cache = self._make_mock_cache(
            functions=[
                {
                    "file": "a.py",
                    "name": "foo",
                    "line": 1,
                    "language": "python",
                    "end_line": 5,
                },
                {
                    "file": "a.py",
                    "name": "bar",
                    "line": 7,
                    "language": "python",
                    "end_line": 10,
                },
            ],
            edges=[
                {
                    "caller_name": "foo",
                    "caller_file": "a.py",
                    "callee_name": "bar",
                    "callee_file": "a.py",
                    "line": 3,
                }
            ],
        )
        cg = CachedCallGraph(".", cache=cache)
        cg.build()
        edges = cg.call_edges()
        assert len(edges) == 1  # one edge: foo → bar
        caller, callee, line = edges[0]
        assert caller.name == "foo"
        assert callee.name == "bar"

    def test_call_edges_returns_tuples(self):
        """Each entry must be a (FunctionRef, FunctionRef, int) tuple."""
        cache = self._make_mock_cache(
            functions=[
                {
                    "file": "x.py",
                    "name": "caller",
                    "line": 1,
                    "language": "python",
                    "end_line": 4,
                },
                {
                    "file": "x.py",
                    "name": "callee",
                    "line": 6,
                    "language": "python",
                    "end_line": 9,
                },
            ],
            edges=[
                {
                    "caller_name": "caller",
                    "caller_file": "x.py",
                    "callee_name": "callee",
                    "callee_file": "x.py",
                    "line": 2,
                }
            ],
        )
        cg = CachedCallGraph(".", cache=cache)
        cg.build()
        edges = cg.call_edges()
        assert edges
        for edge in edges:
            assert len(edge) == 3
            caller_ref, callee_ref, line = edge
            assert isinstance(caller_ref, FunctionRef)
            assert isinstance(callee_ref, FunctionRef)
            assert isinstance(line, int)


# ============================================================
# CallGraph.function_refs(), callees_of(), callers_of()
# (TDD — added to replace private _functions/_callees/_callers
#  accesses in dead_code_analyzer.py and codegraph_impact_tool.py)
# ============================================================


class TestCallGraphInternalAccessors:
    """function_refs(), callees_of(), callers_of() must expose FunctionRef data."""

    @staticmethod
    def _make_mock_cache(functions, edges):
        cache = MagicMock()
        cache.get_functions.return_value = functions
        cache.get_call_edges.return_value = edges
        cache.get_imports.return_value = {}
        return cache

    @staticmethod
    def _two_func_cache():
        return TestCallGraphInternalAccessors._make_mock_cache(
            functions=[
                {
                    "file": "a.py",
                    "name": "entry",
                    "line": 1,
                    "language": "python",
                    "end_line": 5,
                },
                {
                    "file": "a.py",
                    "name": "helper",
                    "line": 7,
                    "language": "python",
                    "end_line": 10,
                },
            ],
            edges=[
                {
                    "caller_name": "entry",
                    "caller_file": "a.py",
                    "callee_name": "helper",
                    "callee_file": "a.py",
                    "line": 3,
                }
            ],
        )

    def test_function_refs_returns_function_ref_objects(self):
        """function_refs() must return FunctionRef objects (not dicts)."""
        cache = self._two_func_cache()
        cg = CachedCallGraph(".", cache=cache)
        cg.build()
        refs = cg.function_refs()
        assert isinstance(refs, list)
        assert len(refs) == 2
        assert all(isinstance(r, FunctionRef) for r in refs)

    def test_function_refs_same_as_private_functions(self):
        """function_refs() must return the functions that were built (data contract)."""
        cache = self._two_func_cache()
        cg = CachedCallGraph(".", cache=cache)
        cg.build()
        refs = cg.function_refs()
        assert isinstance(refs, list)
        assert len(refs) == 2
        assert all(isinstance(r, FunctionRef) for r in refs)

    def test_callee_refs_of_returns_list(self):
        """callee_refs_of(func) must return the callees of a given FunctionRef."""
        cache = self._two_func_cache()
        cg = CachedCallGraph(".", cache=cache)
        cg.build()
        refs = cg.function_refs()
        entry = next(r for r in refs if r.name == "entry")
        callees = cg.callee_refs_of(entry)
        assert isinstance(callees, list)
        assert len(callees) == 1
        assert callees[0].name == "helper"

    def test_caller_refs_of_returns_list(self):
        """caller_refs_of(func) must return the callers of a given FunctionRef."""
        cache = self._two_func_cache()
        cg = CachedCallGraph(".", cache=cache)
        cg.build()
        refs = cg.function_refs()
        helper = next(r for r in refs if r.name == "helper")
        callers = cg.caller_refs_of(helper)
        assert isinstance(callers, list)
        assert len(callers) == 1
        assert callers[0].name == "entry"

    def test_callee_refs_of_unknown_func_returns_empty(self):
        """callee_refs_of(unknown) must return empty list, not raise."""
        cache = self._two_func_cache()
        cg = CachedCallGraph(".", cache=cache)
        cg.build()
        unknown = FunctionRef("x.py", "nonexistent", 0, "python")
        assert cg.callee_refs_of(unknown) == []

    def test_caller_refs_of_unknown_func_returns_empty(self):
        """caller_refs_of(unknown) must return empty list, not raise."""
        cache = self._two_func_cache()
        cg = CachedCallGraph(".", cache=cache)
        cg.build()
        unknown = FunctionRef("x.py", "nonexistent", 0, "python")
        assert cg.caller_refs_of(unknown) == []


_SUBMODULE_ALIAS_PROJECT = {
    "pkg/__init__.py": "",
    "pkg/mod.py": "def f():\n    return 1\n",
    # 调用方位于子目录：绝对导入不得按调用方目录拼接（#1579）。
    "app/run.py": "from pkg import mod as m\n\n\ndef run():\n    return m.f()\n",
}


class TestSubmoduleAliasCallBinding:
    """#1579：``from pkg import mod as m; m.f()`` 必须绑定到 ``pkg/mod.py``。"""

    @pytest.mark.asyncio
    async def test_callers_bind_submodule_alias_call_to_defining_module(self, tmp_path):
        # #1579：持久化解析曾把该调用绑到 pkg/__init__.py（而非定义所在的 pkg/mod.py）。
        from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        for rel, text in _SUBMODULE_ALIAS_PROJECT.items():
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
            {"mode": "full", "max_files": 10}
        )
        assert indexed["published"] is True
        result = await CodeGraphCallersTool(str(tmp_path)).execute(
            {"function_name": "f", "include_bodies": False}
        )
        assert [
            (c["name"], c["file"], c["callee_resolved_file"]) for c in result["callers"]
        ] == [("run", "app/run.py", "pkg/mod.py")]
