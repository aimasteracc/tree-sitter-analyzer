"""Integration tests for SideEffectTool MCP integration."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.side_effect_tool import SideEffectTool


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False,
    )
    f.write(content)
    f.flush()
    f.close()
    return f.name


@pytest.fixture
def tool() -> SideEffectTool:
    return SideEffectTool()


class TestSideEffectToolDefinition:
    def test_tool_name(self, tool: SideEffectTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "side_effects"

    def test_tool_has_description(self, tool: SideEffectTool) -> None:
        defn = tool.get_tool_definition()
        assert "description" in defn
        assert len(defn["description"]) > 20

    def test_tool_has_input_schema(self, tool: SideEffectTool) -> None:
        defn = tool.get_tool_definition()
        assert "inputSchema" in defn
        props = defn["inputSchema"]["properties"]
        assert "file_path" in props
        assert "format" in props


class TestSideEffectToolValidation:
    def test_valid_arguments(self, tool: SideEffectTool) -> None:
        assert tool.validate_arguments({
            "file_path": "/tmp/test.py",
            "format": "json",
        })

    def test_valid_toon_format(self, tool: SideEffectTool) -> None:
        assert tool.validate_arguments({
            "file_path": "/tmp/test.py",
            "format": "toon",
        })

    def test_missing_file_path(self, tool: SideEffectTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({"format": "json"})

    def test_invalid_format(self, tool: SideEffectTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({
                "file_path": "/tmp/test.py",
                "format": "xml",
            })


class TestSideEffectToolExecution:
    @pytest.mark.asyncio
    async def test_execute_json_format(
        self, tool: SideEffectTool,
    ) -> None:
        path = _write_tmp("""counter = 0

def inc():
    global counter
    counter += 1
""")
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert "total_issues" in result
        assert result["total_issues"] >= 1

    @pytest.mark.asyncio
    async def test_execute_toon_format(
        self, tool: SideEffectTool,
    ) -> None:
        path = _write_tmp("""def mutate(lst):
    lst.append(1)
""")
        result = await tool.execute({
            "file_path": path,
            "format": "toon",
        })
        assert "content" in result
        assert "total_issues" in result

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(
        self, tool: SideEffectTool,
    ) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_nonexistent_file(
        self, tool: SideEffectTool,
    ) -> None:
        result = await tool.execute({
            "file_path": "/nonexistent/file.py",
            "format": "json",
        })
        assert result["total_issues"] == 0

    @pytest.mark.asyncio
    async def test_execute_clean_file(
        self, tool: SideEffectTool,
    ) -> None:
        path = _write_tmp("""def pure(x):
    return x + 1
""")
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_issues"] == 0

    @pytest.mark.asyncio
    async def test_execute_javascript(
        self, tool: SideEffectTool,
    ) -> None:
        path = _write_tmp("""let count = 0;
function inc() { count++; }
""", suffix=".js")
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["language"] == "javascript"
