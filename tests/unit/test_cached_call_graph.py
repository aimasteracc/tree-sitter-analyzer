#!/usr/bin/env python3
"""Tests for CachedCallGraph — call graph built from AST cache."""

import os

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.call_graph import CachedCallGraph, CallGraph


@pytest.fixture
def project_with_calls(tmp_path):
    src = tmp_path / "example.py"
    src.write_text(
        "def alpha():\n"
        "    beta()\n"
        "    gamma()\n"
        "\n"
        "def beta():\n"
        "    delta()\n"
        "\n"
        "def gamma():\n"
        "    pass\n"
        "\n"
        "def delta():\n"
        "    pass\n"
    )
    return tmp_path


@pytest.fixture
def cached_index(project_with_calls):
    cache = ASTCache(str(project_with_calls))
    cache.index_file(str(project_with_calls / "example.py"), "python")
    return cache


class TestCachedCallGraphBuild:
    def test_build_from_cache(self, project_with_calls, cached_index):
        cg = CachedCallGraph(str(project_with_calls), cache=cached_index)
        cg.build()
        assert cg._built
        assert cg.summary()["function_count"] == 4

    def test_build_fallback_when_no_cache(self, project_with_calls):
        cg = CachedCallGraph(str(project_with_calls), cache=None, fallback=True)
        cg.build()
        assert cg._built
        assert cg.summary()["function_count"] == 4

    def test_build_no_fallback_no_cache(self, project_with_calls):
        cg = CachedCallGraph(str(project_with_calls), cache=None, fallback=False)
        cg.build()
        assert not cg._built

    def test_empty_cache_falls_back(self, project_with_calls):
        cache = ASTCache(str(project_with_calls))
        cache.close()
        os.makedirs(os.path.join(str(project_with_calls), ".ast-cache"), exist_ok=True)
        cache = ASTCache(str(project_with_calls))
        cg = CachedCallGraph(str(project_with_calls), cache=cache, fallback=True)
        cg.build()
        assert cg._built


class TestCachedCallGraphQueries:
    def test_callers_of(self, project_with_calls, cached_index):
        cg = CachedCallGraph(str(project_with_calls), cache=cached_index)
        callers = cg.callers_of("beta")
        names = [c["name"] for c in callers]
        assert "alpha" in names

    def test_callees_of(self, project_with_calls, cached_index):
        cg = CachedCallGraph(str(project_with_calls), cache=cached_index)
        callees = cg.callees_of("alpha")
        names = [c["name"] for c in callees]
        assert "beta" in names
        assert "gamma" in names

    def test_callers_of_leaf(self, project_with_calls, cached_index):
        cg = CachedCallGraph(str(project_with_calls), cache=cached_index)
        callers = cg.callers_of("delta")
        names = [c["name"] for c in callers]
        assert "beta" in names

    def test_callees_of_leaf(self, project_with_calls, cached_index):
        cg = CachedCallGraph(str(project_with_calls), cache=cached_index)
        callees = cg.callees_of("delta")
        assert callees == []

    def test_all_functions(self, project_with_calls, cached_index):
        cg = CachedCallGraph(str(project_with_calls), cache=cached_index)
        funcs = cg.all_functions()
        names = {f["name"] for f in funcs}
        assert names == {"alpha", "beta", "gamma", "delta"}

    def test_summary(self, project_with_calls, cached_index):
        cg = CachedCallGraph(str(project_with_calls), cache=cached_index)
        s = cg.summary()
        assert s["function_count"] == 4
        assert s["call_edge_count"] == 3
        assert s["file_count"] == 1


class TestCachedVsFreshParity:
    def test_same_callers(self, project_with_calls, cached_index):
        fresh = CallGraph(str(project_with_calls))
        cached = CachedCallGraph(str(project_with_calls), cache=cached_index)

        for func in ["alpha", "beta", "gamma", "delta"]:
            fresh_callers = {c["name"] for c in fresh.callers_of(func)}
            cached_callers = {c["name"] for c in cached.callers_of(func)}
            assert fresh_callers == cached_callers, f"callers mismatch for {func}"

    def test_same_callees(self, project_with_calls, cached_index):
        fresh = CallGraph(str(project_with_calls))
        cached = CachedCallGraph(str(project_with_calls), cache=cached_index)

        for func in ["alpha", "beta", "gamma", "delta"]:
            fresh_callees = {c["name"] for c in fresh.callees_of(func)}
            cached_callees = {c["name"] for c in cached.callees_of(func)}
            assert fresh_callees == cached_callees, f"callees mismatch for {func}"

    def test_same_function_count(self, project_with_calls, cached_index):
        fresh = CallGraph(str(project_with_calls))
        cached = CachedCallGraph(str(project_with_calls), cache=cached_index)
        assert fresh.summary()["function_count"] == cached.summary()["function_count"]


class TestASTCacheCallEdgeStorage:
    def test_call_edges_stored(self, project_with_calls, cached_index):
        edges = cached_index.get_call_edges()
        assert len(edges) > 0
        callee_names = {e["callee_name"] for e in edges}
        assert "beta" in callee_names
        assert "gamma" in callee_names
        assert "delta" in callee_names

    def test_functions_stored(self, project_with_calls, cached_index):
        funcs = cached_index.get_functions()
        names = {f["name"] for f in funcs}
        assert names == {"alpha", "beta", "gamma", "delta"}

    def test_invalidate_clears_edges(self, project_with_calls, cached_index):
        assert len(cached_index.get_call_edges()) > 0
        cached_index.invalidate(str(project_with_calls / "example.py"))
        assert len(cached_index.get_call_edges()) == 0
        assert len(cached_index.get_functions()) == 0

    def test_js_call_edges(self, tmp_path):
        src = tmp_path / "app.js"
        src.write_text(
            "function main() {\n"
            "  helper();\n"
            "  process();\n"
            "}\n"
            "function helper() {\n"
            "  validate();\n"
            "}\n"
            "function process() {}\n"
            "function validate() {}\n"
        )
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(src), "javascript")
        edges = cache.get_call_edges()
        assert len(edges) > 0
        callee_names = {e["callee_name"] for e in edges}
        assert "helper" in callee_names
