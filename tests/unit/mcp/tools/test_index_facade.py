#!/usr/bin/env python3
"""Tests for the ``index`` facade (Wave B, P0 geode layer).

Covers the §5 required cases from the onboarding spec:
1.  builds & routes — factory returns FacadeTool, all 7 actions present.
2.  action routing — {action: X, ...} reaches the right inner.
3.  arg projection — ``action`` is NOT in args the inner received.
4.  sibling-param drop — a param for action A doesn't reach action B's inner.
5.  (R3 normalize skipped — no function_name inner in index facade.)
6.  (no bespoke routes — all via action_map.)
7.  envelope preserved — verdict / agent_summary come through verbatim.
8.  missing/unknown action — returns error envelope with available_actions.
9.  rebind — set_project_path propagates to all action_map inners.
10. no override — build_index_facade returns a FacadeTool (not a subclass
    that overrides set_project_path).
11. end-to-end no strict leak — route status through the REAL inner
    (tmp_path root) and assert no ValueError mentioning 'action'.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
from tree_sitter_analyzer.mcp.tools.index_facade import (
    _INDEX_DESCRIPTION,
    build_index_facade,
)

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
#   - action routing to each of the 7 index lifecycle actions
#     (status/build/full/auto/sync/cache/knowledge)
#   - sibling-param drop between actions
#   - index facade description includes required documentation strings
#   - end-to-end no strict leak (F4 regression guard with real inner tools)
#   - set_project_path rebind propagation (G3)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Expected action set (7 index lifecycle actions)
# ---------------------------------------------------------------------------

_ALL_ACTIONS = {
    "status",
    "build",
    "full",
    "auto",
    "sync",
    "cache",
    "knowledge",
}


# ---------------------------------------------------------------------------
# Case 1: builds & routes
# ---------------------------------------------------------------------------


def test_build_index_facade_returns_facade_tool() -> None:
    facade = build_index_facade(project_root=None)
    assert isinstance(facade, FacadeTool)
    assert facade.facade_name == "index"


def test_cache_action_description_lists_mutating_modes() -> None:
    """#992: action=cache also exposes mutating modes (index/sync/watch_*).

    The description must advertise the real ASTCacheTool capability surface,
    not just read-only query params, and must surface the ``mode`` param.
    """
    for mode_name in ("watch_start", "watch_stop", "sync", "invalidate", "index"):
        assert mode_name in _INDEX_DESCRIPTION, (
            f"index facade description omits cache mode {mode_name!r}"
        )
    assert "mode" in _INDEX_DESCRIPTION


def test_all_7_actions_registered() -> None:
    facade = build_index_facade(project_root=None)
    registered = set(facade.action_map) | set(facade.bespoke_map)
    assert registered == _ALL_ACTIONS, (
        f"Missing: {_ALL_ACTIONS - registered}  |  Extra: {registered - _ALL_ACTIONS}"
    )


def test_all_actions_in_action_map_not_bespoke() -> None:
    """All index facade actions are normal delegates (no bespoke routes)."""
    facade = build_index_facade(project_root=None)
    assert len(facade.bespoke_map) == 0
    assert len(facade.action_map) == 7


# ---------------------------------------------------------------------------
# Case 2: action routing — uses AsyncMock to avoid needing a real index
# ---------------------------------------------------------------------------


def _mock_result(action: str) -> dict[str, Any]:
    return {
        "success": True,
        "verdict": "INFO",
        "routed_to": action,
        "agent_summary": {
            "verdict": "INFO",
            "summary_line": f"fake {action} ok",
            "next_step": "n/a",
        },
    }


def _run_action(action: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    facade = build_index_facade(project_root=None)
    inner = facade.action_map[action]
    inner.execute = AsyncMock(return_value=_mock_result(action))  # type: ignore[method-assign]
    args = {"action": action, **(extra or {})}
    return asyncio.run(facade.execute(args))


@pytest.mark.parametrize("action", sorted(_ALL_ACTIONS))
def test_action_routes_to_correct_inner(action: str) -> None:
    result = _run_action(action)
    assert result["success"] is True
    assert result["routed_to"] == action


# ---------------------------------------------------------------------------
# Case 3: arg projection — ``action`` must NOT reach the inner
# ---------------------------------------------------------------------------


def test_arg_projection_strips_action_key() -> None:
    facade = build_index_facade(project_root=None)
    received: list[dict[str, Any]] = []

    async def _capture(args: dict[str, Any]) -> dict[str, Any]:
        received.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    inner = facade.action_map["status"]
    inner.execute = _capture  # type: ignore[method-assign]
    asyncio.run(facade.execute({"action": "status"}))
    assert received, "inner.execute was never called"
    assert "action" not in received[0], (
        "F4 regression: 'action' was forwarded to the inner strict-param guard"
    )


# ---------------------------------------------------------------------------
# Case 4: sibling-param drop — a param for action A must not reach action B
# ---------------------------------------------------------------------------


def test_sibling_param_dropped_between_actions() -> None:
    """A ``query`` param belonging to the ``cache`` action must not reach the
    ``status`` inner (which doesn't declare ``query`` in its schema)."""
    facade = build_index_facade(project_root=None)
    received: list[dict[str, Any]] = []

    async def _capture(args: dict[str, Any]) -> dict[str, Any]:
        received.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    inner = facade.action_map["status"]
    inner.execute = _capture  # type: ignore[method-assign]
    asyncio.run(facade.execute({"action": "status", "query": "leaked_param"}))
    assert received, "inner.execute was never called"
    assert "query" not in received[0], (
        "Sibling param 'query' (belongs to 'cache' action) leaked into 'status' inner"
    )


# ---------------------------------------------------------------------------
# Case 7: envelope preservation
# ---------------------------------------------------------------------------


def test_envelope_preserved_verbatim() -> None:
    sentinel = {
        "success": True,
        "verdict": "SAFE",
        "detail": "my detail",
        "agent_summary": {
            "verdict": "SAFE",
            "summary_line": "status ok",
            "next_step": "proceed",
        },
    }
    facade = build_index_facade(project_root=None)
    facade.action_map["status"].execute = AsyncMock(  # type: ignore[method-assign]
        return_value=sentinel
    )
    result = asyncio.run(facade.execute({"action": "status"}))
    assert result is sentinel or result == sentinel
    assert result["verdict"] == "SAFE"
    assert result["agent_summary"]["summary_line"] == "status ok"


# ---------------------------------------------------------------------------
# Case 8: missing / unknown action → error envelope
# ---------------------------------------------------------------------------


def test_missing_action_returns_error_envelope() -> None:
    facade = build_index_facade(project_root=None)
    result = asyncio.run(facade.execute({}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    result_str = str(result)
    assert "status" in result_str
    assert "build" in result_str


def test_unknown_action_returns_error_with_available_actions() -> None:
    facade = build_index_facade(project_root=None)
    result = asyncio.run(facade.execute({"action": "nonexistent_xyz"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    assert "available_actions" in result
    assert set(result["available_actions"]) == _ALL_ACTIONS


# ---------------------------------------------------------------------------
# Case 9: G3 rebind — set_project_path propagates to all action_map inners
# ---------------------------------------------------------------------------


def test_set_project_path_rebinds_all_inners(tmp_path: Any) -> None:
    facade = build_index_facade(project_root=None)
    target = str(tmp_path)
    facade.set_project_path(target)
    for action, inner in facade.action_map.items():
        assert inner.project_root == target, (
            f"G3 rebind failed: action={action!r} inner.project_root="
            f"{inner.project_root!r} != {target!r}"
        )


# ---------------------------------------------------------------------------
# Case 10: no override of set_project_path (FacadeTool must inherit it clean)
# ---------------------------------------------------------------------------


def test_no_set_project_path_override() -> None:
    """Factory must return a plain FacadeTool; FacadeTool itself must not
    override set_project_path (guarded by test_no_mcp_tool_overrides_set_project_path)."""
    facade = build_index_facade(project_root=None)
    assert type(facade) is FacadeTool
    assert "set_project_path" not in FacadeTool.__dict__


# ---------------------------------------------------------------------------
# Case 11: end-to-end — no strict-param leak ('action' never reaches inner)
# ---------------------------------------------------------------------------


def test_end_to_end_no_strict_param_leak_status(tmp_path: Any) -> None:
    """Route status through the REAL inner tool (fresh tmp_path, no index).

    The inner may return a NOT_FOUND / error envelope (no index built) — that
    is correct behaviour. The key assertion is that ``action`` is projected
    away BEFORE reaching the inner's strict-param guard, so no ValueError
    mentioning 'action' escapes.
    """
    facade = build_index_facade(project_root=str(tmp_path))
    try:
        result = asyncio.run(facade.execute({"action": "status"}))
    except ValueError as exc:
        assert "action" not in str(exc), (
            f"F4 regression: 'action' leaked to the inner strict-param guard "
            f"for action='status' — {exc}"
        )
        return
    assert isinstance(result, dict), (
        f"Expected dict result for action='status', got {type(result)}"
    )
    assert "success" in result, (
        f"Result missing 'success' key for action='status': {result}"
    )


# ---------------------------------------------------------------------------
# Annotations sanity check
# ---------------------------------------------------------------------------


def test_annotations_set_correctly() -> None:
    """Spec §6: index facade spans read-only (status/cache) and mutating
    (build/full/auto/sync) actions. Must NOT claim readOnlyHint=True."""
    facade = build_index_facade(project_root=None)
    definition = facade.get_tool_definition()
    annotations = definition.get("annotations", {})
    assert annotations.get("readOnlyHint") is False, (
        "index facade includes mutating actions (build/full/auto/sync); "
        "readOnlyHint must be False per spec §6"
    )
    assert annotations.get("destructiveHint") is False
    # All four hints must be declared (test_every_tool_declares_mcp_annotations)
    for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
        assert hint in annotations, f"Missing annotation hint: {hint!r}"


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_schema_includes_action_and_union_params() -> None:
    facade = build_index_facade(project_root=None)
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "action" in props
    assert "action" in schema.get("required", [])
    # action enum must contain all 7 actions
    action_enum = set(props["action"].get("enum", []))
    assert action_enum == _ALL_ACTIONS


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
