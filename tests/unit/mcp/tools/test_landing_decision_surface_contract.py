"""Regression test: every tool tsa-landing reads MUST emit a verdict.

Why this exists
---------------
The F1 canonical-verdict machinery (commit 4984c573 on
``feat/consolidated``) was never merged into ``feat/autonomous-dev``.
Result: every MCP tool returned ``verdict=None`` for ~5 months. The
``tsa-landing`` skill silently read those Nones into its decision
surface, blinding the whole autonomous-dev agent loop.

This test pins the contract: any tool that tsa-landing relies on for
its 4-section decision surface (project_card, recent_signals, health,
agent_next_step) must return a non-empty string verdict drawn from the
canonical vocabulary. If a future refactor / branch divergence wipes
verdict from one of these tools, this test fails loudly *before* the
agent loop starts running blind.

The canonical vocabulary, kept in sync with the
``_LEGAL_VERDICTS`` set from r37f7-F1:
    SAFE, CAUTION, REVIEW, UNSAFE, INFO, WARN, ERROR, NOT_FOUND
"""

from __future__ import annotations

import asyncio
import warnings
from pathlib import Path

import pytest

_LEGAL_VERDICTS = frozenset(
    {"SAFE", "CAUTION", "REVIEW", "UNSAFE", "INFO", "WARN", "ERROR", "NOT_FOUND"}
)


@pytest.fixture
def tiny_project(tmp_path: Path) -> Path:
    """A 1-file project sufficient for every landing tool to run."""
    (tmp_path / "sample.py").write_text(
        "def greet(name: str) -> str:\n    return f'hello {name}'\n"
    )
    return tmp_path


def _run(coro):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return asyncio.run(coro)


def _assert_canonical_verdict(result: dict, tool_name: str) -> None:
    """A landing-tool result must have a canonical verdict at top-level."""
    assert isinstance(result, dict), f"{tool_name}: result must be a dict"
    verdict = result.get("verdict")
    assert verdict is not None, (
        f"{tool_name}: missing 'verdict' field. tsa-landing's decision "
        f"surface reads this; None blinds the agent loop. "
        f"See feedback_branch-divergence-feature-loss.md."
    )
    assert isinstance(verdict, str), (
        f"{tool_name}: verdict must be str, got {type(verdict).__name__}"
    )
    assert verdict in _LEGAL_VERDICTS, (
        f"{tool_name}: verdict '{verdict}' is not in canonical vocabulary. "
        f"Legal values: {sorted(_LEGAL_VERDICTS)}"
    )


class TestLandingDecisionSurfaceVerdict:
    """Each tool tsa-landing reads MUST emit a verdict."""

    def test_project_overview_has_verdict(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json"}))
        _assert_canonical_verdict(result, "get_project_overview")

    def test_project_health_has_verdict(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_health_tool import (
            ProjectHealthTool,
        )

        tool = ProjectHealthTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json", "max_files": 5}))
        _assert_canonical_verdict(result, "check_project_health")

    def test_change_impact_has_verdict(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.change_impact_tool import (
            ChangeImpactTool,
        )

        tool = ChangeImpactTool(str(tiny_project))
        result = _run(tool.execute({"mode": "diff"}))
        _assert_canonical_verdict(result, "analyze_change_impact")

    def test_agent_workflow_has_verdict(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.agent_workflow_tool import (
            AgentWorkflowTool,
        )

        tool = AgentWorkflowTool(str(tiny_project))
        result = _run(
            tool.execute(
                {"file_path": str(tiny_project / "sample.py"), "output_format": "json"}
            )
        )
        _assert_canonical_verdict(result, "get_agent_workflow")

    def test_agent_skills_has_verdict(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.agent_skills_tool import (
            AgentSkillsTool,
        )

        tool = AgentSkillsTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json"}))
        _assert_canonical_verdict(result, "list_agent_skills")


class TestLandingAgentSummaryMirror:
    """When agent_summary is present, verdict must mirror at both surfaces.

    M10 bidirectional pattern: tsa-landing and other consumers branch
    on either ``result.verdict`` or ``result.agent_summary.verdict``,
    so the two surfaces must agree.
    """

    def test_project_health_mirrors_verdict(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.project_health_tool import (
            ProjectHealthTool,
        )

        tool = ProjectHealthTool(str(tiny_project))
        result = _run(tool.execute({"output_format": "json", "max_files": 5}))
        agent_summary = result.get("agent_summary", {})
        assert isinstance(agent_summary, dict)
        if agent_summary:  # only mirror when agent_summary itself is populated
            assert agent_summary.get("verdict") == result["verdict"], (
                "project_health: agent_summary.verdict does not match "
                "top-level verdict — M10 bidirectional pattern broken."
            )

    def test_change_impact_mirrors_verdict(self, tiny_project: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.change_impact_tool import (
            ChangeImpactTool,
        )

        tool = ChangeImpactTool(str(tiny_project))
        result = _run(tool.execute({"mode": "diff"}))
        agent_summary = result.get("agent_summary", {})
        assert isinstance(agent_summary, dict)
        if agent_summary:
            assert agent_summary.get("verdict") == result["verdict"], (
                "change_impact: M10 verdict mirror broken."
            )
