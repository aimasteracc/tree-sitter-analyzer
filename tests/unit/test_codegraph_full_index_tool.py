"""Tests for codegraph_full_index MCP tool — one-shot complete project intelligence."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.incremental_sync import SyncResult
from tree_sitter_analyzer.mcp.tools.full_index_tool import (
    CodeGraphFullIndexTool,
    _candidate_snapshot_report,
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

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )

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

        assert result["success"] is True
        assert result["verdict"] == "WARN"
        assert collect_stats.call_args.kwargs["stamp_manifest"] is False

    async def test_synapse_phase_inherits_ast_backfill_failure(self, tool_with_root):
        result = tool_with_root._phase_synapse({"status": "ok", "backfill_errors": 1})

        assert result["status"] == "error"
        assert result["backfill_errors"] == 1

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

        assert _cache_total_files(tmp_path) == 1
        assert result["phases"]["ast_cache"]["truncated_by_max_files"] is True
        assert result["phases"]["incremental_sync"]["truncated_by_max_files"] is True
        assert result["candidate_snapshot"]["discovered"] == 2
        assert result["candidate_snapshot"]["selected"] == 1
        assert result["candidate_snapshot"]["limited_by_max_files"] == 1
        assert result["candidate_snapshot"]["discovery_reconciled"] is True
        assert result["candidate_snapshot"]["phase_totals_reconciled"] is True

    async def test_full_index_walks_project_once_for_both_phases(self, tmp_path):
        from tree_sitter_analyzer.cache import indexer

        (tmp_path / "a.py").write_text("a = 1\n")
        (tmp_path / "b.py").write_text("b = 2\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))

        with patch.object(
            indexer,
            "_walk_source_files",
            wraps=indexer._walk_source_files,
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
        assert scope["processed"] == 0
        assert scope["changed_during_run"] == 1
        assert scope["changed_during_run_files"] == ["app.py"]
        assert scope["changed_during_run_details"] == [
            {
                "file": "app.py",
                "status": "skipped",
                "reason": "file changed after candidate snapshot",
            }
        ]
        assert scope["selection_reconciled"] is True
        assert scope["phase_totals_reconciled"] is True
        assert incremental["changed_during_run"] == 1
        assert incremental["processed"] == 0

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
        )


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
