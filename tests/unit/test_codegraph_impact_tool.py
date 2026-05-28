"""Tests for CodeGraph Impact tool — function blast radius analysis."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.mcp.tools.codegraph_impact_tool import (
    CodeGraphImpactTool,
    _blast_radius_for_functions,
    _compute_risk_score,
    _compute_transitive_callees,
    _compute_transitive_callers,
)


def _make_func(name: str, file: str = "a.py", line: int = 1) -> FunctionRef:
    return FunctionRef(
        file_path=file,
        name=name,
        start_line=line,
        language="python",
    )


class TestTransitiveCallers:
    def test_no_callers(self):
        graph = MagicMock()
        func = _make_func("foo")
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = []
        result = _compute_transitive_callers(graph, "foo")
        assert result == []

    def test_direct_callers(self):
        graph = MagicMock()
        foo = _make_func("foo")
        bar = _make_func("bar", "b.py", 5)
        graph.resolve_targets.return_value = [foo]
        callers_map = {foo: [bar], bar: []}
        graph.caller_refs_of.side_effect = lambda f: callers_map.get(f, [])
        result = _compute_transitive_callers(graph, "foo")
        assert len(result) == 1
        assert result[0]["name"] == "bar"
        assert result[0]["distance"] == 1

    def test_transitive_chain(self):
        graph = MagicMock()
        foo = _make_func("foo")
        bar = _make_func("bar", "b.py", 5)
        baz = _make_func("baz", "c.py", 10)
        graph.resolve_targets.return_value = [foo]
        callers_map = {foo: [bar], bar: [baz], baz: []}
        graph.caller_refs_of.side_effect = lambda f: callers_map.get(f, [])
        result = _compute_transitive_callers(graph, "foo", max_depth=3)
        assert len(result) == 2
        names = [r["name"] for r in result]
        assert "bar" in names
        assert "baz" in names
        for r in result:
            if r["name"] == "baz":
                assert r["distance"] == 2


class TestTransitiveCallees:
    def test_no_callees(self):
        graph = MagicMock()
        func = _make_func("foo")
        graph.resolve_targets.return_value = [func]
        graph.callee_refs_of.return_value = []
        result = _compute_transitive_callees(graph, "foo")
        assert result == []

    def test_transitive_chain(self):
        graph = MagicMock()
        foo = _make_func("foo")
        bar = _make_func("bar", "b.py", 5)
        baz = _make_func("baz", "c.py", 10)
        graph.resolve_targets.return_value = [foo]
        callees_map = {foo: [bar], bar: [baz], baz: []}
        graph.callee_refs_of.side_effect = lambda f: callees_map.get(f, [])
        result = _compute_transitive_callees(graph, "foo")
        assert len(result) == 2


class TestRiskScore:
    def test_unknown_function(self):
        graph = MagicMock()
        graph.resolve_targets.return_value = []
        result = _compute_risk_score(graph, "nonexistent")
        assert result["score"] == 0
        assert result["level"] == "unknown"

    def test_low_risk(self):
        graph = MagicMock()
        func = _make_func("isolated")
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = []
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []
        result = _compute_risk_score(graph, "isolated")
        assert result["score"] == 0
        assert result["level"] == "low"

    def test_high_risk_many_callers(self):
        graph = MagicMock()
        func = _make_func("core_fn", "core.py")
        callers = [_make_func(f"caller_{i}", f"mod_{i}.py", i) for i in range(12)]
        callees = [_make_func("dep", "dep.py")]
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = callers
        graph.callee_refs_of.return_value = callees
        graph.call_chain.return_value = [{"depth": 3}]
        result = _compute_risk_score(graph, "core_fn")
        assert result["score"] >= 40
        assert result["factors"]["fan_in"] == 12

    def test_critical_risk(self):
        graph = MagicMock()
        func = _make_func("api_handler", "api.py")
        callers = [_make_func(f"c_{i}", f"v{i}.py", i) for i in range(15)]
        callees = [_make_func(f"d_{i}", f"s{i}.py", i) for i in range(8)]
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = callers
        graph.callee_refs_of.return_value = callees
        graph.call_chain.return_value = [{"depth": 5}]
        result = _compute_risk_score(graph, "api_handler")
        assert result["score"] >= 60
        assert result["level"] == "critical"


class TestBlastRadius:
    def test_single_function_no_impact(self):
        graph = MagicMock()
        func = _make_func("solo")
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = []
        graph.callee_refs_of.return_value = []
        result = _blast_radius_for_functions(graph, ["solo"])
        assert result["total_affected_functions"] == 1
        assert result["total_files_at_risk"] == 0

    def test_propagation(self):
        graph = MagicMock()
        foo = _make_func("foo", "a.py")
        bar = _make_func("bar", "b.py")
        baz = _make_func("baz", "c.py")
        graph.resolve_targets.return_value = [foo]
        callers_map = {foo: [bar], bar: [], baz: []}
        callees_map = {foo: [baz], bar: [], baz: []}
        graph.caller_refs_of.side_effect = lambda f: callers_map.get(f, [])
        graph.callee_refs_of.side_effect = lambda f: callees_map.get(f, [])
        result = _blast_radius_for_functions(graph, ["foo"])
        assert result["total_affected_functions"] == 3
        assert result["total_files_at_risk"] == 2

    def test_respects_depth(self):
        graph = MagicMock()
        a = _make_func("a")
        b = _make_func("b", "b.py")
        c = _make_func("c", "c.py")
        graph.resolve_targets.return_value = [a]
        callers_map = {a: [b], b: [c], c: []}
        callees_map = {a: [], b: [], c: []}
        graph.caller_refs_of.side_effect = lambda f: callers_map.get(f, [])
        graph.callee_refs_of.side_effect = lambda f: callees_map.get(f, [])
        result = _blast_radius_for_functions(graph, ["a"], depth=1)
        assert result["total_affected_functions"] == 2


class TestCodeGraphImpactTool:
    def test_tool_definition(self):
        tool = CodeGraphImpactTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_impact"
        assert "blast_radius" in defn["description"]

    def test_validate_function_impact_missing_name(self):
        tool = CodeGraphImpactTool()
        with pytest.raises(ValueError, match="function_name is required"):
            tool.validate_arguments({"mode": "function_impact"})

    def test_validate_blast_radius_missing_names(self):
        tool = CodeGraphImpactTool()
        with pytest.raises(ValueError, match="function_names is required"):
            tool.validate_arguments({"mode": "blast_radius"})

    def test_validate_risk_score_missing_name(self):
        tool = CodeGraphImpactTool()
        with pytest.raises(ValueError, match="function_name is required"):
            tool.validate_arguments({"mode": "risk_score"})

    def test_validate_ok(self):
        tool = CodeGraphImpactTool()
        assert tool.validate_arguments(
            {"mode": "function_impact", "function_name": "foo"}
        )

    @pytest.mark.asyncio
    async def test_execute_risk_score(self):
        tool = CodeGraphImpactTool(project_root="/tmp/nonexistent")
        func = _make_func("test_fn", "test.py")
        mock_graph = MagicMock()
        mock_graph.resolve_targets.return_value = [func]
        mock_graph.caller_refs_of.return_value = []
        mock_graph.callee_refs_of.return_value = []
        mock_graph.call_chain.return_value = []
        tool._call_graph = mock_graph

        result = await tool.execute(
            {"mode": "risk_score", "function_name": "test_fn", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["mode"] == "risk_score"
        assert "score" in result
