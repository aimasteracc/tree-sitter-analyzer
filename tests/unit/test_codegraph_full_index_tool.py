"""Tests for codegraph_full_index MCP tool — one-shot complete project intelligence."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool


@pytest.fixture
def tool():
    return CodeGraphFullIndexTool()


@pytest.fixture
def tool_with_root(tmp_path):
    (tmp_path / "app.py").write_text("def hello():\n    pass\n")
    return CodeGraphFullIndexTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_full_index"

    def test_description_mentions_no_other(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "No other tool" in desc

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {"full", "incremental"}
        assert mode["default"] == "incremental"

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )

    def test_annotations_destructive(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is False
        assert hints["destructiveHint"] is True


class TestValidation:
    def test_valid_incremental(self, tool):
        assert tool.validate_arguments({"mode": "incremental"}) is True

    def test_valid_full(self, tool):
        assert tool.validate_arguments({"mode": "full"}) is True

    def test_invalid_mode_rejected(self, tool):
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "partial"})


@pytest.mark.asyncio
class TestExecute:
    async def test_no_project_root_returns_error(self, tool):
        result = await tool.execute({"mode": "incremental", "output_format": "json"})
        assert result["success"] is False

    async def test_incremental_on_empty_project(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "incremental", "output_format": "json"}
        )
        assert result["success"] is True

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute({"mode": "incremental"})
        assert result["format"] == "toon"
        assert "toon_content" in result

    async def test_verdict_is_warn_when_incremental_sync_has_errors(
        self, tool_with_root
    ):
        """#860: DB flush errors in incremental_sync must escalate verdict to WARN."""
        from unittest.mock import patch

        from tree_sitter_analyzer.incremental_sync import SyncResult

        bad_result = SyncResult(
            scanned=5,
            new_files=0,
            updated_files=0,
            deleted_files=0,
            unchanged_files=5,
            errors=1,
        )
        with patch("tree_sitter_analyzer.incremental_sync.IncrementalSync") as MockSync:
            MockSync.return_value.sync.return_value = bad_result
            result = await tool_with_root.execute(
                {"mode": "incremental", "output_format": "json"}
            )

        assert result["success"] is True
        assert result["verdict"] == "WARN"
        assert result["phases"]["incremental_sync"]["status"] == "error"
        assert result["phases"]["incremental_sync"]["errors"] == 1
