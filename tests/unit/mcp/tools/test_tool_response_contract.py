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
from types import SimpleNamespace

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

    def test_codegraph_metrics_call_graph_is_read_only_on_cold_cache(
        self, tiny_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tree_sitter_analyzer.mcp.tools import codegraph_metrics_tool
        from tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool import (
            CodeGraphMetricsTool,
        )

        monkeypatch.setattr(
            codegraph_metrics_tool, "ensure_indexed", lambda *_, **__: None
        )

        tool = CodeGraphMetricsTool(str(tiny_project))
        result = _run(
            tool.execute({"sections": ["call_graph"], "output_format": "json"})
        )

        validate_tool_response(result, "codegraph_metrics")
        assert result["success"] is True
        assert result["call_graph"]["status"] == "empty"
        assert result["call_graph"]["data_source"] == "none"

    def test_codegraph_metrics_call_graph_uses_cached_graph(
        self, tiny_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tree_sitter_analyzer import call_graph
        from tree_sitter_analyzer.mcp.tools import codegraph_metrics_tool
        from tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool import (
            CodeGraphMetricsTool,
        )

        fake_cache = object()
        monkeypatch.setattr(
            codegraph_metrics_tool, "ensure_indexed", lambda *_, **__: fake_cache
        )

        class FakeCachedCallGraph:
            def __init__(self, project_root: str, cache: object) -> None:
                assert project_root == str(tiny_project)
                assert cache is fake_cache
                self._call_edges = [
                    (
                        SimpleNamespace(file_path="main.py", name="entry"),
                        SimpleNamespace(file_path="main.py", name="helper"),
                        2,
                    )
                ]

            def build(self) -> None:
                self.built = True

            def all_functions(self) -> list[dict[str, str]]:
                return [
                    {"file_path": "main.py", "name": "entry"},
                    {"file_path": "main.py", "name": "helper"},
                ]

            def call_edges(self) -> list:
                """Public accessor used by codegraph_metrics_tool."""
                return self._call_edges

        monkeypatch.setattr(call_graph, "CachedCallGraph", FakeCachedCallGraph)

        tool = CodeGraphMetricsTool(str(tiny_project))
        result = _run(
            tool.execute({"sections": ["call_graph"], "output_format": "json"})
        )

        validate_tool_response(result, "codegraph_metrics")
        assert result["success"] is True
        assert result["call_graph"]["status"] == "computed"
        assert result["call_graph"]["total_functions"] == 2
        assert result["call_graph"]["total_call_edges"] == 1
        assert result["call_graph"]["data_source"] == "ast_cache"


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
            "get_code_outline": {"file_path": sample_file},
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
            "ast_diff": {
                "mode": "diff_strings",
                "old_source": "a = 1",
                "new_source": "a = 2",
                "language": "python",
            },
            "codegraph_callers": {"function_name": "greet"},
            "codegraph_callees": {"function_name": "greet"},
            "codegraph_symbol_search": {"query": "greet"},
            "codegraph_resolve": {"symbol": "greet"},
            "codegraph_ast_path": {"mode": "outline", "file_path": sample_file},
            "codegraph_overview": {},
            # Pain pass 2: 4 new tools were registered without being added
            # to this envelope-contract table, which made the suite fail
            # on a contract-coverage check.
            "codegraph_impact": {
                "mode": "risk_score",
                "function_name": "greet",
            },
            "codegraph_navigate": {"mode": "outline", "file_path": sample_file},
            "codegraph_pr_review": {"mode": "diff"},
            "semantic_classify": {
                "mode": "classify_string",
                "old_source": "a = 1",
                "new_source": "a = 2",
                "language": "python",
            },
            # Pain pass 4: 2 more tools shipped without coverage rows.
            "codegraph_import_graph": {"mode": "summary"},
            "codegraph_dead_code": {"mode": "summary"},
            # Pain pass 5: clone detector + class hierarchy + dependency
            # matrix + Feature 3 constraint DSL — registered without
            # envelope-contract rows.
            "codegraph_similarity": {"mode": "all"},
            "codegraph_class_hierarchy": {"mode": "summary"},
            "codegraph_class_inspect": {
                "class_name": "LanguagePlugin",
                "output_format": "json",
            },
            "codegraph_dependency_matrix": {"mode": "summary"},
            "check_constraints": {"output_format": "json"},
            # Pain pass 6: server.py registry consolidation surfaced 8
            # tools that were in the central registry but missing from
            # server.py's stale copy. They lack envelope-contract rows
            # for the same reason — server.py never instantiated them so
            # the contract sweep never saw them.
            "codegraph_call_path": {
                "mode": "forward",
                "source_function": "greet",
            },
            "codegraph_xref": {"symbol": "greet"},
            "codegraph_sitemap": {"mode": "module"},
            "codegraph_complexity_heatmap": {"mode": "project"},
            "codegraph_visualize": {"mode": "full"},
            "codegraph_uml": {"diagram": "class"},
            "codegraph_autoindex": {"mode": "status"},
            "codegraph_full_index": {"mode": "stats"},
            "codegraph_metrics": {"mode": "project"},
            "codegraph_incremental_sync": {"mode": "status"},
            "codegraph_status": {},
            "codegraph_context": {"task": "greet", "output_format": "json"},
            "codegraph_explore": {"query": "greet"},
            "codegraph_query": {"query": "search('greet').explore()"},
            # consolidated-only tools ported during merge of feat/autonomous-dev
            "trace_impact": {"symbol": "greet", "mode": "callers"},
            "modification_guard": {"file_path": sample_file, "symbol": "greet"},
            "batch_search": {
                "queries": [{"query": "greet", "roots": [str(tiny_project)]}]
            },
            "build_project_index": {"roots": [str(tiny_project)]},
            "check_tools": {},
            # r37fG: persistent decision journal. Search with a no-match
            # query exercises the canonical envelope without needing
            # pre-existing rows in the contract fixture.
            "decision_journal": {
                "mode": "search",
                "query": "contract-test-no-match",
                "output_format": "json",
            },
            "doc_sync": {"output_format": "json"},
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
