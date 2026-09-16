"""Certified navigation failures must retain the ordinary query fallback."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

import pytest

from tree_sitter_analyzer.mcp.tools.call_path_tool import CodeGraphCallPathTool
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.codegraph_navigate_tool import CodeGraphNavigateTool
from tree_sitter_analyzer.mcp.tools.symbol_search_tool import CodeGraphSymbolSearchTool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_type", "arguments"),
    [
        (CodeGraphCallersTool, {"function_name": "target"}),
        (CodeGraphCalleesTool, {"function_name": "target"}),
        (
            CodeGraphCallPathTool,
            {"source_function": "source", "target_function": "target"},
        ),
        (CodeGraphNavigateTool, {"symbol": "target"}),
    ],
)
async def test_sqlite_deadline_failure_falls_back_to_uncertified_query(
    tmp_path, monkeypatch, tool_type, arguments
):
    # PR #1491：SQLite deadline 例外は正文だけを降格し、公開 tool を失敗させない。
    import tree_sitter_analyzer.index_snapshot as snapshot_owner

    @contextmanager
    def interrupted(_project_root):
        raise sqlite3.OperationalError("interrupted")
        yield None

    tool = tool_type(str(tmp_path))
    calls = []

    async def execute_bound(received, bound_cache, source_reader):
        calls.append((received, bound_cache, source_reader))
        return {"success": True, "fallback": True}

    monkeypatch.setattr(snapshot_owner, "certified_index_read", interrupted)
    monkeypatch.setattr(tool, "_execute_bound", execute_bound)

    result = await tool.execute(arguments)

    assert result == {"success": True, "fallback": True}
    assert calls == [(arguments, None, None)]


def test_symbol_search_source_demotion_preserves_non_body_guidance():
    # PR #1491：正文被撤回时，和正文无关的分页提示仍应保留。
    result = {
        "results": [{"name": "target", "code": "x", "body": {"content": "x"}}],
        "next_step": "Raise limit to inspect more coordinates.",
    }

    CodeGraphSymbolSearchTool._remove_unbound_source(result)

    assert result["results"] == [{"name": "target"}]
    assert result["next_step"] == "Raise limit to inspect more coordinates."
