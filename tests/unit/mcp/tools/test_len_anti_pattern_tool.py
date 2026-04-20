"""Tests for Len Anti-pattern MCP Tool (merged len_comparison + range_len)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.len_anti_pattern_tool import LenAntiPatternTool


@pytest.fixture
def tool() -> LenAntiPatternTool:
    return LenAntiPatternTool()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    p = tmp_path / "test.py"
    p.write_text(textwrap.dedent("""\
        if len(items) == 0:
            pass
        for i in range(len(items)):
            pass
    """), encoding="utf-8")
    return p


class TestLenAntiPatternToolDefinition:
    def test_tool_definition(self, tool: LenAntiPatternTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "len_anti_pattern"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_description_contains_languages(self, tool: LenAntiPatternTool) -> None:
        defn = tool.get_tool_definition()
        assert "Python" in defn["description"]
        assert "JavaScript" in defn["description"]

    def test_description_contains_issue_types(self, tool: LenAntiPatternTool) -> None:
        defn = tool.get_tool_definition()
        assert "len_eq_zero" in defn["description"]
        assert "range_len_for" in defn["description"]


class TestLenAntiPatternToolExecution:
    @pytest.mark.asyncio
    async def test_execute_toon_format(
        self, tool: LenAntiPatternTool, tmp_py: Path,
    ) -> None:
        result = await tool.execute({"file_path": str(tmp_py)})
        assert "content" in result
        assert result["issue_count"] == 2

    @pytest.mark.asyncio
    async def test_execute_json_format(
        self, tool: LenAntiPatternTool, tmp_py: Path,
    ) -> None:
        result = await tool.execute({
            "file_path": str(tmp_py),
            "format": "json",
        })
        assert "issues" in result
        assert result["issue_count"] == 2
        assert len(result["issues"]) == 2

    @pytest.mark.asyncio
    async def test_execute_no_file_path(self, tool: LenAntiPatternTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_no_issues(
        self, tool: LenAntiPatternTool, tmp_path: Path,
    ) -> None:
        p = tmp_path / "clean.py"
        p.write_text("if items:\n    for item in items:\n        pass\n", encoding="utf-8")
        result = await tool.execute({"file_path": str(p)})
        assert result["issue_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_len_comparison_only(
        self, tool: LenAntiPatternTool, tmp_path: Path,
    ) -> None:
        p = tmp_path / "comp.py"
        p.write_text("if len(x) > 0:\n    pass\n", encoding="utf-8")
        result = await tool.execute({
            "file_path": str(p),
            "format": "json",
        })
        assert result["issue_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_range_len_only(
        self, tool: LenAntiPatternTool, tmp_path: Path,
    ) -> None:
        p = tmp_path / "range.py"
        p.write_text("for i in range(len(x)):\n    pass\n", encoding="utf-8")
        result = await tool.execute({
            "file_path": str(p),
            "format": "json",
        })
        assert result["issue_count"] == 1
