"""Unit tests for SwitchSmellsTool MCP tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.switch_smells_tool import SwitchSmellsTool


@pytest.fixture
def tool() -> SwitchSmellsTool:
    return SwitchSmellsTool(project_root="/test/project")


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestSwitchSmellsToolBasic:
    def test_init(self, tool: SwitchSmellsTool) -> None:
        assert tool.project_root == "/test/project"

    def test_get_tool_definition(self, tool: SwitchSmellsTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "switch_smells"

    def test_validate_valid(self, tool: SwitchSmellsTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"})

    def test_validate_no_file(self, tool: SwitchSmellsTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})


@pytest.mark.asyncio
class TestSwitchSmellsToolExecute:
    async def test_no_file_path(self, tool: SwitchSmellsTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    async def test_json_format(self, tool: SwitchSmellsTool) -> None:
        path = _write_tmp(
            "match x:\n"
            "    case 1: pass\n"
            "    case 2: pass\n"
            "    case 3: pass\n"
            "    case 4: pass\n"
            "    case 5: pass\n"
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_switches"] >= 1
        assert result["smelly_switches"] >= 1
        Path(path).unlink()

    async def test_json_format_clean(self, tool: SwitchSmellsTool) -> None:
        path = _write_tmp("x = 1\n")
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["total_switches"] == 0
        Path(path).unlink()

    async def test_toon_format(self, tool: SwitchSmellsTool) -> None:
        path = _write_tmp("x = 1\n")
        result = await tool.execute({
            "file_path": path,
            "format": "toon",
        })
        assert "content" in result
        Path(path).unlink()

    async def test_javascript_file(self, tool: SwitchSmellsTool) -> None:
        path = _write_tmp(
            "switch(x) {\n"
            "  case 1: break;\n"
            "  case 2: break;\n"
            "  case 3: break;\n"
            "  case 4: break;\n"
            "  case 5: break;\n"
            "}",
            suffix=".js",
        )
        result = await tool.execute({
            "file_path": path,
            "format": "json",
        })
        assert result["smelly_switches"] >= 1
        Path(path).unlink()

    async def test_nonexistent_file(self, tool: SwitchSmellsTool) -> None:
        result = await tool.execute({
            "file_path": "/nonexistent.py",
            "format": "json",
        })
        assert result["total_switches"] == 0
