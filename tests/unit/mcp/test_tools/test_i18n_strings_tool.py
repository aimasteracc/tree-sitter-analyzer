"""Unit tests for I18nStringsTool MCP tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.i18n_strings_tool import I18nStringsTool


@pytest.fixture
def tool() -> I18nStringsTool:
    return I18nStringsTool(project_root=None)


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestI18nStringsToolBasic:
    def test_init(self, tool: I18nStringsTool) -> None:
        assert tool.project_root is None

    def test_get_tool_definition(self, tool: I18nStringsTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "i18n_strings"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]
        assert "visibility" in defn["inputSchema"]["properties"]

    def test_validate_valid(self, tool: I18nStringsTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"})

    def test_validate_bad_format(self, tool: I18nStringsTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})

    def test_validate_bad_visibility(self, tool: I18nStringsTool) -> None:
        with pytest.raises(ValueError, match="visibility"):
            tool.validate_arguments({"file_path": "test.py", "visibility": "invalid"})

    def test_validate_valid_visibility(self, tool: I18nStringsTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py", "visibility": "user_visible"})
        assert tool.validate_arguments({"file_path": "test.py", "visibility": "all"})


@pytest.mark.asyncio
class TestI18nStringsToolExecute:
    async def test_no_file_path_no_project_root(self, tool: I18nStringsTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    async def test_json_format(self, tool: I18nStringsTool) -> None:
        path = _write_tmp('print("Hello, world!")\n')
        try:
            result = await tool.execute({"file_path": path, "format": "json"})
            assert "file_path" in result
            assert result["user_visible_count"] >= 1
        finally:
            Path(path).unlink()

    async def test_toon_format(self, tool: I18nStringsTool) -> None:
        path = _write_tmp('print("Hello, world!")\n')
        try:
            result = await tool.execute({"file_path": path, "format": "toon"})
            assert "content" in result
            assert result["user_visible_count"] >= 1
        finally:
            Path(path).unlink()

    async def test_visibility_filter(self, tool: I18nStringsTool) -> None:
        path = _write_tmp(
            'print("User visible message")\n'
            'print("x")\n'
        )
        try:
            result = await tool.execute({
                "file_path": path,
                "visibility": "user_visible",
                "format": "json",
            })
            for s in result.get("strings", []):
                assert s["visibility"] == "user_visible"
        finally:
            Path(path).unlink()

    async def test_min_length_filter(self, tool: I18nStringsTool) -> None:
        path = _write_tmp('print("ab")\nprint("A longer message here")\n')
        try:
            result = await tool.execute({
                "file_path": path,
                "min_length": 10,
                "format": "json",
            })
            for s in result.get("strings", []):
                assert len(s["text"]) >= 10
        finally:
            Path(path).unlink()
