"""Unit tests for CognitiveComplexityTool MCP tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.cognitive_complexity_tool import (
    CognitiveComplexityTool,
)


@pytest.fixture
def tool() -> CognitiveComplexityTool:
    return CognitiveComplexityTool(project_root="/test/project")


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestCognitiveComplexityToolBasic:
    def test_init(self, tool: CognitiveComplexityTool) -> None:
        assert tool.project_root == "/test/project"

    def test_get_tool_definition(self, tool: CognitiveComplexityTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "cognitive_complexity"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]
        assert "threshold" in defn["inputSchema"]["properties"]

    def test_validate_valid(self, tool: CognitiveComplexityTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"})

    def test_validate_no_file(self, tool: CognitiveComplexityTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_validate_bad_format(self, tool: CognitiveComplexityTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})


@pytest.mark.asyncio
class TestCognitiveComplexityToolExecute:
    async def test_no_file_path(self, tool: CognitiveComplexityTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    async def test_json_format(self, tool: CognitiveComplexityTool) -> None:
        path = _write_tmp(
            "def check(x):\n"
            "    if x > 0:\n"
            "        if x > 100:\n"
            "            return True\n"
            "    return False\n"
        )
        result = await tool.execute({
            "file_path": path,
            "threshold": 2,
            "format": "json",
        })
        assert result["total_functions"] == 1
        assert result["max_complexity"] == 3
        assert result["complex_function_count"] == 1
        assert len(result["complex_functions"]) == 1
        assert result["complex_functions"][0]["complexity"] == 3
        Path(path).unlink()

    async def test_toon_format(self, tool: CognitiveComplexityTool) -> None:
        path = _write_tmp(
            "def simple():\n"
            "    return 1\n"
        )
        result = await tool.execute({
            "file_path": path,
            "format": "toon",
        })
        assert "content" in result
        assert result["total_functions"] == 1
        assert result["total_complexity"] == 0
        Path(path).unlink()

    async def test_threshold_filtering(self, tool: CognitiveComplexityTool) -> None:
        path = _write_tmp(
            "def simple():\n"
            "    return 1\n"
            "\n"
            "def complex_fn(x):\n"
            "    if x > 0:\n"
            "        if x > 10:\n"
            "            if x > 100:\n"
            "                return x\n"
            "    return 0\n"
        )
        result = await tool.execute({
            "file_path": path,
            "threshold": 5,
            "format": "json",
        })
        assert result["total_functions"] == 2
        assert result["complex_function_count"] == 1
        assert result["complex_functions"][0]["name"] == "complex_fn"
        Path(path).unlink()

    async def test_js_file(self, tool: CognitiveComplexityTool) -> None:
        path = _write_tmp(
            "function check(x) {\n"
            "  if (x > 0) {\n"
            "    return true;\n"
            "  } else {\n"
            "    return false;\n"
            "  }\n"
            "}\n",
            suffix=".js",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_functions"] == 1
        assert result["total_complexity"] == 2
        Path(path).unlink()

    async def test_java_file(self, tool: CognitiveComplexityTool) -> None:
        path = _write_tmp(
            "class S {\n"
            "  public boolean check(int x) {\n"
            "    if (x > 0) {\n"
            "      return true;\n"
            "    }\n"
            "    return false;\n"
            "  }\n"
            "}\n",
            suffix=".java",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_functions"] == 1
        assert result["total_complexity"] == 1
        Path(path).unlink()

    async def test_go_file(self, tool: CognitiveComplexityTool) -> None:
        path = _write_tmp(
            "package main\n\n"
            "func check(x int) bool {\n"
            "  if x > 0 {\n"
            "    return true\n"
            "  }\n"
            "  return false\n"
            "}\n",
            suffix=".go",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_functions"] == 1
        assert result["total_complexity"] == 1
        Path(path).unlink()
