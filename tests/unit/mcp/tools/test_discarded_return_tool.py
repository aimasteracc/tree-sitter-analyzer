"""Tests for Discarded Return Value MCP Tool."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.discarded_return_tool import DiscardedReturnTool


@pytest.fixture
def tool() -> DiscardedReturnTool:
    return DiscardedReturnTool()


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8",
    )
    f.write(content)
    f.close()
    return f.name


class TestDiscardedReturnTool:
    def test_tool_definition(self, tool: DiscardedReturnTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "discarded_return"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_json_format(self, tool: DiscardedReturnTool) -> None:
        path = _write_tmp("compute()\n", ".py")
        result = await tool.execute({"file_path": path, "format": "json"})
        assert "file" in result
        assert "total_calls" in result
        assert result["total_calls"] >= 1

    @pytest.mark.asyncio
    async def test_execute_toon_format(self, tool: DiscardedReturnTool) -> None:
        path = _write_tmp("compute()\n", ".py")
        result = await tool.execute({"file_path": path, "format": "toon"})
        assert "content" in result
        assert "total_calls" in result

    @pytest.mark.asyncio
    async def test_execute_no_file_path(self, tool: DiscardedReturnTool) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_nonexistent_file(self, tool: DiscardedReturnTool) -> None:
        result = await tool.execute(
            {"file_path": "/nonexistent.py", "format": "json"},
        )
        assert result["total_calls"] == 0

    @pytest.mark.asyncio
    async def test_execute_no_issues(self, tool: DiscardedReturnTool) -> None:
        path = _write_tmp("x = compute()\n", ".py")
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["issue_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_js_file(self, tool: DiscardedReturnTool) -> None:
        path = _write_tmp("compute();\n", ".js")
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["total_calls"] >= 1

    def test_validate_valid(self, tool: DiscardedReturnTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"})

    def test_validate_missing_file(self, tool: DiscardedReturnTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_validate_bad_format(self, tool: DiscardedReturnTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})
