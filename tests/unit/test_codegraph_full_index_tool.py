"""Tests for codegraph_full_index MCP tool — one-shot complete project intelligence."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.incremental_sync import SyncResult
from tree_sitter_analyzer.mcp.tools.full_index_tool import (
    CodeGraphFullIndexTool,
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

        incremental_phase.assert_called_once_with(
            7,
            frozenset({"tests/golden/corpus_*", "vendor/*"}),
        )

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

        incremental_phase.assert_called_once_with(3, frozenset({"vendor/*"}))

    async def test_full_mode_max_files_bounds_both_phases(self, tmp_path):
        # Incident 2026-07-26: sync re-indexed files beyond the requested cap.
        (tmp_path / "a.py").write_text("a = 1\n")
        (tmp_path / "b.py").write_text("b = 2\n")
        full_tool = CodeGraphFullIndexTool(str(tmp_path))

        await full_tool.execute(
            {
                "mode": "full",
                "max_files": 1,
                "resolve_synapse": False,
                "output_format": "json",
            }
        )

        assert _cache_total_files(tmp_path) == 1

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
