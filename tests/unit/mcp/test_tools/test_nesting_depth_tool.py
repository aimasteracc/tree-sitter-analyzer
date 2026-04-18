"""Unit tests for NestingDepthTool MCP tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.nesting_depth_tool import NestingDepthTool


@pytest.fixture
def tool() -> NestingDepthTool:
    return NestingDepthTool(project_root="/test/project")


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestNestingDepthToolBasic:
    def test_init(self, tool: NestingDepthTool) -> None:
        assert tool.project_root == "/test/project"

    def test_get_tool_definition(self, tool: NestingDepthTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "nesting_depth"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]
        assert "threshold" in defn["inputSchema"]["properties"]

    def test_validate_valid(self, tool: NestingDepthTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"})

    def test_validate_no_file(self, tool: NestingDepthTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_validate_bad_format(self, tool: NestingDepthTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})


@pytest.mark.asyncio
class TestNestingDepthToolExecute:
    async def test_no_file_path(self, tool: NestingDepthTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    async def test_json_format_deep(self, tool: NestingDepthTool) -> None:
        path = _write_tmp(
            "def deep(a, b, c, d):\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    return 1\n"
            "    return 0\n"
        )
        result = await tool.execute({
            "file_path": path,
            "threshold": 4,
            "format": "json",
        })
        assert result["total_functions"] == 1
        assert result["max_depth"] == 4
        assert result["deep_function_count"] == 1
        assert len(result["deep_functions"]) == 1
        assert result["deep_functions"][0]["max_depth"] == 4
        assert result["deep_functions"][0]["rating"] == "warning"
        Path(path).unlink()

    async def test_json_format_flat(self, tool: NestingDepthTool) -> None:
        path = _write_tmp("def flat():\n    return 1\n")
        result = await tool.execute({
            "file_path": path,
            "threshold": 4,
            "format": "json",
        })
        assert result["total_functions"] == 1
        assert result["max_depth"] == 0
        assert result["deep_function_count"] == 0
        Path(path).unlink()

    async def test_toon_format(self, tool: NestingDepthTool) -> None:
        path = _write_tmp(
            "def foo(x, y):\n"
            "    if x:\n"
            "        if y:\n"
            "            return 1\n"
            "    return 0\n"
        )
        result = await tool.execute({
            "file_path": path,
            "format": "toon",
        })
        assert "content" in result
        assert result["total_functions"] == 1
        assert result["max_depth"] == 2
        Path(path).unlink()

    async def test_toon_format_deep(self, tool: NestingDepthTool) -> None:
        path = _write_tmp(
            "def pyramid(a, b, c, d, e):\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    if e:\n"
            "                        return 1\n"
            "    return 0\n"
        )
        result = await tool.execute({
            "file_path": path,
            "threshold": 4,
            "format": "toon",
        })
        assert result["deep_function_count"] == 1
        Path(path).unlink()

    async def test_nonexistent_file(self, tool: NestingDepthTool) -> None:
        result = await tool.execute({
            "file_path": "/nonexistent.py",
            "format": "json",
        })
        assert result["total_functions"] == 0

    async def test_javascript_file(self, tool: NestingDepthTool) -> None:
        path = _write_tmp(
            "function foo(a, b) {\n"
            "  if (a) {\n"
            "    if (b) {\n"
            "      return 1;\n"
            "    }\n"
            "  }\n"
            "}\n",
            suffix=".js",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_functions"] >= 1
        assert result["max_depth"] == 2
        Path(path).unlink()

    async def test_all_functions_listed_json(self, tool: NestingDepthTool) -> None:
        path = _write_tmp(
            "def flat():\n"
            "    return 1\n"
            "\n"
            "def nested(x, y):\n"
            "    if x:\n"
            "        if y:\n"
            "            return 1\n"
            "    return 0\n"
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_functions"] == 2
        assert len(result["all_functions"]) == 2
        names = {f["name"] for f in result["all_functions"]}
        assert "flat" in names
        assert "nested" in names
        Path(path).unlink()

    async def test_hotspots_in_json(self, tool: NestingDepthTool) -> None:
        path = _write_tmp(
            "def foo(x, y, z):\n"
            "    if x:\n"
            "        if y:\n"
            "            if z:\n"
            "                return 1\n"
            "    return 0\n"
        )
        result = await tool.execute({
            "file_path": path,
            "threshold": 1,
            "format": "json",
        })
        assert len(result["deep_functions"]) == 1
        hotspots = result["deep_functions"][0]["hotspots"]
        assert len(hotspots) == 3
        assert hotspots[0]["depth"] == 1
        assert hotspots[2]["depth"] == 3
        Path(path).unlink()

    async def test_custom_threshold(self, tool: NestingDepthTool) -> None:
        path = _write_tmp(
            "def foo(x):\n"
            "    if x:\n"
            "        return 1\n"
            "    return 0\n"
        )
        result = await tool.execute({
            "file_path": path,
            "threshold": 1,
            "format": "json",
        })
        assert result["deep_function_count"] == 1
        Path(path).unlink()
