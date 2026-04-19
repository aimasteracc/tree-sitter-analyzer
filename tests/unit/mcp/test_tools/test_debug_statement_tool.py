"""Tests for Debug Statement MCP Tool."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.debug_statement_tool import DebugStatementTool


@pytest.fixture
def tool() -> DebugStatementTool:
    return DebugStatementTool()


class TestDebugStatementToolBasic:
    def test_init(self, tool: DebugStatementTool) -> None:
        assert tool is not None

    def test_get_tool_definition(self, tool: DebugStatementTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "debug_statement"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_validate_valid(self, tool: DebugStatementTool) -> None:
        defn = tool.get_tool_definition()
        schema = defn["inputSchema"]
        assert "file_path" in schema["properties"]
        assert "format" in schema["properties"]


class TestDebugStatementToolExecute:
    @pytest.mark.asyncio
    async def test_toon_format(self, tool: DebugStatementTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write('print("hello")\n')
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "toon"})
        assert "content" in result

    @pytest.mark.asyncio
    async def test_json_format(self, tool: DebugStatementTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write('print("hello")\n')
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "json"})
        assert "total_count" in result
        assert result["total_count"] == 1

    @pytest.mark.asyncio
    async def test_no_file_path(self, tool: DebugStatementTool) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tool: DebugStatementTool) -> None:
        result = await tool.execute({"file_path": "/nonexistent.py", "format": "json"})
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_clean_file_toon(self, tool: DebugStatementTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("import logging\nlogger = logging.getLogger(__name__)\n")
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "toon"})
        assert "content" in result

    @pytest.mark.asyncio
    async def test_js_file(self, tool: DebugStatementTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write('console.log("debug");\n')
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "json"})
        assert result["total_count"] == 1

    @pytest.mark.asyncio
    async def test_java_file(self, tool: DebugStatementTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write('public class T { void f() { System.out.println("d"); } }\n')
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "json"})
        assert result["total_count"] == 1

    @pytest.mark.asyncio
    async def test_go_file(self, tool: DebugStatementTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
            f.write('package main\nimport "fmt"\nfunc main() { fmt.Println("d") }\n')
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "json"})
        assert result["total_count"] == 1
