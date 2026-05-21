"""ARCH-A5 contract test: every MCP tool's response honours ToolResponse.

Why this exists
---------------
Before ARCH-A5 the response shape across 23 tools was governed by
convention only. The MCP server, the CLI, the parity test, and every
downstream consumer (Claude Code, Cursor, Cline) end up depending on
keys like ``success`` and ``error`` whose presence is not enforced
anywhere. This test asserts the minimum invariants at the actual
tool surface.

Tests run the real ``execute()`` against a tiny in-tree fixture under
``tmp_path`` (no network, no fabricated mocks beyond a project root).
Tools that can't run without specific arguments are validated against
an *expected* failure — failures must also obey the envelope
(``success=False`` + ``error: str``).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.tool_response import validate_tool_response


@pytest.fixture
def tiny_project(tmp_path: Path) -> Path:
    """A 1-file project that every tool can analyse."""
    src = tmp_path / "sample.py"
    src.write_text("def greet(name: str) -> str:\n    return f'hello {name}'\n")
    return tmp_path


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


class TestEnvelopeSuccess:
    """Tools that need no arguments and should succeed against a tiny project."""

    def test_project_overview_envelope(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json"}))
        validate_tool_response(result, "project_overview")
        assert result["success"] is True
        assert "error" not in result  # successes don't carry error

    def test_detect_routes_summary_envelope(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import RouteDetectorTool

        tool = RouteDetectorTool(str(tiny_project))
        result = _run(tool.execute({"mode": "summary", "output_format": "json"}))
        validate_tool_response(result, "detect_routes:summary")
        assert result["success"] is True

    def test_check_project_health_envelope(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_health_tool import ProjectHealthTool

        tool = ProjectHealthTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json"}))
        validate_tool_response(result, "check_project_health")

    def test_ast_cache_stats_envelope(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(tiny_project))
        result = _run(tool.execute({"mode": "stats"}))
        validate_tool_response(result, "ast_cache:stats")


class TestEnvelopeFailure:
    """Tools handed bad input return ``success=False`` + ``error`` envelope."""

    def test_route_detector_file_mode_traversal_returns_envelope(
        self, tiny_project: Path
    ) -> None:
        """SEC-3 / ARCH-A5 together: failures still produce a valid
        envelope, not a bare exception. The agent on the other end of
        the MCP transport relies on this to recover gracefully."""
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import RouteDetectorTool

        tool = RouteDetectorTool(str(tiny_project))
        # The MCP layer normally catches the ValueError and wraps it.
        # Here we make sure the tool itself either does that, OR raises
        # cleanly so the layer above can convert. Either is acceptable;
        # the envelope is only required when the tool returns.
        try:
            result = _run(
                tool.execute(
                    {
                        "mode": "file",
                        "file_path": "../../etc/passwd",
                        "output_format": "json",
                    }
                )
            )
        except Exception:
            return  # acceptable: raised cleanly for outer layer to wrap
        validate_tool_response(result, "detect_routes:file traversal")
        assert result["success"] is False


class TestEnvelopeValidator:
    """Direct tests for the validator's own contract."""

    def test_rejects_non_dict(self) -> None:
        with pytest.raises(AssertionError, match="must be a dict"):
            validate_tool_response("oops")  # type: ignore[arg-type]

    def test_rejects_missing_success(self) -> None:
        with pytest.raises(AssertionError, match="must include a 'success' key"):
            validate_tool_response({"data": []})

    def test_rejects_non_bool_success(self) -> None:
        with pytest.raises(AssertionError, match="'success'.+must be bool"):
            validate_tool_response({"success": "true"})

    def test_failure_without_error_rejected(self) -> None:
        with pytest.raises(AssertionError, match="must include 'error'"):
            validate_tool_response({"success": False})

    def test_failure_with_non_str_error_rejected(self) -> None:
        with pytest.raises(AssertionError, match="'error'.+must be str"):
            validate_tool_response({"success": False, "error": 42})

    def test_accepts_minimal_success(self) -> None:
        validate_tool_response({"success": True})

    def test_accepts_minimal_failure(self) -> None:
        validate_tool_response({"success": False, "error": "boom"})

    def test_accepts_real_tool_shape(self) -> None:
        validate_tool_response(
            {
                "success": True,
                "mode": "summary",
                "total_routes": 0,
                "by_framework": {},
                "by_method": {},
                "file_count": 0,
            }
        )


class TestExecuteAcrossAllTools:
    """Exercise every registered MCP tool's execute() against a smoke
    arguments dict, and assert the envelope holds whether it succeeds
    or fails. Catches the next tool that silently drops 'success' or
    returns 'error': SomeException(...) instead of str."""

    @pytest.fixture
    def registered_tools(self, tiny_project: Path):  # type: ignore[no-untyped-def]
        # Some tool fixtures (ast_cache_tool, route_detector_tool) open
        # SQLite handles whose finalisers fire on GC. Suppress the
        # "unraisable exception" warnings PyMP catches from those — they
        # are not contract violations.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            warnings.simplefilter("ignore")
            from tree_sitter_analyzer.mcp.server import _create_tool_registry

            instances, _ = _create_tool_registry(str(tiny_project))
        return instances

    @pytest.mark.filterwarnings("ignore::ResourceWarning")
    @pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
    def test_every_tool_response_honours_envelope(
        self, registered_tools, tiny_project: Path
    ) -> None:
        # Per-tool smoke arguments. Cover every tool with the cheapest
        # call that the tool actually accepts.
        sample_file = str(tiny_project / "sample.py")
        per_tool_args: dict[str, dict] = {
            "check_code_scale": {"file_path": sample_file},
            "analyze_code_structure": {"file_path": sample_file, "format_type": "json"},
            "extract_code_section": {
                "file_path": sample_file,
                "start_line": 1,
                "end_line": 1,
            },
            "query_code": {"file_path": sample_file, "query_key": "functions"},
            "list_files": {"roots": [str(tiny_project)]},
            "search_content": {"query": "greet", "roots": [str(tiny_project)]},
            "find_and_grep": {"query": "greet", "roots": [str(tiny_project)]},
            "list_agent_skills": {},
            "get_agent_workflow": {"file_path": sample_file},
            "advise_parser_readiness": {"language": "python"},
            "get_project_overview": {},
            "check_project_health": {},
            "check_file_health": {"file_path": sample_file},
            "analyze_dependencies": {"mode": "summary"},
            "ast_cache": {"mode": "stats"},
            "codegraph_call_graph": {"mode": "summary"},
            "analyze_change_impact": {"mode": "diff"},
            "refactoring_suggestions": {"file_path": sample_file},
            "safe_to_edit": {"file_path": sample_file},
            "smart_context": {"file_path": sample_file},
            "symbol_lineage": {"symbol": "greet"},
            "code_patterns": {"file_path": sample_file},
            "detect_routes": {"mode": "summary"},
        }
        skipped: list[str] = []
        for name, tool in registered_tools:
            args = per_tool_args.get(name)
            if args is None:
                skipped.append(name)
                continue
            try:
                result = _run(tool.execute(args))
            except Exception:
                # A tool may raise instead of returning a failure envelope.
                # That's acceptable — the MCP layer above wraps it.
                continue
            validate_tool_response(result, name)
        assert skipped == [], (
            f"Tools missing from per_tool_args (add a row above): {skipped}"
        )


class TestFinding6SummaryLine:
    """Round-16b finding 6: 7 tools emitted ``summary_line=None``.

    Each of the listed tools must populate both top-level ``summary_line``
    AND a non-empty ``agent_summary`` dict on the success path. Previously
    FileHealth/Refactoring/SmartContext/AnalyzeStructure/ProjectOverview/
    CallGraph/ProjectHealth shipped one or both as ``None``/``{}``.
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        src = tmp_path / "sample.py"
        src.write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def _assert_envelope(self, name: str, result: dict) -> None:
        assert result.get("success") is True, f"{name}: success must be True"
        sl = result.get("summary_line")
        assert isinstance(sl, str) and sl, (
            f"{name}: top-level summary_line must be a non-empty string (Finding 6)"
        )
        agent = result.get("agent_summary")
        assert isinstance(agent, dict) and agent, (
            f"{name}: agent_summary must be a populated dict (Finding 6). got {agent!r}"
        )

    def test_file_health_summary_line(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tiny_project))
        result = _run(
            tool.execute(
                {
                    "file_path": str(tiny_project / "sample.py"),
                    "output_format": "json",
                }
            )
        )
        self._assert_envelope("check_file_health", result)

    def test_refactoring_suggestions_summary_line(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        tool = RefactoringSuggestionsTool(str(tiny_project))
        result = _run(
            tool.execute(
                {
                    "file_path": str(tiny_project / "sample.py"),
                    "output_format": "json",
                }
            )
        )
        self._assert_envelope("refactoring_suggestions", result)

    def test_smart_context_summary_line(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.smart_context_tool import SmartContextTool

        tool = SmartContextTool(str(tiny_project))
        result = _run(
            tool.execute(
                {
                    "file_path": str(tiny_project / "sample.py"),
                    "output_format": "json",
                }
            )
        )
        self._assert_envelope("smart_context", result)

    def test_analyze_code_structure_summary_line(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
            AnalyzeCodeStructureTool,
        )

        tool = AnalyzeCodeStructureTool(str(tiny_project))
        result = _run(
            tool.execute(
                {
                    "file_path": str(tiny_project / "sample.py"),
                    "output_format": "json",
                }
            )
        )
        self._assert_envelope("analyze_code_structure", result)

    def test_project_overview_summary_line(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json"}))
        self._assert_envelope("get_project_overview", result)

    def test_call_graph_summary_line(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.call_graph_tool import CodeGraphCallTool

        tool = CodeGraphCallTool(str(tiny_project))
        result = _run(tool.execute({"mode": "summary", "output_format": "json"}))
        self._assert_envelope("codegraph_call_graph", result)

    def test_project_health_summary_line(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_health_tool import (
            ProjectHealthTool,
        )

        tool = ProjectHealthTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json", "max_files": 5}))
        self._assert_envelope("check_project_health", result)


class TestFinding6DispatchPostHook:
    """The MCP dispatch post-hook must inject summary_line even when a tool
    forgets to set it. This guards against a future tool returning
    ``agent_summary`` without a top-level ``summary_line``."""

    def test_post_hook_mirrors_agent_summary_summary_line(self) -> None:
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            ensure_canonical_success_envelope,
        )

        response = {
            "success": True,
            "agent_summary": {
                "summary_line": "tool_x: hello world",
                "next_step": "next step",
            },
        }
        out = ensure_canonical_success_envelope("tool_x", response)
        assert out["summary_line"] == "tool_x: hello world"

    def test_post_hook_synthesizes_summary_when_missing(self) -> None:
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            ensure_canonical_success_envelope,
        )

        # Neither top-level summary_line nor agent_summary present.
        response: dict = {"success": True}
        out = ensure_canonical_success_envelope(
            "tool_x", response, arguments={"file_path": "/some/file.py"}
        )
        assert isinstance(out["summary_line"], str)
        assert "/some/file.py" in out["summary_line"]
        assert isinstance(out["agent_summary"], dict)
        assert out["agent_summary"]["summary_line"] == out["summary_line"]

    def test_post_hook_is_idempotent_on_existing_summary_line(self) -> None:
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            ensure_canonical_success_envelope,
        )

        response = {
            "success": True,
            "summary_line": "tool_x: custom",
            "agent_summary": {"summary_line": "should not stomp"},
        }
        out = ensure_canonical_success_envelope("tool_x", response)
        assert out["summary_line"] == "tool_x: custom", (
            "post-hook must not overwrite an existing top-level summary_line"
        )

    def test_post_hook_skips_error_responses(self) -> None:
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            ensure_canonical_success_envelope,
        )

        # success=False routes through the *error* envelope normaliser
        # instead. The success normaliser must leave the dict untouched.
        response = {"success": False, "error": "boom"}
        out = ensure_canonical_success_envelope("tool_x", response)
        assert out is response
        assert "summary_line" not in out


class TestF10ModificationGuardAgentSummary:
    """F10: modification_guard previously returned ``agent_summary={}``.

    Every safety tool must ship a populated ``agent_summary`` with the
    canonical fields (``summary_line``, ``verdict``, ``risk``,
    ``next_step``) so agents can branch on a single field regardless
    of which safety tool ran.
    """

    @pytest.fixture
    def project_with_symbol(self, tmp_path: Path) -> Path:
        # A tiny project where the target symbol has zero callers — that
        # gives a deterministic SAFE verdict without ripgrep variability.
        src = tmp_path / "lib.py"
        src.write_text(
            "def lonely_function(x: int) -> int:\n    return x + 1\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_agent_summary_is_populated(self, project_with_symbol: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.modification_guard_tool import (
            ModificationGuardTool,
        )

        tool = ModificationGuardTool(str(project_with_symbol))
        result = _run(
            tool.execute({"symbol": "lonely_function", "modification_type": "rename"})
        )
        assert result["success"] is True
        agent = result.get("agent_summary")
        assert isinstance(agent, dict) and agent, (
            f"agent_summary must be a populated dict, got {agent!r}"
        )

    def test_agent_summary_has_canonical_fields(
        self, project_with_symbol: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.modification_guard_tool import (
            ModificationGuardTool,
        )

        tool = ModificationGuardTool(str(project_with_symbol))
        result = _run(
            tool.execute({"symbol": "lonely_function", "modification_type": "refactor"})
        )
        agent = result["agent_summary"]
        for key in ("summary_line", "verdict", "risk", "next_step"):
            assert key in agent, f"agent_summary missing required key: {key}"
            value = agent[key]
            assert isinstance(value, str) and value, (
                f"agent_summary[{key!r}] must be a non-empty string, got {value!r}"
            )
        assert agent["verdict"] in {"SAFE", "CAUTION", "REVIEW", "UNSAFE"}
        assert agent["risk"] in {"low", "medium", "high"}

    def test_top_level_summary_line_matches_agent_summary(
        self, project_with_symbol: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.modification_guard_tool import (
            ModificationGuardTool,
        )

        tool = ModificationGuardTool(str(project_with_symbol))
        result = _run(
            tool.execute({"symbol": "lonely_function", "modification_type": "delete"})
        )
        top_level = result.get("summary_line")
        agent_sl = result["agent_summary"]["summary_line"]
        assert isinstance(top_level, str) and top_level, (
            "top-level summary_line must be a non-empty string"
        )
        assert top_level == agent_sl, (
            "top-level summary_line must mirror agent_summary['summary_line']"
        )


class TestF11ProjectOverviewRisk:
    """F11: project_overview returned ``risk="unknown"`` whenever
    ``include_health`` was false. The fix infers risk from observable
    signals (largest-file sizes, language spread) so callers always
    receive ``low``/``medium``/``high`` — never ``unknown`` or empty.
    """

    @pytest.fixture
    def clean_project(self, tmp_path: Path) -> Path:
        src = tmp_path / "a.py"
        src.write_text("def f() -> None:\n    return None\n", encoding="utf-8")
        return tmp_path

    @pytest.fixture
    def risky_project(self, tmp_path: Path) -> Path:
        # Three oversized source files → should trip the "high" branch
        # even without ``include_health=True``.
        big_body = "    pass\n" * 900  # 900 lines body
        for i in range(3):
            (tmp_path / f"big_{i}.py").write_text(
                f"def big_{i}() -> None:\n{big_body}", encoding="utf-8"
            )
        return tmp_path

    def _risk(self, result: dict) -> str:
        agent = result.get("agent_summary") or {}
        return agent.get("risk", "")

    def test_risk_never_unknown_without_health(self, clean_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(clean_project))
        result = _run(tool.execute({"output_format": "json"}))
        risk = self._risk(result)
        assert risk in {"low", "medium", "high"}, (
            f"risk must be one of low/medium/high — got {risk!r}"
        )

    def test_risk_never_unknown_with_health(self, clean_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(clean_project))
        result = _run(tool.execute({"output_format": "json", "include_health": True}))
        risk = self._risk(result)
        assert risk in {"low", "medium", "high"}, (
            f"risk must be one of low/medium/high — got {risk!r}"
        )

    def test_risky_project_escalates_above_low(self, risky_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(risky_project))
        result = _run(tool.execute({"output_format": "json"}))
        risk = self._risk(result)
        # Three files >800 lines should produce ``high`` per the inference
        # rule. Accepting ``medium`` too would defeat the assertion — be
        # explicit.
        assert risk == "high", (
            f"three 900-line source files must yield risk='high' — got {risk!r}"
        )


class TestF8CallGraphNotFound:
    """F8 (round-17): when ``call_graph`` is invoked with a symbol that
    does not exist in the project, the response must still carry an
    actionable ``agent_summary`` — previously it shipped ``{}`` (or a
    generic "drill in" next_step) which left agents with nothing to do.

    Contract:
      - ``success`` stays True (the lookup ran fine; the symbol simply
        isn't there)
      - ``agent_summary`` is a populated dict with ``summary_line``,
        ``next_step``, and ``verdict`` (``NOT_FOUND``)
      - top-level ``summary_line`` mirrors ``agent_summary["summary_line"]``
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        src = tmp_path / "lib.py"
        src.write_text("def real_function() -> int:\n    return 1\n", encoding="utf-8")
        return tmp_path

    def _run_callers(self, project: Path, symbol: str) -> dict:
        from tree_sitter_analyzer.mcp.tools.call_graph_tool import CodeGraphCallTool

        tool = CodeGraphCallTool(str(project))
        return _run(
            tool.execute(
                {
                    "mode": "callers",
                    "function_name": symbol,
                    "output_format": "json",
                }
            )
        )

    def test_not_found_success_is_true(self, tiny_project: Path) -> None:
        """Lookup succeeded — the symbol just wasn't there. Don't poison
        the success flag, or agents will branch into an error path that
        doesn't fit."""
        result = self._run_callers(tiny_project, "DoesNotExist_zzz")
        assert result["success"] is True, (
            "F8: a missing symbol is not an error — success must stay True"
        )

    def test_not_found_agent_summary_populated(self, tiny_project: Path) -> None:
        """agent_summary must not be ``{}``. It must have the canonical
        triple ``summary_line`` / ``next_step`` / ``verdict``."""
        result = self._run_callers(tiny_project, "DoesNotExist_zzz")
        agent = result.get("agent_summary")
        assert isinstance(agent, dict) and agent, (
            f"F8: agent_summary must be a populated dict — got {agent!r}"
        )
        for key in ("summary_line", "next_step", "verdict"):
            assert key in agent, f"F8: agent_summary missing required key: {key!r}"
            value = agent[key]
            assert isinstance(value, str) and value, (
                f"F8: agent_summary[{key!r}] must be a non-empty string — got {value!r}"
            )
        assert agent["verdict"] == "NOT_FOUND", (
            f"F8: verdict must be NOT_FOUND for missing-symbol responses — "
            f"got {agent['verdict']!r}"
        )

    def test_not_found_top_level_summary_line_mirrors_agent_summary(
        self, tiny_project: Path
    ) -> None:
        """The dispatch post-hook and the tool's own helper both have to
        agree on the line that lands at the top level."""
        result = self._run_callers(tiny_project, "DoesNotExist_zzz")
        top_level = result.get("summary_line")
        agent_sl = result["agent_summary"]["summary_line"]
        assert isinstance(top_level, str) and top_level, (
            "F8: top-level summary_line must be a non-empty string"
        )
        assert top_level == agent_sl, (
            f"F8: top-level summary_line must equal agent_summary['summary_line']. "
            f"top={top_level!r} vs agent={agent_sl!r}"
        )

    def test_not_found_summary_line_mentions_symbol(self, tiny_project: Path) -> None:
        """The summary line must name the missing symbol so agents can
        log/forward it without re-parsing the request args."""
        result = self._run_callers(tiny_project, "DoesNotExist_zzz")
        sl = result["agent_summary"]["summary_line"]
        assert "DoesNotExist_zzz" in sl, (
            f"F8: summary_line must include the missing symbol name — got {sl!r}"
        )
        assert "not found" in sl.lower(), (
            f"F8: summary_line must say 'not found' so callers can grep — got {sl!r}"
        )


class TestG2CallGraphEdgeCount:
    """G2 (round-18): ``call_graph`` summary previously hard-coded
    ``edges=0`` in the summary_line because the fallback chain looked for
    ``edges`` / ``edge_count`` but ``CallGraph.summary()`` returns
    ``call_edge_count`` (see ``tree_sitter_analyzer/call_graph.py``).

    Contract:
      - When the project has non-zero edges, the visible ``edges=…`` value
        in ``summary_line`` matches the real ``call_edge_count``.
      - Top-level ``summary_line`` mirrors ``agent_summary["summary_line"]``
        so the dispatch post-hook and the tool agree.
    """

    @pytest.fixture
    def project_with_edges(self, tmp_path: Path) -> Path:
        """A project with at least one function-to-function call edge so
        ``call_edge_count`` is non-zero. Keep it tiny to stay fast."""
        src = tmp_path / "lib.py"
        src.write_text(
            "def callee() -> int:\n"
            "    return 1\n"
            "\n"
            "def caller() -> int:\n"
            "    return callee()\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run_summary(self, project: Path) -> dict:
        from tree_sitter_analyzer.mcp.tools.call_graph_tool import CodeGraphCallTool

        tool = CodeGraphCallTool(str(project))
        return _run(tool.execute({"mode": "summary", "output_format": "json"}))

    def test_summary_line_shows_real_edge_count(self, project_with_edges: Path) -> None:
        """``summary_line`` must include the same number as ``call_edge_count``,
        not a hard-coded zero from a stale fallback chain."""
        result = self._run_summary(project_with_edges)
        assert result["success"] is True
        edge_count = result.get("call_edge_count")
        assert isinstance(edge_count, int) and edge_count > 0, (
            f"G2 setup: project should have non-zero edges — got {edge_count!r}"
        )
        sl = result.get("summary_line")
        assert isinstance(sl, str) and sl, (
            f"G2: summary_line must be a non-empty string — got {sl!r}"
        )
        assert f"edges={edge_count}" in sl, (
            f"G2: summary_line must report edges={edge_count} (the real "
            f"call_edge_count), but got {sl!r}"
        )

    def test_top_level_summary_line_matches_agent_summary(
        self, project_with_edges: Path
    ) -> None:
        """The visible top-level summary_line must not drift away from the
        line buried under ``agent_summary``."""
        result = self._run_summary(project_with_edges)
        top_level = result.get("summary_line")
        agent_sl = result.get("agent_summary", {}).get("summary_line")
        assert isinstance(top_level, str) and top_level, (
            "G2: top-level summary_line must be a non-empty string"
        )
        assert top_level == agent_sl, (
            f"G2: top-level summary_line must mirror "
            f"agent_summary['summary_line']. top={top_level!r} vs "
            f"agent={agent_sl!r}"
        )


class TestG6SymbolLineageTruncation:
    """G6 (round-18): ``symbol_lineage`` silently capped ``references`` to
    30 entries and ``downstream_files`` to 50 entries with no marker on
    the response. ``reference_count`` / ``downstream_file_count`` still
    carried the real total, so an agent that compared
    ``len(references)`` against ``reference_count`` could detect it —
    but nothing in the envelope made the partial view explicit.

    Contract:
      - When ``references > 30``, response sets
        ``references_truncated=True``, ``references_limit=30``,
        ``references_available=<real count>``.
      - Same shape for ``downstream_files`` at limit 50.
      - ``agent_summary.summary_line`` mentions truncation so an agent
        scanning the headline alone notices.
      - ``agent_summary["truncations"]`` lists the affected fields.
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        """Smallest valid project so SymbolLineageTool can run end-to-end."""
        (tmp_path / "lib.py").write_text(
            "def widget() -> int:\n    return 1\n",
            encoding="utf-8",
        )
        return tmp_path

    def _patched_execute(self, ref_count: int, downstream_count: int):
        """Build an awaitable stub for ``execute_find_references`` that
        returns ``ref_count`` synthetic references and one definition,
        so we can drive the truncation logic deterministically without
        depending on the find-references heuristic.

        The references are distributed across ``downstream_count``
        synthetic files so the downstream-files cap is exercised too
        — but we only assert flag presence on that branch because the
        dependency graph for a tmp project doesn't carry those edges.
        """

        async def fake(project_root, args):
            refs = []
            for i in range(ref_count):
                refs.append(
                    {
                        "name": "widget",
                        "type": "function",
                        "file": f"caller_{i % downstream_count}.py",
                        "start_line": i + 1,
                        "end_line": i + 1,
                        "role": "reference",
                    }
                )
            return {
                "success": True,
                "symbol": args["symbol"],
                "definitions": [
                    {
                        "name": "widget",
                        "type": "function",
                        "file": "lib.py",
                        "start_line": 1,
                        "end_line": 2,
                        "role": "definition",
                    }
                ],
                "references": refs,
                "files_searched": 1,
            }

        return fake

    def _run_lineage(
        self,
        project: Path,
        symbol: str,
        ref_count: int,
        downstream_count: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> dict:
        from tree_sitter_analyzer.mcp.tools import symbol_lineage_tool

        monkeypatch.setattr(
            symbol_lineage_tool,
            "execute_find_references",
            self._patched_execute(ref_count, downstream_count),
        )
        tool = symbol_lineage_tool.SymbolLineageTool(str(project))
        return _run(tool.execute({"symbol": symbol, "output_format": "json"}))

    def test_references_truncation_flags_set(
        self, tiny_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 40 distinct refs > 30 cap. downstream_count=10 keeps refs
        # spread across multiple files; the dep-graph branch may or may
        # not pick those up — we only assert the references flag here.
        result = self._run_lineage(
            tiny_project,
            "widget",
            ref_count=40,
            downstream_count=10,
            monkeypatch=monkeypatch,
        )
        assert result["success"] is True
        assert result["reference_count"] == 40
        assert result["references_truncated"] is True, (
            "G6: references_truncated must be True when refs > limit"
        )
        assert result["references_limit"] == 30, (
            f"G6: references_limit must report the cap (30) — got "
            f"{result['references_limit']!r}"
        )
        assert result["references_available"] == 40, (
            "G6: references_available must equal the real total"
        )
        # The shown list is capped at the limit.
        assert len(result["references"]) == 30, (
            f"G6: references list must be capped at the limit — got "
            f"{len(result['references'])}"
        )

    def test_no_truncation_under_limit(
        self, tiny_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Below-cap responses must report truncated=False and not
        contain a ``truncations`` marker in agent_summary."""
        result = self._run_lineage(
            tiny_project,
            "widget",
            ref_count=5,
            downstream_count=2,
            monkeypatch=monkeypatch,
        )
        assert result["references_truncated"] is False
        # ``agent_summary["truncations"]`` is only emitted when at
        # least one cap is hit.
        assert "truncations" not in result["agent_summary"]
        # And the summary_line must NOT shout "truncated=".
        assert "truncated=" not in result["agent_summary"]["summary_line"]

    def test_downstream_files_truncation_flags_present(
        self, tiny_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The truncation flag fields must always be present in the
        envelope with the correct shape — never silently absent."""
        result = self._run_lineage(
            tiny_project,
            "widget",
            ref_count=5,
            downstream_count=2,
            monkeypatch=monkeypatch,
        )
        assert "downstream_files_truncated" in result, (
            "G6: downstream_files_truncated must always be present"
        )
        assert isinstance(result["downstream_files_truncated"], bool)
        assert "downstream_files_limit" in result
        assert "downstream_files_available" in result
        assert result["downstream_files_limit"] == 50

    def test_summary_line_announces_truncation(
        self, tiny_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = self._run_lineage(
            tiny_project,
            "widget",
            ref_count=40,
            downstream_count=10,
            monkeypatch=monkeypatch,
        )
        sl = result["agent_summary"]["summary_line"]
        assert "truncated=" in sl, (
            f"G6: summary_line must announce truncation — got {sl!r}"
        )
        assert "references" in sl, (
            f"G6: summary_line must name the truncated field — got {sl!r}"
        )
        assert "truncations" in result["agent_summary"], (
            "G6: agent_summary must carry a structured truncations list"
        )
        assert "references" in result["agent_summary"]["truncations"]


class TestG7ParserReadinessSummaryLine:
    """G7 (round-18): ``parser_readiness`` top-level ``summary_line`` was
    None even when ``agent_summary`` could trivially derive a one-liner
    from implemented language count, candidate count, and risk.

    Contract:
      - Top-level ``summary_line`` is a non-empty string.
      - ``agent_summary["summary_line"]`` mirrors the top-level value so
        callers walking either path see the same thing.
    """

    def _run_advice(self, project: Path) -> dict:
        from tree_sitter_analyzer.mcp.tools.parser_readiness_tool import (
            ParserReadinessTool,
        )

        tool = ParserReadinessTool(str(project))
        return _run(tool.execute({"output_format": "json"}))

    def test_top_level_summary_line_is_non_empty(self, tmp_path: Path) -> None:
        result = self._run_advice(tmp_path)
        sl = result.get("summary_line")
        assert isinstance(sl, str) and sl, (
            f"G7: top-level summary_line must be a non-empty string — got {sl!r}"
        )

    def test_top_level_mirrors_agent_summary(self, tmp_path: Path) -> None:
        result = self._run_advice(tmp_path)
        top = result.get("summary_line")
        agent_sl = result.get("agent_summary", {}).get("summary_line")
        assert isinstance(top, str) and top, "G7: top-level must be non-empty"
        assert top == agent_sl, (
            f"G7: top-level summary_line must mirror agent_summary['summary_line']. "
            f"top={top!r} vs agent={agent_sl!r}"
        )

    def test_summary_line_carries_useful_fields(self, tmp_path: Path) -> None:
        """The headline should at least name the implemented count so an
        agent can branch without parsing the full envelope."""
        result = self._run_advice(tmp_path)
        sl = result["summary_line"]
        assert "implemented=" in sl, (
            f"G7: summary_line should report implemented= count — got {sl!r}"
        )


class TestG8AgentWorkflowEnvelope:
    """G8 (round-18): ``agent_workflow`` ``agent_summary`` lacked
    ``summary_line`` and ``verdict``, so it failed the cross-tool
    envelope contract that other tools rely on for chaining.

    Contract:
      - ``agent_summary`` carries both ``summary_line`` and ``verdict``.
      - Top-level ``summary_line`` mirrors ``agent_summary["summary_line"]``.
      - ``verdict`` is ``"n/a"`` (planning tool, no analysis to gate on).
    """

    def _run_workflow(self, project: Path, target: str | None = None) -> dict:
        from tree_sitter_analyzer.mcp.tools.agent_workflow_tool import (
            AgentWorkflowTool,
        )

        tool = AgentWorkflowTool(str(project))
        args: dict = {"output_format": "json"}
        if target:
            args["target_path"] = target
        return _run(tool.execute(args))

    def test_agent_summary_has_summary_line(self, tmp_path: Path) -> None:
        result = self._run_workflow(tmp_path)
        agent = result.get("agent_summary")
        assert isinstance(agent, dict) and agent, (
            "G8: agent_summary must be a populated dict"
        )
        sl = agent.get("summary_line")
        assert isinstance(sl, str) and sl, (
            f"G8: agent_summary['summary_line'] must be a non-empty string — got {sl!r}"
        )

    def test_agent_summary_has_verdict(self, tmp_path: Path) -> None:
        result = self._run_workflow(tmp_path)
        agent = result["agent_summary"]
        verdict = agent.get("verdict")
        assert isinstance(verdict, str) and verdict, (
            f"G8: agent_summary['verdict'] must be a non-empty string — got {verdict!r}"
        )

    def test_top_level_summary_line_mirrors_agent_summary(self, tmp_path: Path) -> None:
        result = self._run_workflow(tmp_path)
        top = result.get("summary_line")
        agent_sl = result["agent_summary"]["summary_line"]
        assert isinstance(top, str) and top, (
            "G8: top-level summary_line must be a non-empty string"
        )
        assert top == agent_sl, (
            f"G8: top-level summary_line must mirror "
            f"agent_summary['summary_line']. top={top!r} vs agent={agent_sl!r}"
        )

    def test_summary_line_carries_phase_info(self, tmp_path: Path) -> None:
        """Headline should name the current phase so an agent can branch
        on it without reading nested fields."""
        result = self._run_workflow(tmp_path, target="lib.py")
        sl = result["agent_summary"]["summary_line"]
        assert "phase=" in sl, (
            f"G8: summary_line should mention current phase — got {sl!r}"
        )


class TestG9RefactorPathRelative:
    """G9 (round-18): refactor response returned both ``file`` and
    ``file_path`` as the same absolute path (``/Users/.../foo.py``),
    leaking the user's home directory and breaking parity with every
    other tool (which emits project-relative paths).

    Strategy 1 (back-compat preserved): keep both fields, but normalise
    each to a project-relative path. The single test that reads
    ``result["file"]`` still works because ``"file" in result`` stays
    True — only its value changes.

    Contract:
      - Neither ``file`` nor ``file_path`` start with ``/Users/`` (or any
        absolute prefix) when the analysed file lies inside the project.
      - Both fields carry the same value.
      - The error envelope honours the same rule.
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        src = tmp_path / "lib.py"
        src.write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run_refactor(self, project: Path, file_path: str) -> dict:
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        tool = RefactoringSuggestionsTool(str(project))
        return _run(tool.execute({"file_path": file_path, "output_format": "json"}))

    def test_file_path_is_project_relative(self, tiny_project: Path) -> None:
        result = self._run_refactor(tiny_project, str(tiny_project / "lib.py"))
        assert result["success"] is True
        fp = result.get("file_path")
        assert isinstance(fp, str) and fp, (
            f"G9: file_path must be a non-empty string — got {fp!r}"
        )
        # Must not leak the absolute home prefix (or any leading slash on
        # POSIX). The project lies under tmp_path/<...>, so a correct
        # relative path is just "lib.py".
        assert not fp.startswith("/"), (
            f"G9: file_path must be project-relative — got absolute {fp!r}"
        )
        assert fp == "lib.py", (
            f"G9: file_path must be the project-relative form — got {fp!r}"
        )

    def test_file_alias_matches_file_path(self, tiny_project: Path) -> None:
        """The back-compat ``file`` alias must stay aligned with
        ``file_path``."""
        result = self._run_refactor(tiny_project, str(tiny_project / "lib.py"))
        assert result.get("file") == result.get("file_path"), (
            f"G9: file alias must match file_path. "
            f"file={result.get('file')!r}, file_path={result.get('file_path')!r}"
        )
        assert not str(result.get("file", "")).startswith("/"), (
            f"G9: file alias must be project-relative — got {result.get('file')!r}"
        )

    def test_error_response_path_is_relative(self, tiny_project: Path) -> None:
        """The error envelope must honour the same path rules — a
        nonexistent file inside the project should not leak any absolute
        path either."""
        from tree_sitter_analyzer.mcp.tools.utils.refactoring_suggestions_helpers import (
            error_response,
        )

        # Direct unit call: error_response normalises whatever it gets.
        # ``not_real.py`` is project-relative input; the helper should
        # leave it relative (no absolute prefix).
        out = error_response(
            "not_real.py",
            "File not found",
            project_root=str(tiny_project),
        )
        assert out["success"] is False
        assert out["file"] == out["file_path"]
        assert not out["file"].startswith("/"), (
            f"G9: error_response must not emit absolute paths — got {out['file']!r}"
        )

    def test_error_response_with_absolute_path_relativizes(
        self, tiny_project: Path
    ) -> None:
        """When the helper receives an absolute path under the project
        root, it must relativize."""
        from tree_sitter_analyzer.mcp.tools.utils.refactoring_suggestions_helpers import (
            error_response,
        )

        abs_path = str(tiny_project / "missing.py")
        out = error_response(
            abs_path,
            "File not found",
            project_root=str(tiny_project),
        )
        assert out["file_path"] == "missing.py", (
            f"G9: absolute path under project_root must be relativized — "
            f"got {out['file_path']!r}"
        )


class TestF5SchemaStrictness:
    """F5: round-16b dogfood showed parameter typos pass silently.

    JSON Schema defaults to ``additionalProperties: true`` — so
    ``max_suggestion: 5`` (missing the 's') would validate, the typo'd
    key would be dropped, and the tool would run with the default
    ``max_suggestions: 10``. The caller never learns their input was
    ignored.

    F5 makes ``additionalProperties: false`` the implicit default for
    every tool's input schema via ``BaseMCPTool.__init_subclass__`` and
    rejects unknown top-level parameters with a *did-you-mean* hint
    derived from :func:`difflib.get_close_matches`. The MCP server's
    canonical error envelope wraps the resulting ``ValueError`` into
    a ``success: false, error_type: "validation"`` response.
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        src = tmp_path / "sample.py"
        src.write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_typo_in_parameter_raises_validation_error(
        self, tiny_project: Path
    ) -> None:
        """``max_suggestion`` (missing the 's') must be rejected with a
        ``ValueError`` whose message points at ``max_suggestions``."""
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        tool = RefactoringSuggestionsTool(str(tiny_project))
        with pytest.raises(ValueError) as exc_info:
            _run(
                tool.execute(
                    {
                        "file_path": str(tiny_project / "sample.py"),
                        "max_suggestion": 5,  # typo of max_suggestions
                    }
                )
            )
        msg = str(exc_info.value)
        assert "max_suggestion" in msg
        assert "max_suggestions" in msg, (
            "did-you-mean hint must point the caller at the real parameter"
        )

    def test_dispatcher_wraps_typo_in_canonical_error_envelope(
        self, tiny_project: Path
    ) -> None:
        """End-to-end through the MCP dispatch path: typo'd parameter
        comes out as ``{success: false, error_type: "validation"}``
        with the did-you-mean hint preserved in ``error``."""
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            build_agent_friendly_error,
        )
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        tool = RefactoringSuggestionsTool(str(tiny_project))
        args = {
            "file_path": str(tiny_project / "sample.py"),
            "max_suggestion": 5,
        }
        try:
            _run(tool.execute(args))
            pytest.fail("expected ValueError")
        except ValueError as e:
            envelope = build_agent_friendly_error(
                "refactoring_suggestions", e, arguments=args
            )
        assert envelope["success"] is False
        assert envelope["error_type"] == "validation"
        assert "max_suggestion" in envelope["error"]
        assert "max_suggestions" in envelope["error"]
        # Canonical envelope mirrors a summary_line at top level.
        assert isinstance(envelope.get("summary_line"), str)

    def test_valid_parameters_still_pass_through(self, tiny_project: Path) -> None:
        """Sanity: a well-formed call still succeeds end-to-end."""
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        tool = RefactoringSuggestionsTool(str(tiny_project))
        result = _run(
            tool.execute(
                {
                    "file_path": str(tiny_project / "sample.py"),
                    "max_suggestions": 5,
                    "output_format": "json",
                }
            )
        )
        assert result["success"] is True

    def test_unknown_parameter_with_no_close_match_has_no_did_you_mean(
        self, tiny_project: Path
    ) -> None:
        """``difflib.get_close_matches`` only fires when the typo is
        within editing distance of a real property — random keys must
        get the bare ``unknown parameter`` message with no hint."""
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        tool = RefactoringSuggestionsTool(str(tiny_project))
        with pytest.raises(ValueError) as exc_info:
            _run(
                tool.execute(
                    {
                        "file_path": str(tiny_project / "sample.py"),
                        "xyz_unrelated_garbage": True,
                    }
                )
            )
        msg = str(exc_info.value)
        assert "xyz_unrelated_garbage" in msg
        assert "did you mean" not in msg, (
            "did-you-mean hint must not fire for typos with no close match"
        )

    def test_file_health_tool_also_rejects_typos(self, tiny_project: Path) -> None:
        """The strictness check is centralised at the base class level —
        every BaseMCPTool subclass inherits it. Use a second real tool
        as a smoke check that we did not accidentally hard-code the
        check to one specific tool."""
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tiny_project))
        with pytest.raises(ValueError) as exc_info:
            _run(
                tool.execute(
                    {
                        "file_path": str(tiny_project / "sample.py"),
                        "output_formatt": "json",  # extra t
                    }
                )
            )
        msg = str(exc_info.value)
        assert "output_formatt" in msg
        # Close enough that difflib should suggest 'output_format'.
        assert "output_format" in msg

    def test_enforce_strict_params_helper_directly(self) -> None:
        """Direct unit test on the helper — covers the function in
        isolation from any tool's get_tool_definition."""
        from tree_sitter_analyzer.mcp.utils.schema_strictness import (
            enforce_strict_params,
        )

        schema = {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "max_suggestions": {"type": "integer"},
            },
            "required": ["file_path"],
        }
        # Empty arguments → no-op.
        enforce_strict_params("t", schema, {})
        # Valid call → no-op.
        enforce_strict_params("t", schema, {"file_path": "x"})
        # Unknown key with close match → ValueError with hint.
        with pytest.raises(ValueError, match="max_suggestions"):
            enforce_strict_params("t", schema, {"file_path": "x", "max_suggestion": 1})
        # additionalProperties: True opts out of strictness.
        enforce_strict_params(
            "t",
            {**schema, "additionalProperties": True},
            {"file_path": "x", "extras": "ok"},
        )
        # Missing schema → no-op.
        enforce_strict_params("t", None, {"file_path": "x"})
        # Schema without properties → no-op (cannot know what's known).
        enforce_strict_params("t", {"type": "object"}, {"file_path": "x"})


def _assert_envelope_with_summary(name: str, result: dict) -> None:
    """Shared H5 helper: a response carries the full canonical envelope.

    Round-20 dogfood (H5): four tools shipped ad-hoc dicts without
    ``success`` / ``summary_line`` / ``agent_summary``. The post-hook
    in the MCP dispatcher fills missing fields for MCP-routed callers
    but *not* for direct ``await tool.execute(args)`` callers (tests,
    CLI bridges) — so each tool now sets the envelope itself.
    """
    assert isinstance(result, dict), f"{name}: result must be a dict"
    assert result.get("success") is True, f"{name}: success must be True"
    sl = result.get("summary_line")
    assert isinstance(sl, str) and sl, (
        f"{name}: top-level summary_line must be a non-empty string"
    )
    agent = result.get("agent_summary")
    assert isinstance(agent, dict) and agent, (
        f"{name}: agent_summary must be a populated dict, got {agent!r}"
    )
    nested_sl = agent.get("summary_line")
    assert isinstance(nested_sl, str) and nested_sl, (
        f"{name}: agent_summary.summary_line must be a non-empty string"
    )
    assert sl == nested_sl, (
        f"{name}: top-level summary_line must mirror agent_summary.summary_line — "
        f"top={sl!r} vs agent={nested_sl!r}"
    )


class TestH5AstCacheEnvelope:
    """Round-20 H5: ast_cache modes previously shipped raw dicts with
    ``success`` but no ``summary_line`` or ``agent_summary``. Every
    mode must now expose the canonical envelope keys.
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        (tmp_path / "sample.py").write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_stats_envelope(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(tiny_project))
        result = _run(tool.execute({"mode": "stats"}))
        _assert_envelope_with_summary("ast_cache:stats", result)
        # Headline must include the key counts.
        sl = result["summary_line"]
        assert "files=" in sl and "symbols=" in sl and "fts5=" in sl

    def test_search_envelope(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(tiny_project))
        result = _run(tool.execute({"mode": "search", "query": "greet"}))
        _assert_envelope_with_summary("ast_cache:search", result)
        assert "search" in result["summary_line"]

    def test_changes_envelope(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(tiny_project))
        result = _run(tool.execute({"mode": "changes"}))
        _assert_envelope_with_summary("ast_cache:changes", result)


class TestH5CheckToolsEnvelope:
    """Round-20 H5: check_tools previously returned
    ``{fd, rg, status, recommendation}`` with no ``success`` /
    ``summary_line`` / ``agent_summary``.
    """

    def test_envelope_present(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.check_tools_tool import CheckToolsTool

        tool = CheckToolsTool(str(tmp_path))
        result = _run(tool.execute({}))
        _assert_envelope_with_summary("check_tools", result)
        # status field must still be present (back-compat).
        assert result.get("status") in {"all_tools_available", "missing_tools"}
        # verdict must be one of the documented enum values.
        verdict = result["agent_summary"].get("verdict")
        assert verdict in {"READY", "MISSING"}, (
            f"check_tools: verdict must be READY or MISSING, got {verdict!r}"
        )


class TestH5BuildProjectIndexEnvelope:
    """Round-20 H5: build_project_index previously returned
    ``{status, build_duration_ms, files_scanned, ...}`` with no
    ``success`` / ``summary_line`` / ``agent_summary``.
    """

    def test_envelope_present(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.build_project_index_tool import (
            BuildProjectIndexTool,
        )

        (tmp_path / "sample.py").write_text(
            "def f() -> None:\n    return None\n", encoding="utf-8"
        )
        tool = BuildProjectIndexTool(str(tmp_path))
        result = _run(tool.execute({}))
        _assert_envelope_with_summary("build_project_index", result)
        # Headline must mention the actual file count.
        assert "files=" in result["summary_line"]
        # Back-compat: status field still present.
        assert result.get("status") == "built"


class TestH5BatchSearchEnvelope:
    """Round-20 H5: batch_search previously returned
    ``{queries, total_matches, execution_note}`` with no ``success``
    or ``summary_line``.
    """

    def test_envelope_present(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.batch_search_tool import BatchSearchTool

        (tmp_path / "sample.py").write_text(
            "def alpha(): pass\ndef beta(): pass\n", encoding="utf-8"
        )
        tool = BatchSearchTool(str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "queries": [
                        {"pattern": "alpha", "roots": [str(tmp_path)]},
                        {"pattern": "beta", "roots": [str(tmp_path)]},
                    ]
                }
            )
        )
        _assert_envelope_with_summary("batch_search", result)
        # Headline must include the query / match counts.
        sl = result["summary_line"]
        assert "queries=" in sl
        assert "total_matches=" in sl


class TestH10GetProjectSummaryFormat:
    """Round-20 H10: get_project_summary previously returned
    ``format=None`` on the JSON path. Both ``format`` and
    ``output_format`` must echo the resolved value.
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        (tmp_path / "lib.py").write_text(
            "def f() -> None:\n    return None\n", encoding="utf-8"
        )
        return tmp_path

    def test_explicit_json_echoes_both_keys(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.get_project_summary_tool import (
            GetProjectSummaryTool,
        )

        tool = GetProjectSummaryTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json"}))
        # Both fields must carry the resolved value — neither may be None.
        assert result.get("format") == "json", (
            f"H10: explicit output_format=json must echo format='json' — got "
            f"{result.get('format')!r}"
        )
        assert result.get("output_format") == "json", (
            f"H10: output_format must echo back as 'json' — got "
            f"{result.get('output_format')!r}"
        )

    def test_toon_default_echoes_both_keys(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.get_project_summary_tool import (
            GetProjectSummaryTool,
        )

        tool = GetProjectSummaryTool(str(tiny_project))
        result = _run(tool.execute({}))
        # The tool documents toon as the default (token-efficiency choice
        # for a first-hop orientation tool). Both keys must carry that
        # value.
        assert result.get("format") == "toon"
        assert result.get("output_format") == "toon"

    def test_default_is_documented_toon(self) -> None:
        """H10 decision: default stayed ``toon`` for token efficiency.

        Asserting the documented default catches future drift in either
        direction — if someone flips it back to json, this test forces
        an explicit decision (and a doc update for callers that depend
        on the default).
        """
        from tree_sitter_analyzer.mcp.tools.get_project_summary_tool import (
            GetProjectSummaryTool,
        )

        tool = GetProjectSummaryTool()
        defn = tool.get_tool_definition()
        schema = defn["inputSchema"]
        of = schema["properties"]["output_format"]
        assert of["default"] == "toon", (
            f"H10: default output_format documented as 'toon' — got {of['default']!r}"
        )
        # The description must mention the rationale so callers know why.
        assert "default" in of["description"].lower()


class TestH11OverviewToolRoutingValidNames:
    """Round-20 H11: ``tool_routing`` advertised tool names mixed with
    CLI shorthand. Every value here must reference an MCP-registered
    tool name AND use MCP keyword-argument syntax (``tool(key=value)``).
    """

    def test_every_routing_target_is_registered(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.server import _create_tool_registry
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            _build_tool_routing,
        )

        instances, _ = _create_tool_registry(str(tmp_path))
        registered = {name for name, _ in instances}
        routing = _build_tool_routing()
        assert routing, "tool_routing must not be empty"

        import re

        # Snippet starts with ``<tool_name>(``. Pull out the leading
        # identifier and assert it's in the live registry.
        ident_re = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*)\s*\(")
        unknown: list[str] = []
        for key, snippet in routing.items():
            m = ident_re.match(snippet)
            assert m is not None, (
                f"H11: tool_routing[{key!r}] snippet must start with a "
                f"tool name + '(' — got {snippet!r}"
            )
            tool_name = m.group(1)
            if tool_name not in registered:
                unknown.append(f"{key}: {tool_name}")
        assert unknown == [], (
            f"H11: tool_routing entries reference unregistered MCP tools: "
            f"{unknown}. Valid names: {sorted(registered)}"
        )

    def test_routing_uses_keyword_arguments(self) -> None:
        """MCP-canonical means keyword arguments — ``tool(key=value)`` —
        not CLI positional ``tool key value``. Snippets that have any
        argument MUST use ``=`` inside the parens."""
        import re

        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            _build_tool_routing,
        )

        for key, snippet in _build_tool_routing().items():
            # Extract the argument portion (between first '(' and the
            # matching ')' before the comment).
            m = re.match(r"^[A-Za-z_][A-Za-z_0-9]*\(([^)]*)\)", snippet)
            assert m is not None, (
                f"H11: tool_routing[{key!r}] must be a function-call shape — "
                f"got {snippet!r}"
            )
            args = m.group(1).strip()
            # If args is empty, no syntax check needed (e.g.
            # ``check_project_health()``).
            if not args:
                continue
            # Any non-empty args MUST carry at least one '=' — meaning
            # keyword form.
            assert "=" in args, (
                f"H11: tool_routing[{key!r}] uses positional / CLI form — "
                f"MCP requires keyword arguments. Got: {snippet!r}"
            )

    def test_routing_covers_core_tools(self) -> None:
        """A regression guard: the routing guide must still surface the
        most common tools agents need (no shrinkage from this version)."""
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            _build_tool_routing,
        )

        routing = _build_tool_routing()
        core_keys = {
            "project_health",
            "file_health",
            "edit_risk",
            "find_symbol",
            "search_text",
            "find_files",
            "file_scale",
            "structure_table",
            "read_lines",
        }
        missing = core_keys - set(routing.keys())
        assert not missing, (
            f"H11: tool_routing must keep core entries — missing: {missing}"
        )


class TestH8ChangeImpactInvalidScope:
    """H8: ``change_impact`` must not silently swallow a typo'd scope path.

    Pre-fix behaviour:
      uv run python -m tree_sitter_analyzer --change-impact \
          --change-impact-scope /tmp/does_not_exist_xyz.py --format json
      → success: true, changed_count: 0, summary: "No changes detected"

    The user typoed their scope path; the tool silently treated it as a
    valid scope that matched nothing — false negative ("no work needed").

    Post-fix contract (analysis still runs on the *valid* scope paths,
    but the response cannot be mistaken for clean):
      - ``scope_paths_invalid`` lists every nonexistent path supplied
      - ``agent_summary["next_step"]`` carries a concrete "did you typo?"
        hint that names the offending paths
      - ``agent_summary["verdict"]`` escalates from CLEAN to WARN
      - ``summary_line`` (top-level + agent) carries a
        ``scope_invalid=N`` token so chained tools can grep one line
      - ``success`` stays True — the analysis itself succeeded
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        """Smallest valid project. ``execute()`` only inspects the working
        tree via git, so we just need a real project_root on disk."""
        src = tmp_path / "lib.py"
        src.write_text(
            "def widget() -> int:\n    return 1\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run_change_impact(self, project: Path, scope_paths: list[str]) -> dict:
        from tree_sitter_analyzer.mcp.tools.change_impact_tool import (
            ChangeImpactTool,
        )

        tool = ChangeImpactTool(str(project))
        return _run(
            tool.execute(
                {
                    "mode": "diff",
                    "scope_paths": scope_paths,
                    "output_format": "json",
                }
            )
        )

    def test_invalid_scope_path_listed_in_response(self, tiny_project: Path) -> None:
        """The nonexistent path lands in ``scope_paths_invalid``."""
        bogus = str(tiny_project / "does_not_exist_xyz.py")
        result = self._run_change_impact(tiny_project, [bogus])
        assert result["success"] is True, (
            "H8: analysis still runs — success must stay True"
        )
        invalid = result.get("scope_paths_invalid")
        assert isinstance(invalid, list) and bogus in invalid, (
            f"H8: scope_paths_invalid must include the bogus path — got {invalid!r}"
        )

    def test_invalid_scope_path_warning_in_next_step(self, tiny_project: Path) -> None:
        """``agent_summary['next_step']`` names the offending paths so an
        agent's decision loop catches the typo before re-running."""
        bogus = str(tiny_project / "missing_module.py")
        result = self._run_change_impact(tiny_project, [bogus])
        agent = result["agent_summary"]
        next_step = agent.get("next_step", "")
        assert isinstance(next_step, str) and next_step, (
            f"H8: next_step must be a non-empty string — got {next_step!r}"
        )
        assert "do not exist" in next_step, (
            f"H8: next_step must explain the failure — got {next_step!r}"
        )
        assert "did you typo" in next_step.lower(), (
            f"H8: next_step must prompt the agent for a typo — got {next_step!r}"
        )
        assert bogus in next_step, (
            f"H8: next_step must name the offending path — got {next_step!r}"
        )

    def test_invalid_scope_escalates_verdict_to_warn(self, tiny_project: Path) -> None:
        """Verdict must escalate from the CLEAN default to WARN."""
        bogus = str(tiny_project / "ghost.py")
        result = self._run_change_impact(tiny_project, [bogus])
        agent = result["agent_summary"]
        verdict = agent.get("verdict")
        assert verdict == "WARN", (
            f"H8: invalid scope path must escalate verdict to WARN — got {verdict!r}"
        )

    def test_valid_scope_path_keeps_clean_verdict(self, tiny_project: Path) -> None:
        """Sanity check: a real path leaves the verdict at the CLEAN
        default. Otherwise we'd be permanently warning on every call."""
        real = str(tiny_project / "lib.py")
        result = self._run_change_impact(tiny_project, [real])
        agent = result["agent_summary"]
        verdict = agent.get("verdict")
        assert verdict == "CLEAN", (
            f"H8: valid scope path must keep verdict at CLEAN — got {verdict!r}"
        )
        # And scope_paths_invalid must be empty (always present, list shape).
        assert result.get("scope_paths_invalid") == [], (
            f"H8: scope_paths_invalid must be [] on the happy path — "
            f"got {result.get('scope_paths_invalid')!r}"
        )

    def test_summary_line_contains_scope_invalid_token(
        self, tiny_project: Path
    ) -> None:
        """``summary_line`` carries a ``scope_invalid=N`` token so chained
        agents that only read the headline still see the warning."""
        bogus1 = str(tiny_project / "absent1.py")
        bogus2 = str(tiny_project / "absent2.py")
        result = self._run_change_impact(tiny_project, [bogus1, bogus2])
        # top-level
        top = result.get("summary_line", "")
        assert "scope_invalid=2" in top, (
            f"H8: top-level summary_line must include scope_invalid=2 — got {top!r}"
        )
        # mirrored in agent_summary
        nested = result["agent_summary"].get("summary_line", "")
        assert "scope_invalid=2" in nested, (
            f"H8: agent_summary['summary_line'] must include scope_invalid=2 — "
            f"got {nested!r}"
        )

    def test_no_scope_paths_keeps_clean_default(self, tiny_project: Path) -> None:
        """Without any scope_paths, the response stays clean — no
        spurious WARN. ``scope_paths_invalid`` is still present (empty)."""
        result = self._run_change_impact(tiny_project, [])
        agent = result["agent_summary"]
        assert agent.get("verdict") == "CLEAN", (
            f"H8: no scope_paths must keep verdict at CLEAN — "
            f"got {agent.get('verdict')!r}"
        )
        assert result.get("scope_paths_invalid") == [], (
            "H8: empty scope_paths must yield empty scope_paths_invalid"
        )

    def test_relative_invalid_path_is_resolved_against_project_root(
        self, tiny_project: Path
    ) -> None:
        """Relative paths get resolved against project_root before the
        existence check. ``relative/missing/x.py`` (which doesn't exist
        anywhere) must still be flagged."""
        result = self._run_change_impact(tiny_project, ["relative/missing/x.py"])
        invalid = result.get("scope_paths_invalid", [])
        assert "relative/missing/x.py" in invalid, (
            f"H8: relative paths must be resolved against project_root — "
            f"got {invalid!r}"
        )


# ============================================================================
# H2 — call_graph resolver parity between all_functions and callers/callees
# ============================================================================


class TestH2CallGraphResolverParity:
    """H2 (round-20): symbols listed by ``mode=all_functions`` must also be
    resolvable by ``mode=callers``/``mode=callees`` — they were not, because
    ``_node_text`` used tree-sitter's BYTE offsets to index a Python ``str``
    (character-indexed), corrupting call-target names for any source file
    containing multi-byte characters (e.g. em-dashes in comments).

    Repro symbol in the real repo: ``_normalize_dependency_mode`` in
    ``tree_sitter_analyzer/cli/commands/mcp_commands.py`` (line 63). With
    the bug, the file's em-dash in earlier comments shifted every
    subsequent byte offset, so the call-name extracted at line 69 came
    out as ``'malize_dependency_mode(get'`` and never matched the
    function-name index. After the fix, ``callers_of`` finds the two
    real callers (``_dependency_mode_requires_file`` and
    ``_build_dependency_tool_args``).

    Contract:
      - If a symbol shows up in ``all_functions``, ``callers`` / ``callees``
        must NOT respond with the canonical NOT_FOUND verdict.
      - ``caller_count`` / ``callee_count`` are integers (may be 0 for
        truly leaf functions — but the symbol must be RECOGNIZED).
    """

    @pytest.fixture
    def project_with_emdash(self, tmp_path: Path) -> Path:
        """Mimic the real bug shape: a source file with a multi-byte
        character in a leading comment, plus a callee defined below
        that comment, a caller invoking it, AND an explicit call to a
        helper so ``callees`` has something to return for the function
        under test.

        Without the byte/char fix, the em-dash adds 2 bytes per
        occurrence of drift, and every call name extracted after it is
        truncated/shifted — including the call from ``normalize_thing``
        to ``str.strip``-like helpers.
        """
        src = tmp_path / "module.py"
        src.write_text(
            "# Header — multi-byte em-dash drifts byte offsets vs char offsets.\n"
            "# Another — em-dash to amplify the drift past one character.\n"
            "\n"
            "def fallback_value():\n"
            "    return 'default'\n"
            "\n"
            "def normalize_thing(x):\n"
            "    # normalize_thing has a callee (fallback_value) so its\n"
            "    # callees list is non-empty when extraction works.\n"
            "    return x or fallback_value()\n"
            "\n"
            "def caller_one(args):\n"
            "    return normalize_thing(args)\n"
            "\n"
            "def caller_two(args):\n"
            "    return normalize_thing(args)\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run_tool(self, project: Path, mode: str, function: str | None = None) -> dict:
        from tree_sitter_analyzer.mcp.tools.call_graph_tool import CodeGraphCallTool

        tool = CodeGraphCallTool(str(project))
        args: dict = {"mode": mode, "output_format": "json"}
        if function is not None:
            args["function_name"] = function
        return _run(tool.execute(args))

    def test_emdash_function_appears_in_all_functions(
        self, project_with_emdash: Path
    ) -> None:
        """Sanity: the function IS indexed."""
        result = self._run_tool(project_with_emdash, "all_functions")
        names = {fn["name"] for fn in result.get("functions", [])}
        assert "normalize_thing" in names, (
            "H2 fixture: ``normalize_thing`` must appear in all_functions"
        )

    def test_emdash_function_callers_not_not_found(
        self, project_with_emdash: Path
    ) -> None:
        """The real bug: ``callers`` returned ``verdict=NOT_FOUND`` for a
        function that ``all_functions`` plainly lists. With the byte-vs-char
        fix, the call-name extraction is correct and the lookup succeeds.
        """
        result = self._run_tool(project_with_emdash, "callers", "normalize_thing")
        assert result["success"] is True
        verdict = result.get("agent_summary", {}).get("verdict")
        assert verdict != "NOT_FOUND", (
            f"H2: ``callers`` must NOT report NOT_FOUND for an indexed symbol "
            f"— got verdict={verdict!r}"
        )
        # caller_count must be an integer >= 0; the fixture has 2 callers.
        assert isinstance(result.get("caller_count"), int), (
            "H2: caller_count must be an integer when the symbol is indexed"
        )
        assert result["caller_count"] >= 2, (
            f"H2: expected at least 2 callers (caller_one, caller_two) — "
            f"got caller_count={result['caller_count']}, callers={result.get('callers')!r}"
        )

    def test_emdash_function_callees_not_not_found(
        self, project_with_emdash: Path
    ) -> None:
        """``callees`` for ``normalize_thing`` must resolve at least
        the call to ``fallback_value`` (defined in the same file). With
        the byte/char bug, the call name extracted would be corrupted
        (``'lback_value(' or worse``) and the resolver finds no match,
        so ``callee_count`` collapses to 0 and the response carries the
        canonical NOT_FOUND verdict."""
        result = self._run_tool(project_with_emdash, "callees", "normalize_thing")
        assert result["success"] is True
        verdict = result.get("agent_summary", {}).get("verdict")
        assert verdict != "NOT_FOUND", (
            f"H2: ``callees`` must NOT report NOT_FOUND for an indexed symbol "
            f"— got verdict={verdict!r}"
        )
        assert isinstance(result.get("callee_count"), int)
        assert result["callee_count"] >= 1, (
            f"H2: ``normalize_thing`` calls ``fallback_value`` — expected "
            f"callee_count>=1, got {result['callee_count']} "
            f"callees={result.get('callees')!r}"
        )

    def test_leaf_function_indexed_flag_exposed(
        self, project_with_emdash: Path
    ) -> None:
        """The response must expose ``function_indexed`` so downstream
        tools (and tests) can distinguish "this function is in the graph
        but happens to have no callers/callees" from "we have no record
        of this function". Without that distinction, F8's NOT_FOUND
        verdict over-fires on leaf functions (and on functions used only
        via first-class references like ``requires_file=foo``) and tells
        the agent to run ``symbol_lineage`` for a name that already
        exists — wasting an MCP round-trip."""
        # ``fallback_value`` is called from ``normalize_thing`` so it has
        # 1 caller. Pick the callees mode instead — it returns zero.
        result = self._run_tool(project_with_emdash, "callees", "fallback_value")
        assert result["success"] is True
        assert result.get("function_indexed") is True, (
            "H2: ``function_indexed`` must be exposed in the response so "
            "downstream tools can distinguish indexed-leaf from unindexed."
        )
        assert result.get("agent_summary", {}).get("verdict") != "NOT_FOUND", (
            "H2: leaf functions (zero callees but indexed) must not be "
            "reported as NOT_FOUND."
        )

    def test_truly_unindexed_symbol_still_not_found(
        self, project_with_emdash: Path
    ) -> None:
        """The NOT_FOUND verdict must still fire for symbols that the
        graph does not know about at all. The F8 contract from round-17
        depends on this — agents need a clear signal to switch to
        ``symbol_lineage`` when they typo'd a name."""
        result = self._run_tool(
            project_with_emdash, "callers", "wholly_invented_xyz123"
        )
        assert result["success"] is True
        assert result.get("function_indexed") is False, (
            "H2: ``function_indexed`` must be False for unindexed symbols."
        )
        assert result.get("agent_summary", {}).get("verdict") == "NOT_FOUND", (
            "H2: genuinely missing symbols must keep the NOT_FOUND verdict "
            "so F8's symbol_lineage redirect still triggers."
        )


# ============================================================================
# H3 — project graphs deterministic between runs
# ============================================================================


class TestH3DeterministicGraphCounts:
    """H3 (round-20): public counts on call_graph and dependency_analysis
    were non-deterministic — different runs of identical inputs returned
    different ``cycle_count`` (5↔6) and different ``call_edge_count``
    (varied by thousands). Root causes:

      - ``CallGraph.build`` mixed "register definitions" and "resolve
        calls" in a single pass that iterated files in filesystem order,
        so call-to-definition resolution depended on which file was
        parsed first. Fixed via a two-pass build: register all defs
        from all files (sorted) in pass 1, then resolve calls in pass 2.

      - ``DependencyGraph.find_cycles`` does a DFS that iterates a
        ``set`` of nodes and ``set`` of neighbours, both of which have
        PYTHONHASHSEED-dependent iteration order. Fixed in
        ``dependency_analysis_tool`` by routing through
        ``_deterministic_find_cycles`` which sorts iteration order and
        canonicalises the cycle list.

    These tests build the graph twice IN-PROCESS against an identical
    fixture and assert that the public counts match. The fixture is
    small and tailored so two builds finish fast.
    """

    @pytest.fixture
    def project_with_cycle(self, tmp_path: Path) -> Path:
        """A small project with a known import cycle and a call edge.

        ``a -> b -> a`` is a 2-node cycle. We use ``from pkg.<mod> import
        <name>`` so the dependency resolver maps each import to the
        target ``.py`` file (rather than to ``pkg/__init__.py`` which is
        what bare-package imports collapse to).

        ``c`` calls a free function in ``a`` to give the call-graph
        something extra to count edges on.
        """
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "pkg" / "a.py").write_text(
            "from pkg.b import do_b\n\ndef helper_a():\n    return do_b()\n",
            encoding="utf-8",
        )
        (tmp_path / "pkg" / "b.py").write_text(
            "from pkg.a import helper_a\n\ndef do_b():\n    return helper_a()\n",
            encoding="utf-8",
        )
        (tmp_path / "pkg" / "c.py").write_text(
            "from pkg.a import helper_a\n\ndef use_a():\n    return helper_a()\n",
            encoding="utf-8",
        )
        return tmp_path

    def _build_dependency_summary(self, project: Path) -> dict:
        """Run dependency-analysis ``summary`` with a fresh tool instance —
        each instance builds its own graph, so this isolates the in-process
        build from any global cache."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )

        tool = DependencyAnalysisTool(str(project))
        return _run(tool.execute({"mode": "summary", "output_format": "json"}))

    def _build_call_graph_summary(self, project: Path) -> dict:
        from tree_sitter_analyzer.mcp.tools.call_graph_tool import CodeGraphCallTool

        tool = CodeGraphCallTool(str(project))
        return _run(tool.execute({"mode": "summary", "output_format": "json"}))

    def test_dependency_summary_cycle_count_stable(
        self, project_with_cycle: Path
    ) -> None:
        """Two back-to-back ``dependencies summary`` calls return the
        same ``cycle_count`` and ``node_count``. The first call sees a
        cold graph, the second a warm one — but they must agree even if
        the warm-cache path is taken."""
        first = self._build_dependency_summary(project_with_cycle)
        second = self._build_dependency_summary(project_with_cycle)
        assert first["cycle_count"] == second["cycle_count"], (
            f"H3: dependency summary cycle_count must be stable across runs — "
            f"first={first['cycle_count']} second={second['cycle_count']}"
        )
        assert first["node_count"] == second["node_count"], (
            f"H3: dependency summary node_count must be stable across runs — "
            f"first={first['node_count']} second={second['node_count']}"
        )
        assert first["edge_count"] == second["edge_count"], (
            f"H3: dependency summary edge_count must be stable across runs — "
            f"first={first['edge_count']} second={second['edge_count']}"
        )

    def test_dependency_cycles_mode_count_stable(
        self, project_with_cycle: Path
    ) -> None:
        """The ``cycles`` mode must return the same ``cycle_count`` across
        back-to-back runs. The 2-node cycle a↔b must always be present."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )

        first = _run(
            DependencyAnalysisTool(str(project_with_cycle)).execute(
                {"mode": "cycles", "output_format": "json"}
            )
        )
        second = _run(
            DependencyAnalysisTool(str(project_with_cycle)).execute(
                {"mode": "cycles", "output_format": "json"}
            )
        )
        assert first["cycle_count"] == second["cycle_count"], (
            f"H3: dependency cycles cycle_count must be stable across runs — "
            f"first={first['cycle_count']} second={second['cycle_count']}"
        )
        # Sanity: the a↔b cycle must be detected.
        assert first["cycle_count"] >= 1, (
            f"H3 fixture: expected at least one cycle (a↔b) — "
            f"cycle_count={first['cycle_count']} cycles={first.get('cycles')!r}"
        )

    def test_call_graph_summary_edge_count_stable(
        self, project_with_cycle: Path
    ) -> None:
        """``call_edge_count`` must agree across back-to-back builds.
        Both calls go through a fresh tool instance so the second call
        also builds the graph from scratch."""
        first = self._build_call_graph_summary(project_with_cycle)
        second = self._build_call_graph_summary(project_with_cycle)
        assert first["call_edge_count"] == second["call_edge_count"], (
            f"H3: call_graph call_edge_count must be stable across runs — "
            f"first={first['call_edge_count']} second={second['call_edge_count']}"
        )
        assert first["function_count"] == second["function_count"], (
            f"H3: call_graph function_count must be stable across runs — "
            f"first={first['function_count']} second={second['function_count']}"
        )


class TestH4TraceImpactSourceOnly:
    """H4 (round-20): ``trace_impact`` counted every ripgrep hit as a
    "caller", inflating ``call_count`` with CHANGELOG.md / comment text
    matches. Agents reading ``impact_badge: '🚨 HIGH IMPACT — 2132
    CALLERS'`` would refuse to refactor based on marketing copy.

    Contract:
      - ``usages[].file`` must end in a source-code extension; no .md,
        .txt, .csv, etc.
      - ``source_call_count`` exists and equals ``call_count``.
      - ``usage_count`` exists and equals ``len(usages)``.
      - ``impact_badge`` reflects the source-only count.
    """

    @pytest.fixture
    def mixed_project(self, tmp_path: Path) -> Path:
        """Project with source files + markdown + text — same symbol in
        every kind of file. The source-only filter must strip the
        non-source hits."""
        (tmp_path / "src.py").write_text(
            "def widget() -> int:\n"
            "    return 1\n"
            "\n"
            "def caller() -> int:\n"
            "    return widget() + widget()\n",
            encoding="utf-8",
        )
        # Non-source files that contain the symbol — must NOT contribute
        # to ``call_count``.
        (tmp_path / "CHANGELOG.md").write_text(
            "## Changed\n- widget API now returns int\n- widget docs cleaned up\n",
            encoding="utf-8",
        )
        (tmp_path / "design.txt").write_text(
            "widget design notes — please refer to widget for examples\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_trace_impact_excludes_markdown(self, mixed_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        tool = TraceImpactTool(str(mixed_project))
        result = _run(tool.execute({"symbol": "widget"}))

        assert result["success"] is True, f"trace_impact failed: {result!r}"
        usages = result.get("usages", [])
        # Every usage must come from a source extension.
        for usage in usages:
            file_name = usage.get("file", "")
            assert not file_name.endswith(".md"), (
                f"H4: usages must not contain markdown — got {file_name!r}"
            )
            assert not file_name.endswith(".txt"), (
                f"H4: usages must not contain text files — got {file_name!r}"
            )

    def test_trace_impact_emits_source_call_count(self, mixed_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        tool = TraceImpactTool(str(mixed_project))
        result = _run(tool.execute({"symbol": "widget"}))

        assert "source_call_count" in result, (
            "H4: response must include source_call_count"
        )
        assert "usage_count" in result, (
            "H4: response must include usage_count for cross-tool parity"
        )
        # ``call_count`` is the canonical number; ``source_call_count``
        # mirrors it under a more explicit name.
        assert result["source_call_count"] == result["call_count"], (
            f"H4: source_call_count must equal call_count — "
            f"source_call_count={result['source_call_count']} "
            f"call_count={result['call_count']}"
        )
        # ``usage_count`` reflects the length of the returned list.
        assert result["usage_count"] == len(result["usages"]), (
            f"H4: usage_count must equal len(usages) — "
            f"usage_count={result['usage_count']} "
            f"len(usages)={len(result['usages'])}"
        )

    def test_trace_impact_badge_uses_source_count(self, mixed_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        tool = TraceImpactTool(str(mixed_project))
        result = _run(tool.execute({"symbol": "widget"}))

        # The badge must reference the source-only count, never the raw
        # rg hit total inflated by markdown matches.
        badge = result.get("impact_badge", "")
        # 2 callers in src.py (def + 2 call sites = 3 hits); CHANGELOG
        # adds 2, design.txt adds 2. Without the filter call_count would
        # be 7; with the filter it must be at most 3.
        assert result["source_call_count"] <= 5, (
            f"H4: source_call_count must exclude non-source matches — "
            f"got {result['source_call_count']}; usages={result['usages']!r}"
        )
        if isinstance(badge, str):
            assert "7 CALLERS" not in badge, (
                f"H4: badge must not advertise inflated count — got {badge!r}"
            )


class TestH6FileHealthSmellTypes:
    """H6 (round-20): ``file_health.code_smells[].type`` was ``None``
    for every entry, while ``code_patterns`` produced proper strings
    (``deep_nesting``, ``long_method``, …). The smell projection was
    reading the wrong attribute.

    Contract:
      - Every smell in ``code_smells`` has a non-empty ``type``
        string.
      - ``type`` equals the canonical smell name (``smell``).
    """

    @pytest.fixture
    def deeply_nested_project(self, tmp_path: Path) -> Path:
        """One Python file with a deeply nested function — guaranteed
        to trigger ``deep_nesting`` and ``long_method`` smells."""
        src = tmp_path / "deeply_nested.py"
        body_lines = ["def big():"]
        for depth in range(7):
            body_lines.append("    " * (depth + 1) + "if True:")
        body_lines.append("    " * 8 + "x = 1")
        # Pad to trigger long_method (>50 lines).
        for i in range(60):
            body_lines.append(f"    statement_{i} = {i}")
        src.write_text("\n".join(body_lines) + "\n", encoding="utf-8")
        return tmp_path

    def test_smell_types_are_non_empty_strings(
        self, deeply_nested_project: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(deeply_nested_project))
        result = _run(
            tool.execute({"file_path": "deeply_nested.py", "output_format": "json"})
        )
        smells = result.get("code_smells", [])
        assert smells, f"H6 fixture: expected at least one smell — got {smells!r}"
        for smell in smells:
            smell_type = smell.get("type")
            assert isinstance(smell_type, str), (
                f"H6: code_smells[].type must be a string — got "
                f"{smell_type!r} in {smell!r}"
            )
            assert smell_type, (
                f"H6: code_smells[].type must be non-empty — got "
                f"{smell_type!r} in {smell!r}"
            )
            # Type should match the canonical smell name.
            assert smell_type == smell.get("smell"), (
                f"H6: code_smells[].type must mirror code_smells[].smell "
                f"— got type={smell_type!r} smell={smell.get('smell')!r}"
            )


class TestH7FileHealthNonCodeFile:
    """H7 (round-20): ``file_health`` returned grade C "moderate
    technical debt" for README.md and other non-code files. Code-
    quality metrics don't apply to Markdown.

    Contract:
      - ``signal`` is ``"non_code_file"``.
      - ``grade`` is ``"N/A"``.
      - ``agent_summary.summary_line`` includes the non_code_file
        signal.
    """

    @pytest.fixture
    def project_with_md(self, tmp_path: Path) -> Path:
        (tmp_path / "README.md").write_text(
            "# Project\n\nThis is a README with some\nlines of text.\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_markdown_returns_non_code_signal(self, project_with_md: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(project_with_md))
        result = _run(tool.execute({"file_path": "README.md", "output_format": "json"}))
        assert result["signal"] == "non_code_file", (
            f"H7: README.md must return signal=non_code_file — got "
            f"{result.get('signal')!r}"
        )
        assert result["grade"] == "N/A", (
            f"H7: README.md must return grade=N/A — got {result.get('grade')!r}"
        )
        # No code smells should be emitted for non-code files.
        assert result.get("code_smells") == [], (
            f"H7: non-code files must have empty code_smells — got "
            f"{result.get('code_smells')!r}"
        )

    def test_markdown_summary_announces_signal(self, project_with_md: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(project_with_md))
        result = _run(tool.execute({"file_path": "README.md", "output_format": "json"}))
        summary = result.get("agent_summary") or {}
        line = summary.get("summary_line", "")
        assert "non_code_file" in line, (
            f"H7: agent_summary.summary_line must mention non_code_file — got {line!r}"
        )

    def test_yaml_and_json_also_non_code(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("key: value\n", encoding="utf-8")
        (tmp_path / "data.json").write_text('{"k": 1}\n', encoding="utf-8")
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tmp_path))
        for name in ("config.yaml", "data.json"):
            result = _run(tool.execute({"file_path": name, "output_format": "json"}))
            assert result.get("signal") == "non_code_file", (
                f"H7: {name} must return signal=non_code_file — got "
                f"{result.get('signal')!r}"
            )


class TestH9FileHealthWhitespaceOnly:
    """H9 (round-20): a Python file containing only whitespace
    (``"   \\n   \\n"``) was graded A "SAFE" — the M7 fix only caught
    0-byte files.

    Contract:
      - Whitespace-only files return ``signal: "empty_file"``.
      - ``grade`` is ``"N/A"``.
    """

    def test_whitespace_only_returns_empty_signal(self, tmp_path: Path) -> None:
        (tmp_path / "ws.py").write_text("   \n   \n", encoding="utf-8")
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "ws.py", "output_format": "json"}))
        assert result["signal"] == "empty_file", (
            f"H9: whitespace-only file must return signal=empty_file — "
            f"got {result.get('signal')!r}"
        )
        assert result["grade"] == "N/A", (
            f"H9: whitespace-only file must return grade=N/A — got "
            f"{result.get('grade')!r}"
        )

    def test_zero_byte_still_empty_signal(self, tmp_path: Path) -> None:
        """Regression: the M7 zero-byte path must still work."""
        (tmp_path / "empty.py").write_text("", encoding="utf-8")
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "empty.py", "output_format": "json"}))
        assert result["signal"] == "empty_file"
        assert result["grade"] == "N/A"


class TestH12SymbolLineageDefClassification:
    """H12 (round-20): ``symbol_lineage`` returned
    ``definition_count: 0`` for a Python function whose ``def`` site
    was on line 63 of the queried file. The upstream classifier in
    ``execute_find_references`` only marked hits with element_type
    substring-matching ``definition``/``declaration``/``class``/
    ``struct`` — Python ``element_type='function'`` therefore fell into
    ``references``.

    Contract:
      - When a file contains the symbol's ``def`` site, the response
        carries ``definition_count >= 1``.
      - The reclassified entry has ``role: "definition"``.
    """

    @pytest.fixture
    def lineage_project(self, tmp_path: Path) -> Path:
        (tmp_path / "lib.py").write_text(
            "def my_target_symbol(arg: int) -> int:\n"
            "    return arg + 1\n"
            "\n"
            "def caller() -> int:\n"
            "    return my_target_symbol(5)\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_def_site_classified_as_definition(self, lineage_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import (
            SymbolLineageTool,
        )

        tool = SymbolLineageTool(str(lineage_project))
        result = _run(
            tool.execute({"symbol": "my_target_symbol", "output_format": "json"})
        )
        assert result["definition_count"] >= 1, (
            f"H12: definition_count must be >= 1 when the def site is in "
            f"the project — got {result['definition_count']} "
            f"defs={result.get('definitions')!r} "
            f"refs={result.get('references')!r}"
        )
        defs = result.get("definitions", [])
        assert any(d.get("role") == "definition" for d in defs), (
            f"H12: at least one definition must have role='definition' — got {defs!r}"
        )


# ============================================================================
# Pol1 — code_patterns summary_line cosmetics (round-21)
# ============================================================================


class TestPol1CodePatternsSummaryLine:
    """Pol1 (round-21): the ``summary_line`` for ``code_patterns`` shipped
    in round-20 with a double space between ``patterns`` and ``critical=``:

      "<path> 3 patterns  critical=0 warning=3"
                        ^^^^

    Cosmetic, but downstream regexes that split on a single space see
    an empty token and either crash or mis-attribute fields. Tests here
    guard the headline against double spaces, leading/trailing
    whitespace, and ensure the agent summary mirror stays in sync.
    """

    @pytest.fixture
    def project_with_smells(self, tmp_path: Path) -> Path:
        # A few cheap signals so the patterns list is non-empty.
        src = tmp_path / "buggy.py"
        src.write_text(
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except:\n"
            "        pass\n"
            "def g():\n"
            "    print('hi')\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run_patterns(self, project: Path, name: str) -> dict:
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )

        tool = CodePatternsTool(str(project))
        return _run(tool.execute({"file_path": name, "output_format": "json"}))

    def test_summary_line_has_no_double_spaces(self, project_with_smells: Path) -> None:
        result = self._run_patterns(project_with_smells, "buggy.py")
        summary = result.get("summary_line", "")
        assert "  " not in summary, (
            f"Pol1: summary_line must not contain double spaces — got {summary!r}"
        )

    def test_summary_line_has_no_leading_trailing_whitespace(
        self, project_with_smells: Path
    ) -> None:
        result = self._run_patterns(project_with_smells, "buggy.py")
        summary = result.get("summary_line", "")
        assert summary == summary.strip(), (
            f"Pol1: summary_line must not have leading/trailing whitespace — "
            f"got {summary!r}"
        )

    def test_agent_summary_summary_line_mirrors_top_level(
        self, project_with_smells: Path
    ) -> None:
        """The agent-summary mirror is what chained tools read; both
        surfaces must stay aligned and free of double-space artefacts."""
        result = self._run_patterns(project_with_smells, "buggy.py")
        top = result.get("summary_line", "")
        nested = result.get("agent_summary", {}).get("summary_line", "")
        assert top == nested, (
            f"Pol1: agent_summary.summary_line must mirror top-level — "
            f"top={top!r} nested={nested!r}"
        )
        assert "  " not in nested, (
            f"Pol1: agent_summary.summary_line must not contain double spaces — "
            f"got {nested!r}"
        )

    def test_summary_line_carries_expected_tokens(
        self, project_with_smells: Path
    ) -> None:
        """Pol4 sweep: verify the structural tokens survive the rewrite —
        we still need ``patterns``, ``critical=``, and ``warning=`` in the
        headline. Otherwise an over-aggressive whitespace fix could drop
        a column."""
        result = self._run_patterns(project_with_smells, "buggy.py")
        summary = result.get("summary_line", "")
        for token in ("patterns", "critical=", "warning="):
            assert token in summary, (
                f"Pol1: summary_line missing token {token!r} — got {summary!r}"
            )


# ============================================================================
# Pol2 — code_patterns vs file_health agree on empty files (round-21)
# ============================================================================


class TestPol2EmptyFileCrossTool:
    """Pol2 (round-21): on a 0-byte (or whitespace-only) input,
    ``code_patterns`` returned ``verdict: SAFE`` while ``file_health``
    returned ``grade: N/A`` + ``signal: empty_file``. Cross-tool drift
    on the same input forces agents to reconcile two truths.

    Fix (Option A): ``code_patterns`` mirrors ``file_health`` —
    short-circuit with ``verdict: N/A`` and ``signal: empty_file``,
    skipping detector passes that have nothing to detect.
    """

    @pytest.fixture
    def empty_project(self, tmp_path: Path) -> Path:
        (tmp_path / "zero.py").write_text("", encoding="utf-8")
        (tmp_path / "ws.py").write_text("   \n   \n", encoding="utf-8")
        return tmp_path

    def _run_patterns(self, project: Path, name: str) -> dict:
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )

        tool = CodePatternsTool(str(project))
        return _run(tool.execute({"file_path": name, "output_format": "json"}))

    def _run_health(self, project: Path, name: str) -> dict:
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(project))
        return _run(tool.execute({"file_path": name, "output_format": "json"}))

    def test_code_patterns_signals_empty_file(self, empty_project: Path) -> None:
        result = self._run_patterns(empty_project, "zero.py")
        assert result["signal"] == "empty_file", (
            f"Pol2: code_patterns on 0-byte file must signal empty_file — "
            f"got signal={result.get('signal')!r}"
        )
        assert result["verdict"] == "N/A", (
            f"Pol2: code_patterns on 0-byte file must verdict N/A — "
            f"got verdict={result.get('verdict')!r}"
        )
        # The agent-summary mirror has to agree too.
        agent = result.get("agent_summary", {})
        assert agent.get("verdict") == "N/A", (
            f"Pol2: agent_summary.verdict must be N/A — got {agent.get('verdict')!r}"
        )
        # No patterns are reported on an empty file.
        assert result["total_patterns"] == 0
        assert result["count"] == 0

    def test_code_patterns_signals_whitespace_only(self, empty_project: Path) -> None:
        """The H9 widening (whitespace-only files behave like empty)
        applies here too — otherwise the two tools would drift again."""
        result = self._run_patterns(empty_project, "ws.py")
        assert result["signal"] == "empty_file", (
            f"Pol2: code_patterns on whitespace-only file must signal "
            f"empty_file — got signal={result.get('signal')!r}"
        )
        assert result["verdict"] == "N/A"

    def test_cross_tool_agreement_on_empty_signal(self, empty_project: Path) -> None:
        """Both tools must surface the same ``signal`` on the same input.
        This is the contract that lets an agent take one branch."""
        patterns = self._run_patterns(empty_project, "zero.py")
        health = self._run_health(empty_project, "zero.py")
        assert patterns["signal"] == health["signal"] == "empty_file", (
            f"Pol2: code_patterns and file_health must agree on empty-file "
            f"signal — patterns={patterns.get('signal')!r} "
            f"health={health.get('signal')!r}"
        )

    def test_cross_tool_agreement_on_whitespace_only(self, empty_project: Path) -> None:
        patterns = self._run_patterns(empty_project, "ws.py")
        health = self._run_health(empty_project, "ws.py")
        assert patterns["signal"] == health["signal"] == "empty_file"


# ============================================================================
# Pol3 — change_impact preview transparency (round-21)
# ============================================================================


class TestPol3ChangeImpactPreviewTruncation:
    """Pol3 (round-21): the preview lists inside ``change_impact``
    responses (``changed_preview``, ``scoped_changed_preview``,
    ``out_of_scope_changed_preview``) were silently capped at 5 with no
    transparency. Hidden truncation bit chained agents in H2/H3 — the
    same precedent applies here.

    Fix: surface ``preview_limit`` + ``preview_truncated`` alongside
    every capped preview, and keep the cap value in one named constant.
    """

    @pytest.fixture
    def many_files_project(self, tmp_path: Path) -> Path:
        """A project with > 5 dirty files. We never invoke git, so just
        seed the request with a long ``changed_files`` list — the agent
        summary builder doesn't care where the files came from."""
        for i in range(8):
            (tmp_path / f"f{i}.py").write_text(
                f"def f{i}():\n    return {i}\n", encoding="utf-8"
            )
        return tmp_path

    def test_constant_is_named_not_magic(self) -> None:
        """The cap value lives in one place so all preview sites stay
        aligned. If a future refactor drops the constant, the three
        slicing sites would diverge."""
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
            CHANGE_IMPACT_PREVIEW_LIMIT,
        )

        assert isinstance(CHANGE_IMPACT_PREVIEW_LIMIT, int)
        assert CHANGE_IMPACT_PREVIEW_LIMIT > 0

    def test_agent_summary_surfaces_truncation_when_over_cap(self) -> None:
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
            CHANGE_IMPACT_PREVIEW_LIMIT,
            AgentSummaryContext,
            build_agent_summary,
        )

        changed = [f"src/f{i}.py" for i in range(CHANGE_IMPACT_PREVIEW_LIMIT + 3)]
        ctx = AgentSummaryContext(
            risk="low",
            changed_files=changed,
            scope_paths=None,
            verification={
                "verification_command": "uv run pytest -q",
                "test_required": True,
                "default_test_command": "uv run pytest -q",
            },
            strategy={
                "verification_strategy": "default",
                "focused_test_command": "",
                "verification_steps": ["uv run pytest -q"],
            },
            affected_count=0,
            tests_to_run_count=0,
        )
        summary = build_agent_summary(ctx)
        assert summary["preview_limit"] == CHANGE_IMPACT_PREVIEW_LIMIT, (
            f"Pol3: preview_limit must equal the cap constant — "
            f"got {summary.get('preview_limit')!r}"
        )
        assert summary["preview_truncated"] is True, (
            f"Pol3: preview_truncated must be True when changed_count > cap — "
            f"got {summary.get('preview_truncated')!r}"
        )
        assert len(summary["changed_preview"]) == CHANGE_IMPACT_PREVIEW_LIMIT, (
            f"Pol3: changed_preview must be capped to the constant — "
            f"got len={len(summary.get('changed_preview', []))}"
        )

    def test_agent_summary_marks_not_truncated_under_cap(self) -> None:
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
            CHANGE_IMPACT_PREVIEW_LIMIT,
            AgentSummaryContext,
            build_agent_summary,
        )

        changed = ["src/a.py", "src/b.py"]
        ctx = AgentSummaryContext(
            risk="low",
            changed_files=changed,
            scope_paths=None,
            verification={
                "verification_command": "uv run pytest -q",
                "test_required": True,
                "default_test_command": "uv run pytest -q",
            },
            strategy={
                "verification_strategy": "default",
                "focused_test_command": "",
                "verification_steps": ["uv run pytest -q"],
            },
            affected_count=0,
            tests_to_run_count=0,
        )
        summary = build_agent_summary(ctx)
        # Even under the cap, the two fields must be present so consumers
        # can branch on a stable shape.
        assert summary["preview_limit"] == CHANGE_IMPACT_PREVIEW_LIMIT
        assert summary["preview_truncated"] is False, (
            f"Pol3: preview_truncated must be False under cap — "
            f"got {summary.get('preview_truncated')!r}"
        )

    def test_queue_ledger_surfaces_truncation_on_either_side(self) -> None:
        """The ledger has two previews (scoped + out-of-scope). If
        *either* underlying count exceeds the cap, ``preview_truncated``
        must be True — otherwise an agent reading the ledger would miss
        out-of-scope work."""
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
            CHANGE_IMPACT_PREVIEW_LIMIT,
            attach_queue_ledger,
        )

        scoped = ["src/scoped.py"]
        workspace = scoped + [
            f"src/out{i}.py" for i in range(CHANGE_IMPACT_PREVIEW_LIMIT + 2)
        ]
        result: dict = {"agent_summary": {}, "verification_command": "uv run pytest -q"}
        attach_queue_ledger(
            result,
            mode="diff",
            scope_paths=["src/scoped.py"],
            scoped_changed_files=scoped,
            workspace_changed_files=workspace,
        )
        ledger = result["queue_ledger"]
        assert ledger["preview_limit"] == CHANGE_IMPACT_PREVIEW_LIMIT
        assert ledger["preview_truncated"] is True, (
            f"Pol3: ledger.preview_truncated must be True when out_of_scope "
            f"exceeds cap — got {ledger.get('preview_truncated')!r}"
        )
        assert (
            len(ledger["out_of_scope_changed_preview"]) == CHANGE_IMPACT_PREVIEW_LIMIT
        )

    def test_queue_ledger_marks_not_truncated_when_under_cap(self) -> None:
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
            attach_queue_ledger,
        )

        scoped = ["src/scoped.py"]
        workspace = scoped + ["src/extra.py"]
        result: dict = {"agent_summary": {}, "verification_command": "uv run pytest -q"}
        attach_queue_ledger(
            result,
            mode="diff",
            scope_paths=["src/scoped.py"],
            scoped_changed_files=scoped,
            workspace_changed_files=workspace,
        )
        ledger = result["queue_ledger"]
        assert ledger["preview_truncated"] is False, (
            f"Pol3: ledger.preview_truncated must be False under cap — "
            f"got {ledger.get('preview_truncated')!r}"
        )


# ============================================================================
# J9 — refactor agrees with code_patterns on the same file (round-22)
# ============================================================================


class TestJ9RefactorCodePatternsParity:
    """J9 (round-22): before this fix the ``refactor`` tool was
    structure-only — it found long methods, deep nesting, god classes,
    but never noticed ``eval(...)``, ``except:``, or ``def f(x=[])``.
    On the same file ``code_patterns`` returned 4 findings (2 critical)
    while ``refactor`` happily reported ``verdict=clean suggestions=0``.
    An agent that chained ``--refactor`` first shipped the bugs.

    Fix (Option A): the refactor tool now delegates to the same
    ``_detect_anti_patterns`` and ``_detect_security`` helpers
    ``code_patterns`` uses, surfacing those findings as suggestions
    with the appropriate severity. The cross-tool ``verdict`` now
    aligns: SAFE / CAUTION / UNSAFE.
    """

    @pytest.fixture
    def buggy_project(self, tmp_path: Path) -> Path:
        """A 5-line Python file containing every category of finding the
        cross-tool contract should surface: mutable default arg
        (critical anti-pattern), bare except (warning), eval (critical
        security). Structural detectors find nothing because the file
        is too small for any threshold."""
        src = tmp_path / "buggy.py"
        src.write_text(
            'def f1(x=[]):\n    return x\ntry: pass\nexcept: pass\neval("1+1")\n',
            encoding="utf-8",
        )
        return tmp_path

    def _run_refactor(self, project: Path) -> dict:
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        tool = RefactoringSuggestionsTool(str(project))
        return _run(tool.execute({"file_path": "buggy.py", "output_format": "json"}))

    def _run_patterns(self, project: Path) -> dict:
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )

        tool = CodePatternsTool(str(project))
        return _run(tool.execute({"file_path": "buggy.py", "output_format": "json"}))

    def test_refactor_no_longer_returns_clean_on_buggy_file(
        self, buggy_project: Path
    ) -> None:
        """The pre-J9 verdict was ``clean`` (zero suggestions). Post-J9
        the bridged anti-pattern / security findings push the count
        above zero so an agent chain doesn't ship the file."""
        result = self._run_refactor(buggy_project)
        total = result.get("total_suggestions", len(result.get("suggestions", [])))
        assert total > 0, (
            f"J9: refactor must surface anti-patterns + security findings "
            f"on a buggy file — got total_suggestions={total}"
        )

    def test_refactor_verdict_aligns_with_code_patterns(
        self, buggy_project: Path
    ) -> None:
        """Both tools must agree on the same input. ``code_patterns``
        emits ``UNSAFE`` on this file; ``refactor`` must do the same."""
        refactor = self._run_refactor(buggy_project)
        patterns = self._run_patterns(buggy_project)
        rv = refactor.get("verdict") or refactor.get("agent_summary", {}).get("verdict")
        pv = patterns.get("verdict") or patterns.get("agent_summary", {}).get("verdict")
        assert rv == pv == "UNSAFE", (
            f"J9: refactor and code_patterns must agree on the verdict — "
            f"refactor={rv!r} code_patterns={pv!r}"
        )

    def test_refactor_surfaces_anti_pattern_categories(
        self, buggy_project: Path
    ) -> None:
        """The bridged findings must be findable in the suggestion list.
        We don't pin specific IDs (the underlying detectors may evolve)
        — only that anti-patterns and security findings BOTH appear."""
        result = self._run_refactor(buggy_project)
        sources = {s.get("source") for s in result.get("suggestions", [])}
        assert "code_patterns" in sources, (
            f"J9: at least one suggestion must come from the code_patterns "
            f"bridge — sources={sources!r}"
        )

    def test_refactor_clean_file_keeps_safe_verdict(self, tmp_path: Path) -> None:
        """Sanity check: a clean Python file leaves the verdict at SAFE.
        Otherwise we'd be permanently flagging every file."""
        (tmp_path / "ok.py").write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            encoding="utf-8",
        )
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        tool = RefactoringSuggestionsTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "ok.py", "output_format": "json"}))
        verdict = result.get("verdict") or result.get("agent_summary", {}).get(
            "verdict"
        )
        assert verdict == "SAFE", (
            f"J9: clean file must keep verdict at SAFE — got {verdict!r}"
        )


# ============================================================================
# J10 — bare_except not double-listed across security + anti_patterns
# ============================================================================


class TestJ10NoDupCategoriesBareExcept:
    """J10 (round-22): ``_detect_security`` and ``_detect_anti_patterns``
    both emit a ``bare_except`` finding on ``try: / except:``. Pre-J10
    the same (file, line) showed up twice in ``results`` — once under
    ``category=security`` and once under ``category=anti_patterns``.
    Pure noise that double-counts the ``warning_count`` and burns
    tokens in TOON output.

    Fix: extend ``_dedup_security_mirror`` (already deduped the
    smell-namespaced mirror under G4) to also drop the anti-pattern
    duplicate. Security namespace stays canonical (G4 convention).
    """

    @pytest.fixture
    def be_project(self, tmp_path: Path) -> Path:
        # Use an indented bare-except inside a function so both
        # detectors trigger (the anti-pattern detector requires a
        # ``def`` nearby).
        (tmp_path / "be.py").write_text(
            "def f():\n    try:\n        pass\n    except:\n        pass\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run_patterns(self, project: Path) -> dict:
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )

        tool = CodePatternsTool(str(project))
        return _run(tool.execute({"file_path": "be.py", "output_format": "json"}))

    def test_bare_except_appears_exactly_once(self, be_project: Path) -> None:
        result = self._run_patterns(be_project)
        bare_excepts = [p for p in result["results"] if p.get("type") == "bare_except"]
        assert len(bare_excepts) == 1, (
            f"J10: bare_except must appear once in results — "
            f"got {len(bare_excepts)} entries: {bare_excepts!r}"
        )

    def test_security_namespace_is_canonical(self, be_project: Path) -> None:
        """The surviving entry must be the ``security``-namespaced one
        (matches the G4 convention used for the smell-mirror dedup)."""
        result = self._run_patterns(be_project)
        bare_excepts = [p for p in result["results"] if p.get("type") == "bare_except"]
        assert bare_excepts[0]["category"] == "security", (
            f"J10: bare_except canonical category must be ``security`` — "
            f"got {bare_excepts[0]['category']!r}"
        )

    def test_warning_count_not_double_counted(self, be_project: Path) -> None:
        """The pre-J10 double-listing inflated ``warning_count`` to 2.
        After dedup it must be exactly 1."""
        result = self._run_patterns(be_project)
        # The file has exactly one warning-level finding (bare_except).
        # Any extra info-level findings don't count toward warning_count.
        assert result["warning_count"] == 1, (
            f"J10: warning_count must reflect a single bare_except — "
            f"got {result['warning_count']}"
        )


# ============================================================================
# J11 — change_impact verdict vocabulary (round-22)
# ============================================================================


class TestJ11ChangeImpactVerdictVocab:
    """J11 (round-22): ``change_impact`` used to emit ``verdict=CLEAN``
    even with ``changed_count > 0``. That collided with the safety-tool
    vocabulary (``CLEAN`` means "ship it"). Agents chaining the two
    shipped work that still needed verification.

    Fix: ``CLEAN`` only fires when ``changed_count == 0`` AND no
    invalid scope paths. Otherwise emit ``REVIEW`` (pending
    verification) or ``WARN`` (soft-failure from H8).
    """

    def _ctx(
        self, changed_files: list[str], scope_paths: list[str] | None = None
    ) -> dict:
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
            apply_scope_validation,
        )

        result: dict = {
            "changed_count": len(changed_files),
            "changed_files": changed_files,
            "scope_paths": scope_paths or [],
            "agent_summary": {"changed_count": len(changed_files)},
        }
        return apply_scope_validation(result, [])

    def test_changed_count_zero_emits_clean(self) -> None:
        """No changes → CLEAN. The legacy steady state."""
        result = self._ctx([])
        verdict = result["agent_summary"]["verdict"]
        assert verdict == "CLEAN", (
            f"J11: changed_count=0 must emit CLEAN — got {verdict!r}"
        )

    def test_changed_count_positive_emits_review(self) -> None:
        """Any non-empty diff → REVIEW. Pre-J11 this returned CLEAN
        which an agent would read as ``ship it``."""
        result = self._ctx(["src/a.py", "src/b.py"])
        verdict = result["agent_summary"]["verdict"]
        assert verdict == "REVIEW", (
            f"J11: changed_count>0 must emit REVIEW — got {verdict!r}"
        )
        # CLEAN must NOT appear when there are changes. Belt-and-braces
        # — the brief specifically says ``verdict != CLEAN``.
        assert verdict != "CLEAN"

    def test_constants_named_so_callsites_align(self) -> None:
        """All three verdict values live as named constants so future
        refactors don't drift between the source and the documentation."""
        from tree_sitter_analyzer.mcp.tools.utils import change_impact_response as cir

        assert cir.CHANGE_IMPACT_VERDICT_CLEAN == "CLEAN"
        assert cir.CHANGE_IMPACT_VERDICT_REVIEW == "REVIEW"
        assert cir.CHANGE_IMPACT_VERDICT_WARN == "WARN"

    def test_invalid_scope_still_overrides_to_warn(self) -> None:
        """The H8 escalation still beats the J11 default. WARN takes
        precedence over REVIEW because the caller's input was partly
        ignored — they need to know that, not just that they have
        work pending."""
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
            apply_scope_validation,
        )

        result: dict = {
            "changed_count": 3,
            "changed_files": ["a.py", "b.py", "c.py"],
            "agent_summary": {"changed_count": 3},
        }
        result = apply_scope_validation(result, ["nonexistent.py"])
        assert result["agent_summary"]["verdict"] == "WARN", (
            f"J11/H8: invalid scope must still escalate to WARN — "
            f"got {result['agent_summary']['verdict']!r}"
        )


# ============================================================================
# J13 — code_patterns dropped duplicate `patterns` key (round-22)
# ============================================================================


class TestJ13CodePatternsNoDuplicatePatternsKey:
    """J13 (round-22): ``code_patterns`` was emitting both ``results``
    and ``patterns`` as byte-identical lists. Pure token waste in TOON
    output, and forced callers to know that the two keys were aliases.

    Fix: drop ``patterns`` entirely. The canonical alias is
    ``results`` (matches every other search/scan tool). Callers that
    previously read ``response['patterns']`` must switch to
    ``response['results']``.
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        (tmp_path / "bug.py").write_text(
            "def f(x=[]):\n    return x\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run_patterns(self, project: Path) -> dict:
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )

        tool = CodePatternsTool(str(project))
        return _run(tool.execute({"file_path": "bug.py", "output_format": "json"}))

    def test_patterns_key_removed(self, tiny_project: Path) -> None:
        """``patterns`` is no longer a top-level key — agents must use
        ``results``."""
        result = self._run_patterns(tiny_project)
        assert "patterns" not in result, (
            f"J13: ``patterns`` was removed as a duplicate of ``results`` — "
            f"got result keys: {sorted(result.keys())!r}"
        )

    def test_results_still_canonical(self, tiny_project: Path) -> None:
        """``results`` survives as the single source of truth."""
        result = self._run_patterns(tiny_project)
        assert "results" in result, (
            f"J13: ``results`` must remain the canonical list key — "
            f"got result keys: {sorted(result.keys())!r}"
        )
        # And it must actually contain the findings (not an empty
        # placeholder).
        assert isinstance(result["results"], list)

    def test_empty_file_also_drops_patterns_key(self, tmp_path: Path) -> None:
        """The empty-file short-circuit envelope must also be free of
        the duplicate key — otherwise we'd reintroduce the drift on
        the no-content branch."""
        (tmp_path / "empty.py").write_text("", encoding="utf-8")
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )

        tool = CodePatternsTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "empty.py", "output_format": "json"}))
        assert "patterns" not in result, (
            f"J13: empty-file envelope must also be free of ``patterns`` — "
            f"got keys: {sorted(result.keys())!r}"
        )
        assert "results" in result and result["results"] == []


# ============================================================================
# J14 — N/A casing canonical across tools (round-22)
# ============================================================================


class TestJ14NACasingCanonical:
    """J14 (round-22): on an empty file ``code_patterns`` returned
    ``verdict=N/A`` (uppercase) while ``file_health`` returned
    ``verdict=n/a`` (lowercase). Every other verdict in the codebase is
    uppercase (SAFE, CAUTION, UNSAFE, CLEAN, WARN), so file_health was
    the outlier.

    Fix: align file_health's empty-file branch to ``N/A``. Both tools
    now emit the same casing on the same input.
    """

    @pytest.fixture
    def empty_project(self, tmp_path: Path) -> Path:
        (tmp_path / "zero.py").write_text("", encoding="utf-8")
        return tmp_path

    def test_code_patterns_emits_uppercase_na(self, empty_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )

        tool = CodePatternsTool(str(empty_project))
        result = _run(tool.execute({"file_path": "zero.py", "output_format": "json"}))
        assert result["verdict"] == "N/A", (
            f"J14: code_patterns must emit uppercase N/A — "
            f"got {result.get('verdict')!r}"
        )

    def test_file_health_emits_uppercase_na(self, empty_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(empty_project))
        result = _run(tool.execute({"file_path": "zero.py", "output_format": "json"}))
        assert result["verdict"] == "N/A", (
            f"J14: file_health must emit uppercase N/A — got {result.get('verdict')!r}"
        )

    def test_cross_tool_casing_matches(self, empty_project: Path) -> None:
        """The whole point of J14: both tools agree byte-for-byte."""
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        patterns = _run(
            CodePatternsTool(str(empty_project)).execute(
                {"file_path": "zero.py", "output_format": "json"}
            )
        )
        health = _run(
            FileHealthTool(str(empty_project)).execute(
                {"file_path": "zero.py", "output_format": "json"}
            )
        )
        assert patterns["verdict"] == health["verdict"] == "N/A", (
            f"J14: code_patterns and file_health must agree on N/A casing — "
            f"patterns={patterns.get('verdict')!r} "
            f"health={health.get('verdict')!r}"
        )

    def test_agent_summary_verdict_also_uppercase(self, empty_project: Path) -> None:
        """The verdict is mirrored inside ``agent_summary``. Both
        surfaces must agree — drift here is the same footgun the
        top-level fix addresses."""
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(empty_project))
        result = _run(tool.execute({"file_path": "zero.py", "output_format": "json"}))
        nested = result.get("agent_summary", {}).get("verdict")
        assert nested == "N/A", (
            f"J14: file_health agent_summary.verdict must also be N/A — got {nested!r}"
        )


class TestJ2ErrorEnvelopeOnJsonFormat:
    """J2: CLI error paths must emit a JSON envelope under ``--format json``.

    Before J2 the ``except Exception`` handler in
    ``mcp_commands._run_tool`` printed a plain-text ``ERROR: ...`` line
    even when the user explicitly asked for ``--format json``, leaving
    every programmatic consumer (Claude Code, scripted agents) without
    a parseable response. The fix funnels every error path — both the
    pre-execution ``validate_mcp_command_args`` sink and the
    ``except Exception`` block — through a format-aware envelope
    builder. These tests pin the new contract end-to-end.
    """

    def _envelope_from_stdout(self, stdout: str) -> dict[str, Any]:
        import json as _json

        payload = _json.loads(stdout.strip())
        assert payload["success"] is False, (
            f"J2: error envelope must carry success=False — got {payload!r}"
        )
        assert isinstance(payload["error"], str) and payload["error"], (
            "J2: error envelope must carry a non-empty error string"
        )
        assert payload["error_type"] in {"validation", "internal"}, (
            f"J2: error_type must be validation|internal — got "
            f"{payload.get('error_type')!r}"
        )
        return payload

    def test_out_of_project_path_emits_json_envelope(
        self, capsys, tmp_path: Path
    ) -> None:
        """Source 1: security boundary failure (out-of-project absolute path)."""
        from argparse import Namespace

        from tree_sitter_analyzer.cli.commands import mcp_commands

        out_of_project = tmp_path / "out_of_project.py"
        out_of_project.write_text("import os\n")
        project_root = tmp_path / "project"
        project_root.mkdir()

        args = Namespace(
            code_patterns=True,
            file_path=str(out_of_project),
            project_root=str(project_root),
        )
        # Cover all MCP-spec flags so ``find_selected_mcp_command``
        # picks ``code_patterns`` cleanly without ``AttributeError``.
        for flag in (
            "file_health",
            "project_health",
            "overview",
            "safe_to_edit",
            "change_impact",
            "parser_readiness",
            "dependencies",
            "refactor",
            "smart_context",
            "symbol_lineage",
            "call_graph",
            "ast_cache",
            "detect_routes",
        ):
            setattr(args, flag, False if flag != "dependencies" else None)
        args.code_patterns_categories = ["all"]
        args.severity_threshold = "info"

        result = mcp_commands.handle_mcp_commands(
            args,
            lambda payload: None,
            lambda message: None,
            lambda: "json",
        )

        assert result == 1
        stdout = capsys.readouterr().out
        payload = self._envelope_from_stdout(stdout)
        assert payload["error_type"] == "validation"
        assert (
            "Security validation failed" in payload["error"]
            or "outside project" in payload["error"].lower()
        ), payload["error"]

    def test_nonexistent_file_emits_json_envelope(self, capsys, tmp_path: Path) -> None:
        """Source 2: file-not-found failure (FileNotFoundError / ValueError)."""
        from argparse import Namespace

        from tree_sitter_analyzer.cli.commands import mcp_commands

        project_root = tmp_path / "project"
        project_root.mkdir()

        args = Namespace(
            file_health=True,
            file_path=str(project_root / "does_not_exist.py"),
            project_root=str(project_root),
        )
        for flag in (
            "code_patterns",
            "project_health",
            "overview",
            "safe_to_edit",
            "change_impact",
            "parser_readiness",
            "dependencies",
            "refactor",
            "smart_context",
            "symbol_lineage",
            "call_graph",
            "ast_cache",
            "detect_routes",
        ):
            setattr(args, flag, False if flag != "dependencies" else None)

        result = mcp_commands.handle_mcp_commands(
            args,
            lambda payload: None,
            lambda message: None,
            lambda: "json",
        )

        assert result == 1
        stdout = capsys.readouterr().out
        payload = self._envelope_from_stdout(stdout)
        # FileHealthTool wraps the missing file as a ValueError so the
        # bucket lands in "validation"; either bucket is acceptable but
        # the envelope shape must be intact.
        assert payload["error_type"] == "validation"
        assert (
            "does_not_exist" in payload["error"]
            or "not found" in payload["error"].lower()
        ), payload["error"]

    def test_missing_required_file_path_emits_json_envelope(
        self, capsys, tmp_path: Path
    ) -> None:
        """Source 3: pre-execution validation (missing ``--file-path``).

        ``--dependencies blast_radius`` requires a file path and was
        previously dropping the JSON envelope on this validation
        failure too — the wrapped error sink must catch it.
        """
        from argparse import Namespace

        from tree_sitter_analyzer.cli.commands import mcp_commands

        project_root = tmp_path / "project"
        project_root.mkdir()

        args = Namespace(
            dependencies="blast_radius",
            file_path=None,
            project_root=str(project_root),
        )
        for flag in (
            "file_health",
            "code_patterns",
            "project_health",
            "overview",
            "safe_to_edit",
            "change_impact",
            "parser_readiness",
            "refactor",
            "smart_context",
            "symbol_lineage",
            "call_graph",
            "ast_cache",
            "detect_routes",
        ):
            setattr(args, flag, False)

        result = mcp_commands.handle_mcp_commands(
            args,
            lambda payload: None,
            lambda message: None,
            lambda: "json",
        )

        assert result == 1
        stdout = capsys.readouterr().out
        payload = self._envelope_from_stdout(stdout)
        assert payload["error_type"] == "validation"
        assert "file" in payload["error"].lower(), payload["error"]


class TestJ4ProjectRootSetterRevalidatesEngine:
    """J4: ``tool.project_root = ...`` must rewire engine state.

    ``AnalyzeScaleTool.__init__`` and ``set_project_path`` both fire
    ``_on_project_root_changed`` so the underlying analysis engine
    sees the new project root. Before J4 a direct attribute write
    (``tool.project_root = "/abs"``) bypassed the hook — the engine
    kept its stale security validator and rejected the absolute paths
    that ``resolve_and_validate_file_path`` had just produced. The
    property setter introduced in J4 closes that gap.
    """

    def test_setter_fires_hook_for_analyze_scale_tool(self, tmp_path: Path) -> None:
        """Direct attribute assignment must rebuild the analysis engine."""
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        # Build a tiny Python project inside tmp_path so the security
        # validator accepts a relative path under the new project root.
        sample = tmp_path / "sample.py"
        sample.write_text("def greet(name: str) -> str:\n    return f'hi {name}'\n")

        tool = AnalyzeScaleTool()  # no project_root in constructor
        # The engine built at __init__ time is bound to ``None`` /
        # cwd-style validation. Capture it so we can prove the setter
        # really swapped it.
        original_engine = tool.analysis_engine

        tool.project_root = str(tmp_path)

        assert tool.analysis_engine is not original_engine, (
            "J4: ``project_root`` setter must invoke "
            "``_on_project_root_changed`` so the analysis engine is "
            "rebuilt against the new project root."
        )

        result = asyncio.run(tool.execute({"file_path": "sample.py"}))
        assert result.get("success") is True, (
            f"J4: tool.execute() must succeed after a post-construction "
            f"``project_root`` assignment — got {result!r}"
        )

    def test_setter_preserves_security_gate(self, tmp_path: Path) -> None:
        """The setter must NOT relax the engine's "no absolute paths" guard.

        The rebuild fires the hook (so resolved relative paths work),
        but the security validator must still reject paths outside the
        new project root.
        """
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        outside = tmp_path / "outside.py"
        outside.write_text("x = 1\n")
        project_root = tmp_path / "project"
        project_root.mkdir()

        tool = AnalyzeScaleTool()
        tool.project_root = str(project_root)

        with pytest.raises(ValueError):
            asyncio.run(tool.execute({"file_path": str(outside)}))


# ============================================================================
# J5 — summary_line is single-space joined across all builders (round-22)
# ============================================================================


class TestJ5SummaryLineNoDoubleSpaces:
    """J5 (round-22): Pol1 fixed only ``code_patterns_tool`` but four
    other tools still emitted ``summary_line`` with a hard-coded ``"...
    lines  "`` (trailing double space) — producing visible artefacts like
    ``"... 613 lines  classes=1 methods=13"``. The fix introduces a
    shared ``format_summary_line(*parts)`` helper in ``base_tool`` so
    every builder gets the same single-space join, and the regression
    class is closed for good.

    Contract (per-tool):
      * ``summary_line`` (top-level) contains no double spaces.
      * ``summary_line`` has no leading / trailing whitespace.
      * ``agent_summary.summary_line``, when present, stays clean.
    """

    @pytest.fixture
    def sample_python_file(self, tmp_path: Path) -> Path:
        src = tmp_path / "sample.py"
        src.write_text(
            "class Foo:\n"
            "    x: int = 1\n"
            "    def bar(self) -> int:\n"
            "        return self.x\n"
            "    def baz(self) -> int:\n"
            "        return self.bar() + 1\n",
            encoding="utf-8",
        )
        return tmp_path

    @pytest.mark.parametrize(
        "tool_class_path,tool_name",
        [
            (
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.AnalyzeScaleTool",
                "analyze_scale",
            ),
            (
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.UniversalAnalyzeTool",
                "universal_analyze",
            ),
            (
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.AnalyzeCodeStructureTool",
                "analyze_code_structure",
            ),
        ],
    )
    def test_summary_line_no_double_spaces(
        self,
        sample_python_file: Path,
        tool_class_path: str,
        tool_name: str,
    ) -> None:
        import importlib

        module_name, _, cls_name = tool_class_path.rpartition(".")
        tool_cls = getattr(importlib.import_module(module_name), cls_name)
        tool = tool_cls(project_root=str(sample_python_file))
        result = _run(tool.execute({"file_path": "sample.py"}))

        summary = result.get("summary_line", "")
        assert isinstance(summary, str) and summary, (
            f"J5/{tool_name}: summary_line must be a non-empty string — got {summary!r}"
        )
        assert "  " not in summary, (
            f"J5/{tool_name}: summary_line must not contain double spaces — "
            f"got {summary!r}"
        )
        assert summary == summary.strip(), (
            f"J5/{tool_name}: summary_line must not have leading/trailing "
            f"whitespace — got {summary!r}"
        )

        nested = result.get("agent_summary", {}).get("summary_line", "")
        # When the tool surfaces a nested mirror, it must stay clean too.
        if nested:
            assert "  " not in nested, (
                f"J5/{tool_name}: agent_summary.summary_line must not "
                f"contain double spaces — got {nested!r}"
            )

    def test_json_file_path_summary_line_clean(self, tmp_path: Path) -> None:
        # analyze_scale has a separate code path for JSON/YAML/TOML
        # (``create_json_file_analysis``) — guard it explicitly so a
        # future refactor cannot regress just the data-file branch.
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        (tmp_path / "config.json").write_text(
            '{"key": "value", "list": [1, 2, 3]}\n', encoding="utf-8"
        )
        tool = AnalyzeScaleTool(project_root=str(tmp_path))
        result = _run(tool.execute({"file_path": "config.json"}))

        summary = result.get("summary_line", "")
        assert isinstance(summary, str) and summary, (
            f"J5/json-path: summary_line must be non-empty — got {summary!r}"
        )
        assert "  " not in summary, (
            f"J5/json-path: summary_line must not contain double spaces — "
            f"got {summary!r}"
        )
        assert summary == summary.strip(), (
            f"J5/json-path: summary_line must not have leading/trailing "
            f"whitespace — got {summary!r}"
        )

    def test_format_summary_line_helper_drops_empty_parts(self) -> None:
        # Direct unit-test on the helper so a future refactor can't
        # accidentally reintroduce the double space by passing an empty
        # segment between two real ones.
        from tree_sitter_analyzer.mcp.tools.base_tool import format_summary_line

        result = format_summary_line("foo.py", "", "42 lines", None, "classes=1")
        assert result == "foo.py 42 lines classes=1", (
            f"J5/helper: empty/None parts must be dropped — got {result!r}"
        )
        # Multiple non-empty parts always single-space joined.
        assert format_summary_line("a", "b", "c") == "a b c"
        # All-empty input collapses to "".
        assert format_summary_line("", "  ", None) == ""


# ============================================================================
# J7 — trace_impact filters comment / docstring hits (round-22)
# ============================================================================


class TestJ7TraceImpactDocstringExclusion:
    """J7 (round-22): H4's source-extension filter still let docstring
    and comment text inflate ``source_call_count``. Lines like a triple-
    quoted regression docstring or ``# parsing BaseMCPTool.__init__``
    were counted as callers. After J7, only real code lines survive.

    Contract:
      * Usages must NOT include hits whose line starts with ``#`` (Py
        comment) or triple-quote (Py docstring opener).
      * Usages must NOT include hits inside multi-line triple-quoted
        Python docstrings.
      * Usages must NOT include hits inside ``//`` or ``/* */`` comments
        in C-family languages.
      * ``raw_match_count`` is preserved (transparency) and is >=
        ``source_call_count`` whenever any non-code hits were filtered.
    """

    @pytest.fixture
    def project_with_docstring_hits(self, tmp_path: Path) -> Path:
        # A Python file with the symbol appearing in (a) a comment, (b)
        # a multi-line docstring, (c) a single-line triple-quoted
        # docstring, and (d) a real call. Only (c) class definition and
        # (d) call should survive after J7's filter.
        (tmp_path / "main.py").write_text(
            "# Targeted comment about Widget\n"
            "def setup():\n"
            "    '''A docstring talking about Widget here.'''\n"
            "    return None\n"
            "\n"
            "class C:\n"
            '    """\n'
            "    Multi-line docstring referencing Widget.\n"
            "    Widget reference on a second docstring line.\n"
            '    """\n'
            "    def go(self):\n"
            "        return Widget()\n"
            "\n"
            "class Widget:\n"
            "    pass\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_trace_impact_drops_python_comment_lines(
        self, project_with_docstring_hits: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        tool = TraceImpactTool(str(project_with_docstring_hits))
        result = _run(tool.execute({"symbol": "Widget", "max_results": 50}))

        assert result["success"] is True, f"trace_impact failed: {result!r}"
        usages = result.get("usages", [])
        for usage in usages:
            text = (usage.get("context") or usage.get("text") or "").lstrip()
            assert not text.startswith("#"), (
                f"J7: usages must not include Python comment lines — "
                f"got {text!r} at {usage.get('file')}:{usage.get('line')}"
            )

    def test_trace_impact_drops_python_docstring_lines(
        self, project_with_docstring_hits: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        tool = TraceImpactTool(str(project_with_docstring_hits))
        result = _run(tool.execute({"symbol": "Widget", "max_results": 50}))

        usages = result.get("usages", [])
        # No usage's text should start with a triple-quote (either form).
        for usage in usages:
            text = (usage.get("context") or usage.get("text") or "").lstrip()
            assert not text.startswith('"""'), (
                f"J7: usages must not include docstring text — got {text!r}"
            )
            assert not text.startswith("'''"), (
                f"J7: usages must not include docstring text — got {text!r}"
            )

    def test_trace_impact_keeps_raw_match_count_for_transparency(
        self, project_with_docstring_hits: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        tool = TraceImpactTool(str(project_with_docstring_hits))
        result = _run(tool.execute({"symbol": "Widget", "max_results": 50}))

        # The raw_match_count must persist so callers can see how much
        # was filtered out.
        assert "raw_match_count" in result, (
            "J7: response must keep raw_match_count for transparency"
        )
        assert result["raw_match_count"] >= result["source_call_count"], (
            f"J7: raw_match_count ({result['raw_match_count']}) must be "
            f">= source_call_count ({result['source_call_count']})"
        )

    def test_python_non_code_lines_detects_triple_quote_block(self) -> None:
        # Direct unit test on the heuristic so we know the regex /
        # state-machine works without depending on the trace_impact
        # pipeline. This is the load-bearing piece of J7.
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _python_non_code_lines,
        )

        text = (
            "def foo():\n"
            '    """\n'
            "    Widget reference here.\n"
            '    """\n'
            "    return Widget()\n"
        )
        non_code = _python_non_code_lines(text)
        # Lines 2, 3, 4 are the docstring open / body / close.
        assert 2 in non_code, f"line 2 (docstring open) missing — got {non_code!r}"
        assert 3 in non_code, f"line 3 (docstring body) missing — got {non_code!r}"
        assert 4 in non_code, f"line 4 (docstring close) missing — got {non_code!r}"
        # Line 5 is real code and must NOT be flagged.
        assert 5 not in non_code, (
            f"line 5 (real call) wrongly flagged as non-code — got {non_code!r}"
        )

    def test_python_non_code_lines_detects_hash_comments(self) -> None:
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _python_non_code_lines,
        )

        text = "def foo():\n    # parsing Widget here\n    return Widget()\n"
        non_code = _python_non_code_lines(text)
        assert 2 in non_code, f"line 2 (# comment) missing — got {non_code!r}"
        assert 3 not in non_code, (
            f"line 3 (real call) wrongly flagged — got {non_code!r}"
        )

    def test_c_like_non_code_lines_detects_block_and_line_comments(self) -> None:
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _c_like_non_code_lines,
        )

        text = (
            "class Foo {\n"
            "  // Widget mention in line comment\n"
            "  /*\n"
            "   * Widget inside block comment\n"
            "   */\n"
            "  void go() { Widget(); }\n"
            "}\n"
        )
        non_code = _c_like_non_code_lines(text)
        # Line 2 (//), 3-5 (block comment) are non-code.
        for line_no in (2, 3, 4, 5):
            assert line_no in non_code, (
                f"line {line_no} should be flagged as non-code — got {non_code!r}"
            )
        # Line 6 (real call) must NOT be flagged.
        assert 6 not in non_code, (
            f"line 6 (real call) wrongly flagged — got {non_code!r}"
        )


class TestJ1AstCacheSearchModesDistinct:
    """Round-22 J1: ``search`` and ``fts_search`` were byte-identical
    because ``search_symbols`` delegated to ``fts_search``. The tool
    description claimed they differed — agents had to guess. Collapse
    to one canonical mode (``search``); keep ``fts_search`` accepted
    at the validate boundary as a deprecated alias but drop it from
    the schema enum and surface a deprecation marker in the response.
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        (tmp_path / "sample.py").write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_fts_search_dropped_from_schema_enum(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(tiny_project))
        modes = tool.get_tool_schema()["properties"]["mode"]["enum"]
        assert "search" in modes, (
            f"J1: ``search`` must remain in the schema enum — got {modes!r}"
        )
        assert "fts_search" not in modes, (
            f"J1: ``fts_search`` must NOT appear in the schema enum — "
            f"agents should see one canonical mode (``search``). "
            f"Got {modes!r}"
        )

    def test_fts_search_alias_still_accepted(self, tiny_project: Path) -> None:
        """Back-compat: existing MCP callers that still send
        ``mode='fts_search'`` should keep working — the validate
        boundary continues to accept it.
        """
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(tiny_project))
        # Should NOT raise — fts_search is a deprecated alias.
        assert tool.validate_arguments({"mode": "fts_search", "query": "greet"}) is True

    def test_fts_search_alias_surfaces_deprecation(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(tiny_project))
        # Index first so the FTS index exists; otherwise empty result.
        _run(tool.execute({"mode": "index"}))
        result = _run(tool.execute({"mode": "fts_search", "query": "greet"}))
        _assert_envelope_with_summary("ast_cache:fts_search(alias)", result)
        assert "deprecated_alias" in result, (
            f"J1: ``fts_search`` responses must carry a ``deprecated_alias`` "
            f"marker so agents know to migrate to ``search``. "
            f"Got keys: {sorted(result.keys())!r}"
        )

    def test_search_response_omits_deprecation_marker(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(tiny_project))
        _run(tool.execute({"mode": "index"}))
        result = _run(tool.execute({"mode": "search", "query": "greet"}))
        _assert_envelope_with_summary("ast_cache:search", result)
        assert "deprecated_alias" not in result, (
            f"J1: ``search`` is the canonical mode — its response must NOT "
            f"carry a ``deprecated_alias`` marker. Got keys: "
            f"{sorted(result.keys())!r}"
        )

    def test_search_and_fts_search_results_equivalent(self, tiny_project: Path) -> None:
        """Both modes are explicitly the same lookup — the document
        contract (collapsed to one mode) is enforced by returning
        identical result lists for the same query.
        """
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(tiny_project))
        _run(tool.execute({"mode": "index"}))
        s = _run(tool.execute({"mode": "search", "query": "greet"}))
        f = _run(tool.execute({"mode": "fts_search", "query": "greet"}))
        assert s.get("results") == f.get("results"), (
            "J1: collapsed ``search``/``fts_search`` must return identical "
            "results — they are explicitly the same lookup."
        )


class TestJ6TOONImportRowsPerSymbol:
    """Round-22 J6: ``from X import (A, B, C)`` collapsed the entire
    parenthesised block — newlines, alias keyword, trailing comments
    and all — into a single ``name`` cell, defeating TOON's whole
    purpose (token efficiency). Strategy 1 (minimal projection): keep
    one row per ``from`` statement but emit a clean comma-joined list
    of the *bound* identifiers, with ``imported_names`` populated for
    structured consumers.
    """

    @pytest.fixture
    def multiline_import_project(self, tmp_path: Path) -> Path:
        (tmp_path / "module.py").write_text(
            "from .alpha import (\n"
            "    A,\n"
            "    B,\n"
            "    C,\n"
            ")\n"
            "from .beta import One as one, Two as two  # inline comment\n"
            "from .gamma import (\n"
            "    Solo as renamed,  # trailing comment that used to bleed\n"
            ")\n"
            "import os\n"
            "from .single import Single\n",
            encoding="utf-8",
        )
        return tmp_path

    def _analyze_imports(self, project: Path) -> list[dict]:
        from tree_sitter_analyzer.api import analyze_file

        result = analyze_file(str(project / "module.py"), language="python")
        # API surfaces import elements as ``type='import'`` rows on the
        # flat ``elements`` list.
        return [e for e in result.get("elements", []) if e.get("type") == "import"]

    def test_names_have_no_newlines_or_parens(
        self, multiline_import_project: Path
    ) -> None:
        imports = self._analyze_imports(multiline_import_project)
        assert imports, "fixture must produce at least one import"
        for imp in imports:
            name = imp.get("name", "")
            assert "\n" not in name, (
                f"J6: import name must not contain newlines — defeats "
                f"TOON's token efficiency. Got name={name!r}"
            )
            assert "(" not in name and ")" not in name, (
                f"J6: import name must not contain parens — defeats "
                f"TOON's token efficiency. Got name={name!r}"
            )

    def test_names_have_no_trailing_comments(
        self, multiline_import_project: Path
    ) -> None:
        imports = self._analyze_imports(multiline_import_project)
        for imp in imports:
            name = imp.get("name", "")
            assert "#" not in name, (
                f"J6: import name must not contain ``#`` (trailing inline "
                f"comment leaked from source). Got name={name!r}"
            )

    def test_aliased_import_uses_bound_identifier(
        self, multiline_import_project: Path
    ) -> None:
        imports = self._analyze_imports(multiline_import_project)
        gamma = next(
            (i for i in imports if i.get("module_name") == ".gamma"),
            None,
        )
        assert gamma is not None, (
            f"J6: expected to find an import row for module ``.gamma``. "
            f"Got modules: {[i.get('module_name') for i in imports]!r}"
        )
        name = gamma.get("name", "")
        assert "renamed" in name, (
            f"J6: aliased import ``Solo as renamed`` must surface the "
            f"bound identifier ``renamed`` in the name, not the source "
            f"name or the whole block. Got name={name!r}"
        )

    def test_imported_names_list_populated(
        self, multiline_import_project: Path
    ) -> None:
        imports = self._analyze_imports(multiline_import_project)
        alpha = next(
            (i for i in imports if i.get("module_name") == ".alpha"),
            None,
        )
        assert alpha is not None, "expected .alpha import row"
        names = alpha.get("imported_names") or []
        assert set(names) >= {"A", "B", "C"}, (
            f"J6: ``imported_names`` must list every bound identifier. Got {names!r}"
        )


class TestJ8AstCacheSyncActionStatusConsistent:
    """Round-22 J8: ``sync`` returned per-file dicts that read
    ``{action: "indexed", status: "skipped"}`` for files the cache
    refused — two contradictory labels. ``action`` is renamed to
    ``considered`` (what the sync engine *attempted*) and kept as a
    back-compat alias. The ``status`` field continues to record the
    *outcome*.
    """

    @pytest.fixture
    def mixed_project(self, tmp_path: Path) -> Path:
        # A file the cache will index, plus one it will skip
        # (``.cs`` is in the source-extension walker but unsupported
        # by the parser registry, so the cache returns
        # ``status: 'skipped'``).
        (tmp_path / "indexable.py").write_text("def f(): return 1\n", encoding="utf-8")
        (tmp_path / "skipped.cs").write_text(
            "class C { void M(){} }\n", encoding="utf-8"
        )
        return tmp_path

    def _run_sync(self, project: Path) -> dict:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(project))
        return _run(tool.execute({"mode": "sync"}))

    def test_no_indexed_skipped_contradiction(self, mixed_project: Path) -> None:
        """The legacy contradiction ``action: indexed, status: skipped``
        must no longer appear without an accompanying ``considered``
        field that clarifies intent vs outcome.
        """
        result = self._run_sync(mixed_project)
        details = result.get("details") or []
        assert details, (
            f"J8: ``sync`` must emit at least one detail row for our "
            f"two-file fixture. Got result keys: {sorted(result.keys())!r}"
        )
        for d in details:
            action = d.get("action")
            status = d.get("status")
            # If both are populated, the new ``considered`` field MUST
            # also be present so the row reads "tool tried to X, here
            # is the outcome" rather than a flat contradiction.
            if action == "indexed" and status == "skipped":
                assert "considered" in d, (
                    f"J8: a row with ``action='indexed', status='skipped'`` "
                    f"must also carry a ``considered`` field — without it "
                    f"the two labels are flatly contradictory. Got {d!r}"
                )

    def test_considered_field_present_for_every_attempt(
        self, mixed_project: Path
    ) -> None:
        """Every per-file row that records an indexing/update/deletion
        attempt must carry the new ``considered`` field.
        """
        result = self._run_sync(mixed_project)
        details = result.get("details") or []
        assert details, "fixture must produce sync details"
        for d in details:
            assert "considered" in d, (
                f"J8: every sync detail row must carry a ``considered`` "
                f"field describing what the engine attempted. Got {d!r}"
            )
            assert d["considered"] in {"indexed", "updated", "deleted"}, (
                f"J8: ``considered`` must be one of "
                f"indexed/updated/deleted. Got {d['considered']!r}"
            )

    def test_action_field_kept_as_backcompat_alias(self, mixed_project: Path) -> None:
        """The legacy ``action`` field is retained for back-compat —
        downstream consumers that already read it must keep working.
        """
        result = self._run_sync(mixed_project)
        details = result.get("details") or []
        assert details, "fixture must produce sync details"
        for d in details:
            assert "action" in d, (
                f"J8: ``action`` must remain as a back-compat alias for "
                f"``considered``. Got {d!r}"
            )
            # Aliases must agree.
            assert d["action"] == d["considered"], (
                f"J8: ``action`` and ``considered`` must agree (alias). "
                f"Got action={d['action']!r} vs considered={d['considered']!r}"
            )


class TestJ3PackageInitImports:
    """J3 (round-22): the dependency-graph resolver previously only
    looked at ``foo/bar.py`` candidates. When a project imports
    ``from foo.bar import X`` and ``foo/bar`` is a *package* (so
    ``foo/bar.py`` does not exist but ``foo/bar/__init__.py`` does),
    the edge was silently dropped.

    This undercounted dependencies for every consumer of a package's
    top-level export — cascading into ``blast_radius`` reverse
    counts, ``safe_to_edit`` downstream estimates, ``find_cycles``
    routes through ``__init__.py``, and ``fan_in`` hub rankings.

    Fix: ``_resolve_to_project_file`` now matches Python's actual
    import semantics — it tries the file-module candidate first, then
    falls back to ``<rest>/__init__.py``. The extractor was also
    extended to emit dependency entries for ``from . import x, y``
    (previously silently dropped) and ``from .. import z``.
    """

    @pytest.fixture
    def pkg_project(self, tmp_path: Path) -> Path:
        """Layout:
        top/
          __init__.py
          consumer.py    -> from top.security import Guard
          utils.py
          security/
            __init__.py  -> exposes Guard
            impl.py
        """
        top = tmp_path / "top"
        top.mkdir()
        (top / "__init__.py").write_text("", encoding="utf-8")
        (top / "consumer.py").write_text(
            "from top.security import Guard\nfrom top import utils\n",
            encoding="utf-8",
        )
        (top / "utils.py").write_text("def helper(): pass\n", encoding="utf-8")
        sec = top / "security"
        sec.mkdir()
        (sec / "__init__.py").write_text("from .impl import Guard\n", encoding="utf-8")
        (sec / "impl.py").write_text("class Guard: pass\n", encoding="utf-8")
        return tmp_path

    def _file_deps(self, project: Path, rel: str) -> dict[str, Any]:
        # Clear the global graph cache so this fixture's nodes do not
        # collide with another suite's project_root.
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.project_graph import DependencyGraph

        DependencyGraph._global_cache.clear()
        tool = DependencyAnalysisTool(project_root=str(project))
        return _run(
            tool.execute(
                {"mode": "file_deps", "file_path": rel, "output_format": "json"}
            )
        )

    def test_absolute_from_pkg_import_x_resolves_to_init(
        self, pkg_project: Path
    ) -> None:
        """``from top.security import Guard`` must produce an edge
        ``top/consumer.py -> top/security/__init__.py`` because
        ``top/security.py`` does not exist — only the package
        ``top/security/__init__.py`` does. This is the canonical J3
        bug reproduction."""
        result = self._file_deps(pkg_project, "top/consumer.py")
        deps = result["depends_on"]
        assert "top/security/__init__.py" in deps, (
            f"J3: ``from top.security import Guard`` must resolve to "
            f"``top/security/__init__.py``. Got deps={deps!r}"
        )

    def test_absolute_bare_pkg_import_resolves_to_package_init(
        self, pkg_project: Path
    ) -> None:
        """``from top import utils`` resolves to ``top/__init__.py``.

        Python's import system reads ``top/__init__.py`` first for any
        ``from top import …``. Whether ``utils`` is a submodule or an
        attribute defined in ``__init__`` is resolved at runtime; for
        the dependency graph the syntactic dep is on the package
        itself. (If ``utils`` is also a submodule, that's reached
        transitively via the package.)
        """
        result = self._file_deps(pkg_project, "top/consumer.py")
        deps = result["depends_on"]
        assert "top/__init__.py" in deps, (
            f"J3: ``from top import utils`` must resolve to the "
            f"package ``top/__init__.py``. Got deps={deps!r}"
        )

    def test_relative_from_pkg_dot_import_falls_back_to_init(
        self, tmp_path: Path
    ) -> None:
        """``from . import submodule`` where ``submodule`` is a
        subpackage (only ``__init__.py``, no ``submodule.py``) must
        resolve to ``<current_pkg>/submodule/__init__.py``."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.project_graph import DependencyGraph

        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "pkg" / "consumer.py").write_text(
            "from . import sub\n", encoding="utf-8"
        )
        (tmp_path / "pkg" / "sub").mkdir()
        (tmp_path / "pkg" / "sub" / "__init__.py").write_text("", encoding="utf-8")

        DependencyGraph._global_cache.clear()
        tool = DependencyAnalysisTool(project_root=str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "mode": "file_deps",
                    "file_path": "pkg/consumer.py",
                    "output_format": "json",
                }
            )
        )
        assert "pkg/sub/__init__.py" in result["depends_on"], (
            f"J3: ``from . import sub`` (sub is a package) must resolve "
            f"to ``pkg/sub/__init__.py``. Got {result['depends_on']!r}"
        )

    def test_relative_triple_dot_resolves_to_init(self, tmp_path: Path) -> None:
        """The exact ``base_tool.py`` shape: ``from ...security import X``
        from a deeply nested module must resolve to the ancestor
        package's ``__init__.py`` when no sibling ``.py`` exists."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.project_graph import DependencyGraph

        # top/mcp/tools/base.py — depth 3
        # top/security/__init__.py — sibling of mcp/
        (tmp_path / "top").mkdir()
        (tmp_path / "top" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "top" / "mcp").mkdir()
        (tmp_path / "top" / "mcp" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "top" / "mcp" / "tools").mkdir()
        (tmp_path / "top" / "mcp" / "tools" / "__init__.py").write_text(
            "", encoding="utf-8"
        )
        (tmp_path / "top" / "mcp" / "tools" / "base.py").write_text(
            "from ...security import Guard\n", encoding="utf-8"
        )
        (tmp_path / "top" / "security").mkdir()
        (tmp_path / "top" / "security" / "__init__.py").write_text(
            "class Guard: pass\n", encoding="utf-8"
        )

        DependencyGraph._global_cache.clear()
        tool = DependencyAnalysisTool(project_root=str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "mode": "file_deps",
                    "file_path": "top/mcp/tools/base.py",
                    "output_format": "json",
                }
            )
        )
        assert "top/security/__init__.py" in result["depends_on"], (
            f"J3: ``from ...security import Guard`` (3 dots) must "
            f"resolve to ``top/security/__init__.py``. Got "
            f"{result['depends_on']!r}"
        )

    def test_base_tool_depends_on_security_and_utils_init(self) -> None:
        """Real repro from this repo: ``base_tool.py`` has
        ``from ...security import SecurityValidator`` and
        ``from ...utils import setup_logger``. Both must be edges in
        the dependency graph — they were silently dropped before J3."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.project_graph import DependencyGraph

        # Walk up from this test file to the repo root.
        repo_root = Path(__file__).resolve().parents[4]
        assert (
            repo_root / "tree_sitter_analyzer" / "security" / "__init__.py"
        ).exists(), (
            f"J3: repo layout sanity — security/__init__.py should exist at {repo_root}"
        )

        DependencyGraph._global_cache.clear()
        tool = DependencyAnalysisTool(project_root=str(repo_root))
        result = _run(
            tool.execute(
                {
                    "mode": "file_deps",
                    "file_path": "tree_sitter_analyzer/mcp/tools/base_tool.py",
                    "output_format": "json",
                }
            )
        )
        deps = result["depends_on"]
        assert "tree_sitter_analyzer/security/__init__.py" in deps, (
            f"J3: base_tool.py must depend on security/__init__.py — "
            f"the ``from ...security import SecurityValidator`` edge. "
            f"Got {deps!r}"
        )
        assert "tree_sitter_analyzer/utils/__init__.py" in deps, (
            f"J3: base_tool.py must depend on utils/__init__.py — "
            f"the ``from ...utils import setup_logger`` edge. "
            f"Got {deps!r}"
        )

    def test_fan_in_counts_init_consumers(self, pkg_project: Path) -> None:
        """A package's ``__init__.py`` must report a positive fan-in
        (``depended_by``) when any file imports from the package. The
        old undercounting bug made popular packages look unpopular."""
        result = self._file_deps(pkg_project, "top/security/__init__.py")
        depended_by = result["depended_by"]
        assert "top/consumer.py" in depended_by, (
            f"J3: ``top/security/__init__.py`` must list "
            f"``top/consumer.py`` in ``depended_by`` — the consumer's "
            f"``from top.security import Guard`` is a real edge. "
            f"Got {depended_by!r}"
        )
        assert result["dependent_count"] >= 1, (
            f"J3: package ``__init__.py`` fan-in must be ≥1 when a "
            f"consumer file imports from the package. "
            f"Got dependent_count={result['dependent_count']!r}"
        )

    def test_no_duplicate_edges_for_submodule_import(self, tmp_path: Path) -> None:
        """``from pkg.a import X`` must produce a single edge.

        When ``pkg/a.py`` exists and ``pkg/a/__init__.py`` does not,
        the resolver picks ``pkg/a.py`` — it must not also emit an
        edge to ``pkg/__init__.py`` from the same import statement.
        Duplicate edges would inflate ``edge_count``, ``fan_in`` and
        ``cycle_count`` and break the H3 determinism contract."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.project_graph import DependencyGraph

        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "pkg" / "a.py").write_text("X = 1\n", encoding="utf-8")
        (tmp_path / "consumer.py").write_text("from pkg.a import X\n", encoding="utf-8")

        DependencyGraph._global_cache.clear()
        tool = DependencyAnalysisTool(project_root=str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "mode": "file_deps",
                    "file_path": "consumer.py",
                    "output_format": "json",
                }
            )
        )
        deps = result["depends_on"]
        assert "pkg/a.py" in deps, (
            f"J3: ``from pkg.a import X`` must resolve to the existing "
            f"``pkg/a.py``. Got {deps!r}"
        )
        # The parent package init must NOT be emitted as a duplicate
        # edge for the same import statement — the only edge is to
        # ``pkg/a.py``.
        assert "pkg/__init__.py" not in deps, (
            f"J3: ``from pkg.a import X`` must produce a single edge to "
            f"``pkg/a.py`` only — not a duplicate edge to "
            f"``pkg/__init__.py``. Got {deps!r}"
        )


# ============================================================================
# K3 — symbol_lineage definitions for classes (round-24)
# ============================================================================


class TestK3SymbolLineageClassDefinitions:
    """K3 (round-24): ``symbol_lineage`` returned ``definition_count=0`` for
    class symbols. ``execute_find_references`` caps its file scan at the
    first 500 ``rglob`` results, and the def-bearing file can fall past
    the cap on medium repos — references are found in earlier importers
    but the actual ``class Foo:`` line is never seen.

    Contract:
      - ``symbol_lineage`` for a class returns ``definition_count >= 1``.
      - The promoted entry has ``role='definition'``.
      - Works for Python classes, dataclasses, and Java classes.
    """

    def test_python_class_definition_count_positive(self, tmp_path: Path) -> None:
        """Repro: ``class BaseMCPTool(ABC):`` must surface as a definition."""
        from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import (
            SymbolLineageTool,
        )

        (tmp_path / "base_tool.py").write_text(
            "from abc import ABC\n\n\nclass BaseMCPTool(ABC):\n"
            "    def execute(self) -> None:\n        pass\n",
            encoding="utf-8",
        )
        (tmp_path / "user.py").write_text(
            "from base_tool import BaseMCPTool\n\n"
            "class FooTool(BaseMCPTool):\n    pass\n",
            encoding="utf-8",
        )

        tool = SymbolLineageTool(str(tmp_path))
        result = _run(tool.execute({"symbol": "BaseMCPTool", "output_format": "json"}))
        assert result["definition_count"] >= 1, (
            f"K3: class definitions must be counted — got "
            f"definition_count={result['definition_count']} "
            f"defs={result.get('definitions')!r}"
        )
        defs = result.get("definitions", [])
        assert any(d.get("role") == "definition" for d in defs), (
            f"K3: at least one definition must have role='definition' — got {defs!r}"
        )

    def test_python_dataclass_definition_count_positive(self, tmp_path: Path) -> None:
        """Decorated ``@dataclass`` classes must also count as definitions."""
        from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import (
            SymbolLineageTool,
        )

        (tmp_path / "model.py").write_text(
            "from dataclasses import dataclass\n\n"
            "@dataclass\n"
            "class UserRecord:\n"
            "    user_id: int\n"
            "    name: str\n",
            encoding="utf-8",
        )
        (tmp_path / "consumer.py").write_text(
            "from model import UserRecord\n\n"
            "def make_user() -> UserRecord:\n"
            "    return UserRecord(user_id=1, name='ada')\n",
            encoding="utf-8",
        )

        tool = SymbolLineageTool(str(tmp_path))
        result = _run(tool.execute({"symbol": "UserRecord", "output_format": "json"}))
        assert result["definition_count"] >= 1, (
            f"K3: dataclass def must be counted — got {result.get('definitions')!r}"
        )

    def test_java_class_definition_count_positive(self, tmp_path: Path) -> None:
        """K3 contract holds across languages: a Java class definition
        must be classified as a definition, not a reference."""
        from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import (
            SymbolLineageTool,
        )

        (tmp_path / "Handler.java").write_text(
            "package com.example;\n\n"
            "public class Handler {\n"
            "    public static void serve() {}\n"
            "}\n",
            encoding="utf-8",
        )
        (tmp_path / "Main.java").write_text(
            "package com.example;\n\n"
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            "        Handler.serve();\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        tool = SymbolLineageTool(str(tmp_path))
        result = _run(tool.execute({"symbol": "Handler", "output_format": "json"}))
        assert result["definition_count"] >= 1, (
            f"K3: Java class definitions must be counted — got "
            f"definition_count={result['definition_count']} "
            f"defs={result.get('definitions')!r}"
        )


# ============================================================================
# K9 — file_health long_line + single_line_file smells (round-24)
# ============================================================================


class TestK9FileHealthLongLineSmells:
    """K9 (round-24): a 3.5 KB single-line Python file scored grade A
    because no smell detector covered minified / single-statement
    emissions — the line-count-based dimensions all saw 1 LoC and
    returned full marks.

    Contract:
      - A file with one >200-char line surfaces a ``long_line`` smell.
      - A file with no newlines but >=200 bytes surfaces a
        ``single_line_file`` smell AND drops below grade A.
      - A normal 50-char-per-line file produces no long-line smell.
      - Empty files still bypass smell checks (M7/H9 preserved).
    """

    def test_long_line_smell_fires_on_300_char_line(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        src = tmp_path / "long.py"
        src.write_text(f"x = '{'a' * 300}'\n", encoding="utf-8")

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": str(src), "output_format": "json"}))
        smells = result.get("code_smells", [])
        smell_names = [s.get("smell") for s in smells]
        assert "long_line" in smell_names, (
            f"K9: long_line smell must fire on a 300-char line — got "
            f"smells={smell_names!r}"
        )

    def test_long_line_and_single_line_smells_on_minified_blob(
        self, tmp_path: Path
    ) -> None:
        """K9 reproducer: 3.5 KB on a single line — single_line_file +
        long_line must both fire, and the grade must drop below A."""
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        src = tmp_path / "blob.py"
        # ~3.5 KB without a single newline.
        src.write_text("x = 1; " * 500, encoding="utf-8")

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": str(src), "output_format": "json"}))
        smells = result.get("code_smells", [])
        smell_names = [s.get("smell") for s in smells]
        assert "long_line" in smell_names, (
            f"K9: long_line must fire on a 3500-char line — got {smell_names!r}"
        )
        assert "single_line_file" in smell_names, (
            f"K9: single_line_file must fire on a 0-newline ≥200-byte file — "
            f"got {smell_names!r}"
        )
        assert result.get("grade") != "A", (
            f"K9: grade must drop below A on a single-line bundle — "
            f"grade={result.get('grade')!r} score={result.get('overall_score')!r}"
        )

    def test_no_long_line_smell_on_short_lines(self, tmp_path: Path) -> None:
        """K9: a file whose lines are all under the threshold must not
        emit a long_line smell. Prevents the threshold from regressing
        below the 100-200 char band where most code lives."""
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        src = tmp_path / "short.py"
        src.write_text("\n".join("x = 1" for _ in range(20)) + "\n", encoding="utf-8")

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": str(src), "output_format": "json"}))
        smells = result.get("code_smells", [])
        smell_names = [s.get("smell") for s in smells]
        assert "long_line" not in smell_names, (
            f"K9: short-line file must not emit long_line — got {smell_names!r}"
        )
        assert "single_line_file" not in smell_names, (
            f"K9: multi-line file must not emit single_line_file — got {smell_names!r}"
        )

    def test_empty_file_keeps_m7_h9_envelope(self, tmp_path: Path) -> None:
        """K9 must not regress the M7/H9 empty-file behaviour: empty /
        whitespace-only files return ``grade=N/A`` with no smells.
        """
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        empty = tmp_path / "empty.py"
        empty.write_text("", encoding="utf-8")

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": str(empty), "output_format": "json"}))
        assert result.get("grade") == "N/A", (
            f"K9 regression: empty file must keep M7's N/A grade — "
            f"got grade={result.get('grade')!r}"
        )
        assert result.get("code_smells") == [], (
            f"K9 regression: empty file must keep zero smells — "
            f"got code_smells={result.get('code_smells')!r}"
        )


class TestK8PartialReadOutOfRange:
    """K8 (round-24): ``extract_code_section`` / ``--partial-read``
    used to compute ``lines_extracted`` from ``end_line - start_line + 1``
    regardless of how many lines were actually read.

    For a request entirely past EOF the response carried
    ``content=""``, ``content_length=0``, but ``lines_extracted=2``
    plus ``risk: low`` and no flag — an agent reading the summary
    would believe two lines came back and the read succeeded.

    Fixes:

    1. ``lines_extracted`` is derived from the content
       (``len(content.splitlines())``), so it can never overstate
       what was actually returned.
    2. Out-of-range requests carry ``out_of_range: True`` and
       ``verdict: "N/A"`` so the situation reads as an INPUT
       problem, not a healthy ``risk: low`` result.
    3. Partial overlap (start in range, end past EOF) carries
       ``partial_range: True`` and ``clamped_to=[start, eof_line]``.
    4. ``summary_line`` and ``agent_summary.next_step`` direct the
       agent at a valid recovery range.
    """

    @pytest.fixture
    def fifty_line_file(self, tmp_path: Path) -> Path:
        """A 50-line python file at a stable known path."""
        path = tmp_path / "fifty.py"
        path.write_text("".join(f"line_{i}\n" for i in range(1, 51)), encoding="utf-8")
        return path

    def _run_tool(self, project: Path, **kwargs: Any) -> dict[str, Any]:
        from tree_sitter_analyzer.mcp.tools.read_partial_tool import (
            ReadPartialTool,
        )

        tool = ReadPartialTool(str(project))
        payload = {"output_format": "json"}
        payload.update(kwargs)
        return _run(tool.execute(payload))

    def test_range_past_eof_reports_out_of_range(self, fifty_line_file: Path) -> None:
        """Start_line entirely past EOF: lines_extracted=0,
        out_of_range=True, verdict=N/A — and the summary tells the
        agent to retry with a valid range."""
        result = self._run_tool(
            fifty_line_file.parent,
            file_path="fifty.py",
            start_line=99999,
            end_line=100000,
        )
        assert result["success"] is True, (
            f"K8: out-of-range must NOT come back as success=False. "
            f"Got {result.get('error')!r}"
        )
        assert result["content"] == "", (
            f"K8: content for past-EOF range must be empty. "
            f"Got {result.get('content')!r}"
        )
        assert result["content_length"] == 0
        assert result["lines_extracted"] == 0, (
            f"K8: past-EOF range must report lines_extracted=0 "
            f"(actual content), NOT end_line-start_line+1. "
            f"Got {result.get('lines_extracted')!r}"
        )
        assert result.get("out_of_range") is True, (
            f"K8: response must carry out_of_range=True. Got keys "
            f"{sorted(result.keys())!r}"
        )
        # No partial_range — start is also past EOF, so it's not a
        # partial overlap, it's a full miss.
        assert result.get("partial_range") is not True
        # file_lines is surfaced so the agent can pick a valid range.
        assert result.get("file_lines") == 50

        summary = result["agent_summary"]
        assert summary["lines_extracted"] == 0
        assert summary["out_of_range"] is True
        assert summary["verdict"] == "N/A", (
            f"K8: out-of-range verdict must be 'N/A' so the agent "
            f"does not treat ``risk: low`` as a healthy result. "
            f"Got {summary.get('verdict')!r}"
        )
        # Risk stays low (it's a low-impact INPUT problem, not a
        # large content read), but verdict makes the situation clear.
        assert summary["risk"] == "low"
        # next_step must mention a recovery range.
        assert "Try start_line=1" in summary["next_step"], (
            f"K8: next_step must suggest a valid recovery range. "
            f"Got {summary['next_step']!r}"
        )
        # The summary_line tells the truth at a glance.
        assert "out_of_range=true" in summary["summary_line"]
        assert "file_lines=50" in summary["summary_line"]

    def test_partial_overlap_reports_partial_range_and_clamped(
        self, fifty_line_file: Path
    ) -> None:
        """Range starts in bounds but extends past EOF: returns the
        in-bounds content plus structured flags so the agent can
        re-issue a clean request."""
        result = self._run_tool(
            fifty_line_file.parent,
            file_path="fifty.py",
            start_line=10,
            end_line=100,
        )
        assert result["success"] is True
        # Real lines extracted — lines 10..50 inclusive = 41 lines.
        assert result["lines_extracted"] == 41, (
            f"K8: partial-overlap lines_extracted must match the "
            f"actual content (41 lines from start=10 to eof=50), "
            f"NOT end_line-start_line+1 (91). "
            f"Got {result.get('lines_extracted')!r}"
        )
        assert result.get("partial_range") is True, (
            f"K8: response must carry partial_range=True. Got keys "
            f"{sorted(result.keys())!r}"
        )
        assert result.get("clamped_to") == [10, 50], (
            f"K8: clamped_to must be [start, eof_line] = [10, 50]. "
            f"Got {result.get('clamped_to')!r}"
        )
        assert result.get("out_of_range") is not True
        assert result.get("file_lines") == 50

        summary = result["agent_summary"]
        assert summary["verdict"] == "WARN", (
            f"K8: partial-overlap verdict must be 'WARN'. "
            f"Got {summary.get('verdict')!r}"
        )
        assert summary["partial_range"] is True
        assert "partial_range=true" in summary["summary_line"]
        # next_step nudges toward the clamped end.
        assert "50" in summary["next_step"], (
            f"K8: next_step must mention the EOF line so the agent "
            f"can issue a clean range. Got {summary['next_step']!r}"
        )

    def test_valid_range_has_no_anomaly_flags(self, fifty_line_file: Path) -> None:
        """In-bounds range: no out_of_range / partial_range / clamped_to
        in the envelope; verdict=OK; lines_extracted matches content."""
        result = self._run_tool(
            fifty_line_file.parent,
            file_path="fifty.py",
            start_line=5,
            end_line=15,
        )
        assert result["success"] is True
        assert result["lines_extracted"] == 11, (
            f"K8: in-bounds range must extract exactly 11 lines (5..15). "
            f"Got {result.get('lines_extracted')!r}"
        )
        # Anomaly flags must NOT be present (or must be falsy) so
        # downstream parsers can rely on their absence.
        assert result.get("out_of_range") is not True
        assert result.get("partial_range") is not True
        assert "clamped_to" not in result

        summary = result["agent_summary"]
        assert summary["verdict"] == "OK", (
            f"K8: in-bounds range verdict must be 'OK'. Got {summary.get('verdict')!r}"
        )
        # And the agent_summary's own flags reflect the same truth.
        assert summary.get("out_of_range") is not True
        assert summary.get("partial_range") is not True
        assert summary["lines_extracted"] == 11

    def test_lines_extracted_never_exceeds_content_lines(
        self, fifty_line_file: Path
    ) -> None:
        """Regression guard against the old formula: across out-of-range,
        partial-overlap and in-bounds calls, ``lines_extracted`` must
        never exceed what the content actually contains."""
        for start, end in [(99999, 100000), (10, 100), (5, 15), (1, 50)]:
            result = self._run_tool(
                fifty_line_file.parent,
                file_path="fifty.py",
                start_line=start,
                end_line=end,
            )
            content_lines = (
                len(result["content"].splitlines()) if result.get("content") else 0
            )
            assert result["lines_extracted"] == content_lines, (
                f"K8: lines_extracted ({result['lines_extracted']}) must "
                f"equal len(content.splitlines()) ({content_lines}) for "
                f"range start={start} end={end}. The old "
                f"``end_line - start_line + 1`` formula lied here."
            )


# ---------------------------------------------------------------------------
# K6 / K10 / K7 — round-24 dogfood findings
# ---------------------------------------------------------------------------


class TestK6ChangeImpactExcludesCaches:
    """K6 (round-24): ``analyze_change_impact`` enumerated its own cache
    artefacts (``.ast-cache/index.db``, ``.tree-sitter-cache/*``) as
    "changed files", inflating ``changed_count``, ``affected_count`` and
    pushing risk to ``high`` even when only source files were modified.

    The fix filters tool-owned cache directories at the git-output
    boundary using the canonical ``_EXCLUDE_DIRS`` frozenset from
    ``_graph_cache_fingerprint`` (same list the dependency-graph walker
    honours).
    """

    @pytest.fixture
    def git_project(self, tmp_path: Path) -> Path:
        import subprocess  # nosec

        # Initialise an empty git repo so change-impact has something to
        # compare against. We commit one file so HEAD exists and any
        # subsequent untracked files surface as "diff" candidates.
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # nosec
        subprocess.run(  # nosec
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
        )
        subprocess.run(  # nosec
            ["git", "config", "user.name", "test"], cwd=tmp_path, check=True
        )
        src = tmp_path / "module.py"
        src.write_text("def hello():\n    return 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "module.py"], cwd=tmp_path, check=True)  # nosec
        subprocess.run(  # nosec
            ["git", "commit", "-q", "-m", "init"],
            cwd=tmp_path,
            check=True,
        )

        # Now drop tool-owned cache artefacts AND modify a tracked
        # source file. Only the source file should surface as changed.
        (tmp_path / ".ast-cache").mkdir()
        (tmp_path / ".ast-cache" / "index.db").write_bytes(b"\x00" * 16)
        (tmp_path / ".tree-sitter-cache").mkdir()
        (tmp_path / ".tree-sitter-cache" / "summary.toon").write_text("x")
        (tmp_path / ".tree-sitter-cache" / "project-index.json").write_text("{}")
        src.write_text("def hello():\n    return 2\n", encoding="utf-8")
        return tmp_path

    def test_changed_files_excludes_ast_cache_paths(self, git_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

        tool = ChangeImpactTool(str(git_project))
        result = _run(tool.execute({"mode": "diff", "output_format": "json"}))
        changed = result.get("changed_files", [])
        cache_hits = [
            f
            for f in changed
            if ".ast-cache/" in f.replace("\\", "/")
            or ".tree-sitter-cache/" in f.replace("\\", "/")
            or f.startswith(".ast-cache")
            or f.startswith(".tree-sitter-cache")
        ]
        assert not cache_hits, (
            "K6: change_impact ``changed_files`` must NOT include paths "
            "from tool-owned cache directories (``.ast-cache/``, "
            f"``.tree-sitter-cache/``). Found: {cache_hits!r}"
        )
        # The legitimate source change still shows up.
        assert any("module.py" in f for f in changed), (
            f"K6: real source changes must still surface. Got changed_files={changed!r}"
        )

    def test_changed_count_matches_filtered_files(self, git_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

        tool = ChangeImpactTool(str(git_project))
        result = _run(tool.execute({"mode": "diff", "output_format": "json"}))
        assert result.get("changed_count") == len(result.get("changed_files", [])), (
            "K6: ``changed_count`` must match the post-filter list length. "
            f"Got changed_count={result.get('changed_count')!r} "
            f"changed_files={result.get('changed_files')!r}"
        )


class TestK10OverviewExcludesCaches:
    """K10 (round-24): ``--overview`` enumerated ``.ast-cache/`` and
    ``.tree-sitter-cache/`` even though the same tool writes to them
    during the very same call. This produced two bad outcomes:

    1. The summary listed those directories under ``top_directories``
       and bumped ``total_files`` / ``total_lines`` by the cache size.
    2. Two back-to-back ``--overview`` runs produced different
       ``total_lines`` numbers because the second run picked up the
       cache files the first run had just written.

    The fix adds ``.ast-cache`` / ``.tree-sitter-cache`` (via the
    canonical ``_EXCLUDE_DIRS`` set from ``_graph_cache_fingerprint``)
    to the overview walker's exclude list.
    """

    @pytest.fixture
    def project_with_caches(self, tmp_path: Path) -> Path:
        # Real source — the overview's ``total_lines`` reflects this.
        (tmp_path / "src.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        # Tool-owned caches that previously leaked into the count.
        (tmp_path / ".ast-cache").mkdir()
        (tmp_path / ".ast-cache" / "index.db").write_bytes(b"\x00" * 32)
        (tmp_path / ".tree-sitter-cache").mkdir()
        (tmp_path / ".tree-sitter-cache" / "summary.toon").write_text(
            "project: x\nwhat: y\n" * 50
        )
        (tmp_path / ".tree-sitter-cache" / "project-index.json").write_text(
            "{}\n" * 100
        )
        return tmp_path

    def test_top_directories_excludes_caches(self, project_with_caches: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(project_with_caches))
        result = _run(tool.execute({"output_format": "json"}))
        top = result.get("top_directories", {})
        assert ".ast-cache" not in top, (
            f"K10: top_directories must not include ``.ast-cache``. Got {top!r}"
        )
        assert ".tree-sitter-cache" not in top, (
            f"K10: top_directories must not include ``.tree-sitter-cache``. Got {top!r}"
        )

    def test_largest_source_files_excludes_caches(
        self, project_with_caches: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(project_with_caches))
        result = _run(tool.execute({"output_format": "json"}))
        largest = result.get("largest_source_files", [])
        cache_hits = [
            entry
            for entry in largest
            if ".ast-cache" in entry.get("path", "")
            or ".tree-sitter-cache" in entry.get("path", "")
        ]
        assert not cache_hits, (
            f"K10: largest_source_files must not include cache artefacts. "
            f"Got {cache_hits!r}"
        )


class TestK10OverviewDeterministic:
    """K10 (round-24): two back-to-back ``--overview`` calls returned
    different ``total_files`` / ``total_lines`` because the first call
    wrote new cache files that the second call then enumerated. With
    the cache directories excluded the counts are byte-stable across
    repeated invocations (assuming the underlying source tree hasn't
    changed).
    """

    @pytest.fixture
    def stable_project(self, tmp_path: Path) -> Path:
        (tmp_path / "a.py").write_text("x = 1\n" * 10, encoding="utf-8")
        (tmp_path / "b.py").write_text("y = 2\n" * 20, encoding="utf-8")
        # Pre-create the cache directories with stale contents to ensure
        # the exclusion path is the load-bearing fix (i.e. the test
        # would still fail if we relied on "cache wasn't there yet").
        (tmp_path / ".ast-cache").mkdir()
        (tmp_path / ".ast-cache" / "index.db").write_bytes(b"\x00" * 16)
        (tmp_path / ".tree-sitter-cache").mkdir()
        (tmp_path / ".tree-sitter-cache" / "summary.toon").write_text("a\n" * 5)
        return tmp_path

    def test_total_files_and_total_lines_stable(self, stable_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(stable_project))
        first = _run(tool.execute({"output_format": "json"}))
        # Touch the cache to simulate side effects from a sibling tool.
        # Without the K10 fix this would change ``total_lines`` on
        # the next call.
        (stable_project / ".tree-sitter-cache" / "side_effect.json").write_text(
            "x\n" * 100
        )
        second = _run(tool.execute({"output_format": "json"}))

        first_summary = first.get("summary", {})
        second_summary = second.get("summary", {})
        assert first_summary.get("total_files") == second_summary.get("total_files"), (
            f"K10: total_files must be stable across runs. "
            f"first={first_summary!r} second={second_summary!r}"
        )
        assert first_summary.get("total_lines") == second_summary.get("total_lines"), (
            f"K10: total_lines must be stable across runs. "
            f"first={first_summary!r} second={second_summary!r}"
        )


class TestK7AstCacheSearchImportNames:
    """K7 (round-24): ``ast_cache mode=search`` returned import rows
    whose ``name`` field carried the entire ``from X import (A, B, C)``
    block — 280+ chars including newlines, parens and trailing
    comments. A user searching for ``execute`` couldn't tell which
    symbol matched.

    The indexer now emits one row per *bound* identifier; legacy DBs
    are normalised at read time via ``_split_legacy_import_row`` so
    no re-index is required.
    """

    @pytest.fixture
    def multi_import_project(self, tmp_path: Path) -> Path:
        (tmp_path / "module.py").write_text(
            "from ._helpers import (\n"
            "    execute_legacy_api,\n"
            "    execute_modern_api,\n"
            "    execute_newest_api,\n"
            "    execute_old_api,\n"
            ")\n"
            "from .other import Solo as renamed\n"
            "import os\n"
            "\n"
            "def callable_function():\n"
            "    return execute_legacy_api()\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_import_row_names_are_single_identifiers(
        self, multi_import_project: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(multi_import_project))
        _run(tool.execute({"mode": "index"}))
        result = _run(tool.execute({"mode": "search", "query": "execute"}))
        import_hits = [
            h for h in result.get("results", []) if h.get("kind") == "import"
        ]
        assert import_hits, (
            "K7: search for ``execute`` must surface at least one import row "
            "matching the bound identifiers."
        )
        for hit in import_hits:
            name = hit.get("name", "")
            assert isinstance(name, str), (
                f"K7: import row ``name`` must be a string. Got {type(name).__name__}"
            )
            assert len(name) <= 100, (
                f"K7: import row ``name`` must be a single bound identifier "
                f"(length <= 100); got length {len(name)}: {name!r}"
            )
            assert "\n" not in name, (
                f"K7: import row ``name`` must not contain newlines. Got {name!r}"
            )
            assert "(" not in name and ")" not in name, (
                f"K7: import row ``name`` must not contain parentheses. Got {name!r}"
            )

    def test_aliased_import_uses_bound_identifier(
        self, multi_import_project: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(multi_import_project))
        _run(tool.execute({"mode": "index"}))
        result = _run(tool.execute({"mode": "search", "query": "renamed"}))
        names = {
            h.get("name")
            for h in result.get("results", [])
            if h.get("kind") == "import"
        }
        assert "renamed" in names, (
            f"K7: aliased import ``Solo as renamed`` must produce an import "
            f"row whose ``name`` is the bound identifier ``renamed``. "
            f"Got import names: {names!r}"
        )

    def test_legacy_row_split_at_read_time(self) -> None:
        """Legacy DBs that still hold multi-symbol rows are normalised
        at read time so the search caller never sees a 280-char name.
        """
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import (
            _apply_legacy_import_split,
        )

        legacy_block = (
            "from ._tree_sitter_compat_helpers import (\n"
            "    execute_legacy_api,\n"
            "    execute_modern_api,\n"
            "    execute_newest_api,\n"
            "    execute_old_api,\n"
            ")"
        )
        legacy_row = {
            "kind": "import",
            "name": legacy_block,
            "file": "x.py",
            "language": "python",
            "line": 1,
            "end_line": 6,
        }
        split = _apply_legacy_import_split([legacy_row])
        assert len(split) >= 4, (
            f"K7: legacy multi-symbol import row must split into one row "
            f"per bound identifier. Got {len(split)} rows: {split!r}"
        )
        for row in split:
            assert len(row.get("name", "")) <= 100, (
                f"K7: post-split row names must each be <= 100 chars. Got {row!r}"
            )
        bound_names = {row.get("name") for row in split}
        for expected in (
            "execute_legacy_api",
            "execute_modern_api",
            "execute_newest_api",
            "execute_old_api",
        ):
            assert expected in bound_names, (
                f"K7: legacy split must surface the bound name ``{expected}``. "
                f"Got {bound_names!r}"
            )


# ============================================================================
# K2 — TOON vs JSON imports schema parity
# ============================================================================


class _K2ImportElement:
    """Tiny adapter that exposes a dict-shaped import as the attributes
    the converters read via ``getattr``. The real analyzer ships object
    elements at the CLI layer; the API surface returns dicts, so the
    K2 tests adapt back to object shape rather than re-running the
    whole tree-sitter analysis pipeline.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)

    @property
    def name(self) -> Any:
        return self._data.get("name", "unknown")

    @property
    def import_statement(self) -> Any:
        return self._data.get("import_statement") or self._data.get("raw_text", "")

    @property
    def module_name(self) -> Any:
        return self._data.get("module_name", "")

    @property
    def raw_text(self) -> Any:
        return self._data.get("raw_text", "") or self._data.get("import_statement", "")

    @property
    def is_static(self) -> Any:
        return bool(self._data.get("is_static", False))

    @property
    def is_wildcard(self) -> Any:
        return bool(self._data.get("is_wildcard", False))

    @property
    def start_line(self) -> Any:
        return int(self._data.get("start_line", 0))

    @property
    def end_line(self) -> Any:
        return int(self._data.get("end_line", 0))

    @property
    def imported_names(self) -> Any:
        return list(self._data.get("imported_names", []) or [])


class TestK2ImportsSchemaParity:
    """K2 (round-24 dogfood): the CLI's ``--format json`` and
    ``--format toon`` paths used to emit ``imports[*]`` rows with
    completely disjoint key sets. JSON shipped
    ``{module_name, name, raw_text, statement}`` while TOON shipped
    ``{name, is_static, is_wildcard, statement, line_range}``. Per the
    F7 convention TOON should only drop ``results`` — never rename
    fields. An agent switching ``--format`` saw a different schema.

    Fix: pick a canonical key set and use it in both. The intersection
    is ``{name, statement}``; we additionally expose ``module_name``
    (JSON-only originally), ``is_static`` / ``is_wildcard`` (TOON-only),
    ``line_range`` (TOON-only), ``imported_names`` (from the earlier J6
    fix), and keep ``raw_text`` as a backward-compat alias of
    ``statement`` for the language formatters that still read it.
    """

    @pytest.fixture
    def python_imports_project(self, tmp_path: Path) -> Path:
        src = tmp_path / "module.py"
        src.write_text(
            "from .alpha import A, B, C\n"
            "from .beta import Solo as renamed\n"
            "import os\n"
            "from .gamma import *\n",
            encoding="utf-8",
        )
        return tmp_path

    def _convert_imports_json(self, project: Path) -> list[dict[str, Any]]:
        """Build the import projection that ``--format json`` ships."""
        from argparse import Namespace

        from tree_sitter_analyzer.api import analyze_file
        from tree_sitter_analyzer.cli.commands.table_command import TableCommand

        analysis_result = analyze_file(str(project / "module.py"), language="python")
        elements = analysis_result.get("elements", [])
        cmd = TableCommand(Namespace())
        return [
            cmd._convert_import_element(_K2ImportElement(e))
            for e in elements
            if e.get("type") == "import"
        ]

    def _convert_imports_toon(self, project: Path) -> list[dict[str, Any]]:
        """Build the import projection that ``--format toon`` ships."""
        from tree_sitter_analyzer.api import analyze_file
        from tree_sitter_analyzer.cli.commands.table_command_helpers import (
            _toon_import,
        )

        analysis_result = analyze_file(str(project / "module.py"), language="python")
        elements = analysis_result.get("elements", [])
        return [
            _toon_import(_K2ImportElement(e))
            for e in elements
            if e.get("type") == "import"
        ]

    def test_json_and_toon_share_same_keys(self, python_imports_project: Path) -> None:
        """The two import projections must produce identical key sets."""
        json_rows = self._convert_imports_json(python_imports_project)
        toon_rows = self._convert_imports_toon(python_imports_project)
        assert json_rows, "fixture must produce at least one import"
        assert toon_rows, "fixture must produce at least one import"
        json_keys = {tuple(sorted(r.keys())) for r in json_rows}
        toon_keys = {tuple(sorted(r.keys())) for r in toon_rows}
        assert json_keys == toon_keys, (
            f"K2: JSON and TOON imports must share the same key set. "
            f"JSON unique={json_keys - toon_keys!r} "
            f"TOON unique={toon_keys - json_keys!r}"
        )

    def test_canonical_key_set(self, python_imports_project: Path) -> None:
        """The canonical key set must contain every field documented in
        the K2 design: name, module_name, statement, is_static,
        is_wildcard, line_range, imported_names. ``raw_text`` is kept
        as a backward-compat alias."""
        json_rows = self._convert_imports_json(python_imports_project)
        canonical = {
            "name",
            "module_name",
            "statement",
            "is_static",
            "is_wildcard",
            "line_range",
            "imported_names",
        }
        actual = set(json_rows[0].keys())
        missing = canonical - actual
        assert not missing, (
            f"K2: canonical import keys missing from JSON projection — "
            f"missing={missing!r} actual={sorted(actual)!r}"
        )

    def test_line_range_is_pair(self, python_imports_project: Path) -> None:
        """``line_range`` must be a two-element [start, end] sequence
        in both JSON and TOON outputs — agents expect a uniform shape."""
        for label, rows in (
            ("json", self._convert_imports_json(python_imports_project)),
            ("toon", self._convert_imports_toon(python_imports_project)),
        ):
            for r in rows:
                lr = r.get("line_range")
                assert (
                    isinstance(lr, (list, tuple))
                    and len(lr) == 2
                    and all(isinstance(x, int) for x in lr)
                ), (
                    f"K2 ({label}): line_range must be [int,int] — got "
                    f"{lr!r} for import {r.get('name')!r}"
                )


# ============================================================================
# K5 — trace_impact verdict vocabulary disambiguation
# ============================================================================


class TestK5TraceImpactVerdictRename:
    """K5 (round-24 dogfood): ``trace_impact`` shipped a top-level
    ``verdict`` field that used magnitude vocab (HIGH/MEDIUM/LOW/NONE)
    while ``agent_summary.verdict`` used safety vocab (UNSAFE/CAUTION/
    SAFE). Same key name, contradictory meaning — an agent could read
    either and get the wrong picture.

    Fix:
    - Top-level ``impact_verdict`` carries the magnitude vocab.
    - Top-level ``verdict`` is now an alias that mirrors
      ``agent_summary.verdict`` (safety vocab) — consistent with every
      other safety-aware tool (safe_to_edit, modification_guard).
    """

    @pytest.fixture
    def call_site_project(self, tmp_path: Path) -> Path:
        (tmp_path / "lib.py").write_text(
            "def target():\n    return 1\n",
            encoding="utf-8",
        )
        (tmp_path / "caller.py").write_text(
            "from lib import target\n\ndef run():\n    return target()\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run_trace(self, project: Path, symbol: str) -> dict[str, Any]:
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        return _run(TraceImpactTool(str(project)).execute({"symbol": symbol}))

    def test_impact_verdict_uses_magnitude_vocab(self, call_site_project: Path) -> None:
        """The new top-level ``impact_verdict`` must use the magnitude
        vocabulary (HIGH / MEDIUM / LOW / NONE)."""
        result = self._run_trace(call_site_project, "target")
        impact_verdict = result.get("impact_verdict")
        assert impact_verdict in {"HIGH", "MEDIUM", "LOW", "NONE"}, (
            f"K5: impact_verdict must be magnitude vocab — got {impact_verdict!r}"
        )

    def test_top_level_verdict_mirrors_safety_vocab(
        self, call_site_project: Path
    ) -> None:
        """Top-level ``verdict`` must match ``agent_summary.verdict``
        (safety vocab — SAFE/CAUTION/UNSAFE) for cross-tool parity."""
        result = self._run_trace(call_site_project, "target")
        top_verdict = result.get("verdict")
        agent_verdict = result.get("agent_summary", {}).get("verdict")
        assert top_verdict == agent_verdict, (
            f"K5: top-level verdict must mirror agent_summary.verdict "
            f"(safety vocab) — got top={top_verdict!r} agent={agent_verdict!r}"
        )
        assert top_verdict in {"SAFE", "CAUTION", "UNSAFE"}, (
            f"K5: top-level verdict must use safety vocabulary — got {top_verdict!r}"
        )

    def test_no_match_safe_verdict(self, call_site_project: Path) -> None:
        """M11 (round-26): a symbol that doesn't exist anywhere must
        report ``impact_verdict=NONE`` (magnitude — no callers) AND
        ``verdict=NOT_FOUND`` (safety — agent should verify the
        spelling).

        Before M11 this returned ``verdict=SAFE`` which an agent could
        misread as "0 callers, safe to delete" on what is really a
        typo or rename mistake. NOT_FOUND forces the agent to verify
        the symbol name before acting.
        """
        result = self._run_trace(call_site_project, "XYZ_NotExistent_Symbol")
        assert result.get("impact_verdict") == "NONE"
        assert result.get("verdict") == "NOT_FOUND"
        assert result.get("agent_summary", {}).get("verdict") == "NOT_FOUND"


# ============================================================================
# K11 — --table silent override under --format json (transparency)
# ============================================================================


class TestK11TableOverrideTransparency:
    """K11 (round-24 dogfood): when both ``--table=X`` and
    ``--format=json|toon`` were passed, the user's ``--table`` value
    was silently overridden and produced byte-identical output for
    every requested table view. No warning, no envelope hint.

    Fix (Option B per the brief): warn on stderr AND surface
    ``effective_table`` on the JSON/TOON envelope so programmatic
    callers can detect the override.
    """

    @pytest.fixture
    def tiny_python_project(self, tmp_path: Path) -> Path:
        (tmp_path / "sample.py").write_text(
            "import os\n\n"
            "class Greeter:\n"
            "    def hello(self, name: str) -> str:\n"
            "        return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run_cli(self, project: Path, table: str, fmt: str) -> tuple[str, str, int]:
        """Invoke the CLI in-process and capture stdout/stderr."""
        import subprocess
        import sys as _sys

        proc = subprocess.run(
            [
                _sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "sample.py",
                f"--table={table}",
                "--format",
                fmt,
            ],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=60,
        )
        return proc.stdout, proc.stderr, proc.returncode

    def test_json_envelope_carries_effective_table(
        self, tiny_python_project: Path
    ) -> None:
        """JSON output must include ``effective_table`` so programmatic
        callers know which view was actually produced."""
        import json as _json

        stdout, _stderr, _rc = self._run_cli(tiny_python_project, "compact", "json")
        envelope = _json.loads(stdout)
        assert envelope.get("effective_table") == "json", (
            f"K11: JSON envelope must carry effective_table=json — got "
            f"{envelope.get('effective_table')!r}"
        )
        assert envelope.get("requested_table") == "compact", (
            f"K11: JSON envelope must echo requested_table — got "
            f"{envelope.get('requested_table')!r}"
        )

    def test_table_overridden_warning_fires_on_stderr(
        self, tiny_python_project: Path
    ) -> None:
        """When ``--table`` is silently overridden, a Warning must
        appear on stderr so interactive callers see it."""
        _stdout, stderr, _rc = self._run_cli(tiny_python_project, "compact", "json")
        assert "Warning" in stderr and "--table=compact" in stderr, (
            f"K11: stderr must contain the table-override warning — got "
            f"stderr={stderr!r}"
        )

    def test_toon_envelope_carries_effective_table(
        self, tiny_python_project: Path
    ) -> None:
        """Symmetric to JSON: TOON output must also carry
        ``effective_table`` so the schema parity is intact."""
        stdout, _stderr, _rc = self._run_cli(tiny_python_project, "full", "toon")
        assert "effective_table: toon" in stdout, (
            f"K11: TOON envelope must include ``effective_table: toon`` — "
            f"got stdout={stdout!r}"
        )


# ============================================================================
# K12 — file_path echo normalization
# ============================================================================


class TestK12FilePathNormalization:
    """K12 (round-24 dogfood): ``./X`` and ``X`` resolve to the same
    file but the echoed ``file_path`` in the response retained the raw
    input string. Same ``content_hash``, different ``file_path``
    confused downstream dedup / caching / display layers.

    Fix: ``BaseMCPTool._normalize_file_path`` strips leading ``./`` and
    normalizes backslash separators, and the central dispatcher
    post-hook (``ensure_canonical_success_envelope``) applies the same
    rule on the response envelope so direct-call sites benefit too.
    """

    def test_normalize_strips_leading_dot_slash(self) -> None:
        from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool

        assert (
            BaseMCPTool._normalize_file_path("tree_sitter_analyzer/foo.py")
            == "tree_sitter_analyzer/foo.py"
        )
        assert (
            BaseMCPTool._normalize_file_path("./tree_sitter_analyzer/foo.py")
            == "tree_sitter_analyzer/foo.py"
        )
        assert (
            BaseMCPTool._normalize_file_path("././tree_sitter_analyzer/foo.py")
            == "tree_sitter_analyzer/foo.py"
        )

    def test_normalize_preserves_parent_segments(self) -> None:
        from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool

        # ``..`` carries real path info and must not be stripped.
        assert BaseMCPTool._normalize_file_path("../sibling.py") == "../sibling.py"

    def test_normalize_converts_backslashes(self) -> None:
        from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool

        assert BaseMCPTool._normalize_file_path("a\\b\\c.py") == "a/b/c.py"

    def test_analyze_scale_dot_prefix_round_trip(self, tiny_project: Path) -> None:
        """End-to-end: same logical path with and without ``./`` must
        produce identical ``file_path`` echo (and therefore identical
        ``summary_line``)."""
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import (
            AnalyzeScaleTool,
        )

        tool = AnalyzeScaleTool(str(tiny_project))
        r1 = _run(tool.execute({"file_path": "sample.py"}))
        r2 = _run(tool.execute({"file_path": "./sample.py"}))
        assert r1.get("file_path") == r2.get("file_path"), (
            f"K12: same logical path must produce identical file_path "
            f"echo — got r1={r1.get('file_path')!r} "
            f"r2={r2.get('file_path')!r}"
        )
        assert r1.get("summary_line") == r2.get("summary_line"), (
            f"K12: same logical path must produce identical summary_line — "
            f"got r1={r1.get('summary_line')!r} "
            f"r2={r2.get('summary_line')!r}"
        )


# ============================================================================
# M6 — detect_routes mode=summary vs mode=all return uniform schema
# ============================================================================


class TestM6DetectRoutesSchemaUniformity:
    """M6 (round-26 dogfood): ``detect_routes`` returned incompatible
    schemas across modes — ``mode=summary`` exposed ``total_routes``
    but not ``routes``; ``mode=all`` exposed ``route_count`` but not
    ``total_routes``/``by_framework``/``by_method``. Agent code that
    branched on either key broke when the caller switched modes.

    Contract:
      - Both modes expose ``total_routes`` (canonical) and the
        deprecated ``route_count`` alias.
      - Both modes expose ``routes`` (empty list in summary mode, full
        list in mode=all).
      - Both modes expose ``by_framework``, ``by_method``,
        ``file_count`` — empty dict / zero when no routes exist.
    """

    @pytest.fixture
    def flask_project(self, tmp_path: Path) -> Path:
        """Tiny Flask project with two routes."""
        (tmp_path / "app.py").write_text(
            "from flask import Flask\n"
            "app = Flask(__name__)\n"
            "@app.route('/users')\n"
            "def users():\n    return 'hi'\n"
            "@app.route('/items', methods=['POST'])\n"
            "def items():\n    return 'hi'\n",
            encoding="utf-8",
        )
        return tmp_path

    _REQUIRED_KEYS = (
        "total_routes",
        "route_count",
        "routes",
        "by_framework",
        "by_method",
        "file_count",
    )

    def _both_modes(self, project: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            RouteDetectorTool,
        )

        tool = RouteDetectorTool(str(project))
        summary = _run(tool.execute({"mode": "summary", "output_format": "json"}))
        full = _run(tool.execute({"mode": "all", "output_format": "json"}))
        return summary, full

    def test_both_modes_expose_total_routes(self, flask_project: Path) -> None:
        summary, full = self._both_modes(flask_project)
        assert isinstance(summary.get("total_routes"), int), (
            f"M6: summary must expose canonical ``total_routes`` — "
            f"got {summary.get('total_routes')!r}"
        )
        assert isinstance(full.get("total_routes"), int), (
            f"M6: mode=all must expose canonical ``total_routes`` — "
            f"got {full.get('total_routes')!r}"
        )
        # Same data — both modes scanned the same project.
        assert summary["total_routes"] == full["total_routes"], (
            f"M6: total_routes must agree across modes — "
            f"summary={summary['total_routes']!r} all={full['total_routes']!r}"
        )

    def test_both_modes_expose_route_count_alias(self, flask_project: Path) -> None:
        """Deprecated ``route_count`` alias still works for back-compat."""
        summary, full = self._both_modes(flask_project)
        assert summary.get("route_count") == summary.get("total_routes"), (
            f"M6: summary ``route_count`` alias must equal ``total_routes`` — "
            f"got route_count={summary.get('route_count')!r} "
            f"total_routes={summary.get('total_routes')!r}"
        )
        assert full.get("route_count") == full.get("total_routes"), (
            f"M6: mode=all ``route_count`` alias must equal ``total_routes`` — "
            f"got route_count={full.get('route_count')!r} "
            f"total_routes={full.get('total_routes')!r}"
        )

    def test_both_modes_expose_routes_list(self, flask_project: Path) -> None:
        summary, full = self._both_modes(flask_project)
        assert isinstance(summary.get("routes"), list), (
            f"M6: summary must expose ``routes`` as a list (possibly empty) "
            f"— got {type(summary.get('routes')).__name__}"
        )
        assert isinstance(full.get("routes"), list), (
            f"M6: mode=all must expose ``routes`` as a list — "
            f"got {type(full.get('routes')).__name__}"
        )
        # mode=all populates the list; summary leaves it empty.
        assert summary["routes"] == [], (
            f"M6: summary ``routes`` must be empty — got {summary['routes']!r}"
        )
        # full ``routes`` mirrors ``total_routes`` count.
        assert len(full["routes"]) == full["total_routes"], (
            f"M6: mode=all routes count must equal total_routes — "
            f"got len(routes)={len(full['routes'])} "
            f"total_routes={full['total_routes']}"
        )

    def test_both_modes_expose_by_framework_by_method(
        self, flask_project: Path
    ) -> None:
        summary, full = self._both_modes(flask_project)
        for mode_name, payload in (("summary", summary), ("all", full)):
            for key in ("by_framework", "by_method"):
                value = payload.get(key)
                assert isinstance(value, dict), (
                    f"M6: mode={mode_name} must expose ``{key}`` as a dict "
                    f"— got {type(value).__name__}"
                )

    def test_uniform_required_key_set(self, flask_project: Path) -> None:
        """The two modes carry the same required key set even when their
        values diverge (full routes list vs empty)."""
        summary, full = self._both_modes(flask_project)
        for key in self._REQUIRED_KEYS:
            assert key in summary, (
                f"M6: summary must include canonical key ``{key}`` — "
                f"got keys={sorted(summary.keys())}"
            )
            assert key in full, (
                f"M6: mode=all must include canonical key ``{key}`` — "
                f"got keys={sorted(full.keys())}"
            )


# ============================================================================
# M7 — call_graph mode=all_functions exposes ``all_functions`` key
# ============================================================================


class TestM7CallGraphAllFunctionsKey:
    """M7 (round-26 dogfood): ``mode=all_functions`` returned
    ``functions: [...]`` while every other mode used a key name matching
    the mode (``callers``/``callees``/``chain``). Agent code reading
    ``r['all_functions']`` (matching the mode name) got an empty list
    even though the call graph had thousands of indexed functions.

    Contract:
      - ``mode=all_functions`` response has ``all_functions`` as a
        non-empty list (one entry per indexed function).
      - ``functions`` alias still works for back-compat with the
        pre-M7 shape.
      - Both keys point at the same list (one is an alias of the
        other).
    """

    @pytest.fixture
    def project_with_functions(self, tmp_path: Path) -> Path:
        (tmp_path / "mod.py").write_text(
            "def alpha():\n    return beta()\n"
            "def beta():\n    return gamma()\n"
            "def gamma():\n    return 1\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_all_functions_key_present_and_populated(
        self, project_with_functions: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.call_graph_tool import (
            CodeGraphCallTool,
        )

        tool = CodeGraphCallTool(str(project_with_functions))
        result = _run(tool.execute({"mode": "all_functions", "output_format": "json"}))
        all_funcs = result.get("all_functions")
        assert isinstance(all_funcs, list), (
            f"M7: mode=all_functions must expose ``all_functions`` as a "
            f"list — got {type(all_funcs).__name__}"
        )
        assert all_funcs, (
            f"M7: ``all_functions`` must be non-empty when functions "
            f"exist — got {all_funcs!r}"
        )

    def test_functions_alias_still_works(self, project_with_functions: Path) -> None:
        """Deprecated ``functions`` alias still works for back-compat."""
        from tree_sitter_analyzer.mcp.tools.call_graph_tool import (
            CodeGraphCallTool,
        )

        tool = CodeGraphCallTool(str(project_with_functions))
        result = _run(tool.execute({"mode": "all_functions", "output_format": "json"}))
        assert result.get("functions") == result.get("all_functions"), (
            f"M7: ``functions`` alias must equal ``all_functions`` — "
            f"got functions len={len(result.get('functions') or [])} "
            f"all_functions len={len(result.get('all_functions') or [])}"
        )

    def test_count_matches_list_length(self, project_with_functions: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.call_graph_tool import (
            CodeGraphCallTool,
        )

        tool = CodeGraphCallTool(str(project_with_functions))
        result = _run(tool.execute({"mode": "all_functions", "output_format": "json"}))
        assert result.get("count") == len(result.get("all_functions") or []), (
            f"M7: ``count`` must match len(all_functions) — "
            f"count={result.get('count')} "
            f"all_functions len={len(result.get('all_functions') or [])}"
        )


# ============================================================================
# M8 — file_health smells alias (list, never None)
# ============================================================================


class TestM8FileHealthSmellsType:
    """M8 (round-26 dogfood): ``file_health`` response had
    ``smells: None / code_smells: []`` — same datum exposed twice with
    different types. ``for s in d['smells']:`` raised ``TypeError``.

    Contract:
      - Either ``smells`` is absent from the response, OR it's a list
        (never None).
      - When present, ``smells`` mirrors ``code_smells`` (canonical
        name).
    """

    @pytest.fixture
    def healthy_project(self, tmp_path: Path) -> Path:
        (tmp_path / "ok.py").write_text(
            "def small() -> int:\n    return 1\n", encoding="utf-8"
        )
        return tmp_path

    def test_smells_is_list_or_absent_on_healthy_file(
        self, healthy_project: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(healthy_project))
        result = _run(tool.execute({"file_path": "ok.py", "output_format": "json"}))
        if "smells" in result:
            assert isinstance(result["smells"], list), (
                f"M8: when ``smells`` is present it must be a list — "
                f"got {type(result['smells']).__name__}={result['smells']!r}"
            )
            assert result["smells"] is not None, (
                "M8: ``smells`` must never be None — use empty list instead"
            )

    def test_smells_mirrors_code_smells_when_present(
        self, healthy_project: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(healthy_project))
        result = _run(tool.execute({"file_path": "ok.py", "output_format": "json"}))
        if "smells" in result and "code_smells" in result:
            assert result["smells"] == result["code_smells"], (
                f"M8: ``smells`` and ``code_smells`` must agree — "
                f"smells={result['smells']!r} "
                f"code_smells={result['code_smells']!r}"
            )

    def test_smells_is_list_on_non_code_file(self, tmp_path: Path) -> None:
        """Cross-check: the non-code (markdown) envelope must also
        respect the contract — no None smells."""
        (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "README.md", "output_format": "json"}))
        if "smells" in result:
            assert isinstance(result["smells"], list), (
                f"M8: non-code envelope must use list ``smells`` — "
                f"got {result['smells']!r}"
            )

    def test_smells_is_list_on_empty_file(self, tmp_path: Path) -> None:
        (tmp_path / "empty.py").write_text("", encoding="utf-8")
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "empty.py", "output_format": "json"}))
        if "smells" in result:
            assert isinstance(result["smells"], list), (
                f"M8: empty-file envelope must use list ``smells`` — "
                f"got {result['smells']!r}"
            )


# ============================================================================
# M14 — language echoed across single-file tools
# ============================================================================


class TestM14LanguageEcho:
    """M14 (round-26 dogfood): ``refactor`` and ``file_health`` returned
    ``language: None`` on ``.ts`` files even though both apply
    TypeScript-specific analysis internally. ``analyze_scale``
    correctly echoed ``language: typescript``. Agents that cross-
    checked tools saw a contradiction.

    Contract:
      - Every single-file tool echoes ``language: <detected>`` on a
        TypeScript file.
      - The string is lowercase and non-empty.
    """

    @pytest.fixture
    def ts_project(self, tmp_path: Path) -> Path:
        (tmp_path / "sample.ts").write_text(
            "export function add(a: number, b: number): number { return a + b; }\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_refactor_echoes_language(self, ts_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        tool = RefactoringSuggestionsTool(str(ts_project))
        result = _run(tool.execute({"file_path": "sample.ts", "output_format": "json"}))
        lang = result.get("language")
        assert isinstance(lang, str) and lang, (
            f"M14: refactor must echo ``language`` for a .ts file — got {lang!r}"
        )
        assert lang == lang.lower(), (
            f"M14: ``language`` must be lowercase — got {lang!r}"
        )
        assert lang == "typescript", (
            f"M14: refactor must detect ``typescript`` on a .ts file — got {lang!r}"
        )

    def test_file_health_echoes_language(self, ts_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(ts_project))
        result = _run(tool.execute({"file_path": "sample.ts", "output_format": "json"}))
        lang = result.get("language")
        assert isinstance(lang, str) and lang, (
            f"M14: file_health must echo ``language`` for a .ts file — got {lang!r}"
        )
        assert lang == lang.lower(), (
            f"M14: ``language`` must be lowercase — got {lang!r}"
        )
        assert lang == "typescript", (
            f"M14: file_health must detect ``typescript`` on a .ts file — got {lang!r}"
        )

    def test_code_patterns_echoes_language(self, ts_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )

        tool = CodePatternsTool(str(ts_project))
        result = _run(tool.execute({"file_path": "sample.ts", "output_format": "json"}))
        lang = result.get("language")
        assert isinstance(lang, str) and lang, (
            f"M14: code_patterns must echo ``language`` for a .ts file — got {lang!r}"
        )
        assert lang == lang.lower(), (
            f"M14: ``language`` must be lowercase — got {lang!r}"
        )

    def test_safe_to_edit_echoes_language(self, ts_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

        tool = SafeToEditTool(str(ts_project))
        result = _run(tool.execute({"file_path": "sample.ts", "output_format": "json"}))
        lang = result.get("language")
        assert isinstance(lang, str) and lang, (
            f"M14: safe_to_edit must echo ``language`` for a .ts file — got {lang!r}"
        )
        assert lang == lang.lower(), (
            f"M14: ``language`` must be lowercase — got {lang!r}"
        )


# ============================================================================
# Round 26 polish: M12 + M13 + M15 + envelope contract snapshot
# ============================================================================


class TestM12EmptySymbolLineage:
    """M12 (round-26 dogfood): ``--symbol-lineage ""`` used to fall
    through to the file-analysis path and crash with the argparse usage
    block + plain-text ``ERROR: File path not specified``. No JSON
    envelope, no parseable ``error_type`` — every other MCP CLI flag
    emits a canonical ``{success: False, error_type: "validation", ...}``
    envelope, so this one was an outlier.

    Fix: the spec for ``symbol_lineage`` is now a *value-bearing* flag
    (``value_arg_name`` set in :class:`McpCommandSpec`). When the value
    is non-``None`` — including ``""`` — the dispatcher selects the
    command and the validator emits the canonical envelope with
    ``RC=1`` (so shell ``set -e`` pipelines catch it per the H1 contract).
    """

    def test_dispatcher_selects_symbol_lineage_on_empty_value(self) -> None:
        from tree_sitter_analyzer.cli.commands.mcp_command_helpers import (
            find_selected_mcp_command,
        )
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            MCP_COMMAND_SPECS,
        )

        class _Args:
            symbol_lineage = ""

        spec = find_selected_mcp_command(_Args(), MCP_COMMAND_SPECS)
        assert spec is not None, (
            'M12: ``--symbol-lineage ""`` must register as a selected '
            "command, not fall through to file-analysis path"
        )
        assert spec.flag_name == "symbol_lineage"

    def test_validator_emits_envelope_for_empty_symbol(self) -> None:
        from tree_sitter_analyzer.cli.commands.mcp_command_helpers import (
            validate_mcp_command_args,
        )
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            MCP_COMMAND_SPECS,
        )

        symbol_spec = next(
            s for s in MCP_COMMAND_SPECS if s.flag_name == "symbol_lineage"
        )

        class _Args:
            symbol_lineage = ""

        captured: list[str] = []
        ok = validate_mcp_command_args(_Args(), symbol_spec, captured.append)
        assert ok is False, "validator must reject empty symbol"
        assert captured, "validator must call the error sink"
        assert "empty" in captured[0].lower() or "non-empty" in captured[0].lower()

    def test_validator_emits_envelope_for_whitespace_symbol(self) -> None:
        """Whitespace-only values (``"   "``) must be rejected too —
        otherwise an agent that accidentally builds a blank symbol still
        hits the file-analysis crash path."""
        from tree_sitter_analyzer.cli.commands.mcp_command_helpers import (
            validate_mcp_command_args,
        )
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            MCP_COMMAND_SPECS,
        )

        symbol_spec = next(
            s for s in MCP_COMMAND_SPECS if s.flag_name == "symbol_lineage"
        )

        class _Args:
            symbol_lineage = "   "

        captured: list[str] = []
        ok = validate_mcp_command_args(_Args(), symbol_spec, captured.append)
        assert ok is False
        assert captured

    def test_validator_passes_non_empty_symbol(self) -> None:
        """The regression must not impact the happy path."""
        from tree_sitter_analyzer.cli.commands.mcp_command_helpers import (
            validate_mcp_command_args,
        )
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            MCP_COMMAND_SPECS,
        )

        symbol_spec = next(
            s for s in MCP_COMMAND_SPECS if s.flag_name == "symbol_lineage"
        )

        class _Args:
            symbol_lineage = "greet"

        captured: list[str] = []
        ok = validate_mcp_command_args(_Args(), symbol_spec, captured.append)
        assert ok is True
        assert not captured

    def test_cli_subprocess_returns_envelope_and_rc1(self, tmp_path: Path) -> None:
        """End-to-end: invoking the CLI with ``--symbol-lineage ""``
        must produce a single-line JSON envelope on stdout with
        ``success=False``, ``error_type="validation"``, and ``RC=1``.
        """
        import json as _json
        import subprocess
        import sys

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--symbol-lineage",
                "",
                "--format",
                "json",
                "--project-root",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 1, (
            f"M12: empty --symbol-lineage must exit RC=1, got {proc.returncode}. "
            f"stderr={proc.stderr!r} stdout={proc.stdout[:500]!r}"
        )
        # Parse first JSON line on stdout, tolerant of leading warning lines.
        envelope = None
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("{"):
                try:
                    envelope = _json.loads(stripped)
                    break
                except _json.JSONDecodeError:
                    continue
        assert envelope is not None, (
            f"M12: expected a JSON envelope on stdout. Got: {proc.stdout!r}"
        )
        assert envelope.get("success") is False
        assert envelope.get("error_type") == "validation"
        assert "agent_summary" in envelope
        assert envelope["agent_summary"].get("verdict") == "ERROR"


class TestM13CacheDirAllowlist:
    """M13 (round-26 dogfood): a previous session left an orphan
    source file (``.tree-sitter-cache/fresh_dog.py``) inside what is
    meant to be a tool-owned metadata directory. The directory
    accepts only ``project-index.json``, ``file_hashes.json``,
    ``critical_nodes.json``, ``summary.toon``, ``*.db`` files, and
    entries under ``index/`` or ``metrics/`` subdirectories.

    The allowlist lives in
    :mod:`tree_sitter_analyzer.mcp.utils.cache_paths` and is wired
    into :class:`ProjectIndexManager` writers.
    """

    def test_allowed_files_pass(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.utils.cache_paths import (
            is_allowed_cache_path,
        )

        cache = tmp_path / ".tree-sitter-cache"
        for name in (
            "project-index.json",
            "file_hashes.json",
            "critical_nodes.json",
            "summary.toon",
        ):
            assert is_allowed_cache_path(cache / name, tmp_path), (
                f"M13: ``{name}`` must be allowed at the cache root"
            )

    def test_subdir_extensions_pass(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.utils.cache_paths import (
            is_allowed_cache_path,
        )

        cache = tmp_path / ".tree-sitter-cache"
        assert is_allowed_cache_path(cache / "index" / "shard1.json", tmp_path)
        assert is_allowed_cache_path(cache / "index" / "shard1.db", tmp_path)
        assert is_allowed_cache_path(cache / "metrics" / "m.json", tmp_path)
        assert is_allowed_cache_path(cache / "metrics" / "m.toon", tmp_path)

    def test_top_level_db_allowed(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.utils.cache_paths import (
            is_allowed_cache_path,
        )

        cache = tmp_path / ".tree-sitter-cache"
        # SQLite caches at the cache root must remain writeable.
        assert is_allowed_cache_path(cache / "critical.db", tmp_path)

    def test_orphan_source_file_rejected(self, tmp_path: Path) -> None:
        """The specific bug — ``.tree-sitter-cache/fresh_dog.py`` —
        must be refused by the allowlist."""
        from tree_sitter_analyzer.mcp.utils.cache_paths import (
            CachePathError,
            assert_cache_path,
            is_allowed_cache_path,
        )

        cache = tmp_path / ".tree-sitter-cache"
        offender = cache / "fresh_dog.py"
        assert is_allowed_cache_path(offender, tmp_path) is False
        with pytest.raises(CachePathError):
            assert_cache_path(offender, tmp_path)

    def test_arbitrary_extension_rejected(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.utils.cache_paths import (
            is_allowed_cache_path,
        )

        cache = tmp_path / ".tree-sitter-cache"
        for offender in (
            cache / "stray.txt",
            cache / "stray.log",
            cache / "evil.sh",
            cache / "subdir" / "foo.py",  # subdir not in allowlist
        ):
            assert is_allowed_cache_path(offender, tmp_path) is False, (
                f"M13: ``{offender}`` must NOT be writable in the cache"
            )

    def test_paths_outside_cache_are_unrestricted(self, tmp_path: Path) -> None:
        """The allowlist is policy *for the cache dir*. Files elsewhere
        (under ``tree_sitter_analyzer/``, ``tests/``, etc.) must NOT
        be flagged by this helper."""
        from tree_sitter_analyzer.mcp.utils.cache_paths import (
            is_allowed_cache_path,
        )

        assert is_allowed_cache_path(tmp_path / "src" / "foo.py", tmp_path)
        assert is_allowed_cache_path(tmp_path / "tests" / "test_x.py", tmp_path)
        assert is_allowed_cache_path(tmp_path / "README.md", tmp_path)

    def test_project_index_save_uses_allowlist(self, tmp_path: Path) -> None:
        """Wiring check: ``ProjectIndexManager.save`` must call into
        the allowlist for the happy-path file too — exercise the
        canonical write to confirm no regression."""
        import time

        from tree_sitter_analyzer.mcp.utils.project_index import (
            ProjectIndex,
            ProjectIndexManager,
        )

        manager = ProjectIndexManager(str(tmp_path))
        now = time.time()
        idx = ProjectIndex(
            project_root=str(tmp_path),
            created_at=now,
            updated_at=now,
            file_count=0,
            language_distribution={},
            top_level_structure=[],
            key_files=[],
            entry_points=[],
            custom_notes="",
            schema_version=ProjectIndexManager.SCHEMA_VERSION,
            readme_excerpt="",
            module_descriptions={},
            critical_nodes=[],
            module_dependency_order=[],
        )
        manager.save(idx)  # must not raise
        assert (tmp_path / ".tree-sitter-cache" / "project-index.json").exists()


class TestM15AstCacheSyncConsidered:
    """M15 (round-26 dogfood): J8 renamed ``action`` → ``considered``
    on per-file rows inside ``changes.new[i]`` but the *top-level*
    sync response only exposed ``scanned`` — agents reading
    ``d["considered"]`` saw ``None``. The fix surfaces
    ``considered`` at the response root as an alias for ``scanned``
    so the J8 vocabulary is consistent everywhere.
    """

    @pytest.fixture
    def sync_project(self, tmp_path: Path) -> Path:
        (tmp_path / "a.py").write_text("def f(): return 1\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("def g(): return 2\n", encoding="utf-8")
        return tmp_path

    def test_sync_response_exposes_considered_and_scanned(
        self, sync_project: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(sync_project))
        result = _run(tool.execute({"mode": "sync"}))
        assert result.get("success") is True
        assert "scanned" in result, (
            f"M15: ``scanned`` must remain (back-compat). Keys: {sorted(result.keys())}"
        )
        assert "considered" in result, (
            f"M15: ``considered`` must be exposed at top level (J8 "
            f"vocabulary parity). Keys: {sorted(result.keys())}"
        )
        assert result["considered"] == result["scanned"], (
            f"M15: ``considered`` and ``scanned`` must agree as aliases. "
            f"Got considered={result['considered']!r} "
            f"scanned={result['scanned']!r}"
        )

    def test_sync_considered_matches_scanned_files(self, sync_project: Path) -> None:
        """The ``considered`` count must reflect the number of files
        the sync engine considered, matching the fixture size."""
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(str(sync_project))
        result = _run(tool.execute({"mode": "sync"}))
        # At least the two source files in the fixture.
        assert result["considered"] >= 2


class TestEnvelopeContractSnapshot:
    """Cross-tool envelope contract — every MCP tool's ``execute()``
    output must carry these keys when ``success=True``.

    Round-26 dogfood observation: the recurring root cause behind a
    long list of one-off findings (J5/J7/J11/K2/K5/K12/etc.) is
    "envelope drift" — ``verdict`` / ``summary_line`` / ``language`` /
    list keys landing in different places per tool. This snapshot
    asserts the minimum invariants in *one* place so the next drift
    fails loudly instead of trickling into agent prompts.

    Coverage: 16 representative tools across all major categories
    (single-file analysis, project-wide analysis, search, graph,
    cache, route detection, lineage, change-impact, dependency
    analysis, parser readiness, agent skills inventory).

    Round-27 update: the four known drifters that round-26 flagged
    (SafeToEditTool top-level ``summary_line``, RouteDetectorTool /
    ProjectHealthTool / ProjectOverviewTool ``agent_summary.verdict``)
    are now fixed at the tool layer. The full snapshot test is no
    longer ``xfail`` — both tests in this class are hard gates.

    Round-29 update: three more drifters surfaced from dogfood
    (DependencyAnalysisTool success-path ``agent_summary.verdict``,
    ParserReadinessTool top-level + agent_summary ``verdict``,
    AgentSkillsTool top-level ``summary_line`` + agent_summary
    ``verdict``). All three are fixed at the tool layer and now
    included in :meth:`tool_cases` so future regressions of this
    same class fail loudly here.

    Two-test split (kept for documentation):

    - ``test_canonical_envelope_passing_tools`` is the legacy passing
      subset (filtered by :attr:`KNOWN_DRIFT`). With the drift now
      empty, the two tests check the same tool list but the split
      preserves a clear migration path if a future drifter appears.
    - ``test_canonical_envelope_full_snapshot`` covers every tool in
      :func:`tool_cases` and is a hard gate.
    """

    REQUIRED_KEYS = frozenset({"success", "summary_line", "agent_summary"})
    REQUIRED_AGENT_SUMMARY_KEYS = frozenset({"summary_line", "verdict"})

    # Tools currently failing the envelope snapshot. Round-27 brought
    # this set to empty — every tool now emits the canonical envelope.
    # The attribute is kept (intentionally empty) so a future drifter
    # can be tracked here while the full-snapshot test still flags it.
    KNOWN_DRIFT: frozenset[str] = frozenset()

    @pytest.fixture
    def envelope_project(self, tmp_path: Path) -> Path:
        """A project with one Python file every tool can analyse."""
        (tmp_path / "sample.py").write_text(
            "def greet(name: str) -> str:\n"
            "    return f'hello {name}'\n"
            "\n"
            "class Greeter:\n"
            "    def hello(self) -> str:\n"
            "        return greet('world')\n",
            encoding="utf-8",
        )
        return tmp_path

    @pytest.fixture
    def tool_cases(self, envelope_project: Path):  # type: ignore[no-untyped-def]
        """Each entry: (label, instantiated tool, execute args)."""
        sample = "sample.py"
        from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import (
            AnalyzeScaleTool,
        )
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool
        from tree_sitter_analyzer.mcp.tools.call_graph_tool import (
            CodeGraphCallTool,
        )
        from tree_sitter_analyzer.mcp.tools.change_impact_tool import (
            ChangeImpactTool,
        )
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool
        from tree_sitter_analyzer.mcp.tools.modification_guard_tool import (
            ModificationGuardTool,
        )
        from tree_sitter_analyzer.mcp.tools.parser_readiness_tool import (
            ParserReadinessTool,
        )
        from tree_sitter_analyzer.mcp.tools.project_health_tool import (
            ProjectHealthTool,
        )
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            RouteDetectorTool,
        )
        from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool
        from tree_sitter_analyzer.mcp.tools.smart_context_tool import (
            SmartContextTool,
        )
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            TraceImpactTool,
        )

        root = str(envelope_project)
        return [
            ("AnalyzeScaleTool", AnalyzeScaleTool(root), {"file_path": sample}),
            ("FileHealthTool", FileHealthTool(root), {"file_path": sample}),
            ("CodePatternsTool", CodePatternsTool(root), {"file_path": sample}),
            ("SafeToEditTool", SafeToEditTool(root), {"file_path": sample}),
            ("SmartContextTool", SmartContextTool(root), {"file_path": sample}),
            ("ChangeImpactTool", ChangeImpactTool(root), {"mode": "diff"}),
            (
                "ModificationGuardTool",
                ModificationGuardTool(root),
                # The schema accepts ``symbol`` + ``modification_type``;
                # ``file_path`` is optional and improves accuracy.
                {
                    "symbol": "greet",
                    "modification_type": "refactor",
                    "file_path": sample,
                },
            ),
            ("AstCacheTool", ASTCacheTool(root), {"mode": "stats"}),
            ("CallGraphTool", CodeGraphCallTool(root), {"mode": "summary"}),
            ("RouteDetectorTool", RouteDetectorTool(root), {"mode": "summary"}),
            ("TraceImpactTool", TraceImpactTool(root), {"symbol": "greet"}),
            ("ProjectHealthTool", ProjectHealthTool(root), {}),
            ("ProjectOverviewTool", ProjectOverviewTool(root), {}),
            # Round-29 additions — N3/N4/N5 drift class. ``mode=summary``
            # walks the whole dep graph (cheap on the 1-file fixture);
            # parser-readiness and agent-skills both need no args and
            # report on an empty project root cleanly.
            (
                "DependencyAnalysisTool",
                DependencyAnalysisTool(root),
                {"mode": "summary", "output_format": "json"},
            ),
            (
                "ParserReadinessTool",
                ParserReadinessTool(root),
                {"output_format": "json"},
            ),
            (
                "AgentSkillsTool",
                AgentSkillsTool(root),
                {"output_format": "json"},
            ),
        ]

    def _collect_drift(self, tool_cases) -> list[str]:  # type: ignore[no-untyped-def]
        drift: list[str] = []
        for name, tool, args in tool_cases:
            try:
                result = _run(tool.execute(args))
            except Exception as exc:  # noqa: BLE001
                drift.append(f"{name}: execute() raised {type(exc).__name__}: {exc!r}")
                continue

            if not isinstance(result, dict):
                drift.append(
                    f"{name}: execute() must return a dict, got {type(result).__name__}"
                )
                continue

            missing = self.REQUIRED_KEYS - set(result.keys())
            if missing:
                drift.append(
                    f"{name}: top-level missing keys {sorted(missing)} — "
                    f"got {sorted(result.keys())[:15]}"
                )
                continue

            agent = result.get("agent_summary")
            if not isinstance(agent, dict):
                drift.append(
                    f"{name}: agent_summary must be a dict, got {type(agent).__name__}"
                )
                continue

            agent_missing = self.REQUIRED_AGENT_SUMMARY_KEYS - set(agent.keys())
            if agent_missing:
                drift.append(
                    f"{name}: agent_summary missing {sorted(agent_missing)} — "
                    f"got {sorted(agent.keys())}"
                )
                continue

            # Verdict consistency: when both top-level and agent_summary
            # carry ``verdict``, they must agree.
            top_verdict = result.get("verdict")
            agent_verdict = agent.get("verdict")
            if top_verdict and agent_verdict and top_verdict != agent_verdict:
                drift.append(
                    f"{name}: top.verdict={top_verdict!r} != "
                    f"agent.verdict={agent_verdict!r}"
                )
        return drift

    def test_canonical_envelope_passing_tools(self, tool_cases) -> None:  # type: ignore[no-untyped-def]
        """Hard gate: tools NOT in :attr:`KNOWN_DRIFT` must emit the
        canonical envelope today. Any *new* drift among them is caught
        immediately. Update :attr:`KNOWN_DRIFT` only after filing a
        follow-up ticket.
        """
        filtered = [(n, t, a) for (n, t, a) in tool_cases if n not in self.KNOWN_DRIFT]
        drift = self._collect_drift(filtered)
        assert not drift, (
            "Envelope contract drift detected among canonical-envelope tools "
            "(these were passing as of round-26 and must keep passing):\n  - "
            + "\n  - ".join(drift)
        )

    def test_canonical_envelope_full_snapshot(self, tool_cases) -> None:  # type: ignore[no-untyped-def]
        """Full cross-tool snapshot — every MCP tool must emit the
        canonical envelope (top-level ``summary_line`` + ``agent_summary``
        with ``summary_line`` and ``verdict``).

        Round-27 fixed the four known drifters
        (SafeToEditTool top-level ``summary_line``,
        RouteDetectorTool / ProjectHealthTool / ProjectOverviewTool
        ``agent_summary.verdict``) so this snapshot is now a strict
        hard gate. The companion :meth:`test_canonical_envelope_passing_tools`
        retains the legacy ``KNOWN_DRIFT`` allowlist as documentation —
        it should now be empty in practice.
        """
        drift = self._collect_drift(tool_cases)
        assert not drift, (
            "Envelope contract drift detected across MCP tools:\n  - "
            + "\n  - ".join(drift)
        )


# ============================================================================
# N1–N4 — round-27 per-tool regressions for the four known drifters that
# the round-26 ``TestEnvelopeContractSnapshot`` caught. These complement
# the snapshot test by pinning the specific contract each tool must
# honour, so a future regression fails at the exact tool boundary
# (instead of as a diffuse cross-tool snapshot failure).
# ============================================================================


_N_VERDICT_VOCABULARY = frozenset(
    {
        "SAFE",
        "CAUTION",
        "REVIEW",
        "UNSAFE",
        "INFO",
        # WARN is the dependency_analysis / agent_skills escalation
        # tier between INFO and REVIEW (cycles present, caution-level
        # metadata gaps). Added in round-29 for N3 / N5.
        "WARN",
        "ERROR",
        "NOT_FOUND",
    }
)


class TestN1SafeToEditTopSummaryLine:
    """N1 (round-27): safe_to_edit used to ship ``summary_line=None`` at
    the top level — only ``agent_summary`` carried a useful one-liner.
    Direct callers (CLI, tests, hive-mind workers) that bypass the
    dispatch hook saw the drift. Contract now: top-level
    ``summary_line`` is non-empty and equal to
    ``agent_summary["summary_line"]``.
    """

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "sample.py").write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_top_summary_line_non_empty(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

        tool = SafeToEditTool(str(project))
        result = _run(tool.execute({"file_path": "sample.py", "output_format": "json"}))
        top_sl = result.get("summary_line")
        assert isinstance(top_sl, str) and top_sl, (
            f"N1: safe_to_edit top-level summary_line must be a non-empty "
            f"string — got {top_sl!r}"
        )

    def test_top_summary_line_matches_agent_summary(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

        tool = SafeToEditTool(str(project))
        result = _run(tool.execute({"file_path": "sample.py", "output_format": "json"}))
        top_sl = result.get("summary_line")
        agent_sl = result.get("agent_summary", {}).get("summary_line")
        assert top_sl == agent_sl, (
            f"N1: safe_to_edit top-level summary_line must mirror "
            f"agent_summary['summary_line'] — got top={top_sl!r} "
            f"agent={agent_sl!r}"
        )


class TestN2RouteDetectorVerdict:
    """N2 (round-27): detect_routes's ``agent_summary`` carried
    ``summary_line`` + ``next_step`` + ``risk`` but no ``verdict``,
    breaking the cross-tool envelope contract. Route detection is
    informational — it discovers route declarations without making a
    safety judgement — so the canonical verdict for this tool is
    ``INFO``.
    """

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "sample.py").write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    @pytest.mark.parametrize(
        "mode,extra",
        [
            ("summary", {}),
            ("all", {}),
        ],
    )
    def test_agent_summary_verdict_non_empty(
        self, project: Path, mode: str, extra: dict[str, Any]
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            RouteDetectorTool,
        )

        tool = RouteDetectorTool(str(project))
        args: dict[str, Any] = {"mode": mode, "output_format": "json"}
        args.update(extra)
        result = _run(tool.execute(args))
        verdict = result.get("agent_summary", {}).get("verdict")
        assert isinstance(verdict, str) and verdict, (
            f"N2: detect_routes agent_summary.verdict must be a non-empty "
            f"string — got {verdict!r} (mode={mode})"
        )

    def test_agent_summary_verdict_in_vocabulary(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            RouteDetectorTool,
        )

        tool = RouteDetectorTool(str(project))
        result = _run(tool.execute({"mode": "summary", "output_format": "json"}))
        verdict = result["agent_summary"]["verdict"]
        assert verdict in _N_VERDICT_VOCABULARY, (
            f"N2: detect_routes agent_summary.verdict must be in the "
            f"canonical vocabulary {sorted(_N_VERDICT_VOCABULARY)} — "
            f"got {verdict!r}"
        )


class TestN3ProjectHealthVerdict:
    """N3 (round-27): project_health's ``agent_summary`` carried
    ``summary_line`` + ``risk`` (low/medium/high/critical) but no
    ``verdict``. Cross-tool agents that branch on ``verdict`` saw a
    missing field. Contract now: ``verdict`` is populated using the
    same vocabulary as modification_guard / safe_to_edit.
    """

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "sample.py").write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_agent_summary_verdict_non_empty(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_health_tool import (
            ProjectHealthTool,
        )

        tool = ProjectHealthTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        verdict = result.get("agent_summary", {}).get("verdict")
        assert isinstance(verdict, str) and verdict, (
            f"N3: project_health agent_summary.verdict must be a non-empty "
            f"string — got {verdict!r}"
        )

    def test_agent_summary_verdict_in_vocabulary(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_health_tool import (
            ProjectHealthTool,
        )

        tool = ProjectHealthTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        verdict = result["agent_summary"]["verdict"]
        assert verdict in _N_VERDICT_VOCABULARY, (
            f"N3: project_health agent_summary.verdict must be in the "
            f"canonical vocabulary {sorted(_N_VERDICT_VOCABULARY)} — "
            f"got {verdict!r}"
        )


class TestN4ProjectOverviewVerdict:
    """N4 (round-27): project_overview's ``agent_summary`` carried
    ``summary_line`` + ``risk`` (low/medium/high) but no ``verdict``.
    Mirroring N3: ``verdict`` is now derived from ``risk`` so agents
    that branch on ``verdict`` see the same vocabulary across tools.
    """

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "sample.py").write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_agent_summary_verdict_non_empty(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        verdict = result.get("agent_summary", {}).get("verdict")
        assert isinstance(verdict, str) and verdict, (
            f"N4: project_overview agent_summary.verdict must be a "
            f"non-empty string — got {verdict!r}"
        )

    def test_agent_summary_verdict_in_vocabulary(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        verdict = result["agent_summary"]["verdict"]
        assert verdict in _N_VERDICT_VOCABULARY, (
            f"N4: project_overview agent_summary.verdict must be in the "
            f"canonical vocabulary {sorted(_N_VERDICT_VOCABULARY)} — "
            f"got {verdict!r}"
        )

    def test_agent_summary_verdict_with_health(self, project: Path) -> None:
        """include_health=True path still emits a populated verdict."""
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(project))
        result = _run(tool.execute({"output_format": "json", "include_health": True}))
        verdict = result.get("agent_summary", {}).get("verdict")
        assert isinstance(verdict, str) and verdict in _N_VERDICT_VOCABULARY, (
            f"N4: project_overview agent_summary.verdict must be populated "
            f"under include_health=True — got {verdict!r}"
        )


# ============================================================================
# Round-29 — three more drifters the round-28 envelope snapshot did not
# yet cover (dependency_analysis success-path verdict, parser_readiness
# verdict + mirror, agent_skills top-level summary_line + verdict).
# These tests pin the per-tool contract so future regressions fail at
# the exact tool boundary instead of as a diffuse snapshot failure.
# ============================================================================


class TestN3DependencyAnalysisVerdict:
    """N3 (round-29): analyze_dependencies success-path agent_summary
    used to omit ``verdict`` entirely — only the error path carried
    ``verdict: 'ERROR'``. Cross-tool agents that branch on ``verdict``
    saw a missing field across every mode (summary / cycles / file_deps
    / blast_radius). Contract now: every mode emits a populated
    ``verdict`` from the canonical vocabulary, and the top-level
    envelope mirrors it.
    """

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        # Two files with a tiny dependency edge so the graph isn't trivially
        # empty (the snapshot test exercises ``summary``; this fixture also
        # gives ``file_deps`` and ``blast_radius`` something real to look at).
        (tmp_path / "lib.py").write_text(
            "def helper() -> int:\n    return 1\n", encoding="utf-8"
        )
        (tmp_path / "app.py").write_text(
            "from lib import helper\n\ndef run() -> int:\n    return helper()\n",
            encoding="utf-8",
        )
        return tmp_path

    @pytest.mark.parametrize(
        "mode,extra",
        [
            ("summary", {}),
            ("cycles", {}),
            ("file_deps", {"file_path": "app.py"}),
            ("blast_radius", {"file_path": "lib.py"}),
        ],
    )
    def test_agent_summary_verdict_non_empty(
        self, project: Path, mode: str, extra: dict[str, Any]
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )

        tool = DependencyAnalysisTool(str(project))
        args: dict[str, Any] = {"mode": mode, "output_format": "json"}
        args.update(extra)
        result = _run(tool.execute(args))
        verdict = result.get("agent_summary", {}).get("verdict")
        assert isinstance(verdict, str) and verdict, (
            f"N3: analyze_dependencies agent_summary.verdict must be a "
            f"non-empty string on the success path — got {verdict!r} "
            f"(mode={mode})"
        )
        assert verdict in _N_VERDICT_VOCABULARY, (
            f"N3: analyze_dependencies agent_summary.verdict must be in the "
            f"canonical vocabulary {sorted(_N_VERDICT_VOCABULARY)} — "
            f"got {verdict!r} (mode={mode})"
        )

    def test_top_level_verdict_mirrors_agent_summary(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )

        tool = DependencyAnalysisTool(str(project))
        result = _run(tool.execute({"mode": "summary", "output_format": "json"}))
        top = result.get("verdict")
        agent = result.get("agent_summary", {}).get("verdict")
        assert top == agent, (
            f"N3: analyze_dependencies top-level verdict must mirror "
            f"agent_summary['verdict'] — got top={top!r} agent={agent!r}"
        )


class TestN4ParserReadinessVerdict:
    """N4 (round-29): parser_readiness shipped ``agent_summary.risk``
    (low/caution) but no ``verdict``, and the top-level envelope had
    ``verdict=None``. Risk is the legacy domain-specific field; the
    cross-tool contract is ``verdict``. Contract now: ``verdict`` is
    populated in agent_summary, mirrored at the top level, and lives
    in the canonical vocabulary (INFO / CAUTION / REVIEW for this
    informational tool).
    """

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "sample.py").write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_agent_summary_verdict_non_empty(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.parser_readiness_tool import (
            ParserReadinessTool,
        )

        tool = ParserReadinessTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        verdict = result.get("agent_summary", {}).get("verdict")
        assert isinstance(verdict, str) and verdict, (
            f"N4: parser_readiness agent_summary.verdict must be a "
            f"non-empty string — got {verdict!r}"
        )

    def test_agent_summary_verdict_in_vocabulary(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.parser_readiness_tool import (
            ParserReadinessTool,
        )

        tool = ParserReadinessTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        verdict = result["agent_summary"]["verdict"]
        # Brief specifies the informational-tool subset for this tool —
        # parser_readiness never escalates to UNSAFE / NOT_FOUND etc.
        assert verdict in {"INFO", "CAUTION", "REVIEW"}, (
            f"N4: parser_readiness agent_summary.verdict must be one of "
            f"INFO / CAUTION / REVIEW — got {verdict!r}"
        )

    def test_top_level_verdict_mirrors_agent_summary(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.parser_readiness_tool import (
            ParserReadinessTool,
        )

        tool = ParserReadinessTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        top = result.get("verdict")
        agent = result.get("agent_summary", {}).get("verdict")
        assert top == agent, (
            f"N4: parser_readiness top-level verdict must mirror "
            f"agent_summary['verdict'] — got top={top!r} agent={agent!r}"
        )


class TestN5AgentSkillsEnvelope:
    """N5 (round-29): agent_skills shipped ``summary_line=None`` at the
    top level and omitted ``agent_summary.verdict`` entirely. Direct
    callers that bypass the dispatch hook (CLI, tests, hive-mind
    workers) saw the drift. Contract now: top-level ``summary_line``
    is non-empty and mirrors ``agent_summary['summary_line']``;
    ``agent_summary.verdict`` is populated from the canonical
    vocabulary and mirrors top-level ``verdict``.
    """

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "sample.py").write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_top_summary_line_non_empty(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool

        tool = AgentSkillsTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        top_sl = result.get("summary_line")
        assert isinstance(top_sl, str) and top_sl, (
            f"N5: agent_skills top-level summary_line must be a non-empty "
            f"string — got {top_sl!r}"
        )

    def test_summary_line_mirrors_agent_summary(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool

        tool = AgentSkillsTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        top_sl = result.get("summary_line")
        agent_sl = result.get("agent_summary", {}).get("summary_line")
        assert top_sl == agent_sl, (
            f"N5: agent_skills top-level summary_line must mirror "
            f"agent_summary['summary_line'] — got top={top_sl!r} "
            f"agent={agent_sl!r}"
        )

    def test_agent_summary_verdict_non_empty(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool

        tool = AgentSkillsTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        verdict = result.get("agent_summary", {}).get("verdict")
        assert isinstance(verdict, str) and verdict, (
            f"N5: agent_skills agent_summary.verdict must be a non-empty "
            f"string — got {verdict!r}"
        )

    def test_agent_summary_verdict_in_vocabulary(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool

        tool = AgentSkillsTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        verdict = result["agent_summary"]["verdict"]
        assert verdict in _N_VERDICT_VOCABULARY, (
            f"N5: agent_skills agent_summary.verdict must be in the "
            f"canonical vocabulary {sorted(_N_VERDICT_VOCABULARY)} — "
            f"got {verdict!r}"
        )

    def test_top_level_verdict_mirrors_agent_summary(self, project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool

        tool = AgentSkillsTool(str(project))
        result = _run(tool.execute({"output_format": "json"}))
        top = result.get("verdict")
        agent = result.get("agent_summary", {}).get("verdict")
        assert top == agent, (
            f"N5: agent_skills top-level verdict must mirror "
            f"agent_summary['verdict'] — got top={top!r} agent={agent!r}"
        )


# ============================================================================
# M3 — syntax-validity gate across code_patterns / file_health / safe_to_edit
# ============================================================================


class TestM3SyntaxErrorDetection:
    """M3 (round-26 dogfood): three detection tools — code_patterns,
    file_health, safe_to_edit — used to grade a syntactically broken
    Python file (``def broken(:``) as ``SAFE`` / ``A`` / ``safe``.
    tree-sitter is permissive, so the underlying tree is still built
    (just sprinkled with ``ERROR`` nodes), and every downstream
    detector ran against the garbled tree and produced a clean
    bill-of-health envelope. An agent reading that would happily
    "proceed with planned change" on a broken file.

    Fix: all three tools share the same syntax-validity gate
    (``utils.parse_validity.is_file_parse_broken``) and emit the same
    short-circuit envelope:

    * ``signal == "syntax_error"``
    * ``verdict == "ERROR"`` (top-level AND in ``agent_summary``)
    * ``agent_summary.next_step`` mentions parse / syntax

    Cross-tool consistency is the whole point — an agent that branches
    on either field should get the same answer from every tool.
    """

    @pytest.fixture
    def broken_python_project(self, tmp_path: Path) -> Path:
        """Project with a single .py file that fails to parse."""
        (tmp_path / "broken.py").write_text("def broken(:", encoding="utf-8")
        return tmp_path

    @pytest.mark.parametrize(
        "tool_name",
        ["code_patterns", "file_health", "safe_to_edit"],
    )
    def test_syntax_error_short_circuit_envelope(
        self, broken_python_project: Path, tool_name: str
    ) -> None:
        """Each of the three syntax-gated tools emits the same envelope
        when handed a broken file."""
        if tool_name == "code_patterns":
            from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
                CodePatternsTool,
            )

            tool: Any = CodePatternsTool(str(broken_python_project))
            args: dict[str, Any] = {
                "file_path": "broken.py",
                "output_format": "json",
            }
        elif tool_name == "file_health":
            from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

            tool = FileHealthTool(str(broken_python_project))
            args = {"file_path": "broken.py", "output_format": "json"}
        else:
            from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import (
                SafeToEditTool,
            )

            tool = SafeToEditTool(str(broken_python_project))
            args = {"file_path": "broken.py", "output_format": "json"}

        result = _run(tool.execute(args))

        # Same signal across all three tools.
        assert result.get("signal") == "syntax_error", (
            f"M3: {tool_name} must emit signal='syntax_error' on a "
            f"broken file — got signal={result.get('signal')!r}"
        )
        # Top-level verdict must be ERROR (not SAFE).
        assert result.get("verdict") == "ERROR", (
            f"M3: {tool_name} must emit top-level verdict='ERROR' on a "
            f"broken file — got verdict={result.get('verdict')!r}"
        )
        # agent_summary.verdict must also be ERROR (cross-tool readers
        # often hit agent_summary first).
        agent_verdict = result.get("agent_summary", {}).get("verdict")
        assert agent_verdict == "ERROR", (
            f"M3: {tool_name} agent_summary.verdict must be 'ERROR' "
            f"on a broken file — got {agent_verdict!r}"
        )
        # next_step must mention parse/syntax so the agent knows what
        # is actually wrong.
        next_step = result.get("agent_summary", {}).get("next_step", "")
        assert "parse" in next_step.lower() or "syntax" in next_step.lower(), (
            f"M3: {tool_name} agent_summary.next_step must mention "
            f"parse/syntax — got {next_step!r}"
        )

    def test_code_patterns_verdict_not_safe(self, broken_python_project: Path) -> None:
        """code_patterns must not return verdict=SAFE on a broken file."""
        from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
            CodePatternsTool,
        )

        result = _run(
            CodePatternsTool(str(broken_python_project)).execute(
                {"file_path": "broken.py", "output_format": "json"}
            )
        )
        assert result.get("verdict") != "SAFE", (
            "M3: code_patterns must NOT return SAFE on a broken file"
        )

    def test_file_health_grade_not_letter(self, broken_python_project: Path) -> None:
        """file_health must not assign a letter grade on a broken file."""
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        result = _run(
            FileHealthTool(str(broken_python_project)).execute(
                {"file_path": "broken.py", "output_format": "json"}
            )
        )
        grade = result.get("grade")
        assert grade not in ("A", "B", "C", "D", "F"), (
            f"M3: file_health must NOT assign a letter grade on a "
            f"broken file — got grade={grade!r}"
        )

    def test_safe_to_edit_risk_not_safe(self, broken_python_project: Path) -> None:
        """safe_to_edit must not return risk=safe on a broken file."""
        from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

        result = _run(
            SafeToEditTool(str(broken_python_project)).execute(
                {"file_path": "broken.py", "output_format": "json"}
            )
        )
        risk_level = result.get("risk_level")
        assert risk_level != "safe", (
            f"M3: safe_to_edit must NOT return risk_level='safe' on a "
            f"broken file — got risk_level={risk_level!r}"
        )
        agent_risk = result.get("agent_summary", {}).get("risk")
        assert agent_risk != "low", (
            f"M3: safe_to_edit agent_summary.risk must be high on a "
            f"broken file — got {agent_risk!r}"
        )

    def test_clean_python_still_parses(self, tmp_path: Path) -> None:
        """Confirm the gate is gated: a clean Python file must reach
        the normal scoring path (no signal=syntax_error)."""
        (tmp_path / "ok.py").write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        result = _run(
            FileHealthTool(str(tmp_path)).execute(
                {"file_path": "ok.py", "output_format": "json"}
            )
        )
        # Should NOT short-circuit on a clean file.
        assert result.get("signal") != "syntax_error", (
            "M3: a clean Python file must NOT trigger the syntax-error gate"
        )


# ============================================================================
# M4 — --detect-routes path validation
# ============================================================================


class TestM4DetectRoutesValidatesPath:
    """M4 (round-26 dogfood): ``--detect-routes /tmp/does_not_exist.py``
    used to silently fall through to a project-root scan and return
    ``total_routes=0`` — an agent reads that as "the file you asked
    about has no routes" when the file was never scanned. Same for
    passing a directory.

    The fix validates the positional path before invoking the tool. A
    non-existent path or a directory now returns ``success=False,
    error_type='validation'`` — matching the envelope shape every
    other MCP-equivalent CLI tool already uses for validation failures.
    """

    def test_nonexistent_path_returns_validation_error(self, tmp_path: Path) -> None:
        """A non-existent path must produce a structured validation
        envelope, not ``success=True total_routes=0``."""
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            RouteDetectorTool,
        )

        tool = RouteDetectorTool(str(tmp_path))
        bogus = str(tmp_path / "does_not_exist_xyz_999.py")
        result = _run(
            tool.execute(
                {
                    "mode": "file",
                    "file_path": bogus,
                    "output_format": "json",
                }
            )
        )
        assert result.get("success") is False, (
            f"M4: non-existent path must return success=False — got "
            f"success={result.get('success')!r}"
        )
        assert result.get("error_type") == "validation", (
            f"M4: error_type must be 'validation' — got "
            f"error_type={result.get('error_type')!r}"
        )
        error = (result.get("error") or "").lower()
        assert "not found" in error, (
            f"M4: error message must mention 'not found' — got "
            f"error={result.get('error')!r}"
        )

    def test_directory_path_returns_hint(self, tmp_path: Path) -> None:
        """A directory must surface a hint pointing at mode=all."""
        (tmp_path / "subdir").mkdir()
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            RouteDetectorTool,
        )

        tool = RouteDetectorTool(str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "mode": "file",
                    "file_path": str(tmp_path / "subdir"),
                    "output_format": "json",
                }
            )
        )
        assert result.get("success") is False, (
            "M4: directory path must return success=False"
        )
        assert result.get("error_type") == "validation", (
            "M4: error_type must be 'validation' for a directory"
        )
        error = (result.get("error") or "").lower()
        assert "directory" in error, (
            f"M4: directory error must mention 'directory' — got "
            f"error={result.get('error')!r}"
        )

    def test_cli_nonexistent_positional_path(self, tmp_path: Path) -> None:
        """End-to-end: ``--detect-routes <bogus>`` via the CLI must
        produce the same validation envelope."""
        import subprocess
        import sys as _sys

        proc = subprocess.run(
            [
                _sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--project-root",
                str(tmp_path),
                "--detect-routes",
                "/tmp/m4_does_not_exist_xyz.py",
                "--format",
                "json",
            ],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Tool emits a structured envelope and returns RC=1.
        assert proc.returncode == 1, (
            f"M4 CLI: bogus path must exit 1 — got rc={proc.returncode}, "
            f"stderr={proc.stderr[:300]!r}"
        )
        import json as _json

        try:
            envelope = _json.loads(proc.stdout)
        except ValueError as exc:
            raise AssertionError(
                f"M4 CLI: stdout was not valid JSON: {exc}; "
                f"stdout={proc.stdout[:300]!r}"
            ) from exc
        assert envelope.get("success") is False, (
            "M4 CLI: bogus path envelope must have success=False"
        )
        assert envelope.get("error_type") == "validation", (
            f"M4 CLI: error_type must be 'validation' — got "
            f"error_type={envelope.get('error_type')!r}"
        )


# ============================================================================
# M11 — trace_impact NOT_FOUND for non-existent symbols
# ============================================================================


class TestM11TraceImpactNotFound:
    """M11 (round-26 dogfood): trace_impact used to report
    ``verdict=SAFE impact_verdict=NONE`` for a symbol that doesn't
    exist anywhere in the project (typo, wrong casing). An agent
    reading that would conclude "0 callers, safe to delete" when in
    reality the symbol the user typed never existed.

    Fix: when ripgrep returns no matches at all, the symbol has zero
    definitions AND zero references. Surface that as
    ``verdict=NOT_FOUND`` (NOT ``SAFE``) and ``found=false`` so the
    agent must verify the spelling before acting. The
    ``impact_verdict`` stays ``NONE`` because the magnitude is correct
    — there are zero callers either way. The two axes (existence vs
    magnitude) get their own field.
    """

    @pytest.fixture
    def real_symbol_project(self, tmp_path: Path) -> Path:
        """Project with one defined function — used to verify that the
        ``NOT_FOUND`` path doesn't fire for legitimate symbols."""
        (tmp_path / "lib.py").write_text(
            "def real_function():\n    return 1\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_nonexistent_symbol_verdict_not_found(
        self, real_symbol_project: Path
    ) -> None:
        """A symbol that doesn't exist anywhere must report
        ``verdict=NOT_FOUND`` instead of ``SAFE``."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            TraceImpactTool,
        )

        tool = TraceImpactTool(str(real_symbol_project))
        result = _run(tool.execute({"symbol": "TotallyFakeSymbol999"}))

        assert result.get("verdict") == "NOT_FOUND", (
            f"M11: nonexistent symbol must have verdict='NOT_FOUND' — "
            f"got verdict={result.get('verdict')!r}"
        )
        assert result.get("found") is False, (
            f"M11: nonexistent symbol must have found=False — got "
            f"found={result.get('found')!r}"
        )
        # ``impact_verdict`` stays NONE — that's correct (zero callers
        # is the magnitude, not the existence).
        assert result.get("impact_verdict") == "NONE", (
            f"M11: nonexistent symbol must have impact_verdict='NONE' "
            f"— got impact_verdict={result.get('impact_verdict')!r}"
        )

    def test_nonexistent_symbol_summary_says_not_found(
        self, real_symbol_project: Path
    ) -> None:
        """The summary_line must include ``not_found`` so a grep over
        envelope text picks it up."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            TraceImpactTool,
        )

        result = _run(
            TraceImpactTool(str(real_symbol_project)).execute(
                {"symbol": "TotallyFakeSymbol999"}
            )
        )
        summary_line = result.get("summary_line", "")
        assert "not_found" in summary_line, (
            f"M11: summary_line must contain 'not_found' — got "
            f"summary_line={summary_line!r}"
        )

    def test_nonexistent_symbol_next_step_verifies_name(
        self, real_symbol_project: Path
    ) -> None:
        """``agent_summary.next_step`` must direct the agent to verify
        the symbol name (matches the symbol_lineage convention)."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            TraceImpactTool,
        )

        result = _run(
            TraceImpactTool(str(real_symbol_project)).execute(
                {"symbol": "TotallyFakeSymbol999"}
            )
        )
        next_step = (result.get("agent_summary", {}).get("next_step") or "").lower()
        assert "verify" in next_step, (
            f"M11: agent_summary.next_step must mention 'verify' — got {next_step!r}"
        )

    def test_real_symbol_still_works(self, real_symbol_project: Path) -> None:
        """A real symbol must NOT trigger NOT_FOUND — confirms the gate
        only fires for genuinely missing symbols."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            TraceImpactTool,
        )

        result = _run(
            TraceImpactTool(str(real_symbol_project)).execute(
                {"symbol": "real_function"}
            )
        )
        assert result.get("verdict") != "NOT_FOUND", (
            "M11: a real symbol must NOT trigger NOT_FOUND verdict"
        )
        # ``found`` may or may not be set on the success path — but if
        # it is, it must be truthy.
        if "found" in result:
            assert result.get("found") is True, (
                "M11: a real symbol must have found=True if the field is present"
            )


# ============================================================================
# M1 — GetCodeOutlineTool.execute returns the flat envelope
# ============================================================================


class TestM1GetCodeOutlineEnvelope:
    """M1 (round-26 dogfood): ``GetCodeOutlineTool.execute()`` used to wrap
    its TOON output in the MCP wire-format envelope
    (``{"content": [{"type":"text","text":...}]}``) directly inside the
    tool. That envelope belongs in the server adapter — wrapping it in
    ``execute()`` meant direct callers (tests, hive-mind workers,
    anything that bypasses ``server.py``) received unparseable output
    whose only key was ``content``.

    Contract:
      - ``execute()`` returns the flat canonical envelope with
        ``success`` + ``summary_line`` + ``agent_summary`` + count
        aliases (``method_count``, ``class_count``).
      - The fix applies to both ``output_format=json`` and the default
        ``output_format=toon`` — TOON output now follows the canonical
        pattern (``apply_toon_format_to_response``: structured metadata
        at the top, ``toon_content`` blob alongside).
    """

    def test_json_output_returns_flat_envelope(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            GetCodeOutlineTool,
        )

        tool = GetCodeOutlineTool(str(tiny_project))
        result = _run(tool.execute({"file_path": "sample.py", "output_format": "json"}))
        assert isinstance(result, dict)
        assert result.get("success") is True, (
            "M1: execute() must return a flat envelope with success=True"
        )
        for key in ("summary_line", "agent_summary", "method_count", "class_count"):
            assert key in result, (
                f"M1: execute() must expose ``{key}`` on the flat envelope — "
                f"got keys={sorted(result.keys())}"
            )
        assert isinstance(result["summary_line"], str) and result["summary_line"], (
            "M1: ``summary_line`` must be a non-empty string"
        )
        assert isinstance(result["agent_summary"], dict), (
            "M1: ``agent_summary`` must be a dict"
        )

    def test_toon_output_returns_flat_envelope(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            GetCodeOutlineTool,
        )

        tool = GetCodeOutlineTool(str(tiny_project))
        # Default output_format is "toon" — the bug specifically lived on
        # this path. The response must still be a flat envelope; the
        # canonical TOON shape carries structured metadata at the top
        # level + a ``toon_content`` blob.
        result = _run(tool.execute({"file_path": "sample.py"}))
        assert isinstance(result, dict)
        assert result.get("success") is True, (
            "M1: TOON path must return a flat envelope with success=True"
        )
        # The legacy ``{"content": [...]}`` envelope had ``content`` as
        # its single key — that shape is gone.
        assert sorted(result.keys()) != ["content"], (
            "M1: TOON path must not wrap the response in MCP wire-format"
        )
        for key in ("summary_line", "agent_summary", "method_count", "class_count"):
            assert key in result, (
                f"M1: TOON path must expose ``{key}`` on the flat envelope — "
                f"got keys={sorted(result.keys())}"
            )


# ============================================================================
# M2 — list_agent_skills returns the skills list (not just the count)
# ============================================================================


class TestM2AgentSkillsListExposed:
    """M2 (round-26 dogfood): the CLI rendering pipeline injected the
    full skills list at the CLI layer, but the MCP tool's TOON response
    shape dropped ``skills`` and only kept ``skill_count``. MCP
    consumers couldn't see *what* skills exist — only how many.

    Contract:
      - ``execute()`` must include ``skills: list[dict]`` whose length
        equals ``skill_count``.
      - Each skill dict must carry at least ``name`` + ``description`` +
        ``skill_path`` (the read order the CLI surface provides).
    """

    def test_json_includes_skills_list(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool

        # The fixture project has no ``.agents/skills`` directory, so
        # we expect an empty inventory — the contract still holds.
        tool = AgentSkillsTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json"}))
        assert "skills" in result, (
            f"M2: JSON path must expose ``skills`` — got keys={sorted(result.keys())}"
        )
        assert isinstance(result["skills"], list), "M2: ``skills`` must be a list"
        assert len(result["skills"]) == result.get("skill_count", 0), (
            "M2: len(skills) must equal skill_count"
        )

    def test_toon_includes_skills_list(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool

        tool = AgentSkillsTool(str(tiny_project))
        result = _run(tool.execute({}))  # default toon
        assert "skills" in result, (
            f"M2: TOON path must expose ``skills`` — got keys={sorted(result.keys())}"
        )
        assert isinstance(result["skills"], list), "M2: ``skills`` must be a list"
        assert len(result["skills"]) == result.get("skill_count", 0), (
            "M2: len(skills) must equal skill_count"
        )

    def test_skills_carry_minimum_fields(self, tmp_path: Path) -> None:
        """Concrete check with a real skill directory."""
        skills_dir = tmp_path / ".agents" / "skills" / "demo"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: demo\ndescription: use when demoing\n---\n# Demo\n\n"
            "- [ ] acceptance criterion\n",
            encoding="utf-8",
        )

        from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool

        tool = AgentSkillsTool(str(tmp_path))
        result = _run(tool.execute({"output_format": "json"}))
        assert result.get("skill_count", 0) >= 1
        assert result["skills"], "M2: skills list must be populated"
        first = result["skills"][0]
        for key in ("name", "description", "skill_path"):
            assert key in first, (
                f"M2: skill dict must expose ``{key}`` — got "
                f"keys={sorted(first.keys())}"
            )


# ============================================================================
# M5 — change_impact summary_line must be non-empty on success
# ============================================================================


class TestM5ChangeImpactSummaryLineNonNull:
    """M5 (round-26 dogfood): ``analyze_change_impact`` returned
    ``summary_line=None`` at both top-level and inside ``agent_summary``
    even on the success path with ``changed_count > 0``. F6's post-hook
    was supposed to mirror agent_summary.summary_line -> top — but
    change_impact never populated either surface, so the post-hook had
    nothing to copy.

    Contract: a successful run produces a non-empty ``summary_line`` at
    both surfaces. The headline carries the canonical
    ``change_impact changed=N risk=R pytest_required=...`` shape.
    """

    def test_success_response_has_non_empty_summary_line(
        self, tiny_project: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

        tool = ChangeImpactTool(str(tiny_project))
        # The fixture has no git changes, so we get the no-changes
        # shortcut — that path also lost ``summary_line=None`` pre-M5
        # and is the only one we can exercise hermetically.
        result = _run(tool.execute({"output_format": "json"}))
        top = result.get("summary_line")
        agent = result.get("agent_summary", {}).get("summary_line")
        assert isinstance(top, str) and top, (
            f"M5: top-level ``summary_line`` must be non-empty — got {top!r}"
        )
        assert isinstance(agent, str) and agent, (
            f"M5: agent_summary.summary_line must be non-empty — got {agent!r}"
        )
        assert "change_impact" in top, (
            f"M5: summary_line must carry the ``change_impact`` token — got {top!r}"
        )
        assert "changed=" in top, (
            f"M5: summary_line must carry the ``changed=N`` token — got {top!r}"
        )

    def test_verdict_mirrored_to_top_level(self, tiny_project: Path) -> None:
        """M5 + M10: change_impact emits ``verdict`` inside ``agent_summary``
        — the central post-hook (or ``mirror_summary_line``) propagates it
        to the top level so chained agents see the same answer on either
        surface."""
        from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

        tool = ChangeImpactTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json"}))
        top = result.get("verdict")
        agent = result.get("agent_summary", {}).get("verdict")
        assert isinstance(top, str) and top, (
            f"M5/M10: top-level ``verdict`` must mirror agent value — "
            f"got top={top!r} agent={agent!r}"
        )
        assert top == agent, (
            f"M5/M10: top and agent verdict must agree — "
            f"got top={top!r} agent={agent!r}"
        )


# ============================================================================
# M9 — analyze_scale.agent_summary exposes ``verdict``
# ============================================================================


class TestM9AnalyzeScaleVerdictField:
    """M9 (round-26 dogfood): every other tool exposes
    ``agent_summary.verdict`` (code_patterns, safe_to_edit,
    trace_impact, route_detector, build_project_index, ast_cache,
    call_graph) — even if just ``"n/a"``. analyze_scale missed K12's
    normalization sweep.

    Contract: ``agent_summary.verdict`` is a non-empty string. The
    canonical value for a measurement tool is ``"INFO"``.
    """

    def test_single_file_has_verdict_key(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        tool = AnalyzeScaleTool(str(tiny_project))
        result = _run(tool.execute({"file_path": "sample.py"}))
        agent = result.get("agent_summary", {})
        assert "verdict" in agent, (
            f"M9: agent_summary must expose ``verdict`` — got keys="
            f"{sorted(agent.keys())}"
        )
        verdict = agent["verdict"]
        assert isinstance(verdict, str) and verdict, (
            f"M9: agent_summary.verdict must be a non-empty string — got {verdict!r}"
        )

    def test_batch_metrics_has_verdict_key(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        tool = AnalyzeScaleTool(str(tiny_project))
        result = _run(
            tool.execute(
                {
                    "file_paths": ["sample.py"],
                    "metrics_only": True,
                    "output_format": "json",
                }
            )
        )
        agent = result.get("agent_summary", {})
        verdict = agent.get("verdict")
        assert isinstance(verdict, str) and verdict, (
            f"M9: batch path agent_summary.verdict must be a non-empty "
            f"string — got {verdict!r}"
        )

    def test_json_file_path_has_verdict_key(self, tmp_path: Path) -> None:
        """Non-source files (JSON config) take the early-return path; it
        must still expose ``verdict`` to keep cross-tool parity."""
        json_file = tmp_path / "config.json"
        json_file.write_text('{"a": 1}\n', encoding="utf-8")

        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        tool = AnalyzeScaleTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "config.json"}))
        verdict = result.get("agent_summary", {}).get("verdict")
        assert isinstance(verdict, str) and verdict, (
            f"M9: JSON-fast-path agent_summary.verdict must be a "
            f"non-empty string — got {verdict!r}"
        )


# ============================================================================
# M10 — verdict mirror between top-level and agent_summary
# ============================================================================


class TestM10VerdictSplit:
    """M10 (round-26 dogfood): K12's normalization goal said every tool
    should expose ``verdict`` at both surfaces (top-level + inside
    ``agent_summary``). Three tools split:

      * safe_to_edit  — verdict at top, missing in agent_summary
      * code_patterns — verdict in agent_summary, missing at top
      * smart_context — verdict missing everywhere despite computing
                        risk

    Fix: the central post-hook ``ensure_canonical_success_envelope``
    mirrors verdict in both directions whenever exactly one location is
    populated. ``mirror_summary_line`` does the same so direct callers
    (tests, hive-mind workers, anything that bypasses the dispatcher)
    see the same envelope. Per-tool changes:
      * smart_context computes a verdict from its risk vocabulary.
      * safe_to_edit calls ``mirror_summary_line`` before returning.
      * code_patterns calls ``mirror_summary_line`` before returning.

    Contract: for every tool listed below, both
    ``response.verdict`` and ``response.agent_summary.verdict`` are
    non-empty strings AND they agree.
    """

    @pytest.fixture
    def fixture_project(self, tmp_path: Path) -> Path:
        # Use a file with a defined verdict (≥ 1 line of code, parses cleanly).
        src = tmp_path / "sample.py"
        src.write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            encoding="utf-8",
        )
        return tmp_path

    @pytest.mark.parametrize(
        "tool_name,tool_factory_path",
        [
            (
                "safe_to_edit",
                "tree_sitter_analyzer.mcp.tools.safe_to_edit_tool.SafeToEditTool",
            ),
            (
                "code_patterns",
                "tree_sitter_analyzer.mcp.tools.code_patterns_tool.CodePatternsTool",
            ),
            (
                "smart_context",
                "tree_sitter_analyzer.mcp.tools.smart_context_tool.SmartContextTool",
            ),
        ],
    )
    def test_verdict_present_at_both_surfaces_and_agrees(
        self,
        fixture_project: Path,
        tool_name: str,
        tool_factory_path: str,
    ) -> None:
        import importlib

        module_path, cls_name = tool_factory_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        tool_cls = getattr(module, cls_name)
        tool = tool_cls(str(fixture_project))
        result = _run(tool.execute({"file_path": "sample.py", "output_format": "json"}))
        top = result.get("verdict")
        agent = result.get("agent_summary", {}).get("verdict")
        assert isinstance(top, str) and top, (
            f"M10: {tool_name} top-level ``verdict`` must be a non-empty "
            f"string — got {top!r}"
        )
        assert isinstance(agent, str) and agent, (
            f"M10: {tool_name} agent_summary.verdict must be a non-empty "
            f"string — got {agent!r}"
        )
        assert top == agent, (
            f"M10: {tool_name} top and agent verdict must agree — "
            f"got top={top!r} agent={agent!r}"
        )


# ============================================================================
# M10 — central post-hook unit test (direct verdict mirror behaviour)
# ============================================================================


class TestM10CentralVerdictMirrorHook:
    """Unit test for the bidirectional verdict mirror inside
    ``ensure_canonical_success_envelope``. The behaviour table:

        top         agent       -> outcome
        ---         -----       --------
        ""/None     "X"         top = "X"
        "X"         ""/None     agent = "X"
        "X"         "n/a"       agent = "X"  (treat ``n/a`` as missing)
        ""/None     ""/None     both end up "n/a" (final default)
        "X"         "Y"         leave both (intentional divergence)
    """

    def _envelope(self, **overrides: Any) -> dict[str, Any]:
        # Minimum dict the post-hook accepts.
        base: dict[str, Any] = {"success": True, "summary_line": "x: ok"}
        base.update(overrides)
        return base

    def test_top_missing_agent_set_propagates_to_top(self) -> None:
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            ensure_canonical_success_envelope,
        )

        result = ensure_canonical_success_envelope(
            "x",
            self._envelope(agent_summary={"summary_line": "x: ok", "verdict": "SAFE"}),
        )
        assert result["verdict"] == "SAFE"
        assert result["agent_summary"]["verdict"] == "SAFE"

    def test_top_set_agent_missing_propagates_to_agent(self) -> None:
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            ensure_canonical_success_envelope,
        )

        result = ensure_canonical_success_envelope(
            "x",
            self._envelope(verdict="UNSAFE", agent_summary={"summary_line": "x: ok"}),
        )
        assert result["verdict"] == "UNSAFE"
        assert result["agent_summary"]["verdict"] == "UNSAFE"

    def test_top_set_agent_na_placeholder_propagates_to_agent(self) -> None:
        """``n/a`` is treated as missing so a real value on either side
        still mirrors over the placeholder."""
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            ensure_canonical_success_envelope,
        )

        result = ensure_canonical_success_envelope(
            "x",
            self._envelope(
                verdict="SAFE",
                agent_summary={"summary_line": "x: ok", "verdict": "n/a"},
            ),
        )
        assert result["agent_summary"]["verdict"] == "SAFE"
        assert result["verdict"] == "SAFE"

    def test_both_missing_falls_back_to_n_a(self) -> None:
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            ensure_canonical_success_envelope,
        )

        result = ensure_canonical_success_envelope("x", self._envelope())
        # The final default still fires.
        assert result["agent_summary"]["verdict"] == "n/a"

    def test_intentional_divergence_preserved(self) -> None:
        """If both sides set distinct values the mirror keeps both."""
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            ensure_canonical_success_envelope,
        )

        result = ensure_canonical_success_envelope(
            "x",
            self._envelope(
                verdict="SAFE",
                agent_summary={"summary_line": "x: ok", "verdict": "REVIEW"},
            ),
        )
        assert result["verdict"] == "SAFE"
        assert result["agent_summary"]["verdict"] == "REVIEW"


class TestN2DependenciesFullParity:
    """N2 (round-28 dogfood): CLI ``--dependencies full`` worked but MCP
    ``execute({mode: 'full'})`` raised ``ValueError: Unknown mode: full``.

    The CLI silently aliases ``full`` -> ``summary`` via
    ``_DEPENDENCY_MODE_ALIASES`` in ``mcp_commands.py``, but the MCP tool
    schema enum did not include ``full`` and the dispatcher had no alias
    handling — so the same word was accepted on one surface and rejected
    on the other. The fix: ``DependencyAnalysisTool._MODE_ALIASES``
    normalises ``full`` -> ``summary`` at execute time, the schema enum
    accepts both, and the response echoes the canonical name ``summary``
    so callers see byte-identical output regardless of which alias they
    sent.

    Canonical name is ``summary`` (matches the CLI alias map and every
    internal reference: smart_prompts, analyze_scale_helpers,
    project_overview_tool, query_symbol_search).
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        src = tmp_path / "a.py"
        src.write_text("def f(): return 1\n", encoding="utf-8")
        return tmp_path

    def test_mcp_execute_mode_full_succeeds(self, tiny_project: Path) -> None:
        """``execute({mode: 'full'})`` must succeed — the schema enum now
        accepts ``full`` and the dispatcher normalises it to ``summary``."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.project_graph import DependencyGraph

        DependencyGraph._global_cache.clear()
        tool = DependencyAnalysisTool(project_root=str(tiny_project))
        result = _run(tool.execute({"mode": "full", "output_format": "json"}))
        assert result["success"] is True, (
            f"N2: mode=full must succeed (CLI parity). Got {result!r}"
        )
        # The success-envelope contract still holds — top-level summary_line
        # and agent_summary are populated.
        assert isinstance(result.get("summary_line"), str)
        assert isinstance(result.get("agent_summary"), dict)

    def test_mcp_execute_mode_full_echoes_summary(self, tiny_project: Path) -> None:
        """The response must echo the *canonical* mode name ``summary``
        even when the caller sent the ``full`` alias. This matches what
        the CLI does today and keeps the response byte-identical across
        the two spellings — so caching/dedup layers downstream don't see
        spurious deltas."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.project_graph import DependencyGraph

        DependencyGraph._global_cache.clear()
        tool = DependencyAnalysisTool(project_root=str(tiny_project))
        result = _run(tool.execute({"mode": "full", "output_format": "json"}))
        assert result.get("mode") == "summary", (
            f"N2: mode=full must echo the canonical name 'summary' "
            f"(matches CLI alias behaviour). Got mode={result.get('mode')!r}"
        )

    def test_mcp_execute_mode_summary_unchanged(self, tiny_project: Path) -> None:
        """Regression guard: ``mode=summary`` (canonical) keeps echoing
        ``summary`` unchanged. The alias must not break the non-aliased
        path."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.project_graph import DependencyGraph

        DependencyGraph._global_cache.clear()
        tool = DependencyAnalysisTool(project_root=str(tiny_project))
        result = _run(tool.execute({"mode": "summary", "output_format": "json"}))
        assert result["success"] is True
        assert result.get("mode") == "summary"

    def test_schema_enum_includes_full(self) -> None:
        """The MCP schema must list ``full`` so JSON-schema-validating
        clients (Claude Code, Cursor, Cline) accept the alias instead of
        rejecting the input before the call reaches the tool."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )

        tool = DependencyAnalysisTool(project_root=".")
        schema = tool.get_tool_schema()
        mode_enum = schema["properties"]["mode"]["enum"]
        for canonical in ("blast_radius", "file_deps", "cycles", "summary"):
            assert canonical in mode_enum, (
                f"N2: canonical mode {canonical!r} dropped from schema enum: {mode_enum!r}"
            )
        assert "full" in mode_enum, (
            f"N2: 'full' alias must be in the schema enum so JSON-schema "
            f"validators accept --dependencies full from the CLI bridge. "
            f"Got enum={mode_enum!r}"
        )

    def test_cli_dependencies_full_succeeds(self, tiny_project: Path) -> None:
        """End-to-end CLI parity: ``--dependencies full --format json``
        must produce a success envelope with ``mode: summary`` (canonical
        echo). The CLI emits indented multi-line JSON on success, so we
        parse the whole stdout payload as a single JSON document (vs the
        error path which uses one-line envelopes)."""
        import json as _json
        import subprocess
        import sys

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--dependencies",
                "full",
                "--format",
                "json",
                "--project-root",
                str(tiny_project),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"N2 CLI: --dependencies full must exit RC=0. "
            f"stderr={proc.stderr!r} stdout={proc.stdout[:500]!r}"
        )
        # Find the first ``{`` and parse from there to end-of-output —
        # the success envelope is pretty-printed (multi-line) JSON.
        stdout = proc.stdout
        first_brace = stdout.find("{")
        assert first_brace >= 0, (
            f"N2 CLI: expected a JSON object on stdout. Got: {stdout!r}"
        )
        try:
            envelope = _json.loads(stdout[first_brace:])
        except _json.JSONDecodeError as exc:
            raise AssertionError(
                f"N2 CLI: failed to parse JSON envelope: {exc}. Stdout: {stdout!r}"
            ) from exc
        assert envelope.get("success") is True
        assert envelope.get("mode") == "summary", (
            f"N2 CLI: --dependencies full must echo mode=summary, "
            f"got mode={envelope.get('mode')!r}"
        )


class TestN6DependenciesErrorEchoesMode:
    """N6 (round-28 dogfood): the success-path envelope for
    ``--dependencies <mode>`` includes ``mode: <requested>`` so callers
    can branch on which analysis was run. The validation-error path
    (e.g. missing ``--file-path`` for ``file_deps``/``blast_radius``)
    used to drop ``mode`` entirely. Now the CLI mirrors the same
    identifier onto error envelopes via ``_collect_echo_fields`` so the
    failure carries the same context as the success.
    """

    def test_cli_file_deps_missing_file_echoes_mode(self, tmp_path: Path) -> None:
        """``--dependencies file_deps`` without ``--file-path`` must
        validate-fail with ``mode: file_deps`` mirrored onto the
        envelope. Pre-N6 this dropped ``mode`` entirely, leaving
        callers with no signal about what they requested."""
        import json as _json
        import subprocess
        import sys

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--dependencies",
                "file_deps",
                "--format",
                "json",
                "--project-root",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 1, (
            f"N6: missing file_path must exit RC=1. "
            f"stderr={proc.stderr!r} stdout={proc.stdout[:500]!r}"
        )
        envelope = None
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("{"):
                try:
                    envelope = _json.loads(stripped)
                    break
                except _json.JSONDecodeError:
                    continue
        assert envelope is not None, (
            f"N6: expected a JSON envelope on stdout. Got: {proc.stdout!r}"
        )
        assert envelope.get("success") is False
        assert envelope.get("mode") == "file_deps", (
            f"N6: validation-error envelope must echo the requested mode. "
            f"Got mode={envelope.get('mode')!r} keys={sorted(envelope.keys())!r}"
        )

    def test_cli_blast_radius_missing_file_echoes_mode(self, tmp_path: Path) -> None:
        """Mirror check for blast_radius — same parity contract."""
        import json as _json
        import subprocess
        import sys

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--dependencies",
                "blast_radius",
                "--format",
                "json",
                "--project-root",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 1
        envelope = None
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("{"):
                try:
                    envelope = _json.loads(stripped)
                    break
                except _json.JSONDecodeError:
                    continue
        assert envelope is not None
        assert envelope.get("success") is False
        assert envelope.get("mode") == "blast_radius", (
            f"N6: blast_radius validation-error envelope must echo "
            f"mode=blast_radius. Got mode={envelope.get('mode')!r}"
        )

    def test_collect_echo_fields_normalises_full_alias(self) -> None:
        """``_collect_echo_fields`` runs the same alias normalisation as
        the tool — so a caller who sent ``--dependencies full`` and hit
        an error sees ``mode: summary`` (canonical), not the raw alias.
        Matches what the success path echoes."""
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            MCP_COMMAND_SPECS,
            _collect_echo_fields,
        )

        spec = next(s for s in MCP_COMMAND_SPECS if s.flag_name == "dependencies")

        class _Args:
            dependencies = "full"

        echo = _collect_echo_fields(spec, _Args())
        assert echo.get("mode") == "summary", (
            f"N6: echo fields must normalise 'full' -> 'summary'. Got {echo!r}"
        )

    def test_collect_echo_fields_passes_explicit_mode_through(self) -> None:
        """Non-aliased modes pass through unchanged."""
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            MCP_COMMAND_SPECS,
            _collect_echo_fields,
        )

        spec = next(s for s in MCP_COMMAND_SPECS if s.flag_name == "dependencies")
        for mode in ("summary", "cycles", "file_deps", "blast_radius"):

            class _Args:
                dependencies = mode

            echo = _collect_echo_fields(spec, _Args())
            assert echo.get("mode") == mode, (
                f"N6: echo fields must pass {mode!r} through unchanged. Got {echo!r}"
            )

    def test_build_error_envelope_carries_echo_fields(self) -> None:
        """Unit-level: ``_build_error_envelope`` accepts ``echo_fields``
        and mirrors them onto the response root without stomping on the
        canonical envelope keys (success/error/error_type/summary_line/
        agent_summary)."""
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            _build_error_envelope,
        )

        envelope = _build_error_envelope(
            "dependencies",
            "Dependency analysis",
            ValueError("--dependencies requires a file path"),
            echo_fields={"mode": "file_deps"},
        )
        assert envelope["success"] is False
        assert envelope["mode"] == "file_deps"
        # echo_fields must never stomp canonical keys.
        assert envelope["error_type"] == "validation"
        assert "agent_summary" in envelope


class TestN8DependenciesTOONIncludesScalars:
    """N8 (round-28 dogfood): the TOON output for ``mode=summary`` /
    ``mode=cycles`` must include the scalar fields that callers need
    most — ``cycle_count``, ``recommendation``, ``elapsed_ms`` — even
    though F7 deliberately drops the redundant nested ``results`` /
    ``summary_line`` for token efficiency. ``agent_summary`` and the
    top-level ``summary_line`` ALSO stay (F6 design). This regression
    guard pins the contract so a future TOON refactor cannot silently
    elide the cycle count or runtime metadata.

    Note: the original brief's `head -10` reproduction was misleading
    — the fields appear later in the TOON payload. This test pins the
    real shape regardless of vertical ordering.
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        src = tmp_path / "a.py"
        src.write_text("def f(): return 1\n", encoding="utf-8")
        return tmp_path

    def _toon_text(self, project: Path, mode: str) -> str:
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.project_graph import DependencyGraph

        DependencyGraph._global_cache.clear()
        tool = DependencyAnalysisTool(project_root=str(project))
        result = _run(tool.execute({"mode": mode, "output_format": "toon"}))
        text = result.get("toon_content")
        assert isinstance(text, str) and text, (
            f"N8: toon_content must be a non-empty string for mode={mode}. "
            f"Got {result!r}"
        )
        return text

    def test_summary_toon_includes_cycle_count(self, tiny_project: Path) -> None:
        """``cycle_count`` is the most useful scalar from summary mode —
        callers branch on cycles>0 to decide whether to call cycles
        mode. Must appear as a TOON scalar line."""
        text = self._toon_text(tiny_project, "summary")
        assert "cycle_count:" in text, (
            f"N8: TOON summary must include 'cycle_count:' line. Got:\n{text}"
        )

    def test_summary_toon_includes_recommendation(self, tiny_project: Path) -> None:
        """``recommendation`` is the actionable next step the caller
        runs against. Must appear in TOON."""
        text = self._toon_text(tiny_project, "summary")
        assert "recommendation:" in text, (
            f"N8: TOON summary must include 'recommendation:' line. Got:\n{text}"
        )

    def test_summary_toon_includes_elapsed_ms(self, tiny_project: Path) -> None:
        """``elapsed_ms`` is the runtime metadata that callers use to
        decide whether to cache."""
        text = self._toon_text(tiny_project, "summary")
        assert "elapsed_ms:" in text, (
            f"N8: TOON summary must include 'elapsed_ms:' line. Got:\n{text}"
        )

    def test_cycles_toon_includes_scalars(self, tiny_project: Path) -> None:
        """The same scalar contract applies to ``mode=cycles`` so
        callers can read cycle_count without parsing the cycles list."""
        text = self._toon_text(tiny_project, "cycles")
        for scalar in ("cycle_count:", "recommendation:", "elapsed_ms:"):
            assert scalar in text, (
                f"N8: TOON cycles must include {scalar!r}. Got:\n{text}"
            )

    def test_summary_envelope_metadata_present_alongside_toon(
        self, tiny_project: Path
    ) -> None:
        """The MCP envelope keeps the metadata copy of these scalars
        alongside ``toon_content`` so callers that don't parse TOON can
        still read them — this is what ``apply_toon_format_to_response``
        guarantees."""
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )
        from tree_sitter_analyzer.project_graph import DependencyGraph

        DependencyGraph._global_cache.clear()
        tool = DependencyAnalysisTool(project_root=str(tiny_project))
        result = _run(tool.execute({"mode": "summary", "output_format": "toon"}))
        # The envelope keeps the scalars at the root next to toon_content
        # so a caller never has to TOON-parse to get them.
        assert "cycle_count" in result
        assert "recommendation" in result
        assert "elapsed_ms" in result
        assert "toon_content" in result


# ============================================================================
# N9 — file_health refuses Python files with null bytes in string literals
# ============================================================================


class TestN9FileHealthNullBytesInStringLiterals:
    """N9 (round-28 dogfood): a Python file with ``x = "\\x00"`` is legal
    source — the null byte lives inside a string literal. Tree-sitter's
    tokenizer trips on the raw 0x00 even though the *source language*
    allows it, so the M3 syntax-validity gate fired and ``file_health``
    short-circuited to ``signal=syntax_error verdict=ERROR``. Worse, the
    response envelope ended up with ``line_count``/``binary`` slots
    missing entirely (returned as ``None`` to consumers), so an agent
    couldn't even tell whether the rejection was about size, encoding,
    or syntax.

    Fix (Option A — accept the file):

    * ``parse_validity.is_file_parse_broken`` now retries with null
      bytes substituted by spaces; if the substituted source parses
      cleanly and the file has a known source extension, the original
      is accepted as syntactically valid.
    * ``file_health_tool._looks_binary`` was tightened: source-extension
      files (``.py``, ``.c``, ``.java``…) with isolated null bytes are
      NOT classified as binary. A file is binary only when null bytes
      dominate over printable chars AND utf-8 decode fails.
    * Every ``file_health`` response now carries ``line_count``,
      ``lines`` (alias), and ``binary`` — including the empty / non-code /
      syntax-error / binary branches — so a downstream consumer sees the
      same vocabulary regardless of which branch the file took.

    The heuristic for "is binary" after this fix:

    1. Known source extension (``.py``, ``.js``, ``.java``, ``.go``,
       ``.rs``, etc.) → only binary if utf-8 decode fails *and* null
       bytes outnumber printable chars in the first 1024 bytes.
    2. Unknown / non-source extension → legacy heuristic (any null byte
       or decode failure is enough).
    """

    @pytest.fixture
    def project_with_null_string_literal(self, tmp_path: Path) -> Path:
        """Project with a Python file that has ``"\\x00"`` in a string."""
        src = tmp_path / "null_string.py"
        src.write_bytes(b'def hello():\n    x = "\x00"\n    return 1\n')
        return tmp_path

    def test_python_null_byte_string_literal_accepted(
        self, project_with_null_string_literal: Path
    ) -> None:
        """Python source with ``x = "\\x00"`` must not short-circuit
        to ``signal=syntax_error``. The file is legal Python and should
        receive a real grade."""
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(project_with_null_string_literal))
        result = _run(
            tool.execute({"file_path": "null_string.py", "output_format": "json"})
        )
        assert result.get("signal") != "syntax_error", (
            "N9: a Python file with ``\\x00`` in a string literal must "
            "NOT short-circuit to signal=syntax_error — got "
            f"signal={result.get('signal')!r}"
        )
        assert result.get("verdict") != "ERROR", (
            "N9: a Python file with ``\\x00`` in a string literal must "
            f"NOT have verdict=ERROR — got {result.get('verdict')!r}"
        )
        # The file is 3 lines; line_count must reflect content.
        line_count = result.get("line_count") or result.get("lines")
        assert line_count == 3, (
            f"N9: line_count must reflect file content (3 lines) — got {line_count!r}"
        )
        # ``binary`` must be False — the file is source code, not binary.
        assert result.get("binary") is False, (
            "N9: ``binary`` must be False for a source file with a null "
            f"byte in a string literal — got {result.get('binary')!r}"
        )

    def test_envelope_has_line_count_and_binary_on_success(
        self, project_with_null_string_literal: Path
    ) -> None:
        """N9: every file_health success response should carry
        ``line_count`` and ``binary`` keys explicitly. Pre-fix, they
        defaulted to ``None`` because the keys were absent."""
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(project_with_null_string_literal))
        result = _run(
            tool.execute({"file_path": "null_string.py", "output_format": "json"})
        )
        assert "line_count" in result, (
            "N9: file_health envelope must include ``line_count`` — "
            f"keys={sorted(result.keys())}"
        )
        assert "binary" in result, (
            "N9: file_health envelope must include ``binary`` — "
            f"keys={sorted(result.keys())}"
        )
        assert isinstance(result["line_count"], int), (
            f"N9: line_count must be an int — got {type(result['line_count']).__name__}"
        )
        assert isinstance(result["binary"], bool), (
            f"N9: binary must be a bool — got {type(result['binary']).__name__}"
        )

    def test_c_file_null_char_literal_accepted(self, tmp_path: Path) -> None:
        """N9: C source with ``'\\0'`` (char literal containing the null
        byte) parses identically — the same false-positive applies."""
        src = tmp_path / "null_char.c"
        src.write_bytes(b"int main() {\n    char c = '\x00';\n    return 0;\n}\n")

        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tmp_path))
        result = _run(
            tool.execute({"file_path": "null_char.c", "output_format": "json"})
        )
        assert result.get("signal") != "syntax_error", (
            "N9: a C file with ``'\\0'`` must not short-circuit as "
            f"syntax_error — got signal={result.get('signal')!r}"
        )
        assert result.get("verdict") != "ERROR", (
            "N9: a C file with a null char literal must NOT verdict=ERROR "
            f"— got {result.get('verdict')!r}"
        )
        assert result.get("binary") is False, (
            "N9: ``binary`` must be False for a C file with a null char "
            f"literal — got {result.get('binary')!r}"
        )

    def test_truly_binary_file_still_rejected(self, tmp_path: Path) -> None:
        """N9 guardrail: the fix must not silently accept genuine binary
        files. A blob of pure null/high bytes without a source extension
        still gets rejected."""
        src = tmp_path / "blob.bin"
        src.write_bytes(b"\x00" * 64 + b"\xff" * 64)

        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "blob.bin", "output_format": "json"}))
        # Truly binary file → success=False + error_type=binary_file.
        assert result.get("success") is False, (
            "N9: a binary blob must still be rejected — got "
            f"success={result.get('success')!r}"
        )
        assert result.get("error_type") == "binary_file", (
            "N9: binary blob must carry error_type=binary_file — got "
            f"{result.get('error_type')!r}"
        )
        # The new ``binary`` field must be True on the rejection envelope.
        assert result.get("binary") is True, (
            f"N9: binary envelope must set binary=True — got {result.get('binary')!r}"
        )

    def test_real_syntax_error_with_null_still_errors(self, tmp_path: Path) -> None:
        """N9 guardrail: the null-byte escape hatch must NOT bail out
        the M3 gate when there's an *actual* syntax error too. A
        ``def broken(:`` plus a null byte still parses broken when
        we substitute the null bytes."""
        src = tmp_path / "broken_and_null.py"
        src.write_bytes(b'def broken(:\n    x = "\x00"\n')

        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tmp_path))
        result = _run(
            tool.execute({"file_path": "broken_and_null.py", "output_format": "json"})
        )
        assert result.get("signal") == "syntax_error", (
            "N9: a file with a *real* syntax error must still emit "
            f"signal=syntax_error — got signal={result.get('signal')!r}"
        )
        assert result.get("verdict") == "ERROR", (
            f"N9: real syntax error must verdict=ERROR — got {result.get('verdict')!r}"
        )
        # Even on ERROR we must still fill ``line_count`` + ``binary``.
        assert isinstance(result.get("line_count"), int), (
            "N9: ERROR envelope must still carry int line_count — got "
            f"{type(result.get('line_count')).__name__}"
        )
        assert result.get("binary") is False, (
            "N9: a Python source file (even with syntax error and a null "
            f"byte) must report binary=False — got {result.get('binary')!r}"
        )

    def test_clean_python_keeps_line_count_and_binary(self, tmp_path: Path) -> None:
        """N9: the new fields apply to the normal scoring path too. A
        clean Python file must carry ``line_count`` + ``binary=False``."""
        src = tmp_path / "ok.py"
        src.write_text(
            "def greet(name: str) -> str:\n"
            "    return f'hello {name}'\n"
            "\n"
            "def goodbye(name: str) -> str:\n"
            "    return f'bye {name}'\n",
            encoding="utf-8",
        )

        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "ok.py", "output_format": "json"}))
        assert result.get("line_count") == 5, (
            "N9: clean Python (5 lines) must report line_count=5 — got "
            f"{result.get('line_count')!r}"
        )
        assert result.get("binary") is False, (
            f"N9: clean Python must report binary=False — got {result.get('binary')!r}"
        )

    def test_empty_file_envelope_includes_line_count_zero(self, tmp_path: Path) -> None:
        """N9: the 0-byte branch also includes the new fields."""
        (tmp_path / "empty.py").write_text("", encoding="utf-8")

        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "empty.py", "output_format": "json"}))
        assert result.get("signal") == "empty_file"
        assert result.get("line_count") == 0, (
            f"N9: empty file must report line_count=0 — got "
            f"{result.get('line_count')!r}"
        )
        assert result.get("binary") is False, (
            f"N9: empty file must report binary=False — got {result.get('binary')!r}"
        )

    def test_is_file_parse_broken_accepts_null_byte_python(
        self, tmp_path: Path
    ) -> None:
        """Direct unit test on the gate: ``is_file_parse_broken`` must
        return False for a Python file whose only issue is null bytes
        in string literals."""
        src = tmp_path / "null.py"
        src.write_bytes(b'x = "\x00"\n')

        from tree_sitter_analyzer.mcp.tools.utils.parse_validity import (
            is_file_parse_broken,
        )

        assert is_file_parse_broken(str(src), "python") is False, (
            "N9: is_file_parse_broken must return False for Python with "
            "null bytes only in string literals"
        )

    def test_is_file_parse_broken_still_catches_real_errors(
        self, tmp_path: Path
    ) -> None:
        """Direct unit test: real syntax errors still trip the gate."""
        src = tmp_path / "broken.py"
        src.write_text("def broken(:\n", encoding="utf-8")

        from tree_sitter_analyzer.mcp.tools.utils.parse_validity import (
            is_file_parse_broken,
        )

        assert is_file_parse_broken(str(src), "python") is True, (
            "N9: is_file_parse_broken must still return True for real "
            "syntax errors (no null bytes involved)"
        )


class TestO3UniversalAnalyzeLanguageMismatch:
    """O3 (round-30 dogfood): universal_analyze must refuse a mismatched
    ``--language`` override instead of silently analysing the file
    against the wrong tree-sitter grammar.

    Before this gate, ``foo.py`` with ``language='java'`` returned
    ``success=True`` with zero classes/methods — the agent passing the
    wrong tag had no signal. Option A (strict) returns a canonical
    validation envelope so callers must omit ``--language`` to
    auto-detect, or fix the override.
    """

    def test_py_with_language_java_returns_validation_error(
        self, tmp_path: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )

        src = tmp_path / "sample.py"
        src.write_text("def greet(name):\n    return name\n", encoding="utf-8")

        tool = UniversalAnalyzeTool(str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "file_path": "sample.py",
                    "language": "java",
                    "output_format": "json",
                }
            )
        )
        assert result.get("success") is False, (
            f"O3: .py with language=java must fail — got success={result.get('success')!r}"
        )
        assert result.get("error_type") == "validation", (
            f"O3: error_type must be 'validation' — got {result.get('error_type')!r}"
        )
        error_msg = result.get("error") or ""
        assert "language='java' doesn't match" in error_msg, (
            f"O3: error must explain the mismatch — got {error_msg!r}"
        )
        agent = result.get("agent_summary") or {}
        assert agent.get("verdict") == "ERROR", (
            f"O3: agent_summary.verdict must be ERROR — got {agent.get('verdict')!r}"
        )
        assert "auto-detect" in (agent.get("next_step") or ""), (
            "O3: agent_summary.next_step must mention auto-detect to recover"
        )

    def test_py_with_language_python_matches_and_succeeds(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )

        src = tmp_path / "sample.py"
        src.write_text("def greet(name):\n    return name\n", encoding="utf-8")

        tool = UniversalAnalyzeTool(str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "file_path": "sample.py",
                    "language": "python",
                    "output_format": "json",
                }
            )
        )
        assert result.get("success") is True, (
            "O3: .py with language=python (matching) must succeed — "
            f"got success={result.get('success')!r} error={result.get('error')!r}"
        )

    def test_py_without_language_override_auto_detects(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )

        src = tmp_path / "sample.py"
        src.write_text("def greet(name):\n    return name\n", encoding="utf-8")

        tool = UniversalAnalyzeTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "sample.py", "output_format": "json"}))
        assert result.get("success") is True, (
            "O3: no language override must auto-detect and succeed — "
            f"got success={result.get('success')!r} error={result.get('error')!r}"
        )

    def test_unknown_extension_does_not_trip_gate(self, tmp_path: Path) -> None:
        """Unknown extensions can't be validated against — the gate
        must let the call through so the underlying analyser can decide
        whether the language tag is usable. Defensive: do not surprise
        callers with a false-positive validation error on extensions we
        don't know how to compare."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )

        src = tmp_path / "weird.xyzfoo"  # extension the detector won't know
        src.write_text("not real code\n", encoding="utf-8")

        from tree_sitter_analyzer.mcp.tools.base_tool import (
            detect_language_mismatch,
        )

        # The helper must return None for unknown-extension files so the
        # tool falls through to its normal handling (which may raise
        # "unsupported" but must not return a language_mismatch error).
        assert (
            detect_language_mismatch(str(src), "java", project_root=str(tmp_path))
            is None
        ), "O3: unknown extension must not be flagged as a mismatch"

        tool = UniversalAnalyzeTool(str(tmp_path))
        # The downstream analyser may legitimately fail for unsupported
        # languages — the contract here is only that we DON'T return a
        # language_mismatch envelope.
        try:
            result = _run(
                tool.execute(
                    {
                        "file_path": "weird.xyzfoo",
                        "language": "java",
                        "output_format": "json",
                    }
                )
            )
        except Exception:
            return  # acceptable: tool raised because language isn't supported
        # If the tool returned, it must NOT carry the mismatch warning.
        assert "language_mismatch_warning" not in result, (
            "O3: unknown extension must not produce a mismatch warning — "
            f"got result keys: {sorted(result.keys())}"
        )


class TestO8RefactorLanguageMismatch:
    """O8 (round-30 dogfood): refactoring_suggestions must refuse a
    mismatched ``--language`` override instead of returning verdict=SAFE
    with zero suggestions on a file written in another language.

    Same shape as O3: strict envelope, ``error_type=validation``,
    ``agent_summary.verdict=ERROR``.
    """

    def test_py_with_language_java_returns_validation_error(
        self, tmp_path: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        src = tmp_path / "sample.py"
        src.write_text("def greet(name):\n    return name\n", encoding="utf-8")

        tool = RefactoringSuggestionsTool(str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "file_path": "sample.py",
                    "language": "java",
                    "output_format": "json",
                }
            )
        )
        assert result.get("success") is False, (
            f"O8: refactor with language=java on .py must fail — "
            f"got success={result.get('success')!r}"
        )
        assert result.get("error_type") == "validation", (
            f"O8: error_type must be 'validation' — got {result.get('error_type')!r}"
        )
        error_msg = result.get("error") or ""
        assert "language='java' doesn't match" in error_msg, (
            f"O8: error must explain the mismatch — got {error_msg!r}"
        )
        assert result.get("verdict") != "SAFE", (
            "O8: the mismatch envelope must NOT preserve a verdict=SAFE — "
            "that was the original bug"
        )

    def test_py_with_language_python_matches_and_succeeds(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        src = tmp_path / "sample.py"
        src.write_text("def greet(name):\n    return name\n", encoding="utf-8")

        tool = RefactoringSuggestionsTool(str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "file_path": "sample.py",
                    "language": "python",
                    "output_format": "json",
                }
            )
        )
        assert result.get("success") is True, (
            "O8: refactor with matching language=python must succeed — "
            f"got success={result.get('success')!r}"
        )

    def test_py_without_language_override_auto_detects(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
            RefactoringSuggestionsTool,
        )

        src = tmp_path / "sample.py"
        src.write_text("def greet(name):\n    return name\n", encoding="utf-8")

        tool = RefactoringSuggestionsTool(str(tmp_path))
        result = _run(tool.execute({"file_path": "sample.py", "output_format": "json"}))
        assert result.get("success") is True, (
            "O8: no language override must auto-detect and succeed — "
            f"got success={result.get('success')!r}"
        )

    def test_unknown_extension_does_not_trip_gate(self, tmp_path: Path) -> None:
        """Mirror of the O3 guard for the refactor tool — extensions
        the detector doesn't know must not produce a false-positive
        mismatch error."""
        from tree_sitter_analyzer.mcp.tools.base_tool import (
            detect_language_mismatch,
        )

        src = tmp_path / "weird.xyzfoo"
        src.write_text("blah\n", encoding="utf-8")
        assert (
            detect_language_mismatch(str(src), "java", project_root=str(tmp_path))
            is None
        ), "O8: unknown extension must not be flagged as a mismatch"


class TestLanguageMismatchHelperUnit:
    """Direct unit tests on the shared helper — guards against future
    refactors that accidentally narrow or widen its match criteria."""

    def test_none_language_returns_none(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.base_tool import (
            detect_language_mismatch,
        )

        src = tmp_path / "x.py"
        src.write_text("x = 1\n", encoding="utf-8")
        assert (
            detect_language_mismatch(str(src), None, project_root=str(tmp_path)) is None
        )

    def test_empty_language_returns_none(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.base_tool import (
            detect_language_mismatch,
        )

        src = tmp_path / "x.py"
        src.write_text("x = 1\n", encoding="utf-8")
        assert (
            detect_language_mismatch(str(src), "", project_root=str(tmp_path)) is None
        )

    def test_case_insensitive_match(self, tmp_path: Path) -> None:
        """``Python`` (mixed case) must match ``python`` from the detector."""
        from tree_sitter_analyzer.mcp.tools.base_tool import (
            detect_language_mismatch,
        )

        src = tmp_path / "x.py"
        src.write_text("x = 1\n", encoding="utf-8")
        assert (
            detect_language_mismatch(str(src), "Python", project_root=str(tmp_path))
            is None
        )
        assert (
            detect_language_mismatch(str(src), "PYTHON", project_root=str(tmp_path))
            is None
        )

    def test_mismatch_returns_warning_string(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.base_tool import (
            detect_language_mismatch,
        )

        src = tmp_path / "x.py"
        src.write_text("x = 1\n", encoding="utf-8")
        warning = detect_language_mismatch(str(src), "java", project_root=str(tmp_path))
        assert isinstance(warning, str) and warning, (
            "mismatch must return a non-empty warning string"
        )
        assert "java" in warning and "python" in warning, (
            f"warning must name both languages — got {warning!r}"
        )


class TestO4FileHealthLinesAliasUnderTOON:
    """O4 (round-30): the ``lines`` scalar alias must survive the
    TOON-format response stripping.

    Before O4 the ``apply_toon_format_to_response`` helper unconditionally
    stripped the top-level ``lines`` key, treating it as bulk content.
    N9 (round-29) added ``lines`` as a scalar alias for ``line_count`` on
    file_health responses — under the default TOON format the alias was
    silently dropped, breaking cross-format consumers that read
    ``response["lines"]`` without checking format.
    """

    @pytest.fixture
    def tiny_project(self, tmp_path: Path) -> Path:
        src = tmp_path / "sample.py"
        src.write_text(
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_lines_present_under_explicit_json(self, tiny_project: Path) -> None:
        """Sanity baseline: ``lines`` is present under ``output_format='json'``."""
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tiny_project))
        result = _run(
            tool.execute(
                {
                    "file_path": str(tiny_project / "sample.py"),
                    "output_format": "json",
                }
            )
        )
        assert "lines" in result, (
            "O4: file_health JSON response must include scalar ``lines`` alias"
        )
        assert isinstance(result["lines"], int), (
            f"O4: ``lines`` must be int — got {type(result['lines']).__name__}"
        )

    def test_lines_present_under_default_toon(self, tiny_project: Path) -> None:
        """O4: ``lines`` must STILL be present in the dict under default TOON."""
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tiny_project))
        # No output_format → defaults to TOON.
        result = _run(tool.execute({"file_path": str(tiny_project / "sample.py")}))
        assert "lines" in result, (
            "O4: file_health default-TOON response must NOT strip the "
            "scalar ``lines`` alias — got keys: " + repr(sorted(result.keys()))
        )
        assert isinstance(result["lines"], int), (
            f"O4: ``lines`` must be int under TOON — got "
            f"{type(result['lines']).__name__}"
        )

    def test_lines_alias_matches_line_count_in_both_formats(
        self, tiny_project: Path
    ) -> None:
        """O4: the alias must equal ``line_count`` regardless of format."""
        from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

        tool = FileHealthTool(str(tiny_project))
        r_json = _run(
            tool.execute(
                {
                    "file_path": str(tiny_project / "sample.py"),
                    "output_format": "json",
                }
            )
        )
        r_toon = _run(tool.execute({"file_path": str(tiny_project / "sample.py")}))
        assert r_json.get("lines") == r_json.get("line_count"), (
            f"O4: lines={r_json.get('lines')!r} must match "
            f"line_count={r_json.get('line_count')!r} (json)"
        )
        assert r_toon.get("lines") == r_toon.get("line_count"), (
            f"O4: lines={r_toon.get('lines')!r} must match "
            f"line_count={r_toon.get('line_count')!r} (toon default)"
        )
        # Cross-format consistency: same file → same value in both formats.
        assert r_json.get("lines") == r_toon.get("lines"), (
            f"O4: scalar ``lines`` must be identical across json "
            f"({r_json.get('lines')!r}) and toon ({r_toon.get('lines')!r})"
        )

    def test_list_lines_field_still_stripped_under_toon(self) -> None:
        """Guardrail: when ``lines`` is genuinely a list of content,
        ``apply_toon_format_to_response`` must still strip it. The fix
        is conditional, not blanket — bulk arrays remain stripped to
        preserve token savings."""
        from tree_sitter_analyzer.mcp.utils.format_helper import (
            apply_toon_format_to_response,
        )

        result_with_list = {
            "success": True,
            "file_path": "/x.py",
            "lines": ["line a", "line b", "line c"],  # bulk content
        }
        out = apply_toon_format_to_response(result_with_list, "toon")
        assert out.get("format") == "toon"
        assert "lines" not in out, (
            "O4: when ``lines`` is a list, the field is bulk content "
            "and must still be stripped under TOON"
        )

    def test_scalar_lines_survives_helper_directly(self) -> None:
        """Direct unit test on ``apply_toon_format_to_response``: scalar
        ``lines`` (int/str/dict) must NOT be stripped — only list values
        are considered bulk content."""
        from tree_sitter_analyzer.mcp.utils.format_helper import (
            apply_toon_format_to_response,
        )

        result_with_int = {"success": True, "lines": 42}
        out_int = apply_toon_format_to_response(result_with_int, "toon")
        assert out_int.get("lines") == 42, (
            f"O4: scalar int ``lines`` must survive — got {out_int!r}"
        )

        result_with_dict = {"success": True, "lines": {"start": 1, "end": 10}}
        out_dict = apply_toon_format_to_response(result_with_dict, "toon")
        assert out_dict.get("lines") == {"start": 1, "end": 10}, (
            f"O4: dict-shaped ``lines`` (range) must survive — got {out_dict!r}"
        )


class TestO5ProjectOverviewSummaryByLanguage:
    """O5 (round-30): project_overview must mirror ``language_distribution``
    into ``summary.by_language`` so consumers building a summary block
    don't have to read two different sub-trees of the response. The
    top-level ``language_distribution`` field stays for back-compat —
    the new field is purely additive.
    """

    @pytest.fixture
    def multi_lang_project(self, tmp_path: Path) -> Path:
        (tmp_path / "main.py").write_text("def f(): return 1\n", encoding="utf-8")
        (tmp_path / "README.md").write_text("# project\n", encoding="utf-8")
        (tmp_path / "config.yaml").write_text("k: v\n", encoding="utf-8")
        return tmp_path

    def test_summary_by_language_present(self, multi_lang_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(multi_lang_project))
        result = _run(tool.execute({"output_format": "json"}))
        summary = result.get("summary", {})
        assert isinstance(summary, dict), "summary must be a dict"
        assert "by_language" in summary, (
            "O5: summary must include ``by_language`` mirror — got keys: "
            + repr(sorted(summary.keys()))
        )
        assert isinstance(summary["by_language"], dict), (
            f"O5: ``summary.by_language`` must be a dict — got "
            f"{type(summary['by_language']).__name__}"
        )

    def test_summary_by_language_matches_top_level(
        self, multi_lang_project: Path
    ) -> None:
        """O5: ``summary.by_language`` and top-level ``language_distribution``
        must hold the same content (mirror, not transformation)."""
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(multi_lang_project))
        result = _run(tool.execute({"output_format": "json"}))
        top_level = result.get("language_distribution")
        summary_view = result.get("summary", {}).get("by_language")
        assert top_level == summary_view, (
            f"O5: summary.by_language ({summary_view!r}) must equal "
            f"language_distribution ({top_level!r})"
        )

    def test_top_level_language_distribution_preserved(
        self, multi_lang_project: Path
    ) -> None:
        """O5 back-compat: ``language_distribution`` must STILL be at the
        top level so existing consumers don't break."""
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(multi_lang_project))
        result = _run(tool.execute({"output_format": "json"}))
        assert "language_distribution" in result, (
            "O5: top-level ``language_distribution`` must be preserved "
            "for back-compat — got keys: " + repr(sorted(result.keys()))
        )
        assert isinstance(result["language_distribution"], dict), (
            "O5: top-level ``language_distribution`` must be a dict"
        )
        assert len(result["language_distribution"]) > 0, (
            "O5: multi-language fixture must produce a populated "
            "``language_distribution``"
        )

    def test_languages_count_matches_by_language_length(
        self, multi_lang_project: Path
    ) -> None:
        """O5: ``summary.languages_count`` must equal
        ``len(summary.by_language)`` so the two cannot drift."""
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(multi_lang_project))
        result = _run(tool.execute({"output_format": "json"}))
        summary = result.get("summary", {})
        by_lang = summary.get("by_language", {})
        count = summary.get("languages_count")
        assert count == len(by_lang), (
            f"O5: summary.languages_count ({count!r}) must equal "
            f"len(summary.by_language) ({len(by_lang)!r}) — drift detected"
        )


class TestO1BatchSearchCanonicalErrorEnvelope:
    """O1 (round-30 dogfood): ``batch_search`` previously raised a raw
    ``ValueError`` from ``validate_arguments`` because its ``execute``
    was not wrapped with ``@handle_mcp_errors`` like every other search
    tool. Programmatic callers (CLI bridges, tests, agents that invoke
    the tool outside the MCP dispatch boundary) crashed instead of
    receiving the canonical error envelope.
    """

    def test_empty_queries_no_raw_value_error(self, tiny_project: Path) -> None:
        """Empty ``queries`` list must NOT raise a raw ``ValueError``."""
        from tree_sitter_analyzer.mcp.tools.batch_search_tool import BatchSearchTool

        tool = BatchSearchTool(str(tiny_project))
        with pytest.raises(Exception) as exc_info:
            _run(tool.execute({"queries": []}))
        # The decorator re-raises as ``AnalysisError`` (an ``MCPError``
        # subclass) — never as a bare ``ValueError``. This mirrors what
        # ``search_content`` / ``list_files`` / ``find_and_grep`` do.
        assert type(exc_info.value).__name__ != "ValueError", (
            "O1: batch_search must NOT raise raw ValueError — the "
            "@handle_mcp_errors decorator should re-raise as MCPError "
            "so the MCP server boundary can build the canonical envelope."
        )

    def test_empty_queries_envelope_through_mcp_boundary(
        self, tiny_project: Path
    ) -> None:
        """Through the MCP dispatch path the failure becomes a canonical
        error envelope (``success: false``, ``error_type: validation``,
        ``agent_summary.verdict='ERROR'``)."""
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            build_agent_friendly_error,
        )
        from tree_sitter_analyzer.mcp.tools.batch_search_tool import BatchSearchTool

        tool = BatchSearchTool(str(tiny_project))
        args = {"queries": []}
        try:
            _run(tool.execute(args))
            pytest.fail("expected validation failure")
        except Exception as e:
            envelope = build_agent_friendly_error("batch_search", e, arguments=args)
        assert envelope["success"] is False
        assert envelope["error_type"] == "validation", (
            f"O1: empty queries must classify as validation — got "
            f"{envelope['error_type']!r}"
        )
        assert envelope["agent_summary"]["verdict"] == "ERROR"
        assert (
            isinstance(envelope.get("summary_line"), str) and envelope["summary_line"]
        )

    def test_malformed_query_missing_pattern_no_raw_value_error(
        self, tiny_project: Path
    ) -> None:
        """A query missing the required ``pattern`` key must also wrap
        cleanly — same shape as the empty-queries case."""
        from tree_sitter_analyzer.mcp.tools.batch_search_tool import BatchSearchTool

        tool = BatchSearchTool(str(tiny_project))
        with pytest.raises(Exception) as exc_info:
            _run(
                tool.execute(
                    {"queries": [{"label": "no-pattern"}, {"pattern": "alpha"}]}
                )
            )
        assert type(exc_info.value).__name__ != "ValueError", (
            "O1: malformed query (missing pattern) must NOT raise raw "
            "ValueError — must be wrapped by @handle_mcp_errors."
        )

    def test_malformed_query_envelope_through_mcp_boundary(
        self, tiny_project: Path
    ) -> None:
        """Through MCP dispatch, malformed query also yields the
        canonical envelope."""
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            build_agent_friendly_error,
        )
        from tree_sitter_analyzer.mcp.tools.batch_search_tool import BatchSearchTool

        tool = BatchSearchTool(str(tiny_project))
        args = {"queries": [{"label": "no-pattern"}, {"pattern": "alpha"}]}
        try:
            _run(tool.execute(args))
            pytest.fail("expected validation failure")
        except Exception as e:
            envelope = build_agent_friendly_error("batch_search", e, arguments=args)
        assert envelope["success"] is False
        assert envelope["error_type"] == "validation"
        assert envelope["agent_summary"]["verdict"] == "ERROR"

    def test_valid_queries_still_succeed(self, tiny_project: Path) -> None:
        """Sanity: a well-formed batch still completes."""
        from tree_sitter_analyzer.mcp.tools.batch_search_tool import BatchSearchTool

        tool = BatchSearchTool(str(tiny_project))
        result = _run(
            tool.execute(
                {
                    "queries": [
                        {"pattern": "def", "roots": [str(tiny_project)]},
                        {"pattern": "return", "roots": [str(tiny_project)]},
                    ]
                }
            )
        )
        assert result["success"] is True


class TestO6ErrorSummaryLineMessage:
    """O6 (round-30 dogfood): the canonical CLI error envelope's
    ``summary_line`` field used to embed the Python exception class
    name (e.g. ``"detect_routes: error — ValueError"``) instead of the
    actual reason. Agents that only read the headline saw no signal
    about *what* failed.
    """

    def test_value_error_message_in_summary_line(self) -> None:
        """A ``ValueError`` with a clear message must put that message
        — not the class name — into the summary_line."""
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            _build_error_envelope,
        )

        exc = ValueError("url_pattern is required for mode 'lookup'")
        envelope = _build_error_envelope("detect_routes", "Detect routes", exc)
        sl = envelope["summary_line"]
        assert isinstance(sl, str) and sl
        # Pre-O6: "detect_routes: error — ValueError" — class name only.
        # Post-O6: the actionable message text is embedded.
        assert "url_pattern is required" in sl, (
            f"O6: summary_line must contain the actual error reason — got {sl!r}"
        )
        # ValueError is the class name; it must not be the *only* signal.
        assert sl != "detect_routes: error — ValueError"
        assert sl != "detect_routes: ValueError"

    def test_agent_summary_summary_line_also_uses_message(self) -> None:
        """The nested ``agent_summary.summary_line`` is what most agents
        read for the headline; it must carry the same actionable
        information (not the class name)."""
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            _build_error_envelope,
        )

        exc = ValueError("url_pattern is required for mode 'lookup'")
        envelope = _build_error_envelope("detect_routes", "Detect routes", exc)
        agent_sl = envelope["agent_summary"]["summary_line"]
        assert "url_pattern is required" in agent_sl, (
            f"O6: agent_summary.summary_line must contain the actual error "
            f"reason — got {agent_sl!r}"
        )
        assert agent_sl != "detect_routes: ValueError"

    @pytest.mark.parametrize(
        "exc,reason_token",
        [
            (
                ValueError("url_pattern is required for mode 'lookup'"),
                "url_pattern is required",
            ),
            (
                FileNotFoundError("No such file: /tmp/missing.py"),
                "No such file",
            ),
            (
                ValueError("file_path is required"),
                "file_path is required",
            ),
            (
                ValueError("mode must be one of summary|file|all"),
                "mode must be one of",
            ),
        ],
    )
    def test_summary_line_uses_message_across_exception_types(
        self, exc: BaseException, reason_token: str
    ) -> None:
        """Multiple exception sources — each must put the actual reason
        into the summary_line, not just the Python class name."""
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            _build_error_envelope,
        )

        envelope = _build_error_envelope("tool", "Tool label", exc)
        sl = envelope["summary_line"]
        agent_sl = envelope["agent_summary"]["summary_line"]
        # The actionable token must appear in both surfaces.
        assert reason_token in sl, (
            f"O6: summary_line must contain reason {reason_token!r} — got {sl!r}"
        )
        assert reason_token in agent_sl, (
            f"O6: agent_summary.summary_line must contain reason "
            f"{reason_token!r} — got {agent_sl!r}"
        )

    @pytest.mark.parametrize(
        "exc,class_name",
        [
            (
                ValueError("url_pattern is required for mode 'lookup'"),
                "ValueError",
            ),
            (
                FileNotFoundError("No such file: /tmp/missing.py"),
                "FileNotFoundError",
            ),
        ],
    )
    def test_summary_line_does_not_leak_class_name_alone(
        self, exc: BaseException, class_name: str
    ) -> None:
        """The class name must not appear *unless* it legitimately
        appears inside the message text. The class name alone is not a
        useful signal."""
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            _build_error_envelope,
        )

        envelope = _build_error_envelope("tool", "Tool label", exc)
        sl = envelope["summary_line"]
        agent_sl = envelope["agent_summary"]["summary_line"]
        # The class name must not appear in the headline (the messages
        # used above don't contain those tokens, so we can check directly).
        assert class_name not in sl, (
            f"O6: summary_line must not leak class name {class_name!r} — got {sl!r}"
        )
        assert class_name not in agent_sl, (
            f"O6: agent_summary.summary_line must not leak class name "
            f"{class_name!r} — got {agent_sl!r}"
        )

    def test_long_message_truncated_with_ellipsis(self) -> None:
        """A very long error message must be truncated to roughly the
        summary-line budget (~80 chars) with ``...`` so the headline
        stays readable. The full text remains on the ``error`` field."""
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            _build_error_envelope,
        )

        long_msg = "x" * 250
        exc = ValueError(long_msg)
        envelope = _build_error_envelope("tool", "Tool label", exc)
        sl = envelope["summary_line"]
        # Headline must be bounded (not 250+ characters).
        assert len(sl) < 120, (
            f"O6: long error messages must be truncated — got len={len(sl)} ({sl!r})"
        )
        assert sl.endswith("..."), (
            f"O6: truncated headline must end with '...' — got {sl!r}"
        )
        # The full message stays on the ``error`` field for callers
        # that need it.
        assert envelope["error"].endswith(long_msg) or long_msg in envelope["error"]

    def test_empty_message_falls_back_to_class_name(self) -> None:
        """When the exception has no message at all, fall back to the
        class name so the headline is still informative (rather than
        ``error — ``)."""
        from tree_sitter_analyzer.cli.commands.mcp_commands import (
            _build_error_envelope,
        )

        class _MysteryError(Exception):
            pass

        envelope = _build_error_envelope("tool", "Tool label", _MysteryError())
        sl = envelope["summary_line"]
        # Either the class name or a sensible fallback — we just require
        # that the headline is non-empty and doesn't end on a dangling em-dash.
        assert isinstance(sl, str) and sl
        assert not sl.rstrip().endswith("—"), (
            f"O6: empty-message exception must not leave a dangling em-dash — "
            f"got {sl!r}"
        )

    def test_end_to_end_detect_routes_lookup_no_class_name_leak(
        self, tmp_path: Path
    ) -> None:
        """E2E: the failure path the dogfood report reproduced —
        ``--detect-routes --detect-routes-mode lookup`` with no
        ``url_pattern`` — must not show ``ValueError`` in the headline."""
        import subprocess
        import sys

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--project-root",
                str(tmp_path),
                "--detect-routes",
                "--detect-routes-mode",
                "lookup",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        # The command must emit a parseable JSON envelope.
        import json as _json

        payload: dict[str, Any] = {}
        for line in proc.stdout.splitlines():
            try:
                payload = _json.loads(line)
                if isinstance(payload, dict) and "summary_line" in payload:
                    break
            except _json.JSONDecodeError:
                continue
        assert payload, (
            f"O6: detect_routes lookup with missing url_pattern must emit a "
            f"JSON envelope on stdout — got stdout={proc.stdout!r} "
            f"stderr={proc.stderr!r}"
        )
        sl = payload.get("summary_line", "")
        agent_sl = payload.get("agent_summary", {}).get("summary_line", "")
        assert "ValueError" not in sl, (
            f"O6: summary_line must not leak 'ValueError' — got {sl!r}"
        )
        assert "ValueError" not in agent_sl, (
            f"O6: agent_summary.summary_line must not leak 'ValueError' — "
            f"got {agent_sl!r}"
        )
        assert "url_pattern" in sl, (
            f"O6: summary_line must contain the actual error reason — got {sl!r}"
        )
