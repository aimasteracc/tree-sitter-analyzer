"""Unit tests for LoopComplexityTool MCP tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.loop_complexity_tool import LoopComplexityTool


@pytest.fixture
def tool() -> LoopComplexityTool:
    return LoopComplexityTool(project_root="/test/project")


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestLoopComplexityToolBasic:
    def test_init(self, tool: LoopComplexityTool) -> None:
        assert tool.project_root == "/test/project"

    def test_get_tool_definition(self, tool: LoopComplexityTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "loop_complexity"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_validate_valid(self, tool: LoopComplexityTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"})

    def test_validate_no_file(self, tool: LoopComplexityTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_validate_bad_format(self, tool: LoopComplexityTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})


@pytest.mark.asyncio
class TestLoopComplexityToolExecute:
    async def test_no_file_path(self, tool: LoopComplexityTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    async def test_json_format_nested(self, tool: LoopComplexityTool) -> None:
        path = _write_tmp(
            "def foo(matrix):\n"
            "    for row in matrix:\n"
            "        for col in row:\n"
            "            print(col)\n"
        )
        result = await tool.execute({
            "file_path": path,
            "threshold": 2,
            "format": "json",
        })
        assert result["total_loops"] == 2
        assert result["max_loop_depth"] == 2
        assert result["estimated_complexity"] == "O(n\u00b2)"
        assert result["hotspot_count"] >= 1
        Path(path).unlink()

    async def test_json_format_flat(self, tool: LoopComplexityTool) -> None:
        path = _write_tmp("def foo():\n    return 1\n")
        result = await tool.execute({
            "file_path": path,
            "threshold": 2,
            "format": "json",
        })
        assert result["total_loops"] == 0
        assert result["max_loop_depth"] == 0
        assert result["estimated_complexity"] == "O(1)"
        assert result["hotspot_count"] == 0
        Path(path).unlink()

    async def test_toon_format(self, tool: LoopComplexityTool) -> None:
        path = _write_tmp(
            "def foo(items):\n"
            "    for x in items:\n"
            "        print(x)\n"
        )
        result = await tool.execute({
            "file_path": path,
            "format": "toon",
        })
        assert "content" in result
        assert result["total_loops"] == 1
        assert result["max_loop_depth"] == 1
        Path(path).unlink()

    async def test_toon_format_deep(self, tool: LoopComplexityTool) -> None:
        path = _write_tmp(
            "def foo(cube):\n"
            "    for a in cube:\n"
            "        for b in a:\n"
            "            for c in b:\n"
            "                print(c)\n"
        )
        result = await tool.execute({
            "file_path": path,
            "threshold": 2,
            "format": "toon",
        })
        assert result["hotspot_count"] >= 1
        assert result["estimated_complexity"] == "O(n\u00b3)"
        Path(path).unlink()

    async def test_nonexistent_file(self, tool: LoopComplexityTool) -> None:
        result = await tool.execute({
            "file_path": "/nonexistent.py",
            "format": "json",
        })
        assert result["total_loops"] == 0

    async def test_javascript_file(self, tool: LoopComplexityTool) -> None:
        path = _write_tmp(
            "function foo(matrix) {\n"
            "  for (let i = 0; i < matrix.length; i++) {\n"
            "    for (let j = 0; j < matrix[i].length; j++) {\n"
            "      console.log(matrix[i][j]);\n"
            "    }\n"
            "  }\n"
            "}\n",
            suffix=".js",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["max_loop_depth"] == 2
        Path(path).unlink()

    async def test_java_file(self, tool: LoopComplexityTool) -> None:
        path = _write_tmp(
            "public class Test {\n"
            "  void foo(int[][] m) {\n"
            "    for (int i = 0; i < m.length; i++) {\n"
            "      for (int j = 0; j < m[i].length; j++) {}\n"
            "    }\n"
            "  }\n"
            "}\n",
            suffix=".java",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["max_loop_depth"] == 2
        Path(path).unlink()

    async def test_go_file(self, tool: LoopComplexityTool) -> None:
        path = _write_tmp(
            "package main\n\n"
            "func foo(m [][]int) {\n"
            "    for _, row := range m {\n"
            "        for _, v := range row {\n"
            "            _ = v\n"
            "        }\n"
            "    }\n"
            "}\n",
            suffix=".go",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["max_loop_depth"] == 2
        Path(path).unlink()
