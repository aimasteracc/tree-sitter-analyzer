"""Tests for Commented-Out Code MCP Tool."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.commented_code_tool import CommentedCodeTool


@pytest.fixture
def tool() -> CommentedCodeTool:
    return CommentedCodeTool()


class TestCommentedCodeToolBasic:
    def test_init(self, tool: CommentedCodeTool) -> None:
        assert tool is not None

    def test_get_tool_definition(self, tool: CommentedCodeTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "commented_code"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_validate_schema(self, tool: CommentedCodeTool) -> None:
        defn = tool.get_tool_definition()
        schema = defn["inputSchema"]
        assert "file_path" in schema["properties"]
        assert "format" in schema["properties"]


class TestCommentedCodeToolExecute:
    @pytest.mark.asyncio
    async def test_toon_format(self, tool: CommentedCodeTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write('# result = process(data)\n')
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "toon"})
        assert "content" in result
        assert result["total_count"] == 1

    @pytest.mark.asyncio
    async def test_json_format(self, tool: CommentedCodeTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write('# import os\n')
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "json"})
        assert "total_count" in result
        assert result["total_count"] == 1

    @pytest.mark.asyncio
    async def test_no_file_path(self, tool: CommentedCodeTool) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tool: CommentedCodeTool) -> None:
        result = await tool.execute({"file_path": "/nonexistent.py", "format": "json"})
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_clean_file_toon(self, tool: CommentedCodeTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("# This is a normal comment\nimport logging\n")
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "toon"})
        assert "content" in result
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_js_file(self, tool: CommentedCodeTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write('// const x = compute(y);\n')
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "json"})
        assert result["total_count"] >= 1

    @pytest.mark.asyncio
    async def test_java_file(self, tool: CommentedCodeTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write('// public void process() { }\n')
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "json"})
        assert result["total_count"] >= 1

    @pytest.mark.asyncio
    async def test_go_file(self, tool: CommentedCodeTool) -> None:
        with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
            f.write('package main\n// result := compute(input)\nfunc main() {}\n')
            f.flush()
            result = await tool.execute({"file_path": f.name, "format": "json"})
        assert result["total_count"] >= 1
