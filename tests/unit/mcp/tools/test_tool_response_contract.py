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
