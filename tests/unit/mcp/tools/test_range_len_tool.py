"""Tests for Range-Len MCP Tool."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.range_len_tool import RangeLenTool


@pytest.fixture
def tool() -> RangeLenTool:
    return RangeLenTool()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    p = tmp_path / "test.py"
    p.write_text("for i in range(len(items)):\n    pass\n", encoding="utf-8")
    return p


class TestRangeLenToolDefinition:
    def test_tool_definition(self, tool: RangeLenTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "range_len"
        assert "inputSchema" in defn

    def test_description_mentions_python(self, tool: RangeLenTool) -> None:
        defn = tool.get_tool_definition()
        assert "Python" in defn["description"]


class TestRangeLenToolExecution:
    @pytest.mark.asyncio
    async def test_execute_toon(
        self, tool: RangeLenTool, tmp_py: Path,
    ) -> None:
        result = await tool.execute({"file_path": str(tmp_py)})
        assert "content" in result
        assert result["issue_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_json(
        self, tool: RangeLenTool, tmp_py: Path,
    ) -> None:
        result = await tool.execute({
            "file_path": str(tmp_py),
            "format": "json",
        })
        assert "issues" in result
        assert result["issue_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_no_file_path(self, tool: RangeLenTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_no_issues(
        self, tool: RangeLenTool, tmp_path: Path,
    ) -> None:
        p = tmp_path / "clean.py"
        p.write_text("for item in items:\n    pass\n", encoding="utf-8")
        result = await tool.execute({"file_path": str(p)})
        assert result["issue_count"] == 0
