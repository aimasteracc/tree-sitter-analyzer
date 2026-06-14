#!/usr/bin/env python3
"""Tests for codegraph_callers and codegraph_callees dedicated MCP tools."""

from pathlib import Path

import pytest

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
    @pytest.mark.slow_ok  # scans full project graph; ~12s on CI hardware
    async def test_execute_returns_callers(self, callers_tool):
        result = await callers_tool.execute(
            {"function_name": "_walk_tree", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["function"] == "_walk_tree"
        assert "callers" in result
        assert "caller_count" in result
        assert isinstance(result["callers"], list)

    @pytest.mark.asyncio
    @pytest.mark.slow_ok  # clean Py3.13 CI may build the full project graph before SQL cache exists
    async def test_execute_with_file_path(self, callers_tool):
        result = await callers_tool.execute(
            {
                "function_name": "_walk_tree",
                "file_path": "tree_sitter_analyzer/call_graph.py",
                "output_format": "json",
            }
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_toon_format(self, tiny_project_root):
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        result = await callers_tool.execute(
            {"function_name": "bar", "output_format": "toon"}
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_caller_inlines_source_body(self, tiny_project_root):
        """P2: each caller carries its inlined verbatim source body (no Read)."""
        callers_tool = CodeGraphCallersTool(tiny_project_root)
        result = await callers_tool.execute(
            {"function_name": "bar", "output_format": "json"}
        )
        foo = next((c for c in result["callers"] if c["name"] == "foo"), None)
        assert foo is not None, "foo should call bar in the fixture"
        assert "body" in foo, "caller must carry inlined body"
        assert "def foo" in foo["body"]["content"]
        assert "no Read needed" in result["next_step"]

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
    async def test_callee_inlines_source_body(self, tiny_project_root):
        """P2: each callee carries its inlined verbatim source body (no Read)."""
        callees_tool = CodeGraphCalleesTool(tiny_project_root)
        result = await callees_tool.execute(
            {"function_name": "foo", "output_format": "json"}
        )
        bar = next((c for c in result["callees"] if c["name"] == "bar"), None)
        assert bar is not None, "foo should call bar in the fixture"
        assert "body" in bar, "callee must carry inlined body"
        assert "def bar" in bar["body"]["content"]
        assert "no Read needed" in result["next_step"]

    @pytest.mark.asyncio
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
        assert result["success"]
        assert result["caller_count"] == 0

        result2 = await callees_tool.execute(
            {
                "function_name": "zzz_nonexistent_function_xyz",
                "output_format": "json",
            }
        )
        assert result2["success"]
        assert result2["callee_count"] == 0


class TestHonestTruncationCallers:
    """DF-13: default limit=50 caps high-fan-in callers; response carries
    total/truncated/listed_cap so agents know what was omitted."""

    @pytest.fixture
    def many_callers_root(self, tmp_path):
        """Tiny project with one target function called by 60 callers.

        ``target()`` is defined in target.py.
        60 caller modules (caller_NN.py) each define ``fn_NN()`` that calls it.
        This produces 60 call edges to ``target``, which exceeds the default
        cap of 50 so truncation logic fires.
        """
        (tmp_path / "target.py").write_text(
            "def target():\n    return 42\n",
            encoding="utf-8",
        )
        for i in range(60):
            (tmp_path / f"caller_{i:03d}.py").write_text(
                f"from target import target\n\n\ndef fn_{i:03d}():\n    return target()\n",
                encoding="utf-8",
            )
        return str(tmp_path)

    @pytest.mark.asyncio
    async def test_default_limit_caps_at_50(self, many_callers_root):
        """With 60 callers and default limit=50, listed == 50, total == 60."""
        tool = CodeGraphCallersTool(many_callers_root)
        result = await tool.execute(
            {"function_name": "target", "output_format": "json"}
        )
        assert result["success"] is True
        # total must be the pre-cap count (60)
        assert result["caller_count"] == 60
        # listed must be exactly the cap
        assert result["callers_listed"] == 50
        assert result["listed_cap"] == 50
        assert result["truncated"] is True
        assert len(result["callers"]) == 50

    @pytest.mark.asyncio
    async def test_raised_limit_shows_all(self, many_callers_root):
        """limit=100 > 60 callers → no truncation, all listed."""
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
        """1 caller (foo→bar) → truncated=False, callers_listed == caller_count."""
        tool = CodeGraphCallersTool(tiny_project_root)
        result = await tool.execute({"function_name": "bar", "output_format": "json"})
        assert result["success"] is True
        assert result["truncated"] is False
        assert result["callers_listed"] == result["caller_count"]

    @pytest.mark.asyncio
    async def test_truncated_next_step_present(self, many_callers_root):
        """When truncated, next_step must mention the counts and suggest narrowing."""
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
        """0 callers → truncated=False, callers_listed==0."""
        tool = CodeGraphCallersTool(tiny_project_root)
        result = await tool.execute(
            {"function_name": "zzz_nonexistent_xyz", "output_format": "json"}
        )
        assert result["caller_count"] == 0
        assert result["callers_listed"] == 0
        assert result["truncated"] is False


class TestHonestTruncationCallees:
    """Symmetric to TestHonestTruncationCallers — callees_tool must apply the
    same default limit=50 cap and emit honest truncation fields."""

    @pytest.fixture
    def many_callees_root(self, tmp_path):
        """One source function ``hub()`` calling 60 distinct helpers.

        hub.py defines ``hub()`` which calls ``helper_00()`` … ``helper_59()``
        from helpers.py. This produces 60 callee edges from ``hub``, exceeding
        the default cap of 50.
        """
        helpers_code = "\n".join(
            f"def helper_{i:03d}():\n    return {i}\n" for i in range(60)
        )
        (tmp_path / "helpers.py").write_text(helpers_code, encoding="utf-8")
        calls = "\n    ".join(f"helper_{i:03d}()" for i in range(60))
        (tmp_path / "hub.py").write_text(
            f"from helpers import {', '.join(f'helper_{i:03d}' for i in range(60))}\n\n\ndef hub():\n    {calls}\n",
            encoding="utf-8",
        )
        return str(tmp_path)

    @pytest.mark.asyncio
    async def test_default_limit_caps_at_50(self, many_callees_root):
        """With 60 callees and default limit=50, listed == 50, total == 60."""
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
        """limit=100 > 60 callees → no truncation."""
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
        """1 callee (foo→bar) → truncated=False."""
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
        """0 callees → truncated=False, callees_listed==0."""
        tool = CodeGraphCalleesTool(tiny_project_root)
        result = await tool.execute(
            {"function_name": "zzz_nonexistent_xyz", "output_format": "json"}
        )
        assert result["callee_count"] == 0
        assert result["callees_listed"] == 0
        assert result["truncated"] is False


class TestStaleCacheWarning:
    """Stale-cache hint surfaces in callees/callers when ≥80% of edges
    have ``callee_resolution='unknown'``. The detection helper is
    deterministic (no live cache needed)."""

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

    def test_warning_message_recommends_resolve_mode(self) -> None:
        from tree_sitter_analyzer.mcp.tools.callees_tool import _STALE_CACHE_WARNING

        # The user-visible string must point at the right fix. Pinning
        # the substring stops a future "minor wording cleanup" from
        # dropping the actionable command.
        assert "--mode resolve" in _STALE_CACHE_WARNING
        assert "stale_cache" in _STALE_CACHE_WARNING

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
    """Codex P2 (#500): CLI must be able to raise the new limit (MCP/CLI parity)."""
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    args = parser.parse_args(["--callers", "execute", "--call-limit", "200"])
    assert args.call_limit == 200
    # default mirrors the MCP schema default
    args_default = parser.parse_args(["--callers", "execute"])
    assert args_default.call_limit == 50


class TestEmptyIndexHint:
    """#548: callers/callees on an empty/partial call-graph index must surface
    a --full-index hint so users know why NOT_FOUND is returned.

    An empty tmp_path has no indexed call edges — ``has_call_edges()`` returns
    False and the graph-parse fallback produces zero results.  The NOT_FOUND
    response's next_step MUST mention ``--full-index`` so the user is told
    what to do next.
    """

    @pytest.mark.asyncio
    async def test_callers_empty_index_hint_mentions_full_index(self, tmp_path) -> None:
        """Callers NOT_FOUND on empty index carries --full-index hint."""
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
        """Callees NOT_FOUND on empty index carries --full-index hint."""
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
    async def test_callers_non_empty_index_no_spurious_hint(
        self, tiny_project_root
    ) -> None:
        """When the index has call edges, NOT_FOUND for unknown symbol does NOT
        mention --full-index (it's the symbol that's missing, not the index)."""
        tool = CodeGraphCallersTool(tiny_project_root)
        result = await tool.execute(
            {
                "function_name": "zzz_definitely_not_in_tiny_project",
                "output_format": "json",
            }
        )
        # tiny_project_root has foo→bar edges, so the call graph is populated
        assert result["verdict"] == "NOT_FOUND"
        next_step = result.get("next_step", "")
        assert "--full-index" not in next_step, (
            f"--full-index hint must NOT appear when index has edges; "
            f"got: {next_step!r}"
        )

    @pytest.mark.asyncio
    async def test_callers_built_index_zero_edges_no_hint(self, tmp_path) -> None:
        """#705 follow-up: index IS built (total_files > 0) but the project has
        no call edges (e.g. a single ``def solo(): return 1``).  NOT_FOUND must
        NOT carry a --full-index hint — the user already indexed; they just have
        a project with no calls."""
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
        """#705 follow-up: same zero-edge scenario for callees."""
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
    """#546 seam 3 / #577 leftover: callers must emit agent_summary with
    verdict + summary_line + next_step, mirroring the top-level verdict."""

    @pytest.mark.asyncio
    async def test_callers_has_agent_summary_found(self, tiny_project_root) -> None:
        """INFO case: foo calls bar → bar has 1 caller (foo).
        agent_summary must be present and summary_line must report count == 1.
        Top-level verdict must mirror agent_summary.verdict.
        """
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
        """NOT_FOUND case: unknown symbol → agent_summary present, verdict NOT_FOUND."""
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
        """Top-level verdict must always equal agent_summary.verdict (N4/r37u pattern)."""
        tool = CodeGraphCallersTool(tiny_project_root)
        for fn in ("bar", "foo", "zzz_nonexistent_xyz"):
            result = await tool.execute({"function_name": fn, "output_format": "json"})
            agent_summary = result.get("agent_summary", {})
            assert result.get("verdict") == agent_summary.get("verdict"), (
                f"verdict mismatch for {fn!r}: "
                f"top={result.get('verdict')!r} summary={agent_summary.get('verdict')!r}"
            )


class TestAgentSummaryCallees:
    """#546 seam 3 / #577 leftover: callees must emit agent_summary with
    verdict + summary_line + next_step, mirroring the top-level verdict."""

    @pytest.mark.asyncio
    async def test_callees_has_agent_summary_found(self, tiny_project_root) -> None:
        """INFO case: foo calls bar → foo has 1 callee (bar).
        agent_summary must be present and summary_line must report count == 1.
        Top-level verdict must mirror agent_summary.verdict.
        """
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
        """NOT_FOUND case: unknown symbol → agent_summary present, verdict NOT_FOUND."""
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
        """Top-level verdict must always equal agent_summary.verdict (N4/r37u pattern)."""
        tool = CodeGraphCalleesTool(tiny_project_root)
        for fn in ("foo", "bar", "zzz_nonexistent_xyz"):
            result = await tool.execute({"function_name": fn, "output_format": "json"})
            agent_summary = result.get("agent_summary", {})
            assert result.get("verdict") == agent_summary.get("verdict"), (
                f"verdict mismatch for {fn!r}: "
                f"top={result.get('verdict')!r} summary={agent_summary.get('verdict')!r}"
            )
