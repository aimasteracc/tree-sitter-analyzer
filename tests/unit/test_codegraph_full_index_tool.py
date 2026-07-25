"""Tests for codegraph_full_index MCP tool — one-shot complete project intelligence."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.incremental_sync import SyncResult
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

    async def test_verdict_is_warn_when_ast_cache_has_errors(self, tool_with_root):
        with (
            patch.object(
                tool_with_root,
                "_phase_ast_cache",
                return_value={"status": "error", "errors": 1},
            ),
            patch.object(
                tool_with_root,
                "_phase_incremental_sync",
                return_value={"status": "ok", "errors": 0},
            ),
            patch.object(
                tool_with_root,
                "_phase_fts5_stats",
                return_value={"status": "ok"},
            ),
            patch.object(
                tool_with_root,
                "_phase_call_edge_stats",
                return_value={"status": "ok"},
            ),
            patch.object(tool_with_root, "_collect_final_stats", return_value={}),
        ):
            result = await tool_with_root.execute(
                {
                    "mode": "incremental",
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "WARN"

    async def test_default_toon_surfaces_truncation_metadata(self, tool_with_root):
        incremental_phase = {
            "status": "error",
            "errors": 21,
            "error_details": [{"file": "src/00.swift", "status": "error"}],
            "error_details_total": 21,
            "error_details_listed": 20,
            "error_details_cap": 20,
            "error_details_truncated": True,
        }
        with (
            patch.object(
                tool_with_root,
                "_phase_ast_cache",
                return_value={"status": "ok", "errors": 0},
            ),
            patch.object(
                tool_with_root,
                "_phase_incremental_sync",
                return_value=incremental_phase,
            ),
            patch.object(
                tool_with_root,
                "_phase_fts5_stats",
                return_value={"status": "ok"},
            ),
            patch.object(
                tool_with_root,
                "_phase_call_edge_stats",
                return_value={"status": "ok"},
            ),
            patch.object(tool_with_root, "_collect_final_stats", return_value={}),
        ):
            result = await tool_with_root.execute(
                {"mode": "incremental", "resolve_synapse": False}
            )

        assert result["format"] == "toon"
        assert "error_details_truncated: true" in result["toon_content"]


class TestErrorTransparency:
    """Incident 2026-07-26: indexing failures must stay actionable and bounded."""

    @staticmethod
    def _ast_result_with_errors():
        return {
            "indexed": 1,
            "cached": 0,
            "errors": 2,
            "files": [
                {
                    "file": "src/z_bad.swift",
                    "status": "error",
                    "reason": "Swift grammar not installed",
                },
                {"file": "src/good.py", "status": "indexed"},
                {
                    "file": "src/a_bad.lua",
                    "status": "error",
                    "reason": "LUA grammar not installed",
                },
            ],
        }

    def _run_ast_phase(self, tool_with_root):
        ast_result = self._ast_result_with_errors()
        with patch("tree_sitter_analyzer.ast_cache.ASTCache") as cache_cls:
            cache_cls.return_value.index_project.return_value = ast_result
            return tool_with_root._phase_ast_cache(False, 10)

    @staticmethod
    def _run_incremental_phase(tool_with_root, sync_result):
        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache"),
            patch("tree_sitter_analyzer.incremental_sync.IncrementalSync") as sync_cls,
        ):
            sync_cls.return_value.sync.return_value = sync_result
            return tool_with_root._phase_incremental_sync()

    def test_ast_phase_marks_returned_errors(self, tool_with_root):
        phase = self._run_ast_phase(tool_with_root)

        assert phase["status"] == "error"
        assert phase["errors"] == 2

    def test_ast_phase_reports_sorted_error_details(self, tool_with_root):
        phase = self._run_ast_phase(tool_with_root)

        assert phase["error_details"] == [
            {
                "file": "src/a_bad.lua",
                "status": "error",
                "reason": "LUA grammar not installed",
            },
            {
                "file": "src/z_bad.swift",
                "status": "error",
                "reason": "Swift grammar not installed",
            },
        ]

    def test_ast_phase_reports_detail_metadata(self, tool_with_root):
        phase = self._run_ast_phase(tool_with_root)

        assert {
            key: phase[key]
            for key in (
                "error_details_total",
                "error_details_listed",
                "error_details_cap",
                "error_details_truncated",
                "unattributed_errors",
            )
        } == {
            "error_details_total": 2,
            "error_details_listed": 2,
            "error_details_cap": 20,
            "error_details_truncated": False,
            "unattributed_errors": 0,
        }

    def test_incremental_phase_sorts_before_returning_details(self, tool_with_root):
        sync_result = SyncResult(errors=3)
        sync_result.details = [
            {"file": f"src/{index}.swift", "status": "error"}
            for index in reversed(range(3))
        ]

        phase = self._run_incremental_phase(tool_with_root, sync_result)

        assert [detail["file"] for detail in phase["error_details"]] == [
            "src/0.swift",
            "src/1.swift",
            "src/2.swift",
        ]

    def test_incremental_phase_caps_error_details(self, tool_with_root):
        sync_result = SyncResult(errors=21)
        sync_result.details = [
            {
                "file": f"src/{index:02}.swift",
                "status": "error",
                "reason": "Swift grammar not installed",
            }
            for index in reversed(range(21))
        ]

        phase = self._run_incremental_phase(tool_with_root, sync_result)

        assert phase["error_details_total"] == 21
        assert phase["error_details_listed"] == 20
        assert phase["error_details_cap"] == 20
        assert phase["error_details_truncated"] is True
        assert len(phase["error_details"]) == 20
        assert (
            phase["error_details_next_step"]
            == "Run --incremental-sync --format json for uncapped per-file details."
        )

    def test_incremental_phase_reports_unattributed_errors(self, tool_with_root):
        sync_result = SyncResult(errors=2)
        sync_result.details = [{"file": "src/bad.swift", "status": "error"}]

        phase = self._run_incremental_phase(tool_with_root, sync_result)

        assert phase["unattributed_errors"] == 1

    def test_error_detail_keeps_phase_status_honest_when_count_is_inconsistent(
        self, tool_with_root
    ):
        sync_result = SyncResult(errors=0)
        sync_result.details = [{"file": "src/bad.swift", "status": "error"}]

        phase = self._run_incremental_phase(tool_with_root, sync_result)

        assert phase["errors"] == 0
        assert phase["status"] == "error"

    def test_ast_cache_closes_after_index_exception(self, tool_with_root):
        with patch("tree_sitter_analyzer.ast_cache.ASTCache") as cache_cls:
            cache_cls.return_value.index_project.side_effect = RuntimeError("boom")
            tool_with_root._phase_ast_cache(False, 10)

        cache_cls.return_value.close.assert_called_once_with()

    def test_ast_cache_close_failure_does_not_mask_result(self, tool_with_root):
        ast_result = {
            "indexed": 0,
            "cached": 0,
            "errors": 0,
            "files": [],
        }
        with patch("tree_sitter_analyzer.ast_cache.ASTCache") as cache_cls:
            cache_cls.return_value.index_project.return_value = ast_result
            cache_cls.return_value.close.side_effect = RuntimeError("close failed")
            phase = tool_with_root._phase_ast_cache(False, 10)

        assert phase["status"] == "ok"

    def test_ast_outer_exception_is_bounded(self, tool_with_root):
        with patch("tree_sitter_analyzer.ast_cache.ASTCache") as cache_cls:
            cache_cls.return_value.index_project.side_effect = RuntimeError(
                "x" * 10_000
            )
            phase = tool_with_root._phase_ast_cache(False, 10)

        assert len(phase["error"]) == 500
        assert phase["error"].endswith("...")
        assert phase["error_truncated"] is True
