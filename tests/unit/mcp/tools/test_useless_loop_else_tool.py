"""Tests for Useless Loop Else MCP Tool."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.useless_loop_else_tool import UselessLoopElseTool


@pytest.fixture
def tool() -> UselessLoopElseTool:
    return UselessLoopElseTool()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    p = tmp_path / "test.py"
    p.write_text("for x in items:\n    pass\nelse:\n    pass\n", encoding="utf-8")
    return p


class TestUselessLoopElseToolDefinition:
    def test_tool_definition(self, tool: UselessLoopElseTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "useless_loop_else"
        assert "inputSchema" in defn


class TestUselessLoopElseToolExecution:
    @pytest.mark.asyncio
    async def test_execute_toon(
        self, tool: UselessLoopElseTool, tmp_py: Path,
    ) -> None:
        result = await tool.execute({"file_path": str(tmp_py)})
        assert "content" in result
        assert result["issue_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_json(
        self, tool: UselessLoopElseTool, tmp_py: Path,
    ) -> None:
        result = await tool.execute({
            "file_path": str(tmp_py),
            "format": "json",
        })
        assert "issues" in result
        assert result["issue_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_no_file_path(self, tool: UselessLoopElseTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_no_issues(
        self, tool: UselessLoopElseTool, tmp_path: Path,
    ) -> None:
        p = tmp_path / "clean.py"
        p.write_text("for x in items:\n    if x:\n        break\nelse:\n    pass\n", encoding="utf-8")
        result = await tool.execute({"file_path": str(p)})
        assert result["issue_count"] == 0
