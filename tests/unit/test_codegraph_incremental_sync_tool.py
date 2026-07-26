"""Tests for codegraph_incremental_sync MCP tool — content-hash diff re-indexing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.incremental_sync import IncrementalSync, SyncResult
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


class TestCacheLifecycle:
    def test_sync_closes_cache_after_success(self, tool_with_root):
        cache = MagicMock()
        with (
            patch.object(tool_with_root, "_ensure_cache", return_value=cache),
            patch.object(IncrementalSync, "sync", return_value=SyncResult()),
        ):
            tool_with_root._sync(100, "json")

        cache.close.assert_called_once_with()

    def test_sync_closes_cache_after_exception(self, tool_with_root):
        cache = MagicMock()
        with (
            patch.object(tool_with_root, "_ensure_cache", return_value=cache),
            patch.object(
                IncrementalSync,
                "sync",
                side_effect=RuntimeError("sync failed"),
            ),
        ):
            tool_with_root._sync(100, "json")

        cache.close.assert_called_once_with()

    def test_sync_closes_cache_after_sync_constructor_exception(self, tool_with_root):
        cache = MagicMock()
        with (
            patch.object(tool_with_root, "_ensure_cache", return_value=cache),
            patch(
                "tree_sitter_analyzer.mcp.tools.incremental_sync_tool.IncrementalSync",
                side_effect=RuntimeError("constructor failed"),
            ),
        ):
            tool_with_root._sync(100, "json")

        cache.close.assert_called_once_with()

    def test_changes_closes_cache(self, tool_with_root):
        cache = MagicMock()
        with (
            patch.object(tool_with_root, "_ensure_cache", return_value=cache),
            patch.object(IncrementalSync, "get_changes", return_value={}),
        ):
            tool_with_root._changes("json")

        cache.close.assert_called_once_with()

    def test_status_closes_cache(self, tool_with_root):
        cache = MagicMock()
        cache.get_stats.return_value = {}
        with (
            patch(
                "tree_sitter_analyzer.ast_cache.ASTCache",
                return_value=cache,
            ),
            patch.object(IncrementalSync, "get_changes", return_value={}),
        ):
            tool_with_root._status("json")

        cache.close.assert_called_once_with()
