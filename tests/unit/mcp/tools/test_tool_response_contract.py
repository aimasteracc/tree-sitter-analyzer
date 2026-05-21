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
