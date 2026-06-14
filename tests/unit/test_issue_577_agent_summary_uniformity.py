"""Tests for issue #577: uniform agent_summary + verdict across 7 facade actions.

Actions under test:
  search chain       → CodeGraphQueryTool
  nav navigate       → CodeGraphNavigateTool
  nav impact         → CodeGraphImpactTool
  project metrics    → CodeGraphMetricsTool
  project doc_sync   → DocSyncTool
  health imports     → CodeGraphImportGraphTool
  structure ast_path → CodeGraphASTPathTool

RED-first: every test below was written BEFORE the implementation.
Exact assertions only — no >= / > / <= (CLAUDE.md locked rule).

Canonical verdict vocabulary (from base_tool._LEGAL_VERDICTS):
  SAFE, CAUTION, REVIEW, UNSAFE, INFO, WARN, ERROR, NOT_FOUND
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tests.unit._codegraph_query_helpers import _make_def, _patch_resolver_with

# ─── helpers ──────────────────────────────────────────────────────────────────

_LEGAL_VERDICTS = frozenset(
    {"SAFE", "CAUTION", "REVIEW", "UNSAFE", "INFO", "WARN", "ERROR", "NOT_FOUND"}
)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _assert_agent_summary(result: dict[str, Any], *, context: str = "") -> None:
    """Assert that result contains a well-formed agent_summary block."""
    prefix = f"[{context}] " if context else ""
    assert isinstance(result, dict), f"{prefix}result must be a dict"
    agent_summary = result.get("agent_summary")
    assert isinstance(agent_summary, dict), (
        f"{prefix}agent_summary must be a dict; got {type(agent_summary).__name__!r}. "
        f"Keys present: {list(result.keys())}"
    )
    verdict = agent_summary.get("verdict")
    assert verdict in _LEGAL_VERDICTS, (
        f"{prefix}agent_summary.verdict={verdict!r} must be in canonical vocabulary "
        f"{sorted(_LEGAL_VERDICTS)}"
    )


def _assert_verdict_not_none(result: dict[str, Any], *, context: str = "") -> None:
    """Assert top-level verdict is set and in the canonical vocabulary (not None)."""
    prefix = f"[{context}] " if context else ""
    verdict = result.get("verdict")
    assert verdict is not None, f"{prefix}top-level verdict must not be None"
    assert verdict in _LEGAL_VERDICTS, (
        f"{prefix}top-level verdict={verdict!r} must be in canonical vocabulary"
    )


# ─── search chain (CodeGraphQueryTool) ────────────────────────────────────────


class TestSearchChainAgentSummary:
    """#577: search.chain (CodeGraphQueryTool) must emit agent_summary + verdict."""

    def _make_tool(self, tmp_path: Path) -> Any:
        from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
            CodeGraphQueryTool,
        )

        return CodeGraphQueryTool(str(tmp_path))

    def _mock_cache(self) -> MagicMock:
        mc = MagicMock()
        mc.get_stats.return_value = {"total_files": 0}
        mc.search_symbols.return_value = []
        mc.fts_search_symbols.return_value = []
        return mc

    @pytest.mark.asyncio
    async def test_agent_summary_present_on_not_found(self, tmp_path):
        tool = self._make_tool(tmp_path)
        mc = self._mock_cache()
        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mc):
            result = await tool.execute(
                {"query": "NoSuchSymbol", "output_format": "json"}
            )
        _assert_agent_summary(result, context="search.chain NOT_FOUND")
        _assert_verdict_not_none(result, context="search.chain NOT_FOUND")

    @pytest.mark.asyncio
    async def test_agent_summary_verdict_in_canonical_vocab(self, tmp_path):
        tool = self._make_tool(tmp_path)
        mc = self._mock_cache()
        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mc):
            result = await tool.execute(
                {"query": "NoSuchSymbol", "output_format": "json"}
            )
        verdict = result.get("agent_summary", {}).get("verdict")
        assert verdict in _LEGAL_VERDICTS, (
            f"agent_summary.verdict={verdict!r} not in canonical vocab"
        )

    @pytest.mark.asyncio
    async def test_agent_summary_has_summary_line(self, tmp_path):
        tool = self._make_tool(tmp_path)
        mc = self._mock_cache()
        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mc):
            result = await tool.execute(
                {"query": "NoSuchSymbol", "output_format": "json"}
            )
        agent_summary = result.get("agent_summary", {})
        assert isinstance(agent_summary.get("summary_line"), str), (
            "agent_summary.summary_line must be a string"
        )
        assert agent_summary["summary_line"], (
            "agent_summary.summary_line must be non-empty"
        )

    @pytest.mark.asyncio
    async def test_agent_summary_has_next_step(self, tmp_path):
        tool = self._make_tool(tmp_path)
        mc = self._mock_cache()
        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mc):
            result = await tool.execute(
                {"query": "NoSuchSymbol", "output_format": "json"}
            )
        agent_summary = result.get("agent_summary", {})
        assert "next_step" in agent_summary

    @pytest.mark.asyncio
    async def test_agent_summary_present_on_evidence(self, tmp_path):
        """Lines 289, 292: has_evidence=True branch (summary_line + next_step when symbols found).

        Inject one symbol definition via _patch_resolver_with so that
        state.symbols is non-empty → has_evidence=True → verdict='INFO'
        → the if-branch at line 288 is taken.
        """
        tool = self._make_tool(tmp_path)
        mc = self._mock_cache()
        sym_def = _make_def(file="src/found.py", name="FoundSymbol", kind="function")
        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mc),
            _patch_resolver_with({"FoundSymbol": [sym_def]}),
        ):
            result = await tool.execute(
                {"query": "FoundSymbol", "output_format": "json"}
            )
        assert result.get("verdict") == "INFO"
        agent_summary = result.get("agent_summary", {})
        assert agent_summary.get("verdict") == "INFO"
        # Lines 289-292: summary_line and next_step for the evidence branch
        summary_line = agent_summary.get("summary_line", "")
        assert "symbol" in summary_line
        next_step = agent_summary.get("next_step", "")
        assert "navigate" in next_step, "agent_summary must have next_step key"


# ─── nav navigate (CodeGraphNavigateTool) ─────────────────────────────────────


class TestNavNavigateAgentSummary:
    """#577: nav.navigate (CodeGraphNavigateTool) must emit agent_summary + verdict."""

    def _make_tool(self) -> Any:
        from tree_sitter_analyzer.mcp.tools.codegraph_navigate_tool import (
            CodeGraphNavigateTool,
        )

        return CodeGraphNavigateTool()

    @pytest.mark.asyncio
    async def test_agent_summary_present_not_found(self, tmp_path):
        tool = self._make_tool()
        with (
            patch.object(tool, "_resolve_definition", return_value={"found": False}),
            patch.object(tool, "_find_references", return_value={"found": False}),
            patch.object(
                tool, "_call_hierarchy", return_value={"callers": [], "callees": []}
            ),
        ):
            result = await tool.execute({"symbol": "Ghost", "output_format": "json"})
        _assert_agent_summary(result, context="nav.navigate NOT_FOUND")

    @pytest.mark.asyncio
    async def test_agent_summary_present_info(self, tmp_path):
        tool = self._make_tool()
        with (
            patch.object(
                tool,
                "_resolve_definition",
                return_value={
                    "found": True,
                    "definitions": [{"name": "Foo", "file": "foo.py", "line": 1}],
                },
            ),
            patch.object(tool, "_find_references", return_value={"found": False}),
            patch.object(
                tool, "_call_hierarchy", return_value={"callers": [], "callees": []}
            ),
            patch.object(tool, "_inline_definition_bodies", return_value=None),
        ):
            result = await tool.execute({"symbol": "Foo", "output_format": "json"})
        _assert_agent_summary(result, context="nav.navigate INFO")
        _assert_verdict_not_none(result, context="nav.navigate INFO")

    @pytest.mark.asyncio
    async def test_agent_summary_verdict_in_canonical_vocab(self, tmp_path):
        tool = self._make_tool()
        with (
            patch.object(tool, "_resolve_definition", return_value={"found": False}),
            patch.object(tool, "_find_references", return_value={"found": False}),
            patch.object(
                tool, "_call_hierarchy", return_value={"callers": [], "callees": []}
            ),
        ):
            result = await tool.execute({"symbol": "X", "output_format": "json"})
        verdict = result.get("agent_summary", {}).get("verdict")
        assert verdict in _LEGAL_VERDICTS


# ─── nav impact (CodeGraphImpactTool) ─────────────────────────────────────────


class TestNavImpactAgentSummary:
    """#577: nav.impact (CodeGraphImpactTool) must emit agent_summary + verdict."""

    def _make_tool(self, tmp_path: Path) -> Any:
        from tree_sitter_analyzer.mcp.tools.codegraph_impact_tool import (
            CodeGraphImpactTool,
        )

        return CodeGraphImpactTool(str(tmp_path))

    def _mock_graph(self) -> MagicMock:
        mg = MagicMock()
        mg.resolve_targets.return_value = []
        mg.caller_refs_of.return_value = []
        mg.callee_refs_of.return_value = []
        mg.callers_of.return_value = []
        mg.callees_of.return_value = []
        mg.call_chain.return_value = []
        return mg

    @pytest.mark.asyncio
    async def test_agent_summary_present_function_impact(self, tmp_path):
        tool = self._make_tool(tmp_path)
        mg = self._mock_graph()
        with patch.object(tool, "get_call_graph", return_value=mg):
            result = await tool.execute(
                {
                    "mode": "function_impact",
                    "function_name": "foo",
                    "output_format": "json",
                }
            )
        _assert_agent_summary(result, context="nav.impact function_impact")
        _assert_verdict_not_none(result, context="nav.impact function_impact")

    @pytest.mark.asyncio
    async def test_agent_summary_verdict_in_canonical_vocab(self, tmp_path):
        tool = self._make_tool(tmp_path)
        mg = self._mock_graph()
        with patch.object(tool, "get_call_graph", return_value=mg):
            result = await tool.execute(
                {"mode": "risk_score", "function_name": "foo", "output_format": "json"}
            )
        verdict = result.get("agent_summary", {}).get("verdict")
        assert verdict in _LEGAL_VERDICTS

    @pytest.mark.asyncio
    async def test_medium_risk_yields_review_next_step(self, tmp_path):
        """Line 484: elif verdict in ('CAUTION','REVIEW') next_step branch.

        Build a mock graph where resolve_targets returns one target and
        caller_refs_of returns 5 callers spread across 2 distinct non-target files.
        fan_in=5 (score+=20) + cross_file_callers=2 (score+=15) = 35
        → level='medium' → verdict='REVIEW' → the elif branch is taken.
        """
        from tree_sitter_analyzer.call_graph import FunctionRef

        tool = self._make_tool(tmp_path)

        target = FunctionRef(
            file_path="src/core.py",
            name="critical_fn",
            start_line=1,
            language="python",
        )

        # 5 callers across 2 different non-target files → cross_file_callers=2
        callers = [
            FunctionRef(
                file_path=f"src/mod{i % 2}.py",
                name=f"caller_{i}",
                start_line=i + 1,
                language="python",
            )
            for i in range(5)
        ]

        mg = self._mock_graph()
        mg.resolve_targets.return_value = [target]
        mg.caller_refs_of.return_value = callers
        mg.callee_refs_of.return_value = []
        mg.call_chain.return_value = []

        with patch.object(tool, "get_call_graph", return_value=mg):
            result = await tool.execute(
                {
                    "mode": "risk_score",
                    "function_name": "critical_fn",
                    "output_format": "json",
                }
            )

        verdict = result.get("verdict")
        assert verdict == "REVIEW", (
            f"Expected REVIEW for medium-risk fn (score=35, level=medium), got {verdict!r}"
        )
        agent_summary = result.get("agent_summary", {})
        assert agent_summary.get("verdict") == "REVIEW"
        # Confirm the CAUTION/REVIEW branch's next_step is used (line 484-487)
        next_step = agent_summary.get("next_step", "")
        assert "callers" in next_step


# ─── project metrics (CodeGraphMetricsTool) ───────────────────────────────────


class TestProjectMetricsAgentSummary:
    """#577: project.metrics (CodeGraphMetricsTool) must emit agent_summary + verdict."""

    def _make_tool(self, tmp_path: Path) -> Any:
        from tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool import (
            CodeGraphMetricsTool,
        )

        return CodeGraphMetricsTool(str(tmp_path))

    @pytest.mark.asyncio
    async def test_agent_summary_present(self, tmp_path):
        tool = self._make_tool(tmp_path)
        # cache absent → empty index path
        with patch.object(tool, "_get_cache", return_value=None):
            result = await tool.execute(
                {"sections": ["cache"], "output_format": "json"}
            )
        _assert_agent_summary(result, context="project.metrics no-cache")
        _assert_verdict_not_none(result, context="project.metrics no-cache")

    @pytest.mark.asyncio
    async def test_agent_summary_verdict_in_canonical_vocab(self, tmp_path):
        tool = self._make_tool(tmp_path)
        with patch.object(tool, "_get_cache", return_value=None):
            result = await tool.execute({"output_format": "json"})
        verdict = result.get("agent_summary", {}).get("verdict")
        assert verdict in _LEGAL_VERDICTS

    @pytest.mark.asyncio
    async def test_agent_summary_has_summary_line(self, tmp_path):
        tool = self._make_tool(tmp_path)
        with patch.object(tool, "_get_cache", return_value=None):
            result = await tool.execute({"output_format": "json"})
        agent_summary = result.get("agent_summary", {})
        assert isinstance(agent_summary.get("summary_line"), str)
        assert agent_summary["summary_line"]

    @pytest.mark.asyncio
    async def test_agent_summary_has_next_step(self, tmp_path):
        tool = self._make_tool(tmp_path)
        with patch.object(tool, "_get_cache", return_value=None):
            result = await tool.execute({"output_format": "json"})
        agent_summary = result.get("agent_summary", {})
        assert "next_step" in agent_summary


# ─── project doc_sync (DocSyncTool) ───────────────────────────────────────────


class TestProjectDocSyncAgentSummary:
    """#577: project.doc_sync (DocSyncTool) must emit agent_summary + non-None verdict.

    Root cause: TOON path returned raw {"format": "toon", "toon_content": ...}
    without success/verdict → boundary defaulted verdict to "n/a" (not None,
    but not in canonical vocabulary either).
    """

    def _make_tool(self, tmp_path: Path) -> Any:
        from tree_sitter_analyzer.mcp.tools.doc_sync_tool import DocSyncTool

        return DocSyncTool(str(tmp_path))

    @pytest.mark.asyncio
    async def test_agent_summary_present_json_path(self, tmp_path):
        tool = self._make_tool(tmp_path)
        result = await tool.execute({"output_format": "json"})
        _assert_agent_summary(result, context="project.doc_sync JSON")

    @pytest.mark.asyncio
    async def test_verdict_not_none_json(self, tmp_path):
        tool = self._make_tool(tmp_path)
        result = await tool.execute({"output_format": "json"})
        _assert_verdict_not_none(result, context="project.doc_sync JSON")

    @pytest.mark.asyncio
    async def test_verdict_not_none_toon(self, tmp_path):
        """TOON format must also carry a non-None top-level verdict (the bug path)."""
        tool = self._make_tool(tmp_path)
        result = await tool.execute({"output_format": "toon"})
        # TOON wraps into {format, toon_content, ...scalars}
        # verdict must be present and canonical, NOT None or absent
        verdict = result.get("verdict")
        assert verdict is not None, (
            f"doc_sync TOON path must carry a non-None verdict; got None. "
            f"Keys: {list(result.keys())}"
        )
        assert verdict in _LEGAL_VERDICTS, (
            f"doc_sync TOON verdict={verdict!r} not in canonical vocabulary"
        )

    @pytest.mark.asyncio
    async def test_top_level_verdict_mirrors_agent_summary(self, tmp_path):
        """Top-level verdict == agent_summary.verdict (M10 mirror contract)."""
        tool = self._make_tool(tmp_path)
        result = await tool.execute({"output_format": "json"})
        top = result.get("verdict")
        inner = result.get("agent_summary", {}).get("verdict")
        assert top == inner, (
            f"top-level verdict={top!r} must equal agent_summary.verdict={inner!r}"
        )

    @pytest.mark.asyncio
    async def test_no_stale_refs_yields_safe_verdict(self, tmp_path):
        """Clean doc state → verdict SAFE (no broken refs)."""
        (tmp_path / "README.md").write_text("No file refs here.", encoding="utf-8")
        tool = self._make_tool(tmp_path)
        result = await tool.execute({"output_format": "json"})
        verdict = result.get("verdict")
        assert verdict == "SAFE", (
            f"doc_sync with 0 stale refs should emit verdict=SAFE; got {verdict!r}"
        )

    @pytest.mark.asyncio
    async def test_stale_refs_yields_review_verdict(self, tmp_path):
        """Stale doc refs → verdict REVIEW (agent should fix them)."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text(
            "See `missing_file.py` for details.", encoding="utf-8"
        )
        tool = self._make_tool(tmp_path)
        result = await tool.execute(
            {"doc_patterns": ["docs/*.md"], "output_format": "json"}
        )
        verdict = result.get("verdict")
        assert verdict == "REVIEW", (
            f"doc_sync with stale refs should emit verdict=REVIEW; got {verdict!r}"
        )


# ─── health imports (CodeGraphImportGraphTool) ────────────────────────────────


class TestHealthImportsAgentSummary:
    """#577: health.imports (CodeGraphImportGraphTool) must emit agent_summary + verdict."""

    def _make_tool(self, tmp_path: Path) -> Any:
        from tree_sitter_analyzer.mcp.tools.import_graph_tool import (
            CodeGraphImportGraphTool,
        )

        return CodeGraphImportGraphTool(str(tmp_path))

    def _mock_graph(self) -> MagicMock:
        mg = MagicMock()
        mg.summary.return_value = {
            "total_files": 0,
            "total_edges": 0,
            "most_imported": [],
            "most_importing": [],
        }
        mg.build.return_value = MagicMock(cycles=[])
        mg.dependencies_of.return_value = []
        mg.dependents_of.return_value = []
        mg.blast_radius.return_value = {"affected_files": []}
        return mg

    @pytest.mark.asyncio
    async def test_agent_summary_present_summary_mode(self, tmp_path):
        tool = self._make_tool(tmp_path)
        mg = self._mock_graph()
        with patch.object(tool, "_get_graph", return_value=mg):
            result = await tool.execute({"mode": "summary", "output_format": "json"})
        _assert_agent_summary(result, context="health.imports summary")
        _assert_verdict_not_none(result, context="health.imports summary")

    @pytest.mark.asyncio
    async def test_agent_summary_present_cycles_mode(self, tmp_path):
        tool = self._make_tool(tmp_path)
        mg = self._mock_graph()
        with patch.object(tool, "_get_graph", return_value=mg):
            result = await tool.execute({"mode": "cycles", "output_format": "json"})
        _assert_agent_summary(result, context="health.imports cycles")
        _assert_verdict_not_none(result, context="health.imports cycles")

    @pytest.mark.asyncio
    async def test_agent_summary_verdict_in_canonical_vocab(self, tmp_path):
        tool = self._make_tool(tmp_path)
        mg = self._mock_graph()
        with patch.object(tool, "_get_graph", return_value=mg):
            result = await tool.execute({"mode": "coupling", "output_format": "json"})
        verdict = result.get("agent_summary", {}).get("verdict")
        assert verdict in _LEGAL_VERDICTS


# ─── structure ast_path (CodeGraphASTPathTool) ────────────────────────────────


class TestStructureAstPathAgentSummary:
    """#577: structure.ast_path (CodeGraphASTPathTool) must emit agent_summary + verdict."""

    def _make_tool(self, tmp_path: Path) -> Any:
        from tree_sitter_analyzer.mcp.tools.ast_path_tool import CodeGraphASTPathTool

        return CodeGraphASTPathTool(str(tmp_path))

    @pytest.mark.asyncio
    async def test_agent_summary_present_outline_mode(self, tmp_path):
        src = tmp_path / "sample.py"
        src.write_text("def foo():\n    pass\n", encoding="utf-8")
        tool = self._make_tool(tmp_path)
        result = await tool.execute(
            {"file_path": str(src), "mode": "outline", "output_format": "json"}
        )
        _assert_agent_summary(result, context="structure.ast_path outline")
        _assert_verdict_not_none(result, context="structure.ast_path outline")

    @pytest.mark.asyncio
    async def test_agent_summary_verdict_in_canonical_vocab(self, tmp_path):
        src = tmp_path / "sample.py"
        src.write_text("def foo():\n    pass\n", encoding="utf-8")
        tool = self._make_tool(tmp_path)
        result = await tool.execute(
            {"file_path": str(src), "mode": "outline", "output_format": "json"}
        )
        verdict = result.get("agent_summary", {}).get("verdict")
        assert verdict in _LEGAL_VERDICTS

    @pytest.mark.asyncio
    async def test_agent_summary_has_summary_line(self, tmp_path):
        src = tmp_path / "sample.py"
        src.write_text("def foo():\n    pass\n", encoding="utf-8")
        tool = self._make_tool(tmp_path)
        result = await tool.execute(
            {"file_path": str(src), "mode": "outline", "output_format": "json"}
        )
        agent_summary = result.get("agent_summary", {})
        assert isinstance(agent_summary.get("summary_line"), str)

    @pytest.mark.asyncio
    async def test_agent_summary_has_next_step(self, tmp_path):
        src = tmp_path / "sample.py"
        src.write_text("def foo():\n    pass\n", encoding="utf-8")
        tool = self._make_tool(tmp_path)
        result = await tool.execute(
            {"file_path": str(src), "mode": "outline", "output_format": "json"}
        )
        agent_summary = result.get("agent_summary", {})
        assert "next_step" in agent_summary

    @pytest.mark.asyncio
    async def test_not_found_out_of_range_line(self, tmp_path):
        """Lines 148-149: verdict==NOT_FOUND branch (line beyond EOF → empty path)."""
        src = tmp_path / "sample.py"
        src.write_text("def foo():\n    pass\n", encoding="utf-8")
        tool = self._make_tool(tmp_path)
        # line 999 is past the end of a 2-line file → path=[] → has_data=False → NOT_FOUND
        result = await tool.execute(
            {
                "file_path": str(src),
                "mode": "scope",
                "line": 999,
                "output_format": "json",
            }
        )
        assert result.get("verdict") == "NOT_FOUND"
        agent_summary = result.get("agent_summary", {})
        assert agent_summary.get("verdict") == "NOT_FOUND"
        assert "ast_path" in agent_summary.get("summary_line", "")

    @pytest.mark.asyncio
    async def test_scope_mode_inside_function(self, tmp_path):
        """Lines 157-159: mode=='scope' branch in the agent_summary block."""
        src = tmp_path / "sample.py"
        src.write_text("def foo():\n    pass\n", encoding="utf-8")
        tool = self._make_tool(tmp_path)
        result = await tool.execute(
            {
                "file_path": str(src),
                "mode": "scope",
                "line": 2,
                "output_format": "json",
            }
        )
        # Inside the function → path is non-empty → has_data=True → INFO
        assert result.get("verdict") == "INFO"
        summary_line = result.get("agent_summary", {}).get("summary_line", "")
        # The scope branch produces "ast_path: scope at line ..."
        assert "scope" in summary_line

    @pytest.mark.asyncio
    async def test_path_mode_at_valid_line(self, tmp_path):
        """Lines 161-162: else branch (mode=='path') in the agent_summary block."""
        src = tmp_path / "sample.py"
        src.write_text("def foo():\n    pass\n", encoding="utf-8")
        tool = self._make_tool(tmp_path)
        result = await tool.execute(
            {
                "file_path": str(src),
                "mode": "path",
                "line": 2,
                "output_format": "json",
            }
        )
        assert result.get("verdict") == "INFO"
        summary_line = result.get("agent_summary", {}).get("summary_line", "")
        # The else branch produces "ast_path: mode=path line=... depth=..."
        assert "mode=path" in summary_line

    # ── content-correctness tests (BUG 1 follow-up after #577) ────────────────

    @pytest.mark.asyncio
    async def test_outline_summary_line_shows_true_node_count(self, tmp_path):
        """outline summary_line must contain the TRUE top-level count, not 0.

        BUG: #577 code did `len(result_dict.get("outline") or [])` but the
        outline items live in `result_dict["path"]`, so "outline" is always
        absent → count was always 0.  The fix reads `result_dict.get("path")`.

        File has exactly 2 top-level defs (foo + bar) → count must be 2.
        """
        src = tmp_path / "sample.py"
        src.write_text("def foo():\n    pass\ndef bar():\n    pass\n", encoding="utf-8")
        tool = self._make_tool(tmp_path)
        result = await tool.execute(
            {"file_path": str(src), "mode": "outline", "output_format": "json"}
        )
        assert result.get("verdict") == "INFO"
        summary_line = result.get("agent_summary", {}).get("summary_line", "")
        # Must report the true count 2, NOT the buggy "0 top-level node(s)"
        assert "2 top-level node(s)" in summary_line, (
            f"outline summary_line must contain '2 top-level node(s)'; got: {summary_line!r}"
        )

    @pytest.mark.asyncio
    async def test_scope_summary_line_shows_function_name(self, tmp_path):
        """scope summary_line must name the enclosing function, not '?'.

        BUG: #577 code did `result_dict.get("scope")` but the enclosing scope
        dict lives at `result_dict["enclosing_scope"]`, so "scope" is always
        absent → name was always '?'.  The fix reads `result_dict.get("enclosing_scope")`.

        Line 2 is inside `foo` → summary_line must contain 'foo'.
        """
        src = tmp_path / "sample.py"
        src.write_text("def foo():\n    pass\n", encoding="utf-8")
        tool = self._make_tool(tmp_path)
        result = await tool.execute(
            {
                "file_path": str(src),
                "mode": "scope",
                "line": 2,
                "output_format": "json",
            }
        )
        assert result.get("verdict") == "INFO"
        summary_line = result.get("agent_summary", {}).get("summary_line", "")
        # Must report the real enclosing function name, NOT the buggy '?'
        assert "'foo'" in summary_line, (
            f"scope summary_line must contain \"'foo'\"; got: {summary_line!r}"
        )
