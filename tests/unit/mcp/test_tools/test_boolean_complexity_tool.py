"""Unit tests for BooleanComplexityTool MCP tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.boolean_complexity_tool import BooleanComplexityTool


@pytest.fixture
def tool() -> BooleanComplexityTool:
    return BooleanComplexityTool(project_root="/test/project")


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestBooleanComplexityToolBasic:
    def test_init(self, tool: BooleanComplexityTool) -> None:
        assert tool.project_root == "/test/project"

    def test_get_tool_definition(self, tool: BooleanComplexityTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "boolean_complexity"
        assert "inputSchema" in defn

    def test_validate_valid(self, tool: BooleanComplexityTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"})

    def test_validate_no_file(self, tool: BooleanComplexityTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_validate_bad_format(self, tool: BooleanComplexityTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})


@pytest.mark.asyncio
class TestBooleanComplexityToolExecute:
    async def test_no_file_path(self, tool: BooleanComplexityTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    async def test_json_format_complex(self, tool: BooleanComplexityTool) -> None:
        path = _write_tmp(
            "if a and b and c and d and e:\n    pass\n"
        )
        result = await tool.execute({
            "file_path": path,
            "threshold": 4,
            "format": "json",
        })
        assert result["total_expressions"] >= 1
        assert result["max_conditions"] >= 5
        assert result["hotspot_count"] >= 1
        Path(path).unlink()

    async def test_json_format_simple(self, tool: BooleanComplexityTool) -> None:
        path = _write_tmp("x = 1\n")
        result = await tool.execute({
            "file_path": path,
            "threshold": 4,
            "format": "json",
        })
        assert result["total_expressions"] == 0
        assert result["hotspot_count"] == 0
        Path(path).unlink()

    async def test_toon_format(self, tool: BooleanComplexityTool) -> None:
        path = _write_tmp("if a and b:\n    pass\n")
        result = await tool.execute({
            "file_path": path,
            "format": "toon",
        })
        assert "content" in result
        assert result["total_expressions"] >= 1
        Path(path).unlink()

    async def test_nonexistent_file(self, tool: BooleanComplexityTool) -> None:
        result = await tool.execute({
            "file_path": "/nonexistent.py",
            "format": "json",
        })
        assert result["total_expressions"] == 0

    async def test_javascript_file(self, tool: BooleanComplexityTool) -> None:
        path = _write_tmp(
            "if (a && b && c && d) { return 1; }",
            suffix=".js",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["max_conditions"] >= 4
        Path(path).unlink()

    async def test_java_file(self, tool: BooleanComplexityTool) -> None:
        path = _write_tmp(
            "public class T {\n"
            "  boolean f(boolean a, boolean b, boolean c, boolean d) {\n"
            "    return a && b && c && d;\n"
            "  }\n"
            "}\n",
            suffix=".java",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["max_conditions"] >= 4
        Path(path).unlink()

    async def test_go_file(self, tool: BooleanComplexityTool) -> None:
        path = _write_tmp(
            "package main\n\n"
            "func foo(a, b, c, d bool) bool {\n"
            "    return a && b && c && d\n"
            "}\n",
            suffix=".go",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["max_conditions"] >= 4
        Path(path).unlink()
