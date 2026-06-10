"""Tests for CodeGraph Impact tool — function blast radius analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.mcp.tools.codegraph_impact_tool import (
    _MAX_LISTED,
    CodeGraphImpactTool,
    _blast_radius_for_functions,
    _compute_risk_score,
    _compute_transitive_callees,
    _compute_transitive_callers,
    _partition_refs,
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
        # fan_in=12(+35) + cross_file=12(+25) + fan_out=1(+0) + cross_callees=1(+5) + depth=3(+0) = 65
        assert result["score"] == 65
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
        # fan_in=15(+35) + cross_file=15(+25) + fan_out=8(+10) + cross_callees=8(+15) + depth=5(+5) = 90
        assert result["score"] == 90
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
        with patch.object(tool, "get_call_graph", return_value=mock_graph):
            result = await tool.execute(
                {
                    "mode": "risk_score",
                    "function_name": "test_fn",
                    "output_format": "json",
                }
            )
        assert result["success"] is True
        assert result["mode"] == "risk_score"
        assert "score" in result


class TestFunctionImpactListCap:
    """Wave 1b (audit nav-08): function_impact must cap the EMITTED caller/callee
    lists so a hub function does not serialise a ~70k-char payload that overflows
    the tool-result token budget. Full counts + a truncation flag are kept."""

    def _graph_with_n_direct_callers(self, n: int) -> MagicMock:
        graph = MagicMock()
        hub = _make_func("hub")
        graph.resolve_targets.return_value = [hub]
        # direct_callers / direct_callees come from callers_of/callees_of (dicts).
        graph.callers_of.return_value = [
            {"name": f"c{i}", "file": f"f{i}.py", "line": i} for i in range(n)
        ]
        graph.callees_of.return_value = []
        # transitive + risk walk the *_refs_of edges — keep them empty/minimal.
        graph.caller_refs_of.return_value = []
        graph.callee_refs_of.return_value = []
        return graph

    def test_direct_callers_capped_but_count_is_full(self):
        tool = CodeGraphImpactTool()
        graph = self._graph_with_n_direct_callers(_MAX_LISTED + 10)
        result = tool._function_impact(graph, "hub", None, 5)
        assert len(result["direct_callers"]) == _MAX_LISTED
        assert result["direct_caller_count"] == _MAX_LISTED + 10
        assert result["lists_truncated"] is True
        assert result["listed_cap"] == _MAX_LISTED

    def test_small_lists_not_truncated(self):
        tool = CodeGraphImpactTool()
        graph = self._graph_with_n_direct_callers(3)
        result = tool._function_impact(graph, "hub", None, 5)
        assert len(result["direct_callers"]) == 3
        assert result["direct_caller_count"] == 3
        assert result["lists_truncated"] is False


class TestImpactTestPartition:
    """RFC-0014 Phase A: DF-16 test-noise partition for nav action=impact."""

    def test_partition_refs_splits_prod_and_test(self):
        """_partition_refs correctly classifies by is_test_file path."""
        prod_ref = _make_func("real_caller", "src/other.py")
        test_ref = _make_func("test_foo", "tests/test_mod.py")
        prod, test = _partition_refs([prod_ref, test_ref])
        assert len(prod) == 1
        assert len(test) == 1
        assert prod[0].file_path == "src/other.py"
        assert test[0].file_path == "tests/test_mod.py"

    def test_partition_refs_empty_list(self):
        """Empty list → both buckets empty."""
        prod, test = _partition_refs([])
        assert prod == []
        assert test == []

    def test_risk_score_excludes_test_callers(self):
        """12 test + 1 prod caller → fan_in=1, score=0, level='low'."""
        graph = MagicMock()
        func = _make_func("my_fn", "src/mymodule.py")
        test_callers = [
            _make_func(f"test_{i}", "tests/test_mod.py", i) for i in range(12)
        ]
        prod_callers = [_make_func("real_caller", "src/other.py")]
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = test_callers + prod_callers
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []
        result = _compute_risk_score(graph, "my_fn")
        assert result["score"] == 0
        assert result["level"] == "low"
        assert result["tests"]["test_callers_count"] == 12
        assert result["tests"]["test_callees_count"] == 0

    def test_risk_score_all_prod_callers_score_60(self):
        """12 prod callers from 12 distinct files → score==60 exactly.

        fan_in=12(+35) + cross_file=12(+25) + fan_out=0(+0) + cross_callees=0(+0) +
        depth=0(+0) = 60. Tests bucket has count 0.
        """
        graph = MagicMock()
        func = _make_func("core_fn", "src/core.py")
        callers = [_make_func(f"c_{i}", f"src/mod_{i}.py", i) for i in range(12)]
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = callers
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []
        result = _compute_risk_score(graph, "core_fn")
        assert result["score"] == 60
        assert result["level"] == "critical"
        assert result["tests"]["test_callers_count"] == 0

    def test_df16_scenario(self):
        """DF-16: 16 test + 2 prod callers → partitioned score == 0, level 'low'.

        Unpartitioned would give fan_in=18(+35) → score 35 = 'high'.
        Partitioned: fan_in=2(<3→+0), cross_file=1(<2→+0), fan_out=0→0 = score 0.
        """
        graph = MagicMock()
        func = _make_func("target_fn", "src/target.py")
        test_callers = [
            _make_func(f"test_fake_{i}", "tests/test_fakes.py", i) for i in range(16)
        ]
        prod_callers = [
            _make_func("real_a", "src/module_a.py"),
            _make_func("real_b", "src/module_a.py"),  # same file: cross_file=1
        ]
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = test_callers + prod_callers
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []
        result = _compute_risk_score(graph, "target_fn")
        # prod fan_in=2(<3→+0), prod cross_file=1(<2→+0), fan_out=0 → score=0
        assert result["score"] == 0
        assert result["level"] == "low"
        assert result["tests"]["test_callers_count"] == 16
        assert result["tests"]["test_callees_count"] == 0

    def test_tests_bucket_always_present_when_zero(self):
        """tests dict always present; both counts == 0 for isolated function."""
        graph = MagicMock()
        func = _make_func("isolated", "src/foo.py")
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = []
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []
        result = _compute_risk_score(graph, "isolated")
        assert "tests" in result
        assert result["tests"]["test_callers_count"] == 0
        assert result["tests"]["test_callees_count"] == 0

    def test_include_tests_false_omits_file_lists(self):
        """Default (include_tests=False): tests bucket has counts only, no file lists."""
        graph = MagicMock()
        func = _make_func("fn", "src/a.py")
        test_callers = [_make_func("t1", "tests/test_a.py")]
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = test_callers
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []
        result = _compute_risk_score(graph, "fn", include_tests=False)
        assert result["tests"]["test_callers_count"] == 1
        assert "test_caller_files" not in result["tests"]
        assert "test_callee_files" not in result["tests"]

    def test_include_tests_true_adds_file_lists(self):
        """include_tests=True: file lists appear, sorted and deduplicated."""
        graph = MagicMock()
        func = _make_func("fn", "src/a.py")
        test_callers = [
            _make_func("t1", "tests/test_a.py"),
            _make_func("t2", "tests/test_a.py"),  # same file — should dedup
            _make_func("t3", "tests/test_b.py"),
        ]
        test_callees = [_make_func("mock_dep", "tests/fixtures/mock.py")]
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = test_callers
        graph.callee_refs_of.return_value = test_callees
        graph.call_chain.return_value = []
        result = _compute_risk_score(graph, "fn", include_tests=True)
        assert result["tests"]["test_callers_count"] == 3
        assert result["tests"]["test_callees_count"] == 1
        assert result["tests"]["test_caller_files"] == [
            "tests/test_a.py",
            "tests/test_b.py",
        ]
        assert result["tests"]["test_callee_files"] == ["tests/fixtures/mock.py"]

    def test_schema_declares_include_tests(self):
        """include_tests must be in schema properties (P1-2: _project_args whitelist)."""
        tool = CodeGraphImpactTool()
        schema = tool.get_tool_schema()
        assert "include_tests" in schema["properties"]
        # Must NOT be in required (the required-trap)
        assert "include_tests" not in schema.get("required", [])

    def test_transitive_callers_filters_tests_by_default(self):
        """_compute_transitive_callers(include_tests=False) excludes test-file entries."""
        graph = MagicMock()
        func = _make_func("fn", "src/a.py")
        prod_caller = _make_func("prod_c", "src/b.py")
        test_caller = _make_func("test_c", "tests/test_a.py")
        graph.resolve_targets.return_value = [func]
        callers_map = {
            func: [prod_caller, test_caller],
            prod_caller: [],
            test_caller: [],
        }
        graph.caller_refs_of.side_effect = lambda f: callers_map.get(f, [])
        result = _compute_transitive_callers(graph, "fn", include_tests=False)
        assert len(result) == 1
        assert result[0]["name"] == "prod_c"

    def test_transitive_callers_include_tests_true(self):
        """_compute_transitive_callers(include_tests=True) includes test-file entries."""
        graph = MagicMock()
        func = _make_func("fn", "src/a.py")
        prod_caller = _make_func("prod_c", "src/b.py")
        test_caller = _make_func("test_c", "tests/test_a.py")
        graph.resolve_targets.return_value = [func]
        callers_map = {
            func: [prod_caller, test_caller],
            prod_caller: [],
            test_caller: [],
        }
        graph.caller_refs_of.side_effect = lambda f: callers_map.get(f, [])
        result = _compute_transitive_callers(graph, "fn", include_tests=True)
        assert len(result) == 2

    def test_transitive_callees_filters_tests_by_default(self):
        """_compute_transitive_callees(include_tests=False) excludes test-file entries."""
        graph = MagicMock()
        func = _make_func("fn", "src/a.py")
        prod_callee = _make_func("real_dep", "src/c.py")
        test_callee = _make_func("fake_dep", "tests/fixtures/mock.py")
        graph.resolve_targets.return_value = [func]
        callees_map = {
            func: [prod_callee, test_callee],
            prod_callee: [],
            test_callee: [],
        }
        graph.callee_refs_of.side_effect = lambda f: callees_map.get(f, [])
        result = _compute_transitive_callees(graph, "fn", include_tests=False)
        assert len(result) == 1
        assert result[0]["name"] == "real_dep"
