"""Tests for FloatEqualityTool MCP tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.float_equality_tool import FloatEqualityTool


@pytest.fixture
def tool() -> FloatEqualityTool:
    return FloatEqualityTool()


def _write_tmp(content: str, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="test_fe_tool_")
    with open(fd, "w") as f:
        f.write(content)
    return path


class TestFloatEqualityToolDefinition:
    def test_tool_name(self, tool: FloatEqualityTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "float_equality"

    def test_tool_has_input_schema(self, tool: FloatEqualityTool) -> None:
        defn = tool.get_tool_definition()
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]


@pytest.mark.asyncio
class TestFloatEqualityToolExecute:
    async def test_execute_python_float_eq(self, tool: FloatEqualityTool) -> None:
        path = _write_tmp("x == 0.1\n", ".py")
        try:
            result = await tool.execute({"file_path": path})
            assert result["issue_count"] == 1
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_no_issues(self, tool: FloatEqualityTool) -> None:
        path = _write_tmp("x == 5\n", ".py")
        try:
            result = await tool.execute({"file_path": path})
            assert result["issue_count"] == 0
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_missing_path(self, tool: FloatEqualityTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    async def test_execute_json_format(self, tool: FloatEqualityTool) -> None:
        path = _write_tmp("x == 3.14\n", ".py")
        try:
            result = await tool.execute({"file_path": path, "format": "json"})
            assert "file" in result
            assert result["issue_count"] == 1
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_toon_format(self, tool: FloatEqualityTool) -> None:
        path = _write_tmp("x != 2.5\n", ".py")
        try:
            result = await tool.execute({"file_path": path, "format": "toon"})
            assert "content" in result
            assert result["issue_count"] == 1
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_js_float_eq(self, tool: FloatEqualityTool) -> None:
        path = _write_tmp("x === 0.1\n", ".js")
        try:
            result = await tool.execute({"file_path": path})
            assert result["issue_count"] == 1
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_go_float_eq(self, tool: FloatEqualityTool) -> None:
        path = _write_tmp("if x == 3.14 {\n}\n", ".go")
        try:
            result = await tool.execute({"file_path": path})
            assert result["issue_count"] == 1
        finally:
            Path(path).unlink(missing_ok=True)
