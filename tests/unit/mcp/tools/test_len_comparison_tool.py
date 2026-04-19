"""Tests for Len-Comparison MCP Tool."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.len_comparison_tool import LenComparisonTool


@pytest.fixture
def tool() -> LenComparisonTool:
    return LenComparisonTool()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    p = tmp_path / "test.py"
    p.write_text("if len(items) == 0:\n    pass\n", encoding="utf-8")
    return p


class TestLenComparisonToolDefinition:
    def test_tool_definition(self, tool: LenComparisonTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "len_comparison"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_description_contains_languages(self, tool: LenComparisonTool) -> None:
        defn = tool.get_tool_definition()
        assert "Python" in defn["description"]
        assert "JavaScript" in defn["description"]


class TestLenComparisonToolExecution:
    @pytest.mark.asyncio
    async def test_execute_toon_format(
        self, tool: LenComparisonTool, tmp_py: Path,
    ) -> None:
        result = await tool.execute({"file_path": str(tmp_py)})
        assert "content" in result
        assert result["issue_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_json_format(
        self, tool: LenComparisonTool, tmp_py: Path,
    ) -> None:
        result = await tool.execute({
            "file_path": str(tmp_py),
            "format": "json",
        })
        assert "issues" in result
        assert result["issue_count"] == 1
        assert len(result["issues"]) == 1

    @pytest.mark.asyncio
    async def test_execute_no_file_path(self, tool: LenComparisonTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_no_issues(
        self, tool: LenComparisonTool, tmp_path: Path,
    ) -> None:
        p = tmp_path / "clean.py"
        p.write_text("if items:\n    pass\n", encoding="utf-8")
        result = await tool.execute({"file_path": str(p)})
        assert result["issue_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_multiple_issues(
        self, tool: LenComparisonTool, tmp_path: Path,
    ) -> None:
        p = tmp_path / "multi.py"
        p.write_text(textwrap.dedent("""\
            if len(a) == 0:
                pass
            if len(b) > 0:
                pass
        """), encoding="utf-8")
        result = await tool.execute({
            "file_path": str(p),
            "format": "json",
        })
        assert result["issue_count"] == 2
