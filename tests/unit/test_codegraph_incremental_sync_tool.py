"""Tests for codegraph_incremental_sync MCP tool — content-hash diff re-indexing."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
    CodeGraphIncrementalSyncTool,
)


@pytest.fixture
def tool():
    return CodeGraphIncrementalSyncTool()


@pytest.fixture
def tool_with_root(tmp_path):
    (tmp_path / "app.py").write_text("def foo():\n    pass\n")
    return CodeGraphIncrementalSyncTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_incremental_sync"

    def test_description_mentions_no_other(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "No other tool" in desc

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {"sync", "changes", "status"}

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )

    def test_annotations_destructive(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["destructiveHint"] is True
        assert hints["readOnlyHint"] is False


class TestValidation:
    def test_valid_sync(self, tool):
        assert tool.validate_arguments({"mode": "sync"}) is True

    def test_valid_changes(self, tool):
        assert tool.validate_arguments({"mode": "changes"}) is True

    def test_valid_status(self, tool):
        assert tool.validate_arguments({"mode": "status"}) is True

    def test_invalid_mode_rejected(self, tool):
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "rebuild"})


@pytest.mark.asyncio
class TestExecute:
    async def test_status_no_project_root_returns_error(self, tool):
        result = await tool.execute({"mode": "status", "output_format": "json"})
        assert result["success"] is False

    async def test_status_on_empty_project(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "status", "output_format": "json"}
        )
        assert result["success"] is True

    async def test_changes_mode_preview(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "changes", "output_format": "json"}
        )
        assert result["success"] is True

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute({"mode": "status"})
        assert result["format"] == "toon"
        assert "toon_content" in result
