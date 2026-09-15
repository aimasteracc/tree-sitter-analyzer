"""Tests for codegraph_callers and codegraph_callees dedicated MCP tools."""

from pathlib import Path

import pytest

from tests.unit._navigation_test_support import build_many_relation_project
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache import build_state
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.codegraph_relation_tool import (
    CodeGraphRelationToolMixin,
)

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


@pytest.fixture
def callers_tool():
    return CodeGraphCallersTool(_PROJECT_ROOT)


@pytest.fixture
def callees_tool():
    return CodeGraphCalleesTool(_PROJECT_ROOT)


@pytest.fixture
def tiny_project_root(tmp_path):
    (tmp_path / "sample.py").write_text(
        "def foo():\n    bar()\n\ndef bar():\n    return 1\n",
        encoding="utf-8",
    )
    return str(tmp_path)


class TestCodeGraphCallersTool:
    def test_tool_definition(self, callers_tool):
        defn = callers_tool.get_tool_definition()
        assert defn["name"] == "codegraph_callers"
        assert "caller" in defn["description"].lower()
        assert "function_name" in defn["inputSchema"]["properties"]
        assert "function_name" in defn["inputSchema"]["required"]

    def test_validate_missing_function_name(self, callers_tool):
        with pytest.raises(ValueError, match="function_name is required"):
            callers_tool.validate_arguments({})

    def test_validate_with_function_name(self, callers_tool):
        assert callers_tool.validate_arguments({"function_name": "main"})

    @pytest.mark.asyncio
    async def test_execute_returns_callers(self, tiny_project_root):
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        result = await callers_tool.execute(
            {"function_name": "bar", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["function"] == "bar"
        assert "callers" in result
        assert "caller_count" in result
        assert isinstance(result["callers"], list)

    @pytest.mark.asyncio
    async def test_certified_callers_and_callees_restore_bodies(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        (tmp_path / "sample.py").write_text(
            "def caller():\n    return callee()\n\ndef callee():\n"
            "    return 'CERTIFIED_CALLEE_BODY'\n",
            encoding="utf-8",
        )
        indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
            {"mode": "full", "max_files": 10}
        )
        assert indexed["published"] is True
        callers = await CodeGraphCallersTool(str(tmp_path)).execute(
            {"function_name": "callee", "output_format": "json"}
        )
        callees = await CodeGraphCalleesTool(str(tmp_path)).execute(
            {"function_name": "caller", "output_format": "json"}
        )
        assert "def caller" in callers["callers"][0]["body"]["content"]
        assert "CERTIFIED_CALLEE_BODY" in callees["callees"][0]["body"]["content"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool_type", "query", "method", "rows_key"),
        [
            (CodeGraphCallersTool, "callee", "query_callers", "callers"),
            (CodeGraphCalleesTool, "caller", "query_callees", "callees"),
        ],
    )
    async def test_move_after_bound_edge_query_drops_neighbor_body(
        self, tmp_path, monkeypatch, tool_type, query, method, rows_key
    ):
        from tree_sitter_analyzer.index_snapshot_query import CertifiedSnapshotCache
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        source = tmp_path / "sample.py"
        source.write_text(
            "def caller():\n    return callee()\n\ndef callee():\n    return 'INDEXED'\n",
            encoding="utf-8",
        )
        assert (
            await CodeGraphFullIndexTool(str(tmp_path)).execute(
                {"mode": "full", "max_files": 10}
            )
        )["published"] is True
        original = getattr(CertifiedSnapshotCache, method)

        def query_then_move(self, *args, **kwargs):
            rows = original(self, *args, **kwargs)
            source.write_text(
                "\n\ndef caller():\n    return callee()\n\ndef callee():\n    return 'MOVED'\n",
                encoding="utf-8",
            )
            return rows

        monkeypatch.setattr(CertifiedSnapshotCache, method, query_then_move)
        result = await tool_type(str(tmp_path)).execute(
            {"function_name": query, "output_format": "json"}
        )
        assert all("body" not in row for row in result[rows_key])
        assert "no Read needed" not in result.get("next_step", "")

    @pytest.mark.asyncio
    async def test_certified_index_without_edges_keeps_neighbors_coordinate_only(
        self, tmp_path
    ):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        (tmp_path / "sample.py").write_text(
            "def lone():\n    return 1\n", encoding="utf-8"
        )
        assert (
            await CodeGraphFullIndexTool(str(tmp_path)).execute(
                {"mode": "full", "max_files": 10}
            )
        )["published"] is True
        callers = await CodeGraphCallersTool(str(tmp_path)).execute(
            {"function_name": "lone", "output_format": "json"}
        )
        callees = await CodeGraphCalleesTool(str(tmp_path)).execute(
            {"function_name": "lone", "output_format": "json"}
        )
        assert callers["callers"] == []
        assert callees["callees"] == []
        assert "no Read needed" not in callers.get("next_step", "")
        assert "no Read needed" not in callees.get("next_step", "")

    @pytest.mark.asyncio
    async def test_execute_with_file_path(self, tiny_project_root):
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        result = await callers_tool.execute(
            {
                "function_name": "bar",
                "file_path": "sample.py",
                "output_format": "json",
            }
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    @pytest.mark.slow_ok  # Real call-graph build on Windows I/O exceeds 5s budget
    async def test_execute_toon_format(self, tiny_project_root):
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        result = await callers_tool.execute(
            {"function_name": "bar", "output_format": "toon"}
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_uncertified_caller_stays_coordinate_only(self, tiny_project_root):
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        result = await callers_tool.execute(
            {"function_name": "bar", "output_format": "json"}
        )
        foo = next((c for c in result["callers"] if c["name"] == "foo"), None)
        assert foo is not None, "foo should call bar in the fixture"
        assert "body" not in foo
        assert "no Read needed" not in result.get("next_step", "")

    def test_project_root_change_resets_cache(self, tiny_project_root):
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        callers_tool.get_call_graph()
        assert callers_tool.call_graph_initialized
        callers_tool._on_project_root_changed(None)
        assert not callers_tool.call_graph_initialized

    @pytest.mark.asyncio
    async def test_no_project_root_raises(self):
        tool = CodeGraphCallersTool(None)
        with pytest.raises(ValueError, match="Project root not set"):
            await tool.execute({"function_name": "main"})


class TestCodeGraphCalleesTool:
    def test_tool_definition(self, callees_tool):
        defn = callees_tool.get_tool_definition()
        assert defn["name"] == "codegraph_callees"
        assert "callee" in defn["description"].lower()
        assert "function_name" in defn["inputSchema"]["properties"]
        assert "function_name" in defn["inputSchema"]["required"]

    def test_validate_missing_function_name(self, callees_tool):
        with pytest.raises(ValueError, match="function_name is required"):
            callees_tool.validate_arguments({})

    def test_validate_with_function_name(self, callees_tool):
        assert callees_tool.validate_arguments({"function_name": "main"})

    @pytest.mark.asyncio
    async def test_execute_returns_callees(self, tiny_project_root):
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callees_tool.execute(
            {"function_name": "foo", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["function"] == "foo"
        assert "callees" in result
        assert "callee_count" in result
        assert isinstance(result["callees"], list)

    @pytest.mark.asyncio
    async def test_execute_with_file_path(self, tiny_project_root):
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callees_tool.execute(
            {
                "function_name": "foo",
                "file_path": "sample.py",
                "output_format": "json",
            }
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_uncertified_callee_stays_coordinate_only(self, tiny_project_root):
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callees_tool.execute(
            {"function_name": "foo", "output_format": "json"}
        )
        bar = next((c for c in result["callees"] if c["name"] == "bar"), None)
        assert bar is not None, "foo should call bar in the fixture"
        assert "body" not in bar
        assert "no Read needed" not in result.get("next_step", "")

    @pytest.mark.asyncio
    @pytest.mark.slow_ok  # Real call-graph build on Windows I/O exceeds 5s budget
    async def test_execute_toon_format(self, tiny_project_root):
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callees_tool.execute(
            {"function_name": "foo", "output_format": "toon"}
        )
        assert result["success"] is True

    def test_project_root_change_resets_cache(self, tiny_project_root):
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        callees_tool.get_call_graph()
        assert callees_tool.call_graph_initialized
        callees_tool._on_project_root_changed(None)
        assert not callees_tool.call_graph_initialized

    @pytest.mark.asyncio
    async def test_no_project_root_raises(self):
        tool = CodeGraphCalleesTool(None)
        with pytest.raises(ValueError, match="Project root not set"):
            await tool.execute({"function_name": "main"})


class TestCallerCalleeIntegration:
    def test_callers_and_callees_share_relation_bootstrap(self):
        assert issubclass(CodeGraphCallersTool, CodeGraphRelationToolMixin)
        assert issubclass(CodeGraphCalleesTool, CodeGraphRelationToolMixin)

    @pytest.mark.asyncio
    async def test_unknown_function_returns_empty(self, tiny_project_root):
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callers_tool.execute(
            {
                "function_name": "zzz_nonexistent_function_xyz",
                "output_format": "json",
            }
        )
        # NOT_FOUND is a valid result (ran fine, found nothing): the envelope
        # stays success=True; the outcome is in verdict (ARCH-A5).
        assert result["success"] is True
        assert result["verdict"] == "NOT_FOUND"
        assert result["caller_count"] == 0

        result2 = await callees_tool.execute(
            {
                "function_name": "zzz_nonexistent_function_xyz",
                "output_format": "json",
            }
        )
        assert result2["success"] is True
        assert result2["verdict"] == "NOT_FOUND"
        assert result2["callee_count"] == 0


class TestHonestTruncationCallers:
    """DF-13/#500：调用者数量与 CLI limit 必须如实截断。"""

    @pytest.fixture
    def many_callers_root(self, tmp_path):
        return build_many_relation_project(tmp_path, "callers")

    @pytest.mark.asyncio
    async def test_default_limit_caps_at_50(self, many_callers_root):
        tool = CodeGraphCallersTool(many_callers_root)
        result = await tool.execute(
            {"function_name": "target", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["caller_count"] == 60
        assert result["callers_listed"] == 50
        assert result["listed_cap"] == 50
        assert result["truncated"] is True
        assert len(result["callers"]) == 50

    @pytest.mark.asyncio
    async def test_raised_limit_shows_all(self, many_callers_root):
        tool = CodeGraphCallersTool(many_callers_root)
        result = await tool.execute(
            {"function_name": "target", "output_format": "json", "limit": 100}
        )
        assert result["success"] is True
        assert result["caller_count"] == 60
        assert result["callers_listed"] == 60
        assert result["truncated"] is False
        assert len(result["callers"]) == 60

    @pytest.mark.asyncio
    async def test_no_truncation_when_few_callers(self, tiny_project_root):
        tool = CodeGraphCallersTool(tiny_project_root)
        result = await tool.execute({"function_name": "bar", "output_format": "json"})
        assert result["success"] is True
        assert result["truncated"] is False
        assert result["callers_listed"] == result["caller_count"]

    @pytest.mark.asyncio
    async def test_truncated_next_step_present(self, many_callers_root):
        tool = CodeGraphCallersTool(many_callers_root)
        result = await tool.execute(
            {"function_name": "target", "output_format": "json"}
        )
        assert result["truncated"] is True
        assert "next_step" in result
        assert "50 of 60" in result["next_step"]

    def test_schema_declares_limit_param(self):
        tool = CodeGraphCallersTool(None)
        schema = tool.get_tool_schema()
        assert "limit" in schema["properties"]
        assert schema["properties"]["limit"]["default"] == 50
        assert schema["properties"]["limit"]["minimum"] == 1

    @pytest.mark.asyncio
    async def test_zero_callers_not_truncated(self, tiny_project_root):
        tool = CodeGraphCallersTool(tiny_project_root)
        result = await tool.execute(
            {"function_name": "zzz_nonexistent_xyz", "output_format": "json"}
        )
        assert result["caller_count"] == 0
        assert result["callers_listed"] == 0
        assert result["truncated"] is False


class TestHonestTruncationCallees:
    """DF-13/#500：被调用者保持相同的截断契约。"""

    @pytest.fixture
    def many_callees_root(self, tmp_path):
        return build_many_relation_project(tmp_path, "callees")

    @pytest.mark.asyncio
    async def test_default_limit_caps_at_50(self, many_callees_root):
        tool = CodeGraphCalleesTool(many_callees_root)
        result = await tool.execute({"function_name": "hub", "output_format": "json"})
        assert result["success"] is True
        assert result["callee_count"] == 60
        assert result["callees_listed"] == 50
        assert result["listed_cap"] == 50
        assert result["truncated"] is True
        assert len(result["callees"]) == 50

    @pytest.mark.asyncio
    async def test_raised_limit_shows_all(self, many_callees_root):
        tool = CodeGraphCalleesTool(many_callees_root)
        result = await tool.execute(
            {"function_name": "hub", "output_format": "json", "limit": 100}
        )
        assert result["success"] is True
        assert result["callee_count"] == 60
        assert result["callees_listed"] == 60
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_no_truncation_when_few_callees(self, tiny_project_root):
        tool = CodeGraphCalleesTool(tiny_project_root)
        result = await tool.execute({"function_name": "foo", "output_format": "json"})
        assert result["success"] is True
        assert result["truncated"] is False
        assert result["callees_listed"] == result["callee_count"]

    def test_schema_declares_limit_param(self):
        tool = CodeGraphCalleesTool(None)
        schema = tool.get_tool_schema()
        assert "limit" in schema["properties"]
        assert schema["properties"]["limit"]["default"] == 50
        assert schema["properties"]["limit"]["minimum"] == 1

    @pytest.mark.asyncio
    async def test_zero_callees_not_truncated(self, tiny_project_root):
        tool = CodeGraphCalleesTool(tiny_project_root)
        result = await tool.execute(
            {"function_name": "zzz_nonexistent_xyz", "output_format": "json"}
        )
        assert result["callee_count"] == 0
        assert result["callees_listed"] == 0
        assert result["truncated"] is False


class TestStaleCacheWarning:
    def test_helper_is_false_for_empty(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _is_stale_resolution

        assert _is_stale_resolution([]) is False

    def test_helper_is_true_when_all_unknown(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _is_stale_resolution

        entries = [{"callee_resolution": "unknown"} for _ in range(10)]
        assert _is_stale_resolution(entries) is True

    def test_helper_is_false_when_majority_resolved(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _is_stale_resolution

        # 30% unknown / 70% project → below the 80% threshold.
        entries = [{"callee_resolution": "unknown"} for _ in range(3)] + [
            {"callee_resolution": "project"} for _ in range(7)
        ]
        assert _is_stale_resolution(entries) is False

    def test_helper_trips_at_exactly_80_percent(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _is_stale_resolution

        # 8 unknown out of 10 = 80% → at threshold (inclusive).
        entries = [{"callee_resolution": "unknown"} for _ in range(8)] + [
            {"callee_resolution": "project"} for _ in range(2)
        ]
        assert _is_stale_resolution(entries) is True

    def test_warning_message_recommends_valid_rebuild_command(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _STALE_CACHE_WARNING

        # #1028: the user-visible string must point at a command that
        # actually runs. The old text recommended `--ast-cache-mode force`
        # and `--mode resolve`, neither of which is a valid flag/choice
        # (argparse errors with "invalid choice"). Pin the VALID rebuild
        # command and assert the invalid forms never come back.
        assert "stale_cache" in _STALE_CACHE_WARNING
        assert (
            "--ast-cache --ast-cache-mode index --ast-cache-force"
            in _STALE_CACHE_WARNING
        )
        assert "--ast-cache-mode force" not in _STALE_CACHE_WARNING
        assert "--mode resolve" not in _STALE_CACHE_WARNING

    @pytest.mark.asyncio
    async def test_callees_warning_omitted_when_callees_empty(
        self, tiny_project_root
    ) -> None:
        # Empty callee list: nothing to be stale about, no warning.
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callees_tool.execute(
            {"function_name": "zzz_nonexistent_function_xyz", "output_format": "json"}
        )
        assert result["callee_count"] == 0
        assert "warnings" not in result

    @pytest.mark.asyncio
    async def test_callers_warning_omitted_when_callers_empty(
        self, tiny_project_root
    ) -> None:
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        result = await callers_tool.execute(
            {"function_name": "zzz_nonexistent_function_xyz", "output_format": "json"}
        )
        assert result["caller_count"] == 0
        assert "warnings" not in result


def test_cli_call_limit_flag_parity() -> None:
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    args = parser.parse_args(["--callers", "execute", "--call-limit", "200"])
    assert args.call_limit == 200
    # default mirrors the MCP schema default
    args_default = parser.parse_args(["--callers", "execute"])
    assert args_default.call_limit == 50


class TestEmptyIndexHint:
    """#548/#705：区分未建图、重建中和已建但零边。"""

    @pytest.mark.asyncio
    async def test_callers_empty_index_hint_mentions_full_index(self, tmp_path) -> None:
        tool = CodeGraphCallersTool(str(tmp_path))
        result = await tool.execute(
            {"function_name": "some_function", "output_format": "json"}
        )
        assert result["verdict"] == "NOT_FOUND"
        next_step = result.get("next_step", "")
        assert "--full-index" in next_step, (
            f"next_step should mention --full-index when call graph is empty; "
            f"got: {next_step!r}"
        )

    @pytest.mark.asyncio
    async def test_callees_empty_index_hint_mentions_full_index(self, tmp_path) -> None:
        tool = CodeGraphCalleesTool(str(tmp_path))
        result = await tool.execute(
            {"function_name": "some_function", "output_format": "json"}
        )
        assert result["verdict"] == "NOT_FOUND"
        next_step = result.get("next_step", "")
        assert "--full-index" in next_step, (
            f"next_step should mention --full-index when call graph is empty; "
            f"got: {next_step!r}"
        )

    @pytest.mark.asyncio
    async def test_callers_rebuild_marker_warns_without_phantom_count(
        self, tmp_path
    ) -> None:
        (tmp_path / "sample.py").write_text(
            "def foo():\n    bar()\n\ndef bar():\n    return 1\n",
            encoding="utf-8",
        )
        cache = ASTCache(str(tmp_path))
        try:
            cache.index_project(workers=0)
            build_state.mark_build_in_progress(cache.get_conn())

            tool = CodeGraphCallersTool(str(tmp_path))
            result = await tool.execute(
                {"function_name": "bar", "output_format": "json"}
            )
        finally:
            build_state.clear_build_in_progress(cache.get_conn())
            cache.close()

        assert result["verdict"] == "WARN"
        assert result["index_rebuilding"] is True
        assert result["data_source"] == "cache_rebuilding"
        assert "caller_count" not in result
        assert "callers" not in result
        assert "--full-index" not in result["next_step"]
        assert result["agent_summary"]["verdict"] == "WARN"

    @pytest.mark.asyncio
    async def test_callees_rebuild_marker_warns_without_phantom_count(
        self, tmp_path
    ) -> None:
        (tmp_path / "sample.py").write_text(
            "def foo():\n    bar()\n\ndef bar():\n    return 1\n",
            encoding="utf-8",
        )
        cache = ASTCache(str(tmp_path))
        try:
            cache.index_project(workers=0)
            build_state.mark_build_in_progress(cache.get_conn())

            tool = CodeGraphCalleesTool(str(tmp_path))
            result = await tool.execute(
                {"function_name": "foo", "output_format": "json"}
            )
        finally:
            build_state.clear_build_in_progress(cache.get_conn())
            cache.close()

        assert result["verdict"] == "WARN"
        assert result["index_rebuilding"] is True
        assert result["data_source"] == "cache_rebuilding"
        assert "callee_count" not in result
        assert "callees" not in result
        assert "--full-index" not in result["next_step"]
        assert result["agent_summary"]["verdict"] == "WARN"

    @pytest.mark.asyncio
    async def test_callers_non_empty_index_no_spurious_hint(
        self, tiny_project_root
    ) -> None:
        cache = ASTCache(tiny_project_root)
        try:
            cache.index_project(workers=0)
            assert cache.call_graph_built() is True
            assert cache.has_call_edges() is True
        finally:
            cache.close()

        tool = CodeGraphCallersTool(tiny_project_root)
        result = await tool.execute(
            {
                "function_name": "zzz_definitely_not_in_tiny_project",
                "output_format": "json",
            }
        )
        assert result["verdict"] == "NOT_FOUND"
        next_step = result.get("next_step", "")
        assert "--full-index" not in next_step, (
            f"--full-index hint must NOT appear when built index has edges; "
            f"got: {next_step!r}"
        )

    @pytest.mark.asyncio
    async def test_callers_built_index_zero_edges_no_hint(self, tmp_path) -> None:
        from tree_sitter_analyzer.ast_cache import ASTCache

        (tmp_path / "solo.py").write_text(
            "def solo():\n    return 1\n", encoding="utf-8"
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project()
        assert cache.get_stats()["total_files"] == 1
        assert not cache.has_call_edges()
        cache.close()

        tool = CodeGraphCallersTool(str(tmp_path))
        result = await tool.execute({"function_name": "solo", "output_format": "json"})
        assert result["verdict"] == "NOT_FOUND"
        next_step = result.get("next_step", "")
        assert "--full-index" not in next_step, (
            f"--full-index hint must NOT appear when the index is built "
            f"(zero-edge project); got: {next_step!r}"
        )

    @pytest.mark.asyncio
    async def test_callees_built_index_zero_edges_no_hint(self, tmp_path) -> None:
        from tree_sitter_analyzer.ast_cache import ASTCache

        (tmp_path / "solo.py").write_text(
            "def solo():\n    return 1\n", encoding="utf-8"
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project()
        assert cache.get_stats()["total_files"] == 1
        assert not cache.has_call_edges()
        cache.close()

        tool = CodeGraphCalleesTool(str(tmp_path))
        result = await tool.execute({"function_name": "solo", "output_format": "json"})
        assert result["verdict"] == "NOT_FOUND"
        next_step = result.get("next_step", "")
        assert "--full-index" not in next_step, (
            f"--full-index hint must NOT appear when the index is built "
            f"(zero-edge project); got: {next_step!r}"
        )


class TestAgentSummaryCallers:
    @pytest.mark.asyncio
    async def test_callers_has_agent_summary_found(self, tiny_project_root) -> None:
        tool = CodeGraphCallersTool(tiny_project_root)
        result = await tool.execute({"function_name": "bar", "output_format": "json"})
        assert result["verdict"] == "INFO"
        agent_summary = result.get("agent_summary")
        assert isinstance(agent_summary, dict), "agent_summary must be a dict"
        assert agent_summary.get("verdict") in (
            "INFO",
            "NOT_FOUND",
            "CAUTION",
            "REVIEW",
            "ERROR",
        )
        assert result["verdict"] == agent_summary["verdict"], (
            "top-level verdict must mirror agent_summary.verdict"
        )
        summary_line = agent_summary.get("summary_line", "")
        assert isinstance(summary_line, str) and summary_line, (
            "summary_line must be non-empty"
        )
        # Extract the count from summary_line — fixture has exactly 1 caller (foo→bar).
        import re

        m = re.search(r"(\d+)\s+caller", summary_line)
        assert m is not None, (
            f"summary_line must mention caller count; got: {summary_line!r}"
        )
        assert int(m.group(1)) == 1, (
            f"summary_line must report TRUE count 1, got {m.group(1)!r} in {summary_line!r}"
        )
        next_step = agent_summary.get("next_step", "")
        assert isinstance(next_step, str) and next_step, "next_step must be non-empty"

    @pytest.mark.asyncio
    async def test_callers_has_agent_summary_not_found(self, tiny_project_root) -> None:
        tool = CodeGraphCallersTool(tiny_project_root)
        result = await tool.execute(
            {"function_name": "zzz_nonexistent_xyz", "output_format": "json"}
        )
        assert result["verdict"] == "NOT_FOUND"
        agent_summary = result.get("agent_summary")
        assert isinstance(agent_summary, dict), (
            "agent_summary must be present even on NOT_FOUND"
        )
        assert agent_summary["verdict"] == "NOT_FOUND"
        assert result["verdict"] == agent_summary["verdict"]
        summary_line = agent_summary.get("summary_line", "")
        assert isinstance(summary_line, str) and summary_line

    @pytest.mark.asyncio
    async def test_callers_verdict_mirrors_agent_summary(
        self, tiny_project_root
    ) -> None:
        tool = CodeGraphCallersTool(tiny_project_root)
        for fn in ("bar", "foo", "zzz_nonexistent_xyz"):
            result = await tool.execute({"function_name": fn, "output_format": "json"})
            agent_summary = result.get("agent_summary", {})
            assert result.get("verdict") == agent_summary.get("verdict"), (
                f"verdict mismatch for {fn!r}: "
                f"top={result.get('verdict')!r} summary={agent_summary.get('verdict')!r}"
            )


class TestAgentSummaryCallees:
    @pytest.mark.asyncio
    async def test_callees_has_agent_summary_found(self, tiny_project_root) -> None:
        tool = CodeGraphCalleesTool(tiny_project_root)
        result = await tool.execute({"function_name": "foo", "output_format": "json"})
        assert result["verdict"] == "INFO"
        agent_summary = result.get("agent_summary")
        assert isinstance(agent_summary, dict), "agent_summary must be a dict"
        assert agent_summary.get("verdict") in (
            "INFO",
            "NOT_FOUND",
            "CAUTION",
            "REVIEW",
            "ERROR",
        )
        assert result["verdict"] == agent_summary["verdict"], (
            "top-level verdict must mirror agent_summary.verdict"
        )
        summary_line = agent_summary.get("summary_line", "")
        assert isinstance(summary_line, str) and summary_line, (
            "summary_line must be non-empty"
        )
        # Extract the count from summary_line — fixture has exactly 1 callee (foo→bar).
        import re

        m = re.search(r"(\d+)\s+(?:callee|function)", summary_line)
        assert m is not None, (
            f"summary_line must mention callee count; got: {summary_line!r}"
        )
        assert int(m.group(1)) == 1, (
            f"summary_line must report TRUE count 1, got {m.group(1)!r} in {summary_line!r}"
        )
        next_step = agent_summary.get("next_step", "")
        assert isinstance(next_step, str) and next_step, "next_step must be non-empty"

    @pytest.mark.asyncio
    async def test_callees_has_agent_summary_not_found(self, tiny_project_root) -> None:
        tool = CodeGraphCalleesTool(tiny_project_root)
        result = await tool.execute(
            {"function_name": "zzz_nonexistent_xyz", "output_format": "json"}
        )
        assert result["verdict"] == "NOT_FOUND"
        agent_summary = result.get("agent_summary")
        assert isinstance(agent_summary, dict), (
            "agent_summary must be present even on NOT_FOUND"
        )
        assert agent_summary["verdict"] == "NOT_FOUND"
        assert result["verdict"] == agent_summary["verdict"]
        summary_line = agent_summary.get("summary_line", "")
        assert isinstance(summary_line, str) and summary_line

    @pytest.mark.asyncio
    async def test_callees_verdict_mirrors_agent_summary(
        self, tiny_project_root
    ) -> None:
        tool = CodeGraphCalleesTool(tiny_project_root)
        for fn in ("foo", "bar", "zzz_nonexistent_xyz"):
            result = await tool.execute({"function_name": fn, "output_format": "json"})
            agent_summary = result.get("agent_summary", {})
            assert result.get("verdict") == agent_summary.get("verdict"), (
                f"verdict mismatch for {fn!r}: "
                f"top={result.get('verdict')!r} summary={agent_summary.get('verdict')!r}"
            )
