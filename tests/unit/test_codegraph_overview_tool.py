"""Unit tests for codegraph_overview_tool.py — CodeGraphOverviewTool MCP tool."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.mcp.tools.codegraph_overview_tool import (
    CodeGraphOverviewTool,
    _compute_depth_distribution,
    _compute_module_coupling,
    _find_dead_code,
    _find_entry_points,
    _find_hub_functions,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "call_graph"
PY_PROJECT = str(FIXTURES_DIR / "python_project")


@pytest.fixture
def tool():
    return CodeGraphOverviewTool(PY_PROJECT)


async def _execute(tool, args=None):
    return await tool.execute(args or {"output_format": "json"})


# ============================================================
# Initialization and configuration
# ============================================================


class TestCodeGraphOverviewToolInit:
    def test_init_with_project_root(self):
        t = CodeGraphOverviewTool(PY_PROJECT)
        assert t.project_root == PY_PROJECT
        assert not t.call_graph_initialized

    def test_init_without_project_root(self):
        t = CodeGraphOverviewTool()
        assert t.project_root is None

    def test_set_project_path_resets_graph(self, tool):
        tool.get_call_graph()
        assert tool.call_graph_initialized
        tool.set_project_path(PY_PROJECT)
        assert not tool.call_graph_initialized

    def test_get_call_graph_caches(self, tool):
        cg1 = tool.get_call_graph()
        cg2 = tool.get_call_graph()
        assert cg1 is cg2

    def test_get_call_graph_raises_without_root(self):
        t = CodeGraphOverviewTool()
        with pytest.raises(ValueError, match="Project root not set"):
            t.get_call_graph()


# ============================================================
# Tool definition and schema
# ============================================================


class TestCodeGraphOverviewToolDefinition:
    def test_get_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_overview"
        assert "entry points" in defn["description"].lower()
        assert "dead code" in defn["description"].lower()
        assert "inputSchema" in defn

    def test_get_tool_schema_has_required_properties(self, tool):
        schema = tool.get_tool_schema()
        props = schema["properties"]
        assert "max_entry_points" in props
        assert "max_hubs" in props
        assert "max_dead" in props
        assert "max_coupled_files" in props
        assert "output_format" in props

    def test_validate_arguments_always_true(self, tool):
        assert tool.validate_arguments({}) is True
        assert tool.validate_arguments({"max_entry_points": 5}) is True


# ============================================================
# Execute — integration with call graph
# ============================================================


class TestCodeGraphOverviewToolExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_success(self, tool):
        result = await _execute(tool)
        assert result["success"] is True
        assert result["project_root"] == PY_PROJECT

    @pytest.mark.asyncio
    async def test_execute_summary_fields(self, tool):
        result = await _execute(tool)
        summary = result["summary"]
        assert "function_count" in summary
        assert "call_edge_count" in summary
        assert "file_count" in summary
        assert "entry_point_count" in summary
        assert "dead_code_count" in summary
        assert "max_call_depth" in summary
        assert summary["function_count"] > 0

    @pytest.mark.asyncio
    async def test_execute_entry_points(self, tool):
        result = await _execute(tool, {"max_entry_points": 5, "output_format": "json"})
        entry_points = result["entry_points"]
        assert isinstance(entry_points, list)
        assert len(entry_points) <= 5
        if entry_points:
            ep = entry_points[0]
            assert "name" in ep
            assert "file" in ep
            assert "line" in ep
            assert "callee_count" in ep

    @pytest.mark.asyncio
    async def test_execute_hub_functions(self, tool):
        result = await _execute(tool, {"max_hubs": 3, "output_format": "json"})
        hubs = result["hub_functions"]
        assert isinstance(hubs, list)
        assert len(hubs) <= 3

    @pytest.mark.asyncio
    async def test_execute_dead_code(self, tool):
        result = await _execute(tool, {"max_dead": 5, "output_format": "json"})
        dead = result["dead_code"]
        assert isinstance(dead, list)
        assert len(dead) <= 5

    @pytest.mark.asyncio
    async def test_execute_depth_distribution(self, tool):
        result = await _execute(tool)
        depth = result["call_depth_distribution"]
        assert "max_depth" in depth
        assert "avg_depth" in depth
        assert "distribution" in depth

    @pytest.mark.asyncio
    async def test_execute_module_coupling(self, tool):
        result = await _execute(tool, {"max_coupled_files": 3, "output_format": "json"})
        coupling = result["module_coupling"]
        assert isinstance(coupling, list)
        assert len(coupling) <= 3

    @pytest.mark.asyncio
    async def test_execute_toon_format(self, tool):
        result = await _execute(tool, {"output_format": "toon"})
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_empty_project(self, tmp_path):
        empty_dir = str(tmp_path / "empty")
        import os

        os.makedirs(empty_dir)
        t = CodeGraphOverviewTool(empty_dir)
        result = await _execute(t)
        assert result["success"] is True
        assert result["summary"]["function_count"] == 0


# ============================================================
# Standalone helper functions
# ============================================================


class TestFindEntryPoints:
    def test_finds_entry_points(self, tool):
        graph = tool._get_call_graph()
        graph.build()
        eps = _find_entry_points(graph, 100)
        assert isinstance(eps, list)
        for ep in eps:
            assert "name" in ep
            assert "callee_count" in ep

    def test_respects_limit(self, tool):
        graph = tool._get_call_graph()
        graph.build()
        eps = _find_entry_points(graph, 1)
        assert len(eps) <= 1


class TestFindHubFunctions:
    def test_hubs_have_min_three_callers(self, tool):
        graph = tool._get_call_graph()
        graph.build()
        hubs = _find_hub_functions(graph, 100)
        for hub in hubs:
            assert hub["caller_count"] >= 3

    def test_hub_caller_files_are_sampled(self):
        hub = FunctionRef("hub.py", "hub", 1, "python")
        callers = [
            FunctionRef(f"caller_{i}.py", f"caller_{i}", i + 1, "python")
            for i in range(40)
        ]
        graph = MagicMock()
        graph.function_refs.return_value = [hub, *callers]
        callers_map = {hub: callers, **{c: [] for c in callers}}
        graph.caller_refs_of.side_effect = lambda f: callers_map.get(f, [])

        hubs = _find_hub_functions(graph, 10)

        assert hubs[0]["caller_count"] == 40
        assert hubs[0]["caller_file_count"] == 40
        assert len(hubs[0]["caller_files"]) == 25
        assert hubs[0]["caller_files_truncated"] is True


class TestFindDeadCode:
    def test_dead_code_has_no_callers_or_callees(self, tool):
        graph = tool._get_call_graph()
        graph.build()
        dead = _find_dead_code(graph, 100)
        for d in dead:
            assert "name" in d
            assert "file" in d


class TestComputeDepthDistribution:
    def test_returns_expected_keys(self, tool):
        graph = tool._get_call_graph()
        graph.build()
        dist = _compute_depth_distribution(graph)
        assert "max_depth" in dist
        assert "avg_depth" in dist
        assert "distribution" in dist
        assert dist["max_depth"] >= 0

    def test_handles_cycles_without_recursive_explosion(self):
        a = FunctionRef("graph.py", "a", 1, "python")
        b = FunctionRef("graph.py", "b", 2, "python")
        c = FunctionRef("graph.py", "c", 3, "python")
        d = FunctionRef("graph.py", "d", 4, "python")
        callees_map = {a: [b, c], b: [d], c: [d], d: [b]}
        graph = MagicMock()
        graph.function_refs.return_value = [a, b, c, d]
        graph.callee_refs_of.side_effect = lambda f: callees_map.get(f, [])

        dist = _compute_depth_distribution(graph)

        assert dist["depth_cap"] == 10
        assert dist["max_depth"] <= dist["depth_cap"]
        assert sum(dist["distribution"].values()) == 4

    def test_uses_function_references_not_ambiguous_names(self):
        root = FunctionRef("root.py", "run", 1, "python")
        unrelated = FunctionRef("a.py", "handle", 1, "python")
        target = FunctionRef("b.py", "handle", 1, "python")
        leaf = FunctionRef("b.py", "leaf", 2, "python")
        callees_map = {root: [target], target: [leaf]}
        graph = MagicMock()
        graph.function_refs.return_value = [root, unrelated, target, leaf]
        graph.callee_refs_of.side_effect = lambda f: callees_map.get(f, [])

        dist = _compute_depth_distribution(graph)

        assert dist["distribution"]["depth_0"] == 2
        assert dist["distribution"]["depth_1"] == 1
        assert dist["distribution"]["depth_2"] == 1

    def test_caps_deep_call_chains(self):
        funcs = [FunctionRef("chain.py", f"f{i}", i + 1, "python") for i in range(13)]
        callees_map = {funcs[i]: [funcs[i + 1]] for i in range(len(funcs) - 1)}
        graph = MagicMock()
        graph.function_refs.return_value = funcs
        graph.callee_refs_of.side_effect = lambda f: callees_map.get(f, [])

        dist = _compute_depth_distribution(graph)

        assert dist["max_depth"] == dist["depth_cap"]
        assert dist["capped"] is True
        assert dist["distribution"]["depth_10+"] >= 1


class TestComputeModuleCoupling:
    def test_coupling_cross_file_only(self, tool):
        graph = tool._get_call_graph()
        graph.build()
        coupling = _compute_module_coupling(graph, 100)
        for c in coupling:
            assert c["outgoing_calls"] > 0
            assert c["target_files"] > 0
