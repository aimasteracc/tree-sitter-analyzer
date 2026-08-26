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

    def test_annotations_destructive(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["destructiveHint"] is True
        assert hints["readOnlyHint"] is False

    def test_schema_requires_positive_max_files(self, tool):
        assert tool.get_tool_schema()["properties"]["max_files"]["minimum"] == 1


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

    @pytest.mark.parametrize("value", [True, 0, -1])
    def test_invalid_max_files_rejected(self, tool, value):
        with pytest.raises(ValueError, match="max_files must be a positive integer"):
            tool.validate_arguments({"mode": "sync", "max_files": value})

    def test_omitted_max_files_is_normalized(self, tool):
        arguments = {"mode": "sync"}

        assert tool.validate_arguments(arguments) is True
        assert arguments["max_files"] == 20_000


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


class TestCacheLifecycle:
    def test_sync_uses_limit_for_cold_cache_warmup(self, tool_with_root):
        cache = MagicMock()
        with (
            patch.object(tool_with_root, "_ensure_cache", return_value=cache) as ensure,
            patch.object(IncrementalSync, "sync", return_value=SyncResult()),
        ):
            tool_with_root._sync(7, "json")

        ensure.assert_called_once_with("json", max_files=7)

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


def test_candidate_less_incremental_response_is_not_authoritative_success(
    tool_with_root,
):
    # PR #1253 review 3762603012: public sync has no frozen candidate evidence.
    cache = MagicMock()
    live_walk = SyncResult(scope_complete=False)
    with (
        patch.object(tool_with_root, "_ensure_cache", return_value=cache),
        patch.object(IncrementalSync, "sync", return_value=live_walk),
    ):
        result = tool_with_root._sync(10, "json")

    assert (result["success"], result["verdict"], result["completeness"]) == (
        False,
        "WARN",
        "incomplete",
    )


def test_parse_failure_makes_incremental_response_non_success(tool_with_root):
    # PR #1253 thread 3761514130: missing parsed rows are not MCP success.
    cache = MagicMock()
    parse_failure = SyncResult(errors=1, scope_complete=False)
    with (
        patch.object(tool_with_root, "_ensure_cache", return_value=cache),
        patch.object(IncrementalSync, "sync", return_value=parse_failure),
    ):
        result = tool_with_root._sync(10, "json")

    assert (result["success"], result["verdict"], result["completeness"]) == (
        False,
        "WARN",
        "incomplete",
    )


def test_manifest_stamp_failure_makes_incremental_response_non_success(
    tool_with_root,
):
    # PR #1253 thread 3761514130: failed certification is not MCP success.
    cache = MagicMock()
    stamp_failure = SyncResult(
        scope_complete=False,
        manifest_certification_failed=True,
    )
    with (
        patch.object(tool_with_root, "_ensure_cache", return_value=cache),
        patch.object(IncrementalSync, "sync", return_value=stamp_failure),
    ):
        result = tool_with_root._sync(10, "json")

    assert (
        result["success"],
        result["verdict"],
        result["manifest_certification_failed"],
    ) == (False, "WARN", True)


def test_pipeline_warning_makes_incremental_response_non_success(tool_with_root):
    # PR #1253 review 3757240532: incomplete navigation is not an INFO success.
    cache = MagicMock()
    pipeline_failure = SyncResult(errors=1, backfill_errors=1)
    pipeline_failure.details.append(
        {
            "stage": "cross_file",
            "considered": "backfill",
            "action": "backfill",
            "status": "warning",
            "reason": "BACKFILL_REPORTED_ERRORS",
        }
    )
    with (
        patch.object(tool_with_root, "_ensure_cache", return_value=cache),
        patch.object(IncrementalSync, "sync", return_value=pipeline_failure),
    ):
        result = tool_with_root._sync(10, "json")

    assert (result["success"], result["verdict"], result["backfill_errors"]) == (
        False,
        "WARN",
        1,
    )
