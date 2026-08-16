#!/usr/bin/env python3
"""Tests for the ``nav`` facade (Wave B, P0 geode layer).

Required cases per p0-facade-framework-spec.md §5:

1.  builds & routes        — factory returns FacadeTool, every action present
2.  action routing         — {"action": X, ...} reaches the right inner
3.  arg projection         — action NOT in args the inner received
4.  sibling-param drop     — param for action A doesn't reach action B's inner
5.  R3 normalize           — symbol -> function_name for function_name-typed inners
6.  bespoke route          — scope-discriminated callers/callees (R4)
7.  envelope preserved     — verdict / agent_summary come through verbatim
8.  missing/unknown action — returns error envelope (success=False, available_actions)
9.  rebind                 — set_project_path propagates to action_map + bespoke inners
10. no override            — factory returns FacadeTool (set_project_path not overridden)
11. end-to-end no strict   — route through REAL inner, assert no strict-param ValueError
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# INVARIANT DELEGATION NOTICE
# The following 4 common facade invariants are tested canonically in:
#   tests/unit/mcp/test_facade_envelope_contract.py
#
# Delegated invariants (do NOT add new duplicates here):
#   - envelope preserved       (verdict / agent_summary verbatim pass-through)
#   - arg projection           (action key stripped before reaching inner tool)
#   - missing action error     (success=False, verdict in {ERROR, NOT_FOUND})
#   - unknown action error     (success=False, available_actions listed)
#
# Facade-specific tests that remain in this file:
#   - action routing to each named nav action (navigate/callers/callees/resolve/...)
#   - sibling-param drop between actions
#   - R3 normalize (symbol -> function_name for function_name-typed inners)
#   - R4 bespoke route: scope-discriminated callers/callees via bespoke closure
#   - end-to-end no strict leak (F4 regression guard with real inner tools)
#   - set_project_path rebind propagation to action_map and bespoke inners (G3)
# ---------------------------------------------------------------------------
from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

# ---------------------------------------------------------------------------
# 1. builds & routes
# ---------------------------------------------------------------------------


def test_nav_facade_builds_returns_facade_tool() -> None:
    facade = build_nav_facade(project_root=None)
    assert isinstance(facade, FacadeTool)
    assert facade.facade_name == "nav"


def test_nav_facade_all_actions_present() -> None:
    facade = build_nav_facade(project_root=None)
    all_actions = set(facade.action_map) | set(facade.bespoke_map)
    expected = {
        "navigate",
        "call_path",
        "xref",
        "resolve",
        "lineage",
        "impact",
        "trace",
        "context",
        "callers",
        "callees",
        "callee_tree",
        "caller_tree",
        # RFC-0014 Phase B: test_map
        "test_map",
        # RFC-0014 Phase C: co_change
        "co_change",
    }
    assert expected == all_actions


def test_nav_facade_bespoke_actions_are_context_callers_callees() -> None:
    facade = build_nav_facade(project_root=None)
    # context, callers, callees, test_map, co_change are all bespoke routes
    for bespoke_action in ("context", "callers", "callees", "test_map", "co_change"):
        assert bespoke_action in facade.bespoke_map, (
            f"Expected '{bespoke_action}' in bespoke_map"
        )
        assert bespoke_action not in facade.action_map, (
            f"'{bespoke_action}' must NOT appear in action_map (only bespoke)"
        )


# ---------------------------------------------------------------------------
# 2. action routing — patch each inner's execute and verify it's called
# ---------------------------------------------------------------------------


def test_navigate_action_routes_to_navigate_inner() -> None:
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["navigate"]
    sentinel = {"success": True, "verdict": "INFO", "agent_summary": {}}
    with patch.object(
        inner, "execute", new=AsyncMock(return_value=sentinel)
    ) as mock_exec:
        result = asyncio.run(facade.execute({"action": "navigate", "symbol": "Foo"}))
    mock_exec.assert_called_once()
    assert result is sentinel


def test_call_path_action_routes_to_call_path_inner() -> None:
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["call_path"]
    sentinel = {"success": True, "verdict": "INFO", "agent_summary": {}}
    with patch.object(inner, "execute", new=AsyncMock(return_value=sentinel)):
        result = asyncio.run(
            facade.execute(
                {
                    "action": "call_path",
                    "source_function": "A",
                    "target_function": "B",
                }
            )
        )
    assert result is sentinel


def test_xref_action_routes_to_xref_inner() -> None:
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["xref"]
    sentinel = {"success": True, "verdict": "INFO", "agent_summary": {}}
    with patch.object(inner, "execute", new=AsyncMock(return_value=sentinel)):
        result = asyncio.run(facade.execute({"action": "xref", "symbol": "Bar"}))
    assert result is sentinel


def test_resolve_action_routes_to_resolve_inner() -> None:
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["resolve"]
    sentinel = {"success": True, "verdict": "INFO", "agent_summary": {}}
    with patch.object(inner, "execute", new=AsyncMock(return_value=sentinel)):
        result = asyncio.run(facade.execute({"action": "resolve", "symbol": "MyClass"}))
    assert result is sentinel


def test_lineage_action_routes_to_lineage_inner() -> None:
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["lineage"]
    sentinel = {"success": True, "verdict": "INFO", "agent_summary": {}}
    with patch.object(inner, "execute", new=AsyncMock(return_value=sentinel)):
        result = asyncio.run(facade.execute({"action": "lineage", "symbol": "Base"}))
    assert result is sentinel


def test_impact_action_routes_to_impact_inner() -> None:
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["impact"]
    sentinel = {"success": True, "verdict": "INFO", "agent_summary": {}}
    with patch.object(inner, "execute", new=AsyncMock(return_value=sentinel)):
        result = asyncio.run(
            facade.execute(
                {
                    "action": "impact",
                    "mode": "function_impact",
                    "function_name": "go",
                }
            )
        )
    assert result is sentinel


def test_trace_action_routes_to_trace_inner() -> None:
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["trace"]
    sentinel = {"success": True, "verdict": "INFO", "agent_summary": {}}
    with patch.object(inner, "execute", new=AsyncMock(return_value=sentinel)):
        result = asyncio.run(facade.execute({"action": "trace", "symbol": "go"}))
    assert result is sentinel


# ---------------------------------------------------------------------------
# 3. arg projection — action key must NOT reach the inner
# ---------------------------------------------------------------------------


def _capture_inner(facade: FacadeTool, action: str) -> tuple[Any, list[dict[str, Any]]]:
    """Patch an action_map inner's execute to capture received args."""
    inner = facade.action_map[action]
    captured: list[dict[str, Any]] = []

    async def _capture(args: dict[str, Any]) -> dict[str, Any]:
        captured.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    return inner, captured, _capture


def test_arg_projection_strips_action_from_navigate() -> None:
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["navigate"]
    received: list[dict[str, Any]] = []

    async def _spy(args: dict[str, Any]) -> dict[str, Any]:
        received.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    with patch.object(inner, "execute", new=_spy):
        asyncio.run(
            facade.execute({"action": "navigate", "symbol": "Foo", "mode": "full"})
        )

    assert received, "inner.execute was not called"
    assert "action" not in received[0], "action key leaked through to inner"


def test_arg_projection_strips_action_from_impact() -> None:
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["impact"]
    received: list[dict[str, Any]] = []

    async def _spy(args: dict[str, Any]) -> dict[str, Any]:
        received.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    with patch.object(inner, "execute", new=_spy):
        asyncio.run(
            facade.execute(
                {
                    "action": "impact",
                    "mode": "function_impact",
                    "function_name": "run",
                }
            )
        )

    assert received and "action" not in received[0]


# ---------------------------------------------------------------------------
# 4. sibling-param drop
# ---------------------------------------------------------------------------


def test_sibling_param_not_forwarded_to_navigate() -> None:
    """source_function (call_path param) must not reach navigate inner."""
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["navigate"]
    received: list[dict[str, Any]] = []

    async def _spy(args: dict[str, Any]) -> dict[str, Any]:
        received.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    with patch.object(inner, "execute", new=_spy):
        asyncio.run(
            facade.execute(
                {
                    "action": "navigate",
                    "symbol": "Foo",
                    "source_function": "Bar",
                }
            )
        )

    assert received and "source_function" not in received[0]


def test_sibling_param_not_forwarded_to_trace() -> None:
    """function_names (impact param) must not reach trace inner."""
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["trace"]
    received: list[dict[str, Any]] = []

    async def _spy(args: dict[str, Any]) -> dict[str, Any]:
        received.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    with patch.object(inner, "execute", new=_spy):
        asyncio.run(
            facade.execute(
                {
                    "action": "trace",
                    "symbol": "Foo",
                    "function_names": ["A", "B"],
                }
            )
        )

    assert received and "function_names" not in received[0]


# ---------------------------------------------------------------------------
# 5. R3 normalize — symbol -> function_name
# ---------------------------------------------------------------------------


def test_r3_symbol_normalized_for_action_map_routes() -> None:
    """navigate inner reads ``symbol`` — normalization should NOT overwrite it.
    lineage also reads ``symbol`` — same. Check a function_name-only inner."""
    # We don't have a direct action_map inner that ONLY reads function_name in nav's
    # action_map — the impact inner reads function_name though.
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["impact"]
    received: list[dict[str, Any]] = []

    async def _spy(args: dict[str, Any]) -> dict[str, Any]:
        received.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    with patch.object(inner, "execute", new=_spy):
        # Pass symbol= instead of function_name= — framework R3 should copy it.
        asyncio.run(
            facade.execute(
                {
                    "action": "impact",
                    "mode": "function_impact",
                    "symbol": "myFunc",
                }
            )
        )

    assert received
    # R3: framework copies symbol -> function_name when inner declares function_name
    assert received[0].get("function_name") == "myFunc"


# ---------------------------------------------------------------------------
# 6. bespoke route (R4) — scope-discriminated callers/callees
# ---------------------------------------------------------------------------


def _build_facade_with_mock_inners() -> tuple[FacadeTool, dict[str, AsyncMock]]:
    """Build a nav facade and replace all bespoke backing instances with mocks."""
    facade = build_nav_facade(project_root=None)
    mocks: dict[str, AsyncMock] = {}
    # The bespoke inners are at specific positions in _bespoke_inners.
    # Instead, patch the execute of each tracked bespoke inner by index.
    # Order from build_nav_facade: context_inner[0], callers_point[1],
    # callers_graph[2], callees_point[3], callees_graph[4].
    names = [
        "context_inner",
        "callers_point",
        "callers_graph",
        "callees_point",
        "callees_graph",
    ]
    for i, name in enumerate(names):
        m = AsyncMock(
            return_value={
                "success": True,
                "verdict": "INFO",
                "inner": name,
                "agent_summary": {},
            }
        )
        facade._bespoke_inners[i].execute = m
        mocks[name] = m
    return facade, mocks


def test_callers_scope_point_uses_callers_tool() -> None:
    facade, mocks = _build_facade_with_mock_inners()
    result = asyncio.run(
        facade.execute(
            {
                "action": "callers",
                "symbol": "run",
                "scope": "point",
            }
        )
    )
    assert result["inner"] == "callers_point"
    mocks["callers_point"].assert_called_once()
    mocks["callers_graph"].assert_not_called()


def test_callers_default_scope_is_point() -> None:
    """scope=point is the default; omitting scope should behave the same."""
    facade, mocks = _build_facade_with_mock_inners()
    result = asyncio.run(
        facade.execute(
            {
                "action": "callers",
                "function_name": "run",
            }
        )
    )
    assert result["inner"] == "callers_point"
    mocks["callers_point"].assert_called_once()
    mocks["callers_graph"].assert_not_called()


def test_callers_scope_graph_uses_call_graph_tool() -> None:
    facade, mocks = _build_facade_with_mock_inners()
    result = asyncio.run(
        facade.execute(
            {
                "action": "callers",
                "symbol": "run",
                "scope": "graph",
            }
        )
    )
    assert result["inner"] == "callers_graph"
    mocks["callers_graph"].assert_called_once()
    mocks["callers_point"].assert_not_called()
    # Must inject mode=callers into the call-graph inner args.
    call_args = mocks["callers_graph"].call_args[0][0]
    assert call_args.get("mode") == "callers"


def test_callees_scope_point_uses_callees_tool() -> None:
    facade, mocks = _build_facade_with_mock_inners()
    result = asyncio.run(
        facade.execute(
            {
                "action": "callees",
                "symbol": "process",
                "scope": "point",
            }
        )
    )
    assert result["inner"] == "callees_point"
    mocks["callees_point"].assert_called_once()
    mocks["callees_graph"].assert_not_called()


def test_callees_scope_graph_uses_call_graph_tool() -> None:
    facade, mocks = _build_facade_with_mock_inners()
    result = asyncio.run(
        facade.execute(
            {
                "action": "callees",
                "function_name": "process",
                "scope": "graph",
            }
        )
    )
    assert result["inner"] == "callees_graph"
    mocks["callees_graph"].assert_called_once()
    mocks["callees_point"].assert_not_called()
    call_args = mocks["callees_graph"].call_args[0][0]
    assert call_args.get("mode") == "callees"


def test_callers_bespoke_r3_symbol_to_function_name() -> None:
    """Bespoke route: symbol= should be defensively copied to function_name= by
    _clean_bespoke_args before the closure receives it."""
    facade, mocks = _build_facade_with_mock_inners()
    asyncio.run(
        facade.execute(
            {
                "action": "callers",
                "symbol": "myFunc",
                "scope": "point",
            }
        )
    )
    call_args = mocks["callers_point"].call_args[0][0]
    # After R3 copy and scope-routing, function_name should be present.
    assert call_args.get("function_name") == "myFunc"


def test_scope_not_forwarded_to_callers_point_inner() -> None:
    """scope is a facade control key; must not leak into the callers_point inner."""
    facade, mocks = _build_facade_with_mock_inners()
    asyncio.run(
        facade.execute(
            {
                "action": "callers",
                "function_name": "go",
                "scope": "point",
            }
        )
    )
    call_args = mocks["callers_point"].call_args[0][0]
    assert "scope" not in call_args


def test_scope_not_forwarded_to_callees_graph_inner() -> None:
    facade, mocks = _build_facade_with_mock_inners()
    asyncio.run(
        facade.execute(
            {
                "action": "callees",
                "function_name": "go",
                "scope": "graph",
            }
        )
    )
    call_args = mocks["callees_graph"].call_args[0][0]
    assert "scope" not in call_args


# ---------------------------------------------------------------------------
# 7. envelope preserved
# ---------------------------------------------------------------------------


def test_envelope_verdict_preserved() -> None:
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["trace"]
    envelope = {
        "success": True,
        "verdict": "SAFE",
        "agent_summary": {"verdict": "SAFE", "summary_line": "ok", "next_step": "n/a"},
    }
    with patch.object(inner, "execute", new=AsyncMock(return_value=envelope)):
        result = asyncio.run(facade.execute({"action": "trace", "symbol": "X"}))
    assert result["verdict"] == "SAFE"
    assert result["agent_summary"]["summary_line"] == "ok"


def test_envelope_not_rewrapped() -> None:
    """The facade must not nest the inner envelope inside another dict."""
    facade = build_nav_facade(project_root=None)
    inner = facade.action_map["navigate"]
    envelope = {"success": True, "verdict": "INFO", "custom_key": "preserved"}
    with patch.object(inner, "execute", new=AsyncMock(return_value=envelope)):
        result = asyncio.run(facade.execute({"action": "navigate", "symbol": "Z"}))
    assert result.get("custom_key") == "preserved"


# ---------------------------------------------------------------------------
# 8. missing / unknown action -> error envelope
# ---------------------------------------------------------------------------


def test_missing_action_returns_error_envelope() -> None:
    facade = build_nav_facade(project_root=None)
    result = asyncio.run(facade.execute({"symbol": "Foo"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    assert "available_actions" in result
    assert "navigate" in result["available_actions"]


def test_unknown_action_returns_error_envelope() -> None:
    facade = build_nav_facade(project_root=None)
    result = asyncio.run(facade.execute({"action": "teleport", "symbol": "Foo"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    all_listed = str(result["available_actions"])
    assert "callers" in all_listed
    assert "navigate" in all_listed


# ---------------------------------------------------------------------------
# 9. rebind — set_project_path propagates to action_map + bespoke inners
# ---------------------------------------------------------------------------


def test_set_project_path_rebinds_action_map_inners(tmp_path: Any) -> None:
    facade = build_nav_facade(project_root=None)
    new_root = str(tmp_path)
    facade.set_project_path(new_root)
    for action, inner in facade.action_map.items():
        assert inner.project_root == new_root, (
            f"action_map[{action!r}] not rebound; got {inner.project_root!r}"
        )


def test_set_project_path_rebinds_bespoke_inners(tmp_path: Any) -> None:
    """G3: all four bespoke inners (callers_point, callers_graph, callees_point,
    callees_graph) must be rebound when set_project_path is called."""
    facade = build_nav_facade(project_root=None)
    new_root = str(tmp_path)
    facade.set_project_path(new_root)
    for i, inner in enumerate(facade._bespoke_inners):
        assert inner.project_root == new_root, (
            f"_bespoke_inners[{i}] not rebound; got {inner.project_root!r}"
        )


def test_six_bespoke_inners_registered() -> None:
    """Exactly 6 bespoke inners: context_inner, callers_point, callers_graph,
    callees_point, callees_graph, impact_inner — required by G3 for reliable
    multi-project rebind. impact_inner added in RFC-0014 Phase B (test_map)."""
    facade = build_nav_facade(project_root=None)
    assert len(facade._bespoke_inners) == 6, (
        f"Expected 6 registered bespoke inners, got {len(facade._bespoke_inners)}"
    )


# ---------------------------------------------------------------------------
# 10. no set_project_path override (trivially satisfied; explicit assertion)
# ---------------------------------------------------------------------------


def test_nav_facade_returns_facade_tool_not_subclass() -> None:
    """The factory returns an instance of FacadeTool — no subclassing means
    set_project_path is not overridden (guarded by the framework test)."""
    facade = build_nav_facade(project_root=None)
    assert type(facade) is FacadeTool  # noqa: E721 — exact type, not isinstance


# ---------------------------------------------------------------------------
# 11. end-to-end no strict-param leak (F4 regression guard)
# ---------------------------------------------------------------------------


def test_navigate_action_no_strict_leak(tmp_path: Any) -> None:
    """Route navigate through the REAL CodeGraphNavigateTool in a fresh tmp dir.

    The inner tool's strict-param guard must NOT raise ``unknown parameter 'action'``.
    The inner may return an error envelope (no index in tmp_path) — that is fine.
    """
    facade = build_nav_facade(project_root=str(tmp_path))
    try:
        result = asyncio.run(
            facade.execute({"action": "navigate", "symbol": "zzz_nonexistent"})
        )
    except ValueError as exc:
        assert "action" not in str(exc), (
            f"facade leaked 'action' to the inner strict-param guard (F4 regression): {exc}"
        )
        raise
    assert isinstance(result, dict)
    assert "success" in result


def test_callers_point_action_no_strict_leak(tmp_path: Any) -> None:
    """Bespoke callers route (scope=point) must not trip the inner's strict-param guard."""
    facade = build_nav_facade(project_root=str(tmp_path))
    try:
        result = asyncio.run(
            facade.execute(
                {
                    "action": "callers",
                    "symbol": "zzz_nonexistent",
                    "scope": "point",
                }
            )
        )
    except ValueError as exc:
        assert "action" not in str(exc), (
            f"bespoke callers route leaked unexpected param (F4 regression): {exc}"
        )
        raise
    assert isinstance(result, (dict, int))


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_nav_facade_schema_contains_action() -> None:
    facade = build_nav_facade(project_root=None)
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "action" in props
    assert "action" in schema.get("required", [])
    # Scope and mode must be present (control keys declared on facade schema).
    assert "scope" in props
    assert "mode" in props


def test_nav_facade_schema_action_enum_complete() -> None:
    facade = build_nav_facade(project_root=None)
    schema = facade.get_tool_schema()
    enum = set(schema["properties"]["action"]["enum"])
    expected = {
        "navigate",
        "call_path",
        "xref",
        "resolve",
        "lineage",
        "impact",
        "trace",
        "context",
        "callers",
        "callees",
        "callee_tree",
        "caller_tree",
        # RFC-0014 Phase B: test_map
        "test_map",
        # RFC-0014 Phase C: co_change
        "co_change",
    }
    assert expected == enum


def test_nav_facade_annotations_read_only() -> None:
    """All nav actions are read-only — annotations must reflect this honestly."""
    facade = build_nav_facade(project_root=None)
    defn = facade.get_tool_definition()
    ann = defn.get("annotations", {})
    assert ann.get("readOnlyHint") is True
    assert ann.get("destructiveHint") is False
    assert ann.get("idempotentHint") is True
    assert ann.get("openWorldHint") is False


# ---------------------------------------------------------------------------
# Fix ② — description discoverability: "codegraph" keyword must be present
# ---------------------------------------------------------------------------


def test_nav_facade_description_contains_codegraph_keyword() -> None:
    """Fix ②: nav description must contain 'codegraph' so ToolSearch/keyword
    matching by headless agents lands here when they search for 'codegraph'."""
    facade = build_nav_facade(project_root=None)
    defn = facade.get_tool_definition()
    description = defn.get("description", "")
    assert "codegraph" in description.lower(), (
        "nav facade description must contain 'codegraph' for agent discoverability "
        "(fix ②: headless agents ToolSearch 'codegraph' must find facade tools)"
    )


# ---------------------------------------------------------------------------
# Fix ③ — context action: symbol/query → task normalization in running loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_action_with_symbol_normalizes_to_task_no_valueerror(
    tmp_path: Any,
) -> None:
    """Fix ③: nav action=context with symbol= must NOT raise ValueError('task is
    required') when called inside an already-running event loop (MCP server context).

    Before fix: CodeGraphContextTool validated 'task is required' but the
    description said 'symbol/query (required)', causing agents to always fail
    when passing symbol= to action=context.
    After fix: the bespoke _context_route normalizes symbol/query → task before
    delegating, so no ValueError is raised.
    """
    facade = build_nav_facade(project_root=str(tmp_path))
    # Passing symbol= instead of task= — this is what agents do per the description.
    result = await facade.execute(
        {
            "action": "context",
            "symbol": "execute",
        }
    )
    # Must return a dict (success or not — no index in tmp_path is fine).
    assert isinstance(result, dict), "context action must return a dict"
    assert "success" in result, "context action result must have 'success' key"
    # Critically: must NOT raise ValueError("task is required").


@pytest.mark.asyncio
async def test_context_action_with_query_normalizes_to_task_no_valueerror(
    tmp_path: Any,
) -> None:
    """Fix ③: nav action=context with query= (alternate alias) must also work."""
    facade = build_nav_facade(project_root=str(tmp_path))
    result = await facade.execute(
        {
            "action": "context",
            "query": "how does execute work",
        }
    )
    assert isinstance(result, dict)
    assert "success" in result


@pytest.mark.asyncio
async def test_call_path_in_running_event_loop_returns_dict(tmp_path: Any) -> None:
    """Fix ③: nav action=call_path in an already-running event loop must not
    raise ValueError or any asyncio error.

    Regression guard for the benchmark-stream diagnosis: 'call_path in MCP
    async context reports ValueError: task...' — confirmed root cause was
    action=context being called with symbol= (not call_path itself), but this
    test guards that call_path itself is also clean in the running-loop context.
    """
    facade = build_nav_facade(project_root=str(tmp_path))
    result = await facade.execute(
        {
            "action": "call_path",
            "source_function": "foo",
            "target_function": "bar",
        }
    )
    assert isinstance(result, dict)
    assert result.get("verdict") in {"PATH_FOUND", "NO_PATH", "ERROR", "NOT_FOUND"}


# ---------------------------------------------------------------------------
# DF-13: limit param survives nav action=callers/callees projection
# ---------------------------------------------------------------------------


def test_callers_limit_forwarded_to_point_inner() -> None:
    """DF-13: limit= must reach callers_point inner when action=callers scope=point.

    The _callers_route whitelist now includes 'limit'; verify it is forwarded
    so the budget cap is honoured through the facade boundary.
    """
    facade, mocks = _build_facade_with_mock_inners()
    asyncio.run(
        facade.execute(
            {
                "action": "callers",
                "function_name": "execute",
                "scope": "point",
                "limit": 10,
            }
        )
    )
    call_args = mocks["callers_point"].call_args[0][0]
    assert call_args.get("limit") == 10, (
        f"limit not forwarded to callers_point inner: {call_args}"
    )


def test_callees_limit_forwarded_to_point_inner() -> None:
    """DF-13: limit= must reach callees_point inner when action=callees scope=point."""
    facade, mocks = _build_facade_with_mock_inners()
    asyncio.run(
        facade.execute(
            {
                "action": "callees",
                "function_name": "execute",
                "scope": "point",
                "limit": 10,
            }
        )
    )
    call_args = mocks["callees_point"].call_args[0][0]
    assert call_args.get("limit") == 10, (
        f"limit not forwarded to callees_point inner: {call_args}"
    )


# ---------------------------------------------------------------------------
# RFC-0022 P0.4: explicit read-existing context access
# ---------------------------------------------------------------------------

_CONTEXT_READ_EXISTING_ARGS: dict[str, Any] = {
    "action": "context",
    "task": "explain dispatch",
    "access_mode": "read_existing",
    "snapshot_id": "idxsnap_01",
    "source_generation": "generation_01",
}
_ACCESS_EVIDENCE: dict[str, Any] = {
    "success": True,
    "verdict": "WARN",
    "access_mode": "read_existing",
    "access_state": "unknown",
    "access_reason": "READ_EXISTING_AUTHORITY_UNCERTIFIED",
    "source_snapshots": [],
}
_ACCESS_EVIDENCE_TOON = (
    "success: true\n"
    "verdict: WARN\n"
    "access_mode: read_existing\n"
    "access_state: unknown\n"
    "access_reason: READ_EXISTING_AUTHORITY_UNCERTIFIED\n"
    "source_snapshots: []\n"
    "output_format: toon\n"
    # RFC-0022 P0.5: wire owner echo in the TOON control surface.
    "action_version: nav.context/v1"
)


def test_context_forwards_explicit_read_existing_capability() -> None:
    facade = build_nav_facade(project_root=None)
    context_inner = facade._bespoke_inners[0]
    sentinel = {"forwarded": True}

    with patch.object(
        context_inner, "execute", new=AsyncMock(return_value=sentinel)
    ) as mock_execute:
        result = asyncio.run(facade.execute(_CONTEXT_READ_EXISTING_ARGS))

    mock_execute.assert_awaited_once_with(
        {
            key: value
            for key, value in _CONTEXT_READ_EXISTING_ARGS.items()
            if key != "action"
        }
    )
    assert result == sentinel


@pytest.mark.parametrize(
    ("output_format", "format_fields"),
    [
        pytest.param("json", {}, id="json"),
        pytest.param(
            "toon",
            {"format": "toon", "toon_content": _ACCESS_EVIDENCE_TOON},
            id="toon",
        ),
    ],
)
def test_context_read_existing_returns_exact_access_evidence_without_backend(
    tmp_path: Any, output_format: str, format_fields: dict[str, Any]
) -> None:
    import sys

    facade = build_nav_facade(project_root=str(tmp_path))
    context_inner = facade._bespoke_inners[0]

    with patch.object(
        context_inner,
        "_get_cache",
        side_effect=AssertionError("context backend must not run"),
    ) as get_cache:
        result = asyncio.run(
            facade.execute(
                {**_CONTEXT_READ_EXISTING_ARGS, "output_format": output_format}
            )
        )

    # On every axis the certified/live backends never touch the live ASTCache
    # (zero-write); the missing snapshot classifies before the reader runs.
    get_cache.assert_not_called()
    if sys.platform.startswith("linux"):
        # RFC-0022 P0.4: the certified backend runs and classifies the
        # never-published pair as an unknown acquisition failure.
        assert {
            key: result[key]
            for key in (
                "success",
                "access_mode",
                "access_state",
                "access_reason",
                "error_code",
                "source_snapshots",
                "action_version",
                "output_format",
            )
        } == {
            "success": False,
            "access_mode": "read_existing",
            "access_state": "unknown",
            "access_reason": "INDEX_SNAPSHOT_UNKNOWN",
            "error_code": "INDEX_SNAPSHOT_UNKNOWN",
            "source_snapshots": [],
            "action_version": "nav.context/v1",
            "output_format": output_format,
        }
        return
    assert result == {
        **format_fields,
        **_ACCESS_EVIDENCE,
        # RFC-0022 P0.5: wire-owner echo on the unavailable envelope.
        "action_version": "nav.context/v1",
        "output_format": output_format,
    }


def test_context_rejects_malformed_task_before_unavailable_classification(
    tmp_path: Any,
) -> None:
    facade = build_nav_facade(project_root=str(tmp_path))

    with patch(
        "tree_sitter_analyzer.read_existing_access.format_read_existing_unavailable",
        side_effect=AssertionError("classification must follow validation"),
    ) as classify_unavailable:
        with pytest.raises(ValueError, match=r"^task must have JSON type string$"):
            asyncio.run(
                facade.execute(
                    {
                        **_CONTEXT_READ_EXISTING_ARGS,
                        "task": 7,
                        "output_format": "json",
                    }
                )
            )

    classify_unavailable.assert_not_called()


def test_navigate_rejects_context_only_access_mode() -> None:
    facade = build_nav_facade(project_root=None)
    navigate_inner = facade.action_map["navigate"]
    poison = AsyncMock(side_effect=AssertionError("navigate inner must not run"))

    with patch.object(navigate_inner, "execute", new=poison):
        result = asyncio.run(
            facade.execute(
                {
                    "action": "navigate",
                    "symbol": "dispatch",
                    "access_mode": "read_existing",
                }
            )
        )

    poison.assert_not_awaited()
    assert (
        result["success"],
        result["verdict"],
        result["error_type"],
        result["error"],
    ) == (
        False,
        "ERROR",
        "validation",
        "parameter 'access_mode' applies only to action(s): context",
    )


# ---------------------------------------------------------------------------
# RFC-0022 P0.4: certified-axis index-snapshot consumers (portable gate open)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _close_index_snapshot_registry():
    yield
    from tree_sitter_analyzer.index_snapshot import REGISTRY

    REGISTRY.close_all()


def _indexed_project(tmp_path: Any) -> Any:
    """Index one small project and return its resolved root."""
    from pathlib import Path

    from tree_sitter_analyzer.ast_cache import ASTCache

    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text(
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        return self._find_user(user_id)\n"
        "\n"
        "    def _find_user(self, user_id):\n"
        "        return {'id': user_id}\n"
        "\n"
        "def handle_request(request):\n"
        "    svc = UserService()\n"
        "    return svc.get_user(1)\n",
        encoding="utf-8",
    )
    (project / "routes.py").write_text(
        "from app import handle_request\n"
        "\n"
        "def dispatch(request):\n"
        "    return handle_request(request)\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(project))
    cache.index_project(max_files=20)
    cache.close()
    return Path(str(project.resolve()))


def _publish_index_snapshot(project: Any, *, source_generation: str | None = None):
    """Publish one real index.db connection under the process-global registry.

    The published capability carries the REAL captured source generation and
    a full source scope so the consumer's after-read recapture passes: a
    hand-faked generation would raise SOURCE_GENERATION_MISMATCH on exit.
    """
    import sqlite3

    from tree_sitter_analyzer.index_snapshot import (
        REGISTRY,
        IndexSnapshot,
        _capture_sources_with_deadline,
    )
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    current = _capture_sources_with_deadline(str(project), scope, deadline=10**18)
    assert current.state == "exact", current.reason
    conn = sqlite3.connect(str(project / ".ast-cache" / "index.db"))
    conn.row_factory = sqlite3.Row
    snapshot = IndexSnapshot(
        None,
        current.fingerprint,
        "index-fp",
        source_generation or current.generation,
        "complete",
        None,
        str(project.resolve()),
        2,
        None,
        None,
        scope,
    )
    return REGISTRY.publish(snapshot, conn, 0)


def test_context_read_existing_fails_closed_without_project_root() -> None:
    """MISSING_PROJECT_ROOT on the certified axis; UNCERTIFIED elsewhere.

    Codex P1 (#1257) mirror for nav.context: an unbound root must never let
    the certified backend run (it would classify success with no project
    boundary). Non-certified axes keep the stable UNCERTIFIED success stub.
    """
    import sys

    facade = build_nav_facade(project_root=None)
    context_inner = facade._bespoke_inners[0]
    arguments = {
        key: value
        for key, value in _CONTEXT_READ_EXISTING_ARGS.items()
        if key != "action"
    }
    arguments["output_format"] = "json"

    if sys.platform.startswith("linux"):
        # The consumer seam classifies the unbound root (evidence + wire
        # owner), it does not escape as a bare raise.
        result = asyncio.run(context_inner.execute(arguments))
        assert result["success"] is False
        assert result["error_code"] == "MISSING_PROJECT_ROOT"
        assert result["access_reason"] == "MISSING_PROJECT_ROOT"
        assert result["access_state"] == "missing"
        assert result["action_version"] == "nav.context/v1"
        return
    result = asyncio.run(context_inner.execute(arguments))
    assert result["success"] is True
    assert result["access_reason"] == "READ_EXISTING_AUTHORITY_UNCERTIFIED"
    assert result["action_version"] == "nav.context/v1"


@pytest.mark.slow_ok  # real git + index_project + source capture: subprocess work
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
def test_context_read_existing_consumes_published_snapshot(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The certified backend serves graph content from the snapshot connection."""
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    published = _publish_index_snapshot(project)

    facade = build_nav_facade(project_root=str(project))
    result = asyncio.run(
        facade.execute(
            {
                "action": "context",
                "task": "explain dispatch",
                "access_mode": "read_existing",
                "snapshot_id": published.snapshot_id,
                "source_generation": published.source_generation,
                "output_format": "json",
            }
        )
    )

    assert result["success"] is True
    assert result["verdict"] == "INFO"
    assert result["access_mode"] == "read_existing"
    assert result["access_state"] == "available"
    assert result["access_reason"] is None
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
        }
    ]
    # The echo must come from the ACQUIRED snapshot, byte-matching the
    # source_snapshots record (RFC-0022 route-table common rule 5).
    assert result["snapshot_id"] == published.snapshot_id
    assert result["source_generation"] == published.source_generation
    assert result["snapshot_id"] == published.snapshot_id
    assert result["source_generation"] == published.source_generation
    assert result["action_version"] == "nav.context/v1"
    # C46: the certified adapter never echoes raw task text.
    assert "task" not in result
    assert [entry.get("name") for entry in result["entry_points"]] == ["dispatch"]
    assert result["related_symbols"]
    assert result["code_blocks"]


@pytest.mark.slow_ok  # real git + index_project + source capture: subprocess work
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
def test_context_read_existing_no_match_returns_not_found(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A task with no symbol hits yields a certified NOT_FOUND envelope.

    The empty-nodes path must still carry the full read_existing evidence
    (echo tokens + action_version), not a bare success stub.
    """
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    published = _publish_index_snapshot(project)

    facade = build_nav_facade(project_root=str(project))
    result = asyncio.run(
        facade.execute(
            {
                "action": "context",
                "task": "zzz_nonexistent_symbol_xyz",
                "access_mode": "read_existing",
                "snapshot_id": published.snapshot_id,
                "source_generation": published.source_generation,
                "output_format": "json",
            }
        )
    )

    assert result["success"] is True
    assert result["verdict"] == "NOT_FOUND"
    assert result["access_mode"] == "read_existing"
    assert result["access_state"] == "available"
    assert result["access_reason"] is None
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
        }
    ]
    assert result["snapshot_id"] == published.snapshot_id
    assert result["source_generation"] == published.source_generation
    assert result["action_version"] == "nav.context/v1"
    assert result["entry_points"] == []
    assert result["code_blocks"] == []
    assert result["stats"] == {
        "entry_points": 0,
        "entry_points_total": 0,
        "nodes_total": 0,
        "edges_total": 0,
        "code_blocks": 0,
    }


@pytest.mark.slow_ok  # real git + index_project + source capture: subprocess work
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
def test_context_read_existing_generation_mismatch_fails_closed(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong source_generation token classifies, never a successful read."""
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    published = _publish_index_snapshot(project)

    facade = build_nav_facade(project_root=str(project))
    result = asyncio.run(
        facade.execute(
            {
                "action": "context",
                "task": "explain dispatch",
                "access_mode": "read_existing",
                "snapshot_id": published.snapshot_id,
                "source_generation": "WRONG-GENERATION",
                "output_format": "json",
            }
        )
    )

    assert result["success"] is False
    assert result["access_state"] == "unknown"
    assert result["access_reason"] == "SOURCE_GENERATION_MISMATCH"
    assert result["error_code"] == "SOURCE_GENERATION_MISMATCH"
    assert result["source_snapshots"] == []
    assert result["action_version"] == "nav.context/v1"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_snapshot_search_surface_degrades_without_fts5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without FTS5 the snapshot search surface returns no raw hits."""
    import sqlite3

    import tree_sitter_analyzer.mcp.tools.codegraph_context_tool as cgt

    monkeypatch.setattr(cgt, "sqlite_compile_supports_fts5", lambda conn: False)
    conn = sqlite3.connect(":memory:")
    surface = cgt._snapshot_search_surface(conn)
    assert surface.fts_search("anything") == []
    assert surface.fts_search_ranked("anything") == []


def test_snapshot_search_surface_queries_real_fts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With FTS5 the snapshot search surface queries the connection."""
    import sqlite3

    import tree_sitter_analyzer.mcp.tools.codegraph_context_tool as cgt

    monkeypatch.setattr(cgt, "sqlite_compile_supports_fts5", lambda conn: True)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER PRIMARY KEY, name TEXT, "
        "kind TEXT, file_path TEXT, language TEXT, line INTEGER, end_line INTEGER)"
    )
    conn.execute("CREATE VIRTUAL TABLE ast_symbols_fts USING fts5(name, content='')")
    conn.execute(
        "INSERT INTO ast_symbol_rows VALUES "
        "(1, 'hello_world', 'function', 'a.py', 'python', 1, 3)"
    )
    conn.execute("INSERT INTO ast_symbols_fts (rowid, name) VALUES (1, 'hello_world')")
    surface = cgt._snapshot_search_surface(conn)
    hits = surface.fts_search("hello")
    assert hits == [
        {
            "name": "hello_world",
            "kind": "function",
            "file": "a.py",
            "language": "python",
            "line": 1,
            "end_line": 3,
        }
    ]
