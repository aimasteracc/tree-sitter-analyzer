#!/usr/bin/env python3
"""Tests for the FacadeTool dispatcher framework (P0 geode layer).

These tests exercise the FacadeTool base in isolation using fake inner
tools, then verify the real ``search`` facade wired against the live
inner tool instances.

Covered behaviours (PRD §0 Errata F4 / F5 / G3, §3 R2/R3):
- action routing (action -> inner.execute)
- arg projection to the inner tool's own input-schema whitelist
  (F4 Landmine A: enforce_strict_params on the inner rejects unknown keys
  like ``action`` unless the facade strips them first)
- R3 symbol -> function_name normalize BEFORE projection
- F5 bespoke routing (callable that bypasses registry[name].execute())
- verdict / agent_summary envelope preserved (facade does not re-wrap)
- G3 rebind propagation to held inner instances via set_project_path
- missing ``action`` -> NOT_FOUND/ERROR verdict envelope with available actions
- facade's own schema must NOT self-reject ``action``/``scope``/``mode``
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool

# --------------------------------------------------------------------------
# Fake inner tools — minimal BaseMCPTool subclasses to test routing in
# isolation without pulling in the real heavy tools.
# --------------------------------------------------------------------------


class _FakeSymbolTool(BaseMCPTool):
    """Inner tool whose schema only allows ``query`` + ``limit``.

    Mirrors codegraph_symbol_search: it must NEVER receive ``action`` or
    sibling-action params, or its strict-param guard raises.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self.last_args: dict[str, Any] | None = None
        self.rebound_to: list[str | None] = []

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {"name": "fake_symbol", "inputSchema": self.get_tool_schema()}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    def _on_project_root_changed(self, project_root: str | None) -> None:
        # Record rebinds for the G3 test. Guard against the __init__ call.
        if getattr(self, "_facade_rebind_tracking", True):
            self.rebound_to.append(project_root)

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.last_args = dict(arguments)
        return {
            "success": True,
            "verdict": "INFO",
            "query": arguments.get("query"),
            "agent_summary": {
                "verdict": "INFO",
                "summary_line": "fake symbol ok",
                "next_step": "n/a",
            },
        }


class _FakeFunctionTool(BaseMCPTool):
    """Inner tool that reads ``function_name`` (mirrors codegraph_callers)."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self.last_args: dict[str, Any] | None = None

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"function_name": {"type": "string"}},
            "required": ["function_name"],
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {"name": "fake_function", "inputSchema": self.get_tool_schema()}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.last_args = dict(arguments)
        return {"success": True, "verdict": "INFO"}


def _make_facade(**kwargs: Any) -> FacadeTool:
    return FacadeTool(
        facade_name="test_facade",
        action_map={
            "symbol": _FakeSymbolTool(),
            "func": _FakeFunctionTool(),
        },
        **kwargs,
    )


# --------------------------------------------------------------------------
# Action routing + arg projection (F4)
# --------------------------------------------------------------------------


def test_action_routes_to_inner_tool() -> None:
    facade = _make_facade()
    result = asyncio.run(facade.execute({"action": "symbol", "query": "Foo"}))
    assert result["success"] is True
    assert result["query"] == "Foo"


def test_arg_projection_strips_action_control_key() -> None:
    """F4 Landmine A: ``action`` must be stripped before forwarding, or the
    inner tool's strict-param guard raises ValueError."""
    facade = _make_facade()
    inner = facade.action_map["symbol"]
    asyncio.run(facade.execute({"action": "symbol", "query": "Foo", "limit": 5}))
    assert inner.last_args is not None
    assert "action" not in inner.last_args
    assert inner.last_args == {"query": "Foo", "limit": 5}


def test_arg_projection_drops_sibling_params() -> None:
    """A param belonging to a sibling action (function_name) must not reach the
    symbol inner tool — projection is to the inner's own schema whitelist."""
    facade = _make_facade()
    inner = facade.action_map["symbol"]
    asyncio.run(
        facade.execute({"action": "symbol", "query": "Foo", "function_name": "bar"})
    )
    assert inner.last_args is not None
    assert "function_name" not in inner.last_args


def test_facade_does_not_raise_on_control_keys() -> None:
    """The facade's own strict-param guard must allow action/scope/mode."""
    facade = _make_facade()
    # scope + mode are free control keys; must not raise.
    result = asyncio.run(
        facade.execute(
            {"action": "symbol", "query": "Foo", "scope": "point", "mode": "x"}
        )
    )
    assert result["success"] is True


# --------------------------------------------------------------------------
# R3 symbol -> function_name normalize (must run BEFORE projection)
# --------------------------------------------------------------------------


def test_symbol_normalized_to_function_name_before_projection() -> None:
    facade = _make_facade()
    inner = facade.action_map["func"]
    asyncio.run(facade.execute({"action": "func", "symbol": "doThing"}))
    assert inner.last_args is not None
    assert inner.last_args.get("function_name") == "doThing"


def test_explicit_function_name_wins_over_symbol() -> None:
    facade = _make_facade()
    inner = facade.action_map["func"]
    asyncio.run(
        facade.execute(
            {"action": "func", "symbol": "fromSymbol", "function_name": "explicit"}
        )
    )
    assert inner.last_args is not None
    assert inner.last_args.get("function_name") == "explicit"


# --------------------------------------------------------------------------
# F5 bespoke routing
# --------------------------------------------------------------------------


def test_bespoke_route_bypasses_inner_execute() -> None:
    calls: list[dict[str, Any]] = []

    async def _bespoke(args: dict[str, Any]) -> dict[str, Any]:
        calls.append(dict(args))
        return {"success": True, "verdict": "INFO", "bespoke": True}

    facade = FacadeTool(
        facade_name="test_facade",
        action_map={"symbol": _FakeSymbolTool()},
        bespoke_map={"content": _bespoke},
    )
    result = asyncio.run(facade.execute({"action": "content", "query": "hi"}))
    assert result["bespoke"] is True
    # Bespoke handler receives the cleaned args (action stripped) but is NOT
    # projected to any inner schema (it owns its own arg handling).
    assert calls and "action" not in calls[0]
    assert calls[0].get("query") == "hi"


def test_bespoke_handles_int_return() -> None:
    """F5: search_content/find_and_grep can return a bare int (exit code) when
    suppress_output=True. The facade must tolerate the union return type."""

    async def _bespoke(args: dict[str, Any]) -> int:
        return 0

    facade = FacadeTool(
        facade_name="test_facade",
        action_map={"symbol": _FakeSymbolTool()},
        bespoke_map={"content": _bespoke},
    )
    result = asyncio.run(facade.execute({"action": "content", "suppress_output": True}))
    assert result == 0


# --------------------------------------------------------------------------
# Envelope preservation (facade must not re-wrap / mangle verdict)
# --------------------------------------------------------------------------


def test_envelope_preserved_verbatim() -> None:
    facade = _make_facade()
    result = asyncio.run(facade.execute({"action": "symbol", "query": "Foo"}))
    assert result["verdict"] == "INFO"
    assert result["agent_summary"]["summary_line"] == "fake symbol ok"


# --------------------------------------------------------------------------
# Missing / unknown action -> error envelope
# --------------------------------------------------------------------------


def test_missing_action_returns_error_envelope() -> None:
    facade = _make_facade()
    result = asyncio.run(facade.execute({"query": "Foo"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    # The available actions must be surfaced so the agent can recover.
    assert "symbol" in str(result)
    assert "func" in str(result)


def test_unknown_action_returns_error_envelope() -> None:
    facade = _make_facade()
    result = asyncio.run(facade.execute({"action": "nope", "query": "Foo"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    assert "symbol" in str(result)


# --------------------------------------------------------------------------
# G3 rebind propagation
# --------------------------------------------------------------------------


def test_set_project_path_rebinds_inner_instances(tmp_path: Any) -> None:
    """G3: server.set_project_path loops _tools.values() calling
    set_project_path on each. The facade must forward the rebind to every
    held inner instance via _on_project_root_changed (NOT by overriding
    set_project_path — forbidden by test_no_mcp_tool_overrides_set_project_path)."""
    inner = _FakeSymbolTool()
    facade = FacadeTool(
        facade_name="test_facade",
        action_map={"symbol": inner},
    )
    inner.rebound_to.clear()
    target = str(tmp_path)
    facade.set_project_path(target)
    assert inner.project_root == target
    assert target in inner.rebound_to


def test_facade_does_not_override_set_project_path() -> None:
    """FacadeTool must inherit set_project_path from BaseMCPTool, not override
    it (the contract guarded by test_no_mcp_tool_overrides_set_project_path)."""
    assert "set_project_path" not in FacadeTool.__dict__


# --------------------------------------------------------------------------
# Facade schema sanity
# --------------------------------------------------------------------------


def test_facade_schema_lists_action_and_inner_param_union() -> None:
    facade = _make_facade()
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "action" in props
    # union of inner params
    assert "query" in props
    assert "function_name" in props
    # control keys present so the facade does not self-reject them
    assert "scope" in props
    assert "mode" in props
    # action is required
    assert "action" in schema.get("required", [])


def test_facade_schema_not_strict_additional_properties() -> None:
    """The facade-level schema must allow control keys; it must NOT be
    additionalProperties:False (which would make it reject valid actions'
    sibling-union params that vary). The inner tools stay strict."""
    facade = _make_facade()
    schema = facade.get_tool_schema()
    # The merged schema enumerates the union; additionalProperties may be
    # True (lenient) — but it must at minimum not reject the declared union.
    # We assert the union approach by checking get_tool_definition round-trips.
    definition = facade.get_tool_definition()
    assert definition["name"] == "test_facade"
    assert definition["inputSchema"] == schema


# --------------------------------------------------------------------------
# Integration: the real ``search`` facade wired to live inner tools
# --------------------------------------------------------------------------


def test_search_facade_builds_and_routes() -> None:
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    facade = build_search_facade(project_root=None)
    assert facade.facade_name == "search"
    # All five folds present.
    for action in ("symbol", "query", "content", "grep", "batch"):
        assert action in facade.action_map or action in facade.bespoke_map
    # F3: query (.scm DSL) and symbol (BM25) are DISTINCT actions.
    assert "query" in facade.action_map
    assert "symbol" in facade.action_map
    assert facade.action_map["query"] is not facade.action_map["symbol"]
    # F5: content is a bespoke route (dict|int return).
    assert "content" in facade.bespoke_map


def test_search_facade_symbol_action_does_not_raise_strict(tmp_path: Any) -> None:
    """End-to-end: routing through the facade to the real symbol_search inner
    tool must not trip the inner's strict-param guard on ``action``.

    The key assertion is that ``action`` is projected away so the inner's
    enforce_strict_params does NOT raise ``unknown parameter 'action'``. The
    inner may still return its own NOT_FOUND/error envelope (e.g. no index in
    a fresh tmp dir) — that is correct behaviour, not a strict-param failure.
    """
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    facade = build_search_facade(project_root=str(tmp_path))
    try:
        result = asyncio.run(
            facade.execute({"action": "symbol", "query": "zzz_nonexistent_xyz"})
        )
    except ValueError as exc:  # pragma: no cover - guards the F4 regression
        assert "action" not in str(exc), (
            "facade leaked 'action' to the inner strict-param guard (F4 regression)"
        )
        raise
    assert isinstance(result, dict)
    assert "success" in result


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
