"""Tests for codegraph_full_index MCP tool — one-shot complete project intelligence."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.incremental_sync import SyncResult
from tree_sitter_analyzer.mcp.tools.full_index_tool import (
    CodeGraphFullIndexTool,
    _candidate_snapshot_report,
    _grammar_errors_only,
    _resolve_exclude_patterns,
)


@pytest.fixture
def tool():
    return CodeGraphFullIndexTool()


@pytest.fixture
def tool_with_root(tmp_path):
    (tmp_path / "app.py").write_text("def hello():\n    pass\n")
    return CodeGraphFullIndexTool(str(tmp_path))


def _cache_total_files(project_root) -> int:
    cache = ASTCache(str(project_root))
    try:
        return int(cache.get_stats()["total_files"])
    finally:
        cache.close()


def _cache_file_paths(project_root) -> set[str]:
    cache = ASTCache(str(project_root))
    try:
        rows = cache.get_conn().execute("SELECT file_path FROM ast_index").fetchall()
        return {str(row["file_path"]) for row in rows}
    finally:
        cache.close()


def test_snapshot_report_intersects_phase_processed_files(tmp_path):
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("a = 1\n")
    second.write_text("b = 1\n")
    snapshot = CodeGraphFullIndexTool(str(tmp_path))._build_candidate_snapshot(
        10,
        frozenset(),
    )

    report = _candidate_snapshot_report(
        snapshot,
        {
            "processed": 1,
            "changed_during_run": 1,
            "changed_during_run_files": ["a.py"],
        },
        {
            "processed": 1,
            "changed_during_run": 1,
            "changed_during_run_files": ["b.py"],
        },
    )

    assert (
        report["processed"],
        report["selection_reconciled"],
        report["phase_totals_reconciled"],
    ) == (0, True, True)


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

    def test_annotations_destructive(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is False
        assert hints["destructiveHint"] is True

    def test_schema_requires_positive_max_files(self, tool):
        assert tool.get_tool_schema()["properties"]["max_files"]["minimum"] == 1


class TestValidation:
    def test_valid_incremental(self, tool):
        assert tool.validate_arguments({"mode": "incremental"}) is True

    def test_valid_full(self, tool):
        assert tool.validate_arguments({"mode": "full"}) is True

    def test_invalid_mode_rejected(self, tool):
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "partial"})

    @pytest.mark.parametrize("value", [True, 0, -1])
    def test_invalid_max_files_rejected(self, tool, value):
        with pytest.raises(ValueError, match="max_files must be a positive integer"):
            tool.validate_arguments({"mode": "incremental", "max_files": value})

    def test_omitted_max_files_is_normalized(self, tool):
        arguments = {"mode": "incremental"}

        assert tool.validate_arguments(arguments) is True
        assert arguments["max_files"] == 20_000

    @pytest.mark.parametrize("value", [None, "src/*", [1]])
    def test_invalid_exclude_patterns_are_rejected(self, tool, value):
        # PR #1253: persisted source-scope patterns must be strings in an array.
        with pytest.raises(ValueError, match="exclude_patterns must be an array"):
            tool.validate_arguments({"exclude_patterns": value})

    def test_non_boolean_no_default_excludes_is_rejected(self, tool):
        # PR #1253: source-scope policy flags cannot rely on truthiness.
        with pytest.raises(ValueError, match="no_default_excludes must be a boolean"):
            tool.validate_arguments({"no_default_excludes": 1})


class TestExcludeResolution:
    def test_no_default_excludes_can_resolve_to_empty_scope(self):
        assert _resolve_exclude_patterns([], True) == frozenset()

    def test_windows_separators_are_normalized_for_both_phases(self):
        assert _resolve_exclude_patterns([r"src\generated\*"], True) == frozenset(
            {"src/generated/*"}
        )


@pytest.mark.asyncio
class TestExecute:
    async def test_no_project_root_returns_error(self, tool):
        result = await tool.execute({"mode": "incremental", "output_format": "json"})
        assert result["success"] is False

    async def test_oversize_scope_is_rejected_before_index_discovery(
        self, tool_with_root
    ):
        # PR #1253: invalid public scope input cannot mutate the index.
        with patch.object(tool_with_root, "_build_candidate_snapshot") as discover:
            with pytest.raises(ValueError, match="SOURCE_SCOPE_DESCRIPTOR_TOO_LARGE"):
                await tool_with_root.execute(
                    {
                        "mode": "full",
                        "exclude_patterns": ["x" * (64 * 1024)],
                        "output_format": "json",
                    }
                )

        discover.assert_not_called()

    async def test_incremental_on_empty_project(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "incremental", "output_format": "json"}
        )
        assert result["success"] is True

    async def test_incremental_on_truly_empty_project_reconciles_zero_scope(
        self, tmp_path
    ):
        empty_tool = CodeGraphFullIndexTool(str(tmp_path))

        result = await empty_tool.execute(
            {
                "mode": "incremental",
                "resolve_synapse": False,
                "output_format": "json",
            }
        )

        assert result["success"] is True
        assert result["candidate_snapshot"]["selected"] == 0
        assert result["candidate_snapshot"]["selection_reconciled"] is True

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

        assert result["success"] is False
        assert result["verdict"] == "WARN"
        assert result["phases"]["incremental_sync"]["status"] == "error"
        assert result["phases"]["incremental_sync"]["errors"] == 1

    async def test_backfill_errors_withhold_two_phase_manifest(self, tool_with_root):
        with (
            patch.object(
                tool_with_root,
                "_phase_ast_cache",
                return_value={"status": "ok", "errors": 0, "backfill_errors": 1},
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
            patch.object(
                tool_with_root, "_collect_final_stats", return_value={}
            ) as collect_stats,
        ):
            result = await tool_with_root.execute(
                {
                    "mode": "incremental",
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        assert result["success"] is False
        assert result["verdict"] == "WARN"
        assert collect_stats.call_args.kwargs["stamp_manifest"] is False

    async def test_manifest_certification_warning_escalates_all_verdicts(
        self, tool_with_root
    ):
        clean_phase = {"status": "ok", "processed": 1}
        with (
            patch.object(tool_with_root, "_phase_ast_cache", return_value=clean_phase),
            patch.object(
                tool_with_root, "_phase_incremental_sync", return_value=clean_phase
            ),
            patch.object(
                tool_with_root, "_phase_fts5_stats", return_value={"status": "ok"}
            ),
            patch.object(
                tool_with_root,
                "_phase_call_edge_stats",
                return_value={"status": "ok"},
            ),
            patch.object(
                tool_with_root,
                "_collect_final_stats",
                return_value={
                    "manifest_warning": "INDEX_MANIFEST_CERTIFICATION_FAILED"
                },
            ),
        ):
            result = await tool_with_root.execute(
                {
                    "mode": "full",
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        assert (
            result["success"],
            result["verdict"],
            result["agent_summary"]["verdict"],
            result["summary_line"],
            result["agent_summary"]["summary_line"],
        ) == (
            False,
            "WARN",
            "WARN",
            "codegraph_full_index: completed with warn",
            "codegraph_full_index: completed with warn",
        )

    async def test_incremental_manifest_certification_failure_is_not_operational_success(
        self, tool_with_root
    ):
        clean_phase = {"status": "ok", "processed": 1}
        with (
            patch.object(tool_with_root, "_phase_ast_cache", return_value=clean_phase),
            patch.object(
                tool_with_root, "_phase_incremental_sync", return_value=clean_phase
            ),
            patch.object(
                tool_with_root, "_phase_fts5_stats", return_value={"status": "ok"}
            ),
            patch.object(
                tool_with_root, "_phase_call_edge_stats", return_value={"status": "ok"}
            ),
            patch.object(
                tool_with_root,
                "_collect_final_stats",
                return_value={
                    "_manifest_certified": False,
                    "manifest_certification_failed": True,
                    "manifest_warning": "INDEX_MANIFEST_CERTIFICATION_FAILED",
                },
            ),
        ):
            result = await tool_with_root.execute(
                {
                    "mode": "incremental",
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        assert (result["success"], result["verdict"]) == (False, "WARN")

    async def test_manifest_warning_next_step_reaches_the_caller(self, tool_with_root):
        """The remedial step must be in the response, not just derivable.

        The first version of this change was covered only by unit tests on the
        helper. Reverting the wiring that puts its result into agent_summary
        left those three tests green -- the helper worked and its output
        reached nobody, which is the exact defect class RFC-0029 corpus item 4
        names. This test drives the real response assembly instead.
        """
        clean_phase = {"status": "ok", "processed": 1}
        with (
            patch.object(tool_with_root, "_phase_ast_cache", return_value=clean_phase),
            patch.object(
                tool_with_root, "_phase_incremental_sync", return_value=clean_phase
            ),
            patch.object(
                tool_with_root, "_phase_fts5_stats", return_value={"status": "ok"}
            ),
            patch.object(
                tool_with_root, "_phase_call_edge_stats", return_value={"status": "ok"}
            ),
            patch.object(
                tool_with_root,
                "_collect_final_stats",
                return_value={
                    "_manifest_certified": False,
                    "manifest_certification_failed": True,
                    "manifest_warning": "INDEX_MANIFEST_CERTIFICATION_FAILED",
                },
            ),
        ):
            result = await tool_with_root.execute(
                {
                    "mode": "incremental",
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        step = result["agent_summary"]["next_step"]
        assert step is not None
        assert "--callers" in step
        assert "re-index" in step.lower()

    async def test_a_certified_run_carries_no_remedial_next_step(self, tool_with_root):
        """A clean run must not tell the caller to remedy anything."""
        clean_phase = {"status": "ok", "processed": 1}
        with (
            patch.object(tool_with_root, "_phase_ast_cache", return_value=clean_phase),
            patch.object(
                tool_with_root, "_phase_incremental_sync", return_value=clean_phase
            ),
            patch.object(
                tool_with_root, "_phase_fts5_stats", return_value={"status": "ok"}
            ),
            patch.object(
                tool_with_root, "_phase_call_edge_stats", return_value={"status": "ok"}
            ),
            patch.object(
                tool_with_root,
                "_collect_final_stats",
                return_value={"_manifest_certified": True},
            ),
        ):
            result = await tool_with_root.execute(
                {
                    "mode": "incremental",
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        assert result["agent_summary"]["next_step"] is None

    async def test_synapse_phase_inherits_ast_backfill_failure(self, tool_with_root):
        result = tool_with_root._phase_synapse({"status": "ok", "backfill_errors": 1})

        assert (result["status"], result["backfill_errors"]) == ("error", 1)

    async def test_synapse_phase_counts_unresolved_backfill(self, tool_with_root):
        result = tool_with_root._phase_synapse(
            {"status": "ok", "unresolved_refs_backfill": {"resolved": 2}}
        )

        assert result["resolved_edges"] == 2

    async def test_synapse_phase_ignores_non_mapping_backfills(self, tool_with_root):
        result = tool_with_root._phase_synapse(
            {
                "status": "ok",
                "synapse_backfill": "invalid",
                "unresolved_refs_backfill": "invalid",
            }
        )

        assert result["resolved_edges"] == 0

    async def test_scope_options_are_forwarded_to_incremental_phase(
        self, tool_with_root
    ):
        # Incident 2026-07-26: sync discarded max_files and exclude_patterns.
        with (
            patch.object(
                tool_with_root,
                "_phase_ast_cache",
                return_value={"status": "ok"},
            ),
            patch.object(
                tool_with_root,
                "_phase_incremental_sync",
                return_value={"status": "ok"},
            ) as incremental_phase,
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
            await tool_with_root.execute(
                {
                    "mode": "incremental",
                    "max_files": 7,
                    "exclude_patterns": ["vendor/*"],
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        incremental_phase.assert_called_once()
        call_args, call_kwargs = incremental_phase.call_args
        assert call_args == (
            7,
            frozenset({"tests/golden/corpus_*", "vendor/*"}),
        )
        snapshot = call_kwargs["candidate_snapshot"]
        assert snapshot.max_files == 7
        assert snapshot.selected == 1

    async def test_no_default_excludes_are_forwarded_exactly(self, tool_with_root):
        # Incident 2026-07-26: sync silently restored disabled default excludes.
        with (
            patch.object(
                tool_with_root,
                "_phase_ast_cache",
                return_value={"status": "ok"},
            ),
            patch.object(
                tool_with_root,
                "_phase_incremental_sync",
                return_value={"status": "ok"},
            ) as incremental_phase,
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
            await tool_with_root.execute(
                {
                    "mode": "incremental",
                    "max_files": 3,
                    "exclude_patterns": ["vendor/*"],
                    "no_default_excludes": True,
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        incremental_phase.assert_called_once()
        call_args, call_kwargs = incremental_phase.call_args
        assert call_args == (3, frozenset({"vendor/*"}))
        snapshot = call_kwargs["candidate_snapshot"]
        assert snapshot.max_files == 3
        assert snapshot.selected == 1

    async def test_normalized_patterns_are_persisted_in_both_phase_scopes(
        self, tool_with_root
    ):
        with (
            patch.object(
                tool_with_root,
                "_phase_ast_cache",
                return_value={"status": "ok", "processed": 0},
            ) as ast_phase,
            patch.object(
                tool_with_root,
                "_phase_incremental_sync",
                return_value={"status": "ok", "processed": 0},
            ) as sync_phase,
            patch.object(
                tool_with_root, "_phase_fts5_stats", return_value={"status": "ok"}
            ),
            patch.object(
                tool_with_root,
                "_phase_call_edge_stats",
                return_value={"status": "ok"},
            ),
            patch.object(
                tool_with_root,
                "_collect_final_stats",
                return_value={"_manifest_certified": True},
            ),
        ):
            await tool_with_root.execute(
                {
                    "mode": "full",
                    "exclude_patterns": [r"src\generated\*"],
                    "no_default_excludes": True,
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        ast_scope = ast_phase.call_args.kwargs["source_scope"]
        sync_scope = sync_phase.call_args.kwargs["source_scope"]
        assert (ast_scope.exclude_patterns, sync_scope.exclude_patterns) == (
            ("src/generated/*",),
            ("src/generated/*",),
        )

    async def test_full_mode_max_files_bounds_both_phases(self, tmp_path):
        # Incident 2026-07-26: sync re-indexed files beyond the requested cap.
        (tmp_path / "a.py").write_text("a = 1\n")
        (tmp_path / "b.py").write_text("b = 2\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))

        result = await full_tool.execute(
            {
                "mode": "full",
                "max_files": 1,
                "resolve_synapse": False,
                "output_format": "json",
            }
        )

        assert _cache_total_files(tmp_path) == 0
        assert result["success"] is False
        assert result["verdict"] == "WARN"
        assert result["phases"]["ast_cache"]["truncated_by_max_files"] is True
        assert result["phases"]["ast_cache"]["errors"] == 1
        assert result["phases"]["ast_cache"]["abort_remaining_phases"] is True
        assert result["phases"]["remaining_phases"]["status"] == "skipped"
        assert "incremental_sync" not in result["phases"]
        assert result["candidate_snapshot"]["discovered"] == 2
        assert result["candidate_snapshot"]["selected"] == 1
        assert result["candidate_snapshot"]["limited_by_max_files"] == 1
        assert result["candidate_snapshot"]["discovery_reconciled"] is True

    async def test_unsafe_force_abort_never_calls_incremental_or_final_writes(
        self, tmp_path
    ):
        # PR #1253 review 3759391272: terminal force results stop the pipeline.
        (tmp_path / "app.py").write_text("value = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))

        with (
            patch.object(
                full_tool,
                "_phase_ast_cache",
                return_value={
                    "status": "error",
                    "abort_remaining_phases": True,
                    "changed_during_run": 1,
                    "changed_during_run_files": ["app.py"],
                },
            ),
            patch.object(full_tool, "_phase_incremental_sync") as incremental,
            patch.object(full_tool, "_collect_final_stats") as final_stats,
        ):
            result = await full_tool.execute({"mode": "full", "output_format": "json"})

        incremental.assert_not_called()
        final_stats.assert_not_called()
        assert result["success"] is False
        assert result["phases"]["remaining_phases"]["status"] == "skipped"

    async def test_full_mode_shared_cache_construction_failure_aborts_handoff(
        self, tmp_path
    ):
        # PR #1253 P1: full mode never falls back to a second pathname owner.
        (tmp_path / "app.py").write_text("value = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))

        with (
            patch(
                "tree_sitter_analyzer.ast_cache.ASTCache",
                side_effect=OSError("injected cache construction failure"),
            ),
            patch.object(full_tool, "_phase_ast_cache") as ast_phase,
            patch.object(full_tool, "_phase_incremental_sync") as incremental,
        ):
            result = await full_tool.execute({"mode": "full", "output_format": "json"})

        ast_phase.assert_not_called()
        incremental.assert_not_called()
        assert result["success"] is False
        assert result["phases"]["ast_cache"]["abort_remaining_phases"] is True
        assert result["phases"]["ast_cache"]["error"] == (
            "OSError: injected cache construction failure"
        )

    async def test_full_mode_legacy_platform_reaches_incremental_phase(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: unsupported root leases preserve the Windows legacy data plane.
        import tree_sitter_analyzer.indexing_candidate_materialization as materialization

        (tmp_path / "app.py").write_text("value = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))
        monkeypatch.setattr(
            materialization,
            "secure_candidate_materialization_supported",
            lambda: False,
        )

        result = await full_tool.execute(
            {"mode": "full", "resolve_synapse": False, "output_format": "json"}
        )

        assert result["phases"]["ast_cache"]["abort_remaining_phases"] is False
        assert result["phases"]["incremental_sync"]["status"] == "ok"

    @pytest.mark.skipif(os.name != "posix", reason="GH-1253: frozen handoff")
    async def test_full_handoff_validation_gets_fresh_bounded_deadline(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3763401188: AST duration must not expire handoff evidence.
        import tree_sitter_analyzer.indexing_candidate_materialization as materialization

        (tmp_path / "app.py").write_text("value = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))
        snapshot = full_tool._build_candidate_snapshot(
            20_000, frozenset(), materialize=True
        )
        assert snapshot.frozen_read_deadline is not None
        expired_at_handoff = snapshot.frozen_read_deadline + 1.0
        observed_deadlines = []

        def validate_handoff(candidate, *, deadline=None):
            observed_deadlines.append(deadline)
            return deadline is not None and deadline > expired_at_handoff

        monkeypatch.setattr(
            materialization,
            "index_candidate_snapshot_is_materialized",
            validate_handoff,
        )
        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.full_index_tool.time",
            SimpleNamespace(monotonic=lambda: expired_at_handoff),
        )
        with (
            patch.object(full_tool, "_build_candidate_snapshot", return_value=snapshot),
            patch.object(
                full_tool,
                "_phase_ast_cache",
                return_value={"status": "ok", "changed_during_run": 0},
            ),
            patch.object(
                full_tool,
                "_phase_incremental_sync",
                return_value={"status": "ok", "processed": 1},
            ) as incremental,
            patch.object(full_tool, "_phase_fts5_stats", return_value={"status": "ok"}),
            patch.object(
                full_tool, "_phase_call_edge_stats", return_value={"status": "ok"}
            ),
            patch.object(
                full_tool,
                "_collect_final_stats",
                return_value={"_manifest_certified": True},
            ),
        ):
            result = await full_tool.execute(
                {"mode": "full", "resolve_synapse": False, "output_format": "json"}
            )

        incremental.assert_called_once()
        assert observed_deadlines == [expired_at_handoff + 35.0]
        assert "snapshot_handoff_error" not in result["phases"]["ast_cache"]

    @pytest.mark.skipif(
        os.name != "posix", reason="GH-1253: requires POSIX root rename"
    )
    async def test_full_mode_root_swap_before_handoff_check_aborts(self, tmp_path):
        (tmp_path / "app.py").write_text("value = 1\n")
        displaced = tmp_path.with_name(f"{tmp_path.name}-displaced")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))

        def swap_root(*_args, **_kwargs):
            tmp_path.rename(displaced)
            tmp_path.mkdir()
            return {"status": "ok", "changed_during_run": 0}

        with (
            patch.object(full_tool, "_phase_ast_cache", side_effect=swap_root),
            patch.object(full_tool, "_phase_incremental_sync") as incremental,
        ):
            result = await full_tool.execute({"mode": "full", "output_format": "json"})

        incremental.assert_not_called()
        assert result["phases"]["ast_cache"]["snapshot_handoff_error"] == (
            "INDEX_CANDIDATE_FROZEN_EVIDENCE_INVALID"
        )

    @pytest.mark.skipif(
        os.name != "posix", reason="GH-1253: requires POSIX root rename"
    )
    async def test_full_mode_root_swap_after_handoff_check_reuses_cache_owner(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3763821273: a replacement after frozen validation is
        # rejected by the independent visible-hierarchy validation.
        import tree_sitter_analyzer.indexing_candidate_materialization as materialization

        (tmp_path / "app.py").write_text("value = 1\n")
        displaced = tmp_path.with_name(f"{tmp_path.name}-displaced")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))
        real_check = materialization.index_candidate_snapshot_is_materialized
        phase_caches = []

        def check_then_swap(snapshot, *, deadline=None):
            assert real_check(snapshot, deadline=deadline) is True
            tmp_path.rename(displaced)
            tmp_path.mkdir()
            (tmp_path / "sentinel").write_text("replacement\n")
            return True

        def ast_phase(*_args, _cache=None, **_kwargs):
            phase_caches.append(_cache)
            return {"status": "ok", "changed_during_run": 0}

        def incremental_phase(*_args, _cache=None, **_kwargs):
            phase_caches.append(_cache)
            return {"status": "error", "processed": 0, "changed_during_run": 1}

        monkeypatch.setattr(
            materialization,
            "index_candidate_snapshot_is_materialized",
            check_then_swap,
        )
        with (
            patch.object(full_tool, "_phase_ast_cache", side_effect=ast_phase),
            patch.object(
                full_tool,
                "_phase_incremental_sync",
                side_effect=incremental_phase,
            ),
        ):
            result = await full_tool.execute({"mode": "full", "output_format": "json"})

        assert len(phase_caches) == 1
        assert phase_caches[0] is not None
        assert result["phases"]["ast_cache"]["snapshot_handoff_error"] == (
            "INDEX_CACHE_HIERARCHY_CHANGED"
        )
        assert result["phases"]["remaining_phases"]["status"] == "skipped"
        assert sorted(path.name for path in tmp_path.iterdir()) == ["sentinel"]

    @pytest.mark.skipif(
        os.name != "posix", reason="GH-1253: requires POSIX cache hierarchy"
    )
    async def test_full_mode_cache_swap_after_ast_phase_aborts_later_writes(
        self, tmp_path
    ):
        # PR #1253 thread 3763821273: later phases revalidate the pinned cache.
        (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))
        displaced_cache = tmp_path / ".ast-cache-displaced"

        def ast_then_swap(*_args, _cache=None, **_kwargs):
            assert _cache is not None
            (tmp_path / ".ast-cache").rename(displaced_cache)
            (tmp_path / ".ast-cache").mkdir()
            (tmp_path / ".ast-cache" / "replacement").write_text(
                "untouched\n", encoding="utf-8"
            )
            return {"status": "ok", "changed_during_run": 0}

        with (
            patch.object(full_tool, "_phase_ast_cache", side_effect=ast_then_swap),
            patch.object(full_tool, "_phase_incremental_sync") as incremental,
            patch.object(full_tool, "_collect_final_stats") as final_stats,
        ):
            result = await full_tool.execute({"mode": "full", "output_format": "json"})

        incremental.assert_not_called()
        final_stats.assert_not_called()
        assert (
            result["phases"]["ast_cache"]["abort_remaining_phases"],
            result["phases"]["ast_cache"]["snapshot_handoff_error"],
            (tmp_path / ".ast-cache" / "replacement").read_text(encoding="utf-8"),
        ) == (True, "INDEX_CACHE_HIERARCHY_CHANGED", "untouched\n")

    @pytest.mark.skipif(
        os.name != "posix", reason="GH-1253: requires POSIX cache hierarchy"
    )
    async def test_full_mode_cache_swap_after_incremental_aborts_final_stats(
        self, tmp_path
    ):
        (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))
        displaced = tmp_path / ".ast-cache-displaced"

        def incremental_then_swap(*_args, **_kwargs):
            (tmp_path / ".ast-cache").rename(displaced)
            (tmp_path / ".ast-cache").mkdir()
            return {"status": "ok", "processed": 1, "changed_during_run": 0}

        with (
            patch.object(
                full_tool, "_phase_incremental_sync", side_effect=incremental_then_swap
            ),
            patch.object(full_tool, "_collect_final_stats") as final_stats,
        ):
            result = await full_tool.execute({"mode": "full", "output_format": "json"})
        final_stats.assert_not_called()
        assert (result["success"], result["phases"]["remaining_phases"]["status"]) == (
            False,
            "skipped",
        )

    async def test_full_index_walks_project_once_for_both_phases(self, tmp_path):
        import tree_sitter_analyzer.mcp.tools.full_index_tool as full_index_module

        (tmp_path / "a.py").write_text("a = 1\n")
        (tmp_path / "b.py").write_text("b = 2\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))

        with patch.object(
            full_index_module,
            "walk_index_candidate_entries",
            wraps=full_index_module.walk_index_candidate_entries,
        ) as walk:
            result = await full_tool.execute(
                {
                    "mode": "full",
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        assert walk.call_count == 1
        assert result["candidate_snapshot"]["selected"] == 2
        assert result["candidate_snapshot"]["processed"] == 2

    async def test_cached_snapshot_completeness_does_not_trigger_another_walk(
        self, tmp_path
    ):
        (tmp_path / "app.py").write_text("value = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))
        await full_tool.execute(
            {
                "mode": "incremental",
                "resolve_synapse": False,
                "output_format": "json",
            }
        )

        with patch.object(
            ASTCache,
            "_indexed_source_files_are_complete",
            side_effect=AssertionError("legacy completeness walk used"),
        ):
            result = await full_tool.execute(
                {
                    "mode": "incremental",
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        assert result["candidate_snapshot"]["processed"] == 1
        assert result["candidate_snapshot"]["phase_totals_reconciled"] is True

    async def test_both_index_phases_receive_the_same_snapshot_object(self, tmp_path):
        (tmp_path / "app.py").write_text("value = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))
        received = []

        def ast_phase(*_args, candidate_snapshot, **_kwargs):
            received.append(candidate_snapshot)
            return {
                "status": "ok",
                "processed": candidate_snapshot.selected,
                "changed_during_run": 0,
                "changed_during_run_files": [],
            }

        def incremental_phase(*_args, candidate_snapshot, **_kwargs):
            received.append(candidate_snapshot)
            return {
                "status": "ok",
                "processed": candidate_snapshot.selected,
                "changed_during_run": 0,
                "changed_during_run_files": [],
            }

        with (
            patch.object(full_tool, "_phase_ast_cache", side_effect=ast_phase),
            patch.object(
                full_tool,
                "_phase_incremental_sync",
                side_effect=incremental_phase,
            ),
            patch.object(
                full_tool,
                "_phase_fts5_stats",
                return_value={"status": "ok"},
            ),
            patch.object(
                full_tool,
                "_phase_call_edge_stats",
                return_value={"status": "ok"},
            ),
            patch.object(full_tool, "_collect_final_stats", return_value={}),
        ):
            await full_tool.execute(
                {
                    "mode": "incremental",
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        assert len(received) == 2
        assert received[0] is received[1]
        assert received[0].selected_entries[0].rel_path == "app.py"

    async def test_elapsed_time_includes_snapshot_discovery(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text("value = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))
        snapshot = full_tool._build_candidate_snapshot(
            10,
            frozenset(),
        )
        events = []
        ticks = iter((10.0, 15.0))

        def clock():
            events.append("clock")
            return next(ticks)

        def build_snapshot(*_args):
            events.append("snapshot")
            return snapshot

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.full_index_tool.time.monotonic",
                side_effect=clock,
            ),
            patch.object(
                full_tool,
                "_build_candidate_snapshot",
                side_effect=build_snapshot,
            ),
            patch.object(
                full_tool,
                "_phase_ast_cache",
                return_value={"status": "ok", "processed": 1},
            ),
            patch.object(
                full_tool,
                "_phase_incremental_sync",
                return_value={"status": "ok", "processed": 1},
            ),
            patch.object(
                full_tool,
                "_phase_fts5_stats",
                return_value={"status": "ok"},
            ),
            patch.object(
                full_tool,
                "_phase_call_edge_stats",
                return_value={"status": "ok"},
            ),
            patch.object(full_tool, "_collect_final_stats", return_value={}),
        ):
            result = await full_tool.execute(
                {
                    "mode": "incremental",
                    "max_files": 10,
                    "resolve_synapse": False,
                    "output_format": "json",
                    "no_default_excludes": True,
                }
            )

        assert events == ["clock", "snapshot", "clock"]
        assert result["elapsed_seconds"] == 5.0

    @pytest.mark.skipif(
        os.name != "posix", reason="GH-1253: authoritative frozen epoch"
    )
    async def test_mutation_between_phases_is_skipped_and_reported(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text("value = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))
        original_ast_phase = full_tool._phase_ast_cache

        def ast_then_mutate(*args, **kwargs):
            phase = original_ast_phase(*args, **kwargs)
            path.write_text("value = 200\n")
            return phase

        with patch.object(
            full_tool,
            "_phase_ast_cache",
            side_effect=ast_then_mutate,
        ):
            result = await full_tool.execute(
                {
                    "mode": "full",
                    "resolve_synapse": False,
                    "output_format": "json",
                }
            )

        scope = result["candidate_snapshot"]
        incremental = result["phases"]["incremental_sync"]
        assert result["verdict"] == "WARN"
        assert scope["selected"] == 1
        # PR #1253: the complete frozen epoch remains indexed despite live drift.
        assert scope["processed"] == 1
        assert scope["changed_during_run"] == 1
        assert scope["changed_during_run_files"] == ["app.py"]
        assert scope["changed_during_run_details"] == [
            {
                "file": "app.py",
                "status": "warning",
                "reason": "file changed after candidate snapshot",
            }
        ]
        assert scope["selection_reconciled"] is True
        assert scope["phase_totals_reconciled"] is True
        assert incremental["changed_during_run"] == 1
        assert incremental["processed"] == 1
        cache = ASTCache(str(tmp_path))
        row = (
            cache.get_conn()
            .execute("SELECT content_hash FROM ast_index WHERE file_path='app.py'")
            .fetchone()
        )
        cache.close()
        assert row["content_hash"] == hashlib.sha256(b"value = 1\n").hexdigest()

    async def test_default_exclude_is_not_reintroduced_by_sync(self, tmp_path):
        # Incident 2026-07-26: sync reintroduced a default-excluded corpus file.
        (tmp_path / "app.py").write_text("app = 1\n")
        golden = tmp_path / "tests" / "golden"
        golden.mkdir(parents=True)
        (golden / "corpus_bad.py").write_text("bad = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))

        await full_tool.execute(
            {
                "mode": "full",
                "resolve_synapse": False,
                "output_format": "json",
            }
        )

        assert _cache_file_paths(tmp_path) == {"app.py"}

    async def test_custom_exclude_is_not_reintroduced_by_sync(self, tmp_path):
        # Incident 2026-07-26: sync reintroduced a custom-excluded source file.
        (tmp_path / "app.py").write_text("app = 1\n")
        src = tmp_path / "src"
        src.mkdir()
        (src / "skip.py").write_text("skip = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))

        await full_tool.execute(
            {
                "mode": "full",
                "exclude_patterns": ["src/*"],
                "resolve_synapse": False,
                "output_format": "json",
            }
        )

        assert _cache_file_paths(tmp_path) == {"app.py"}

    async def test_no_default_excludes_indexes_golden_file(self, tmp_path):
        # Incident 2026-07-26: both phases must share the custom-only scope.
        (tmp_path / "app.py").write_text("app = 1\n")
        golden = tmp_path / "tests" / "golden"
        golden.mkdir(parents=True)
        (golden / "corpus_allowed.py").write_text("allowed = 1\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))

        await full_tool.execute(
            {
                "mode": "full",
                "no_default_excludes": True,
                "resolve_synapse": False,
                "output_format": "json",
            }
        )

        assert _cache_file_paths(tmp_path) == {
            "app.py",
            "tests/golden/corpus_allowed.py",
        }


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

    def test_orchestrated_ast_phase_defers_manifest_certification(self, tool_with_root):
        # PR #1253 review 3755736551: only the final phase may certify.
        ast_result = {"indexed": 0, "cached": 0, "errors": 0, "files": []}
        with patch("tree_sitter_analyzer.ast_cache.ASTCache") as cache_cls:
            cache_cls.return_value.index_project.return_value = ast_result
            tool_with_root._phase_ast_cache(False, 10)

        assert (
            cache_cls.return_value.index_project.call_args.kwargs["certify_manifest"]
            is False
        )

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


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
async def test_full_orchestration_stamps_manifest_exactly_once(tmp_path):
    # PR #1253 review 3755736551: intermediate engines must not re-certify.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    (tmp_path / "sample.py").write_text("value = 1\n")
    tool = CodeGraphFullIndexTool(str(tmp_path))
    with patch.object(
        schema,
        "stamp_full_index_manifest",
        wraps=schema.stamp_full_index_manifest,
    ) as stamp:
        result = await tool.execute({"mode": "full", "output_format": "json"})

    assert (result["verdict"], stamp.call_count) == ("INFO", 1)


def test_final_stats_stamp_failure_does_not_delete_later_manifest(tmp_path):
    # PR #1253 review 3755736546: callers only downgrade stamper failures.
    import tree_sitter_analyzer.index_snapshot_schema as schema
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(str(tmp_path))
    conn = cache.get_conn()
    conn.execute(
        "INSERT INTO ast_index_snapshot_manifest "
        "(singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version) "
        "VALUES (1, 'root', 'source', 'index', 0, 'scope', 2)"
    )
    conn.commit()
    cache.close()

    tool = CodeGraphFullIndexTool(str(tmp_path))
    with patch.object(
        schema,
        "stamp_full_index_manifest",
        side_effect=RuntimeError("busy"),
    ):
        result = tool._collect_final_stats(stamp_manifest=True)

    cache = ASTCache(str(tmp_path))
    manifest = (
        cache.get_conn()
        .execute("SELECT index_fingerprint FROM ast_index_snapshot_manifest")
        .fetchone()
    )
    cache.close()
    assert (
        result["manifest_warning"],
        result["manifest_certification_failed"],
        result["certification_errors"],
        result["scope_complete"],
        manifest[0],
    ) == ("INDEX_MANIFEST_CERTIFICATION_FAILED", True, 1, False, "index")


class TestGrammarErrorsOnly:
    """Unit tests for _grammar_errors_only helper."""

    def test_all_grammar_errors_returns_true(self):
        phases = {
            "ast_cache": {
                "error_details_total": 2,
                "error_details": [
                    {"reason": "Swift grammar not installed — pip install tree-sitter-analyzer[swift]"},
                    {"reason": "LUA grammar not installed — pip install tree-sitter-analyzer[lua]"},
                ],
            }
        }
        assert _grammar_errors_only(phases) is True

    def test_mixed_errors_returns_false(self):
        phases = {
            "ast_cache": {
                "error_details_total": 2,
                "error_details": [
                    {"reason": "Swift grammar not installed — pip install tree-sitter-analyzer[swift]"},
                    {"reason": "File read error: permission denied"},
                ],
            }
        }
        assert _grammar_errors_only(phases) is False

    def test_no_errors_returns_false(self):
        phases = {"ast_cache": {"error_details_total": 0, "error_details": []}}
        assert _grammar_errors_only(phases) is False

    def test_truncated_details_returns_false(self):
        phases = {
            "ast_cache": {
                "error_details_total": 5,
                "error_details": [
                    {"reason": "Swift grammar not installed — pip install tree-sitter-analyzer[swift]"},
                ],
            }
        }
        assert _grammar_errors_only(phases) is False

    def test_non_dict_phase_is_skipped(self):
        phases = {
            "fts5": "ok",  # non-dict phase value
            "ast_cache": {
                "error_details_total": 1,
                "error_details": [
                    {"reason": "Ruby grammar not installed — pip install tree-sitter-analyzer[ruby]"},
                ],
            },
        }
        assert _grammar_errors_only(phases) is True

    def test_multiple_phases_all_grammar_errors(self):
        phases = {
            "ast_cache": {
                "error_details_total": 1,
                "error_details": [{"reason": "Swift grammar not installed — ..."}],
            },
            "incremental_sync": {
                "error_details_total": 1,
                "error_details": [{"reason": "LUA grammar not installed — ..."}],
            },
        }
        assert _grammar_errors_only(phases) is True


@pytest.mark.asyncio
async def test_grammar_only_errors_yield_success_true(tool_with_root):
    """When all errors are optional grammar packages, success must be True."""
    grammar_error_phase = {
        "status": "error",
        "processed": 1,
        "errors": 1,
        "completeness": "incomplete",
        "scope_complete": False,
        "error_details_total": 1,
        "error_details": [
            {
                "file": "sample.swift",
                "reason": "Swift grammar not installed — pip install tree-sitter-analyzer[swift]",
            }
        ],
    }
    clean_phase = {"status": "ok", "processed": 0, "errors": 0}
    with (
        patch.object(tool_with_root, "_phase_ast_cache", return_value=grammar_error_phase),
        patch.object(
            tool_with_root, "_phase_incremental_sync", return_value=grammar_error_phase
        ),
        patch.object(tool_with_root, "_phase_fts5_stats", return_value={"status": "ok"}),
        patch.object(
            tool_with_root,
            "_phase_call_edge_stats",
            return_value={"status": "ok"},
        ),
        patch.object(
            tool_with_root,
            "_collect_final_stats",
            return_value={"scope_complete": False},
        ),
    ):
        result = await tool_with_root.execute(
            {"mode": "incremental", "resolve_synapse": False, "output_format": "json"}
        )

    assert result["success"] is True
    assert result["verdict"] == "WARN"


def test_collect_final_stats_returns_empty_on_cache_failure(tmp_path, monkeypatch):
    import tree_sitter_analyzer.ast_cache as ast_cache

    monkeypatch.setattr(
        ast_cache, "ASTCache", Mock(side_effect=RuntimeError("cache unavailable"))
    )
    result = CodeGraphFullIndexTool(str(tmp_path))._collect_final_stats()
    assert result == {}


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
async def test_full_index_accepts_configured_symlink_root(tmp_path):
    # PR #1253 review 3761093597: canonicalize once before no-follow traversal.
    real_root = tmp_path / "real"
    real_root.mkdir()
    (real_root / "sample.py").write_text("value = 1\n")
    link_root = tmp_path / "configured-root"
    link_root.symlink_to(real_root, target_is_directory=True)

    result = await CodeGraphFullIndexTool(str(link_root)).execute(
        {"mode": "full", "output_format": "json"}
    )

    assert (
        result["success"],
        result["verdict"],
        result["total_files"],
        result["phases"]["incremental_sync"]["completeness"],
    ) == (True, "INFO", 1, "complete")


def test_incremental_phase_converts_cache_failure_to_phase_error(tmp_path, monkeypatch):
    import tree_sitter_analyzer.ast_cache as cache_module

    monkeypatch.setattr(
        cache_module,
        "ASTCache",
        lambda _root: (_ for _ in ()).throw(RuntimeError("open failed")),
    )
    result = CodeGraphFullIndexTool(str(tmp_path))._phase_incremental_sync()
    assert (result["status"], result["error"]) == ("error", "RuntimeError: open failed")


class TestIncrementalPhaseScope:
    def test_forwards_limit_above_old_hardcoded_cap_to_engine(self, tool_with_root):
        # Incident 2026-07-26: the phase hard-coded a 20,000-file ceiling.
        exclude_patterns = frozenset({"tests/golden/corpus_*"})
        sync_result = SyncResult()
        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache"),
            patch("tree_sitter_analyzer.incremental_sync.IncrementalSync") as sync_cls,
        ):
            sync_cls.return_value.sync.return_value = sync_result
            tool_with_root._phase_incremental_sync(25_001, exclude_patterns)

        sync_cls.return_value.sync.assert_called_once_with(
            max_files=25_001,
            exclude_patterns=exclude_patterns,
            certify_manifest=False,
        )


def test_fts_stats_converts_cache_failure_to_phase_error(tmp_path, monkeypatch):
    import tree_sitter_analyzer.ast_cache as cache_module

    monkeypatch.setattr(
        cache_module,
        "ASTCache",
        lambda _root: (_ for _ in ()).throw(RuntimeError("open failed")),
    )
    result = CodeGraphFullIndexTool(str(tmp_path))._phase_fts5_stats()
    assert (result["status"], result["error"]) == ("error", "RuntimeError: open failed")


def test_call_edge_stats_converts_cache_failure_to_phase_error(tmp_path, monkeypatch):
    # PR #1253: final stats remain bounded when opening the cache fails.
    import tree_sitter_analyzer.ast_cache as cache_module

    monkeypatch.setattr(
        cache_module,
        "ASTCache",
        lambda _root: (_ for _ in ()).throw(RuntimeError("open failed")),
    )

    result = CodeGraphFullIndexTool(str(tmp_path))._phase_call_edge_stats()

    assert (result["status"], result["error"]) == ("error", "RuntimeError: open failed")


@pytest.mark.asyncio
async def test_incremental_scope_change_prunes_newly_excluded_rows(tmp_path):
    # PR #1253: a newly excluded file cannot survive in primary or graph rows.
    keep = tmp_path / "keep.py"
    drop = tmp_path / "drop.py"
    keep.write_text("def keep():\n    return 1\n")
    drop.write_text("def drop():\n    return keep()\n")
    tool = CodeGraphFullIndexTool(str(tmp_path))
    first = await tool.execute(
        {"mode": "full", "resolve_synapse": False, "output_format": "json"}
    )
    # PR #1254: full indexing and its portable manifest are cross-platform.
    assert first["success"] is True

    second = await tool.execute(
        {
            "mode": "incremental",
            "exclude_patterns": ["drop.py"],
            "resolve_synapse": False,
            "output_format": "json",
        }
    )
    cache = ASTCache(str(tmp_path))
    try:
        paths = {
            str(row[0])
            for row in cache.get_conn().execute("SELECT file_path FROM ast_index")
        }
        graph_rows = (
            cache.get_conn()
            .execute("SELECT COUNT(*) FROM edges WHERE file_path = 'drop.py'")
            .fetchone()[0]
        )
        graph_built = cache.call_graph_built()
    finally:
        cache.close()

    assert (second["success"], paths, graph_rows, graph_built) == (
        True,
        {"keep.py"},
        0,
        True,
    )


async def test_execute_exception_releases_materialized_candidate(tool_with_root):
    # PR #1253 thread 3760428941: exceptional exits share the release boundary.
    with (
        patch.object(
            tool_with_root,
            "_phase_ast_cache",
            side_effect=RuntimeError("primary phase failed"),
        ),
        pytest.raises(RuntimeError, match="primary phase failed"),
    ):
        await tool_with_root.execute(
            {"mode": "full", "max_files": 10, "output_format": "json"}
        )


@pytest.mark.asyncio
async def test_candidate_discovery_exception_returns_structured_error(tmp_path):
    # PR #1253 thread 3763044680: discovery failures cross the MCP boundary safely.
    tool = CodeGraphFullIndexTool(str(tmp_path))
    with patch.object(
        tool, "_build_candidate_snapshot", side_effect=OSError("walk failed")
    ):
        result = await tool.execute({"mode": "incremental", "output_format": "json"})

    assert (result["success"], result["verdict"], result["phase"]) == (
        False,
        "ERROR",
        "candidate_discovery",
    )
    assert result["error"] == "Candidate discovery failed: OSError: walk failed"


def test_collect_final_stats_source_scope_unsupported_is_operational(tmp_path):
    # PR #1253 thread 3762955392: platform incapability is warning-only.
    cache = MagicMock()
    cache.get_stats.return_value = {}
    tool = CodeGraphFullIndexTool(str(tmp_path))
    with patch(
        "tree_sitter_analyzer.index_snapshot_schema.stamp_full_index_manifest",
        side_effect=sqlite3.OperationalError("SOURCE_SCOPE_UNSUPPORTED"),
    ):
        result = tool._collect_final_stats(stamp_manifest=True, _cache=cache)

    assert (
        result["manifest_warning"],
        result["manifest_certification_failed"],
        result["certification_errors"],
    ) == ("SOURCE_SCOPE_UNSUPPORTED", False, 0)


def test_manifest_warning_carries_an_actionable_next_step() -> None:
    """A WARN that names no action is a WARN an agent reads past.

    Dogfood, 2026-08-20: --full-index returned verdict=WARN,
    scope_complete=False and manifest_warning=INDEX_MANIFEST_CERTIFICATION_FAILED
    with exit code 1 -- all correct -- but agent_summary.next_step was absent.
    Every other route used in that session (--callers, --test-map,
    --safe-to-edit, --self-health) carries a next_step, so that is the field an
    agent is trained to read. The one output meaning 'do not trust graph
    queries from this run' was the only one with nothing there, and the agent
    ran --callers immediately afterwards.
    """
    from tree_sitter_analyzer.mcp.tools.full_index_tool import (
        manifest_warning_next_step,
    )

    step = manifest_warning_next_step("INDEX_MANIFEST_CERTIFICATION_FAILED")

    assert step is not None
    lowered = step.lower()
    assert "re-index" in lowered
    assert "not certified" in lowered
    assert "--callers" in step


def test_a_certified_run_reports_no_remedial_next_step() -> None:
    """The remedial step must be absent when nothing needs remedying."""
    from tree_sitter_analyzer.mcp.tools.full_index_tool import (
        manifest_warning_next_step,
    )

    assert manifest_warning_next_step(None) is None


def test_an_unrecognised_warning_still_gets_a_next_step() -> None:
    """A new warning code must not silently fall back to no guidance."""
    from tree_sitter_analyzer.mcp.tools.full_index_tool import (
        manifest_warning_next_step,
    )

    step = manifest_warning_next_step("SOME_FUTURE_CODE")

    assert step is not None
    assert "SOME_FUTURE_CODE" in step
