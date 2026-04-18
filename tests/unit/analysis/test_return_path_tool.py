"""Tests for Return Path MCP Tool."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.return_path_tool import ReturnPathTool


@pytest.fixture
def tool() -> ReturnPathTool:
    return ReturnPathTool()


def _write_temp(code: str, suffix: str = ".py") -> str:
    with tempfile.NamedTemporaryFile(
        suffix=suffix, mode="w", delete=False
    ) as f:
        f.write(code)
        f.flush()
        return f.name


class TestToolDefinition:
    def test_name(self, tool: ReturnPathTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "return_path"

    def test_has_input_schema(self, tool: ReturnPathTool) -> None:
        defn = tool.get_tool_definition()
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_description_mentions_languages(self, tool: ReturnPathTool) -> None:
        desc = tool.get_tool_definition()["description"]
        assert "Python" in desc
        assert "JavaScript" in desc
        assert "Java" in desc
        assert "Go" in desc


class TestToolExecution:
    @pytest.mark.asyncio
    async def test_json_format(self, tool: ReturnPathTool) -> None:
        path = _write_temp(
            "def foo(x):\n"
            "    if x > 0:\n"
            "        return x\n"
            "    return\n"
        )
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["total_functions"] == 1
        assert result["functions_with_issues"] == 1
        assert len(result["issues"]) == 1

    @pytest.mark.asyncio
    async def test_toon_format(self, tool: ReturnPathTool) -> None:
        path = _write_temp(
            "def foo():\n    return 42\n"
        )
        result = await tool.execute({"file_path": path, "format": "toon"})
        assert "content" in result
        assert result["total_functions"] == 1
        assert result["functions_with_issues"] == 0

    @pytest.mark.asyncio
    async def test_no_file_path(self, tool: ReturnPathTool) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tool: ReturnPathTool) -> None:
        result = await tool.execute(
            {"file_path": "/nonexistent/test.py", "format": "json"}
        )
        assert result["total_functions"] == 0

    @pytest.mark.asyncio
    async def test_javascript_file(self, tool: ReturnPathTool) -> None:
        path = _write_temp(
            "function foo(x) {\n"
            "  if (x > 0) return x;\n"
            "  return;\n"
            "}\n",
            ".js",
        )
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["total_functions"] == 1
        assert result["functions_with_issues"] == 1

    @pytest.mark.asyncio
    async def test_java_file(self, tool: ReturnPathTool) -> None:
        path = _write_temp(
            "public class Test {\n"
            "  public int foo() { return 42; }\n"
            "}\n",
            ".java",
        )
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["total_functions"] == 1
        assert result["functions_with_issues"] == 0

    @pytest.mark.asyncio
    async def test_go_file(self, tool: ReturnPathTool) -> None:
        path = _write_temp(
            "package main\n"
            "func foo() int { return 42 }\n",
            ".go",
        )
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["total_functions"] == 1
        assert result["functions_with_issues"] == 0


class TestValidation:
    def test_valid_args(self, tool: ReturnPathTool) -> None:
        assert tool.validate_arguments({"file_path": "/tmp/test.py"})

    def test_invalid_format(self, tool: ReturnPathTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "/tmp/test.py", "format": "xml"})

    def test_missing_file_path(self, tool: ReturnPathTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({"format": "json"})
