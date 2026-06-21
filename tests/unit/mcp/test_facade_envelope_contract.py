#!/usr/bin/env python3
"""Parametrized contract tests for the 4 common facade invariants.

Canonical location for these 4 invariants across all 8 production facades:
  - Envelope preserved       (verdict / agent_summary verbatim pass-through)
  - Arg projection           (action key stripped before reaching inner tool)
  - Missing action error     (success=False, verdict in {ERROR, NOT_FOUND})
  - Unknown action error     (success=False, available_actions listed)

Each invariant is parametrized over all 8 production facades so any regression
in the FacadeTool base class or a specific facade builder is caught immediately.

REQ covered: REQ-M-001, REQ-M-002 (a/b/c/d), REQ-C-003, REQ-D-001
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade
from tree_sitter_analyzer.mcp.tools.health_facade import build_health_facade
from tree_sitter_analyzer.mcp.tools.index_facade import build_index_facade
from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade
from tree_sitter_analyzer.mcp.tools.project_facade import build_project_facade
from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade
from tree_sitter_analyzer.mcp.tools.structure_facade import build_structure_facade
from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

# ---------------------------------------------------------------------------
# FakeInnerTool — minimal BaseMCPTool for isolation testing
#
# Designed to be compatible with the arg-projection contract: declares a
# minimal schema so _project_args keeps the keys we send and strips action.
# Supports configurable verdict/agent_summary for envelope-preserved tests.
# set_project_path is inherited from BaseMCPTool (G3 rebind not tested here).
# ---------------------------------------------------------------------------


class FakeInnerTool(BaseMCPTool):
    """Minimal inner tool that records calls and returns a configurable envelope.

    Compatible with all 8 production facades because:
    - schema declares common keys (file_path, symbol, query) so projection keeps them
    - execute() records last_args for assertion
    - verdict and agent_summary are configurable for envelope-preserved tests
    """

    def __init__(
        self,
        verdict: str = "INFO",
        agent_summary: str | dict[str, Any] | None = "fake-summary-sentinel",
        project_root: str | None = None,
    ) -> None:
        self._verdict = verdict
        self._agent_summary = agent_summary
        super().__init__(project_root)
        self.last_args: dict[str, Any] | None = None
        self.call_count: int = 0

    def get_tool_schema(self) -> dict[str, Any]:
        # Declare common cross-facade params so projection does not strip them.
        # additionalProperties: True so any extra key passes through projection
        # without raising on the inner's strict-param guard.
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "symbol": {"type": "string"},
                "query": {"type": "string"},
                "mode": {"type": "string"},
            },
            "additionalProperties": True,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {"name": "fake_inner", "inputSchema": self.get_tool_schema()}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.last_args = dict(arguments)
        self.call_count += 1
        return {
            "success": True,
            "verdict": self._verdict,
            "agent_summary": self._agent_summary,
        }


# ---------------------------------------------------------------------------
# Builder function registry
#
# Each param wraps a builder function with a human-readable id for pytest
# output. All 8 production facades are included; search is included because
# it uses the standard FacadeTool action-map protocol for action=symbol/query.
# ---------------------------------------------------------------------------

_FIRST_VALID_ACTION: dict[str, str] = {
    "edit": "safe",
    "health": "project",
    "index": "status",
    "nav": "navigate",
    "project": "overview",
    "search": "symbol",
    "structure": "outline",
    "viz": "uml",
}

BUILD_FNS = [
    pytest.param(build_edit_facade, id="edit"),
    pytest.param(build_health_facade, id="health"),
    pytest.param(build_index_facade, id="index"),
    pytest.param(build_nav_facade, id="nav"),
    pytest.param(build_project_facade, id="project"),
    pytest.param(build_search_facade, id="search"),
    pytest.param(build_structure_facade, id="structure"),
    pytest.param(build_viz_facade, id="viz"),
]


def _build_with_fake_inner(build_fn: Any) -> tuple[Any, FakeInnerTool]:
    """Build a real facade and inject a FakeInnerTool into its action_map.

    Because the builder functions hardcode their inner tools, we build the real
    facade (project_root=None) and then replace the first action's inner with
    our FakeInnerTool. This gives us a single controllable inner without
    affecting the facade's routing logic or available_actions list.

    Returns (facade, fake_inner) where fake_inner is injected into the first
    registered action so tests can inspect last_args and call_count.
    """
    facade = build_fn(None)
    # Find the first action from the known mapping by facade_name.
    first_action = _FIRST_VALID_ACTION[facade.facade_name]
    fake = FakeInnerTool()
    facade.action_map[first_action] = fake
    return facade, fake, first_action


# ---------------------------------------------------------------------------
# Invariant 1 — Envelope preserved (REQ-M-002a)
#
# The facade must not re-wrap the inner tool's response. verdict and
# agent_summary must pass through verbatim.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("build_fn", BUILD_FNS)
def test_envelope_preserved(build_fn: Any) -> None:
    """verdict and agent_summary pass through the facade verbatim (REQ-M-002a)."""
    facade = build_fn(None)
    first_action = _FIRST_VALID_ACTION[facade.facade_name]

    fake = FakeInnerTool(verdict="SUCCESS", agent_summary="summary-sentinel")
    facade.action_map[first_action] = fake

    result = asyncio.run(facade.execute({"action": first_action}))

    assert result["verdict"] == "SUCCESS", (
        f"facade '{facade.facade_name}': verdict was not passed through verbatim; "
        f"got {result.get('verdict')!r}"
    )
    assert result["agent_summary"] == "summary-sentinel", (
        f"facade '{facade.facade_name}': agent_summary was not passed through verbatim; "
        f"got {result.get('agent_summary')!r}"
    )


# ---------------------------------------------------------------------------
# Invariant 2 — Arg projection: action key stripped (REQ-M-002b)
#
# The 'action' key is a facade control key and must NOT reach the inner tool.
# F4 Landmine A: the inner's strict-param guard raises ValueError on unknown
# keys — the facade must project args before delegating.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("build_fn", BUILD_FNS)
def test_arg_projection_strips_action(build_fn: Any) -> None:
    """The 'action' key must NOT reach the inner tool (REQ-M-002b / F4)."""
    facade = build_fn(None)
    first_action = _FIRST_VALID_ACTION[facade.facade_name]

    fake = FakeInnerTool()
    facade.action_map[first_action] = fake

    asyncio.run(facade.execute({"action": first_action, "file_path": "src/foo.py"}))

    assert fake.last_args is not None, (
        f"facade '{facade.facade_name}': inner tool was never called"
    )
    assert "action" not in fake.last_args, (
        f"facade '{facade.facade_name}': 'action' key leaked into inner tool args; "
        f"got last_args={fake.last_args!r}"
    )


# ---------------------------------------------------------------------------
# Invariant 3 — Missing action returns error envelope (REQ-M-002c)
#
# A call with no 'action' key must return success=False with a verdict of
# ERROR or NOT_FOUND. The inner tool must not be called.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("build_fn", BUILD_FNS)
def test_missing_action_returns_error_envelope(build_fn: Any) -> None:
    """Call with no action key returns success=False, verdict ERROR or NOT_FOUND (REQ-M-002c)."""
    facade = build_fn(None)

    result = asyncio.run(facade.execute({}))

    assert result["success"] is False, (
        f"facade '{facade.facade_name}': expected success=False for missing action, "
        f"got {result.get('success')!r}"
    )
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}, (
        f"facade '{facade.facade_name}': expected verdict in {{ERROR, NOT_FOUND}}, "
        f"got {result.get('verdict')!r}"
    )


# ---------------------------------------------------------------------------
# Invariant 4 — Unknown action returns error envelope with available_actions (REQ-M-002d)
#
# An unregistered action name must return success=False and include
# 'available_actions' in the response so callers can discover valid actions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("build_fn", BUILD_FNS)
def test_unknown_action_returns_error_envelope(build_fn: Any) -> None:
    """Unregistered action returns success=False and lists available_actions (REQ-M-002d)."""
    facade = build_fn(None)

    result = asyncio.run(facade.execute({"action": "__nonexistent_xyz__"}))

    assert result["success"] is False, (
        f"facade '{facade.facade_name}': expected success=False for unknown action, "
        f"got {result.get('success')!r}"
    )
    assert "available_actions" in result, (
        f"facade '{facade.facade_name}': 'available_actions' missing from error envelope; "
        f"got keys={list(result.keys())!r}"
    )
