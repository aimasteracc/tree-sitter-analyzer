"""Tests for Double Negation MCP Tool."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.double_negation_tool import DoubleNegationTool


@pytest.fixture
def tool() -> DoubleNegationTool:
    return DoubleNegationTool()


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8",
    )
    f.write(content)
    f.close()
    return f.name


class TestDoubleNegationTool:
    def test_tool_definition(self, tool: DoubleNegationTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "double_negation"
        assert "inputSchema" in defn

    @pytest.mark.asyncio
    async def test_execute_json_format(self, tool: DoubleNegationTool) -> None:
        path = _write_tmp("x = not not y\n", ".py")
        result = await tool.execute({"file_path": path, "format": "json"})
        assert "file" in result
        assert "total_unary_ops" in result
        assert result["issue_count"] >= 1

    @pytest.mark.asyncio
    async def test_execute_toon_format(self, tool: DoubleNegationTool) -> None:
        path = _write_tmp("x = not not y\n", ".py")
        result = await tool.execute({"file_path": path, "format": "toon"})
        assert "content" in result
        assert "total_unary_ops" in result

    @pytest.mark.asyncio
    async def test_execute_no_file_path(self, tool: DoubleNegationTool) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_nonexistent_file(self, tool: DoubleNegationTool) -> None:
        result = await tool.execute(
            {"file_path": "/nonexistent.py", "format": "json"},
        )
        assert result["total_unary_ops"] == 0

    @pytest.mark.asyncio
    async def test_execute_no_issues(self, tool: DoubleNegationTool) -> None:
        path = _write_tmp("x = not y\n", ".py")
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["issue_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_js_file(self, tool: DoubleNegationTool) -> None:
        path = _write_tmp("const x = !!y;\n", ".js")
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["issue_count"] >= 1

    def test_validate_valid(self, tool: DoubleNegationTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"})

    def test_validate_missing_file(self, tool: DoubleNegationTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_validate_bad_format(self, tool: DoubleNegationTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})
