"""Tests for codegraph_autoindex MCP tool — transparent AST cache warming."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.auto_index_tool import CodeGraphAutoIndexTool


@pytest.fixture
def tool():
    return CodeGraphAutoIndexTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphAutoIndexTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_autoindex"

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {"status", "warm", "reset"}
        assert mode["default"] == "status"

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )

    def test_annotations_not_readonly(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is False
        assert hints["destructiveHint"] is True


class TestValidation:
    def test_valid_status(self, tool):
        assert tool.validate_arguments({"mode": "status"}) is True

    def test_valid_warm(self, tool):
        assert tool.validate_arguments({"mode": "warm"}) is True

    def test_valid_reset(self, tool):
        assert tool.validate_arguments({"mode": "reset"}) is True

    def test_invalid_mode_rejected(self, tool):
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "delete"})


@pytest.mark.asyncio
class TestExecute:
    async def test_status_no_project_root_returns_warn(self, tool):
        result = await tool.execute({"mode": "status", "output_format": "json"})
        assert result["verdict"] == "WARN"
        assert result["indexed"] is False

    async def test_status_empty_project_returns_info(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "status", "output_format": "json"}
        )
        assert result["success"] is True
        assert "indexed" in result

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute({"mode": "status"})
        assert result["format"] == "toon"
        assert "toon_content" in result

    async def test_reset_mode_runs_without_error(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "reset", "output_format": "json"}
        )
        assert result["success"] is True

    async def test_warm_mode_returns_indexed_true(self, tool_with_root):
        # DF-8: verify warm mode returns indexed=true and cache_stats after successful index
        result = await tool_with_root.execute(
            {"mode": "warm", "max_files": 100, "output_format": "json"}
        )
        assert result["success"] is True
        assert result["indexed"] is True
        assert result["cache_stats"] is not None
        assert isinstance(result["cache_stats"], dict)
