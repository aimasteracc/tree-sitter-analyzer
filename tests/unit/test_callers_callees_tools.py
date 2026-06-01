#!/usr/bin/env python3
"""Tests for codegraph_callers and codegraph_callees dedicated MCP tools."""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.codegraph_relation_tool import (
    CodeGraphRelationToolMixin,
)

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


@pytest.fixture
def callers_tool():
    return CodeGraphCallersTool(_PROJECT_ROOT)


@pytest.fixture
def callees_tool():
    return CodeGraphCalleesTool(_PROJECT_ROOT)


@pytest.fixture
def tiny_project_root(tmp_path):
    (tmp_path / "sample.py").write_text(
        "def foo():\n    bar()\n\ndef bar():\n    return 1\n",
        encoding="utf-8",
    )
    return str(tmp_path)


class TestCodeGraphCallersTool:
    def test_tool_definition(self, callers_tool):
        defn = callers_tool.get_tool_definition()
        assert defn["name"] == "codegraph_callers"
        assert "caller" in defn["description"].lower()
        assert "function_name" in defn["inputSchema"]["properties"]
        assert "function_name" in defn["inputSchema"]["required"]

    def test_validate_missing_function_name(self, callers_tool):
        with pytest.raises(ValueError, match="function_name is required"):
            callers_tool.validate_arguments({})

    def test_validate_with_function_name(self, callers_tool):
        assert callers_tool.validate_arguments({"function_name": "main"})

    @pytest.mark.asyncio
    @pytest.mark.slow_ok  # scans full project graph; ~12s on CI hardware
    async def test_execute_returns_callers(self, callers_tool):
        result = await callers_tool.execute(
            {"function_name": "_walk_tree", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["function"] == "_walk_tree"
        assert "callers" in result
        assert "caller_count" in result
        assert isinstance(result["callers"], list)

    @pytest.mark.asyncio
    @pytest.mark.slow_ok  # clean Py3.13 CI may build the full project graph before SQL cache exists
    async def test_execute_with_file_path(self, callers_tool):
        result = await callers_tool.execute(
            {
                "function_name": "_walk_tree",
                "file_path": "tree_sitter_analyzer/call_graph.py",
                "output_format": "json",
            }
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_toon_format(self, tiny_project_root):
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        result = await callers_tool.execute(
            {"function_name": "bar", "output_format": "toon"}
        )
        assert result["success"] is True

    def test_project_root_change_resets_cache(self, tiny_project_root):
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        callers_tool.get_call_graph()
        assert callers_tool.call_graph_initialized
        callers_tool._on_project_root_changed(None)
        assert not callers_tool.call_graph_initialized

    @pytest.mark.asyncio
    async def test_no_project_root_raises(self):
        tool = CodeGraphCallersTool(None)
        with pytest.raises(ValueError, match="Project root not set"):
            await tool.execute({"function_name": "main"})


class TestCodeGraphCalleesTool:
    def test_tool_definition(self, callees_tool):
        defn = callees_tool.get_tool_definition()
        assert defn["name"] == "codegraph_callees"
        assert "callee" in defn["description"].lower()
        assert "function_name" in defn["inputSchema"]["properties"]
        assert "function_name" in defn["inputSchema"]["required"]

    def test_validate_missing_function_name(self, callees_tool):
        with pytest.raises(ValueError, match="function_name is required"):
            callees_tool.validate_arguments({})

    def test_validate_with_function_name(self, callees_tool):
        assert callees_tool.validate_arguments({"function_name": "main"})

    @pytest.mark.asyncio
    async def test_execute_returns_callees(self, tiny_project_root):
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callees_tool.execute(
            {"function_name": "foo", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["function"] == "foo"
        assert "callees" in result
        assert "callee_count" in result
        assert isinstance(result["callees"], list)

    @pytest.mark.asyncio
    async def test_execute_with_file_path(self, tiny_project_root):
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callees_tool.execute(
            {
                "function_name": "foo",
                "file_path": "sample.py",
                "output_format": "json",
            }
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_toon_format(self, tiny_project_root):
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callees_tool.execute(
            {"function_name": "foo", "output_format": "toon"}
        )
        assert result["success"] is True

    def test_project_root_change_resets_cache(self, tiny_project_root):
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        callees_tool.get_call_graph()
        assert callees_tool.call_graph_initialized
        callees_tool._on_project_root_changed(None)
        assert not callees_tool.call_graph_initialized

    @pytest.mark.asyncio
    async def test_no_project_root_raises(self):
        tool = CodeGraphCalleesTool(None)
        with pytest.raises(ValueError, match="Project root not set"):
            await tool.execute({"function_name": "main"})


class TestCallerCalleeIntegration:
    def test_callers_and_callees_share_relation_bootstrap(self):
        assert issubclass(CodeGraphCallersTool, CodeGraphRelationToolMixin)
        assert issubclass(CodeGraphCalleesTool, CodeGraphRelationToolMixin)

    @pytest.mark.asyncio
    async def test_unknown_function_returns_empty(self, tiny_project_root):
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callers_tool.execute(
            {
                "function_name": "zzz_nonexistent_function_xyz",
                "output_format": "json",
            }
        )
        assert result["success"]
        assert result["caller_count"] == 0

        result2 = await callees_tool.execute(
            {
                "function_name": "zzz_nonexistent_function_xyz",
                "output_format": "json",
            }
        )
        assert result2["success"]
        assert result2["callee_count"] == 0


class TestStaleCacheWarning:
    """Stale-cache hint surfaces in callees/callers when ≥80% of edges
    have ``callee_resolution='unknown'``. The detection helper is
    deterministic (no live cache needed)."""

    def test_helper_is_false_for_empty(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _is_stale_resolution

        assert _is_stale_resolution([]) is False

    def test_helper_is_true_when_all_unknown(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _is_stale_resolution

        entries = [{"callee_resolution": "unknown"} for _ in range(10)]
        assert _is_stale_resolution(entries) is True

    def test_helper_is_false_when_majority_resolved(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _is_stale_resolution

        # 30% unknown / 70% project → below the 80% threshold.
        entries = [{"callee_resolution": "unknown"} for _ in range(3)] + [
            {"callee_resolution": "project"} for _ in range(7)
        ]
        assert _is_stale_resolution(entries) is False

    def test_helper_trips_at_exactly_80_percent(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _is_stale_resolution

        # 8 unknown out of 10 = 80% → at threshold (inclusive).
        entries = [{"callee_resolution": "unknown"} for _ in range(8)] + [
            {"callee_resolution": "project"} for _ in range(2)
        ]
        assert _is_stale_resolution(entries) is True

    def test_warning_message_recommends_resolve_mode(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _STALE_CACHE_WARNING

        # The user-visible string must point at the right fix. Pinning
        # the substring stops a future "minor wording cleanup" from
        # dropping the actionable command.
        assert "--mode resolve" in _STALE_CACHE_WARNING
        assert "stale_cache" in _STALE_CACHE_WARNING

    @pytest.mark.asyncio
    async def test_callees_warning_omitted_when_callees_empty(
        self, tiny_project_root
    ) -> None:
        # Empty callee list: nothing to be stale about, no warning.
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callees_tool.execute(
            {"function_name": "zzz_nonexistent_function_xyz", "output_format": "json"}
        )
        assert result["callee_count"] == 0
        assert "warnings" not in result

    @pytest.mark.asyncio
    async def test_callers_warning_omitted_when_callers_empty(
        self, tiny_project_root
    ) -> None:
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        result = await callers_tool.execute(
            {"function_name": "zzz_nonexistent_function_xyz", "output_format": "json"}
        )
        assert result["caller_count"] == 0
        assert "warnings" not in result
