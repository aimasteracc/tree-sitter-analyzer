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
