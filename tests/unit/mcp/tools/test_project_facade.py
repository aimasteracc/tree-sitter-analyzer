#!/usr/bin/env python3
"""Tests for the ``project`` facade (Wave B, P0 geode layer).

Covers the §5 required cases from the onboarding spec:
1.  builds & routes — factory returns FacadeTool, all 10 actions present.
2.  action routing — {action: X, ...} reaches the right inner.
3.  arg projection — ``action`` is NOT in args the inner received.
4.  sibling-param drop — a param for action A doesn't reach action B's inner.
5.  (R3 normalize skipped — no function_name inner in project facade.)
6.  (no bespoke routes — all via action_map.)
7.  envelope preserved — verdict / agent_summary come through verbatim.
8.  missing/unknown action — returns error envelope with available_actions.
9.  rebind — set_project_path propagates to all action_map inners.
10. no override — build_project_facade returns a FacadeTool (not a subclass
    that overrides set_project_path).
11. end-to-end no strict leak — route overview + smart through REAL inners
    (tmp_path root) and assert no ValueError mentioning 'action'.
    (index_status has moved to the ``index`` facade; see test_index_facade.py.)
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
from tree_sitter_analyzer.mcp.tools.project_facade import build_project_facade

# ---------------------------------------------------------------------------
# Expected action set (10 actions — index lifecycle extracted to index facade)
# ---------------------------------------------------------------------------

_ALL_ACTIONS = {
    "overview",
    "files",
    "smart",
    "parser",
    "tools",
    "metrics",
    "skills",
    "workflow",
    "journal",
    "doc_sync",
}


# ---------------------------------------------------------------------------
# Case 1: builds & routes
# ---------------------------------------------------------------------------


def test_build_project_facade_returns_facade_tool() -> None:
    facade = build_project_facade(project_root=None)
    assert isinstance(facade, FacadeTool)
    assert facade.facade_name == "project"


def test_all_10_actions_registered() -> None:
    facade = build_project_facade(project_root=None)
    registered = set(facade.action_map) | set(facade.bespoke_map)
    assert registered == _ALL_ACTIONS, (
        f"Missing: {_ALL_ACTIONS - registered}  |  Extra: {registered - _ALL_ACTIONS}"
    )


def test_all_actions_in_action_map_not_bespoke() -> None:
    """All project facade actions are normal delegates (no bespoke routes)."""
    facade = build_project_facade(project_root=None)
    assert len(facade.bespoke_map) == 0
    assert len(facade.action_map) == 10


def test_index_actions_not_in_project_facade() -> None:
    """Index lifecycle actions must have been extracted to the index facade."""
    facade = build_project_facade(project_root=None)
    all_actions = set(facade.action_map) | set(facade.bespoke_map)
    index_actions = {
        "index_status",
        "index_build",
        "index_full",
        "index_auto",
        "index_sync",
        "cache",
    }
    leaked = all_actions & index_actions
    assert not leaked, (
        f"Index lifecycle actions must live in the index facade, not project: {leaked}"
    )


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
    facade = build_project_facade(project_root=None)
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
    facade = build_project_facade(project_root=None)
    received: list[dict[str, Any]] = []

    async def _capture(args: dict[str, Any]) -> dict[str, Any]:
        received.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    inner = facade.action_map["overview"]
    inner.execute = _capture  # type: ignore[method-assign]
    asyncio.run(facade.execute({"action": "overview", "format": "json"}))
    assert received, "inner.execute was never called"
    assert "action" not in received[0], (
        "F4 regression: 'action' was forwarded to the inner strict-param guard"
    )


# ---------------------------------------------------------------------------
# Case 4: sibling-param drop — a param for action A must not reach action B
# ---------------------------------------------------------------------------


def test_sibling_param_dropped_between_actions() -> None:
    """A ``query`` param belonging to the ``cache`` action must not reach the
    ``overview`` inner (which doesn't declare ``query`` in its schema)."""
    facade = build_project_facade(project_root=None)
    received: list[dict[str, Any]] = []

    async def _capture(args: dict[str, Any]) -> dict[str, Any]:
        received.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    inner = facade.action_map["overview"]
    inner.execute = _capture  # type: ignore[method-assign]
    asyncio.run(facade.execute({"action": "overview", "query": "leaked_param"}))
    assert received, "inner.execute was never called"
    assert "query" not in received[0], (
        "Sibling param 'query' (belongs to 'cache' action) leaked into 'overview' inner"
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
            "summary_line": "overview ok",
            "next_step": "proceed",
        },
    }
    facade = build_project_facade(project_root=None)
    facade.action_map["overview"].execute = AsyncMock(  # type: ignore[method-assign]
        return_value=sentinel
    )
    result = asyncio.run(facade.execute({"action": "overview"}))
    assert result is sentinel or result == sentinel
    assert result["verdict"] == "SAFE"
    assert result["agent_summary"]["summary_line"] == "overview ok"


# ---------------------------------------------------------------------------
# Case 8: missing / unknown action → error envelope
# ---------------------------------------------------------------------------


def test_missing_action_returns_error_envelope() -> None:
    facade = build_project_facade(project_root=None)
    result = asyncio.run(facade.execute({"format": "json"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    result_str = str(result)
    assert "overview" in result_str
    assert "smart" in result_str


def test_unknown_action_returns_error_with_available_actions() -> None:
    facade = build_project_facade(project_root=None)
    result = asyncio.run(facade.execute({"action": "nonexistent_xyz"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    assert "available_actions" in result
    assert set(result["available_actions"]) == _ALL_ACTIONS
    # Index actions must not appear — they moved to the index facade.
    index_actions = {
        "index_status",
        "index_build",
        "index_full",
        "index_auto",
        "index_sync",
        "cache",
    }
    assert not (set(result["available_actions"]) & index_actions)


# ---------------------------------------------------------------------------
# Case 9: G3 rebind — set_project_path propagates to all action_map inners
# ---------------------------------------------------------------------------


def test_set_project_path_rebinds_all_inners(tmp_path: Any) -> None:
    facade = build_project_facade(project_root=None)
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
    facade = build_project_facade(project_root=None)
    assert type(facade) is FacadeTool
    assert "set_project_path" not in FacadeTool.__dict__


# ---------------------------------------------------------------------------
# Case 11: end-to-end — no strict-param leak ('action' never reaches inner)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action,extra_args",
    [
        ("overview", {}),
        # smart requires file_path; supply a dummy path so the inner validates
        # the projected args (not the action key) — the inner will raise its
        # own "file not found" error, never an 'action' strict-param error.
        ("smart", {"file_path": "/nonexistent_dummy_path_xyz"}),
    ],
    ids=["overview", "smart"],
)
def test_end_to_end_no_strict_param_leak(
    tmp_path: Any, action: str, extra_args: dict[str, Any]
) -> None:
    """Route action through the REAL inner tool (fresh tmp_path, no index).

    The inner may return a NOT_FOUND / error envelope (no index built) or raise
    its own validation error (e.g. file not found) — that is correct behaviour.
    The key assertion is that ``action`` is projected away BEFORE reaching the
    inner's strict-param guard, so no ValueError mentioning 'action' escapes.
    """
    facade = build_project_facade(project_root=str(tmp_path))
    try:
        result = asyncio.run(facade.execute({"action": action, **extra_args}))
    except ValueError as exc:
        # Only fail if the error mentions 'action' — that is the F4 regression.
        # Other ValueError (e.g. file_path validation) are expected and fine.
        assert "action" not in str(exc) or "file_path" in str(exc), (
            f"F4 regression: 'action' leaked to the inner strict-param guard for "
            f"action={action!r} — {exc}"
        )
        return  # inner raised its own validation error — not an F4 regression
    assert isinstance(result, dict), (
        f"Expected dict result for action={action!r}, got {type(result)}"
    )
    assert "success" in result, (
        f"Result missing 'success' key for action={action!r}: {result}"
    )


# ---------------------------------------------------------------------------
# Annotations sanity check
# ---------------------------------------------------------------------------


def test_annotations_set_correctly() -> None:
    """Spec §6: project spans read + mutating (journal/doc_sync) actions.
    Must NOT claim readOnlyHint=True."""
    facade = build_project_facade(project_root=None)
    definition = facade.get_tool_definition()
    annotations = definition.get("annotations", {})
    assert annotations.get("readOnlyHint") is False, (
        "project facade includes mutating actions (journal/doc_sync); "
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
    facade = build_project_facade(project_root=None)
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "action" in props
    assert "action" in schema.get("required", [])
    # action enum must contain all 10 actions (index lifecycle is in index facade)
    action_enum = set(props["action"].get("enum", []))
    assert action_enum == _ALL_ACTIONS


# ---------------------------------------------------------------------------
# Issue #540 — Leg 1: journal facade-doc drift
# The description must use the REAL inner param names: mode, title, rationale,
# query, verdict_filter — NOT the stale placeholders 'operation' or 'entry'.
# ---------------------------------------------------------------------------


def test_journal_description_uses_real_param_names() -> None:
    """project facade journal description must reference real inner params."""
    facade = build_project_facade(project_root=None)
    defn = facade.get_tool_definition()
    description = defn["description"]
    assert "action=journal" in description, (
        "action=journal entry missing from description"
    )

    # Extract the journal line to scope assertions to that section only
    journal_line = next(
        (line for line in description.splitlines() if "action=journal" in line), ""
    )

    # Real params that DecisionJournalTool actually accepts
    assert "mode" in journal_line, (
        f"journal description must mention 'mode' (the real inner param). "
        f"Got journal line: {journal_line!r}"
    )
    assert "rationale" in journal_line, (
        f"journal description must mention 'rationale' (real inner param). "
        f"Got journal line: {journal_line!r}"
    )
    # Stale placeholders that the inner does NOT accept
    assert "operation" not in journal_line, (
        f"journal description must NOT mention 'operation' — the inner rejects it "
        f"(real param is 'mode'). Got journal line: {journal_line!r}"
    )
    assert "entry" not in journal_line, (
        f"journal description must NOT mention 'entry' — the inner rejects it "
        f"(real params are title+rationale+verdict for record mode). "
        f"Got journal line: {journal_line!r}"
    )


def test_smart_action_documented_params_subset_of_inner_schema() -> None:
    """#573: the facade's documented params for ``action=smart`` must all exist
    in SmartContextTool's schema. It previously documented ``task``/``limit``
    (neither in the inner, which requires ``file_path``), so every doc-following
    call hard-failed with ``file_path is required`` — the worst of the
    facade-doc-drift family because the documented invocation CANNOT work."""
    import re

    facade = build_project_facade(project_root=None)
    desc = facade.get_tool_definition()["description"]
    block = re.search(r"action=smart\b(.*?)(?=- action=|\Z)", desc, re.S)
    assert block, "action=smart not found in the project facade description"
    params = re.search(r"Params:\s*([^.\n]+)", block.group(1))
    assert params, "action=smart documents no Params"
    documented = {p.strip() for p in params.group(1).split(",") if p.strip()}

    inner = facade.action_map["smart"]
    props = set(inner.get_tool_definition()["inputSchema"]["properties"].keys())
    # output_format is the universal envelope param (#651), accepted everywhere.
    drift = documented - props - {"output_format"}
    assert not drift, (
        f"project action=smart documents params absent from SmartContextTool's "
        f"schema: {sorted(drift)} (inner props: {sorted(props)}). Doc/inner "
        f"drift — a doc-following call would fail (#573)."
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
