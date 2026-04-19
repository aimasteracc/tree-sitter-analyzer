"""Tests for Literal Boolean Comparison MCP Tool."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.literal_boolean_comparison_tool import (
    LiteralBooleanComparisonTool,
)


@pytest.fixture
def tool() -> LiteralBooleanComparisonTool:
    return LiteralBooleanComparisonTool()


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8",
    )
    f.write(content)
    f.close()
    return f.name


class TestLiteralBooleanComparisonTool:
    def test_tool_definition(self, tool: LiteralBooleanComparisonTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "literal_boolean_comparison"
        assert "inputSchema" in defn

    @pytest.mark.asyncio
    async def test_execute_json_format(self, tool: LiteralBooleanComparisonTool) -> None:
        path = _write_tmp("if x == True:\n    pass\n", ".py")
        result = await tool.execute({"file_path": path, "format": "json"})
        assert "file" in result
        assert "total_comparisons" in result
        assert result["issue_count"] >= 1

    @pytest.mark.asyncio
    async def test_execute_toon_format(self, tool: LiteralBooleanComparisonTool) -> None:
        path = _write_tmp("if x == None:\n    pass\n", ".py")
        result = await tool.execute({"file_path": path, "format": "toon"})
        assert "content" in result
        assert "total_comparisons" in result

    @pytest.mark.asyncio
    async def test_execute_no_file_path(self, tool: LiteralBooleanComparisonTool) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_nonexistent_file(self, tool: LiteralBooleanComparisonTool) -> None:
        result = await tool.execute(
            {"file_path": "/nonexistent.py", "format": "json"},
        )
        assert result["total_comparisons"] == 0

    @pytest.mark.asyncio
    async def test_execute_no_issues(self, tool: LiteralBooleanComparisonTool) -> None:
        path = _write_tmp("if x is None:\n    pass\n", ".py")
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["issue_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_js_file(self, tool: LiteralBooleanComparisonTool) -> None:
        path = _write_tmp("if (x == null) {}\n", ".js")
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["issue_count"] >= 1

    def test_validate_valid(self, tool: LiteralBooleanComparisonTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"})

    def test_validate_missing_file(self, tool: LiteralBooleanComparisonTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_validate_bad_format(self, tool: LiteralBooleanComparisonTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})
