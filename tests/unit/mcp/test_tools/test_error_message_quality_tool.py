"""Unit tests for ErrorMessageQualityTool MCP tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.error_message_quality_tool import (
    ErrorMessageQualityTool,
)


@pytest.fixture
def tool() -> ErrorMessageQualityTool:
    return ErrorMessageQualityTool(project_root="/test/project")


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestErrorMessageQualityToolBasic:
    def test_init(self, tool: ErrorMessageQualityTool) -> None:
        assert tool.project_root == "/test/project"

    def test_get_tool_definition(self, tool: ErrorMessageQualityTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "error_message_quality"

    def test_validate_valid(self, tool: ErrorMessageQualityTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"})

    def test_validate_no_file(self, tool: ErrorMessageQualityTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})


@pytest.mark.asyncio
class TestErrorMessageQualityToolExecute:
    async def test_no_file_path(self, tool: ErrorMessageQualityTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    async def test_json_format_poor(self, tool: ErrorMessageQualityTool) -> None:
        path = _write_tmp("raise ValueError('error')\n")
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_raises"] == 1
        assert result["poor_messages"] == 1
        Path(path).unlink()

    async def test_json_format_good(self, tool: ErrorMessageQualityTool) -> None:
        path = _write_tmp("raise ValueError('Invalid input: empty string')\n")
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_raises"] == 1
        assert result["poor_messages"] == 0
        Path(path).unlink()

    async def test_toon_format(self, tool: ErrorMessageQualityTool) -> None:
        path = _write_tmp("raise ValueError('error')\n")
        result = await tool.execute({
            "file_path": path,
            "format": "toon",
        })
        assert "content" in result
        Path(path).unlink()

    async def test_nonexistent_file(self, tool: ErrorMessageQualityTool) -> None:
        result = await tool.execute({
            "file_path": "/nonexistent.py",
            "format": "json",
        })
        assert result["total_raises"] == 0

    async def test_javascript_file(self, tool: ErrorMessageQualityTool) -> None:
        path = _write_tmp(
            "throw new Error('error');",
            suffix=".js",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_raises"] >= 1
        assert result["poor_messages"] >= 1
        Path(path).unlink()
