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
#   - FacadeTool base framework tests (routing, R3 normalize, F5 bespoke)
#   - symbol -> function_name normalize (R3) before projection
#   - symbol -> class_name normalize (Wave 1b) before projection
#   - bespoke route (F5) bypass of schema projection
#   - G3 rebind propagation to action_map + bespoke inners
#   - facade's own schema must not self-reject action/scope/mode
# --------------------------------------------------------------------------

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


class _FakeClassTool(BaseMCPTool):
    """Inner tool that reads ``class_name`` (mirrors codegraph_class_inspect /
    codegraph_class_hierarchy)."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self.last_args: dict[str, Any] | None = None

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"class_name": {"type": "string"}},
            "required": ["class_name"],
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {"name": "fake_class", "inputSchema": self.get_tool_schema()}

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
            "cls": _FakeClassTool(),
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
# Wave 1b (audit structure-01): symbol -> class_name normalize. Without it the
# facade dropped ``symbol`` before projection because the class inner declares
# ``class_name`` (not symbol/function_name), so class_tree/class_detail
# silently ignored the requested class.
# --------------------------------------------------------------------------


def test_symbol_normalized_to_class_name_before_projection() -> None:
    facade = _make_facade()
    inner = facade.action_map["cls"]
    asyncio.run(facade.execute({"action": "cls", "symbol": "MyClass"}))
    assert inner.last_args is not None
    assert inner.last_args.get("class_name") == "MyClass"


def test_explicit_class_name_wins_over_symbol() -> None:
    facade = _make_facade()
    inner = facade.action_map["cls"]
    asyncio.run(
        facade.execute(
            {"action": "cls", "symbol": "fromSymbol", "class_name": "explicit"}
        )
    )
    assert inner.last_args is not None
    assert inner.last_args.get("class_name") == "explicit"


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


def test_unknown_action_error_string_enumerates_valid_actions() -> None:
    """F4 DX: the bare ``error`` string itself (not just the envelope's
    ``available_actions`` list) must enumerate the sorted valid actions so an
    agent that only logs the message can still recover without a wasted turn."""
    facade = _make_facade()
    result = asyncio.run(facade.execute({"action": "nope", "query": "Foo"}))
    error = result["error"]
    # The unknown action that was supplied is echoed back...
    assert "nope" in error
    # ...and the sorted list of valid actions appears verbatim in the message.
    assert "func" in error
    assert "symbol" in error
    # Sorted order is part of the contract (stable, scannable).
    assert error.index("func") < error.index("symbol")


def test_unknown_action_close_to_valid_suggests_did_you_mean() -> None:
    """TURN-SAVER: a typo'd action close to a valid one self-heals in-band.

    When the unknown action is a near-miss of a registered action
    (e.g. ``symbl`` -> ``symbol``), the error message prepends a
    ``did you mean: <closest>`` hint so an agent can correct the typo
    without a wasted discovery turn. The full valid-action list is still
    enumerated for the case where the suggestion is wrong."""
    facade = _make_facade()
    result = asyncio.run(facade.execute({"action": "symbl", "query": "Foo"}))
    error = result["error"]
    assert "did you mean: symbol" in error
    # The full valid-action list is still present (suggestion is additive).
    assert "func" in error
    assert "symbol" in error
    # The structured envelope also surfaces the suggestion for programmatic use.
    assert result["suggestion"] == "symbol"


def test_far_off_unknown_action_has_no_spurious_suggestion() -> None:
    """A far-off action yields no ``did you mean`` hint (no false suggestion),
    but still enumerates the valid actions."""
    facade = _make_facade()
    result = asyncio.run(facade.execute({"action": "zzqqxx", "query": "Foo"}))
    error = result["error"]
    assert "did you mean" not in error
    # Valid actions are still listed so the agent can recover.
    assert "func" in error
    assert "symbol" in error
    assert result.get("suggestion") is None


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


def test_facade_schema_lists_action_and_core_params() -> None:
    """Wave D slim schema: ``action`` + curated core params, NOT a full union.

    The public schema declares ``action`` plus the cross-action core params
    (query/symbol/function_name/file_path/scope/mode/...) and relies on
    ``additionalProperties: True`` for everything else. It must NOT verbatim
    union every inner tool's parameters (that is what blew the token budget).
    """
    facade = _make_facade()
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "action" in props
    # Core shared params are declared explicitly.
    assert "query" in props  # core
    assert "function_name" in props  # core
    # control keys present so the facade does not self-reject them
    assert "scope" in props
    assert "mode" in props
    # action is required
    assert "action" in schema.get("required", [])
    # Slim schema: only action + the 9 core params, never a per-inner union.
    from tree_sitter_analyzer.mcp.tools.facade_tool import _CORE_FACADE_PARAMS

    assert set(props) == {"action"} | set(_CORE_FACADE_PARAMS)
    # Inner-specific param ``limit`` (declared by _FakeSymbolTool) IS a core
    # param so it appears — but an arbitrary inner-only param would not be
    # unioned in. additionalProperties carries those.
    assert schema.get("additionalProperties") is True


def test_facade_schema_does_not_union_inner_only_params() -> None:
    """A param declared ONLY by an inner tool (not a core param) must NOT be
    unioned into the public schema — it is accepted via additionalProperties
    and projected internally against the inner's real schema (F4)."""

    class _InnerWithBespokeParam(BaseMCPTool):
        def get_tool_schema(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"rg_flag_xyz": {"type": "boolean"}},
                "additionalProperties": False,
            }

        def get_tool_definition(self) -> dict[str, Any]:
            return {"name": "inner_x", "inputSchema": self.get_tool_schema()}

        def validate_arguments(self, arguments: dict[str, Any]) -> bool:
            return True

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "verdict": "INFO"}

    facade = FacadeTool(facade_name="t", action_map={"x": _InnerWithBespokeParam()})
    props = facade.get_tool_schema()["properties"]
    assert "rg_flag_xyz" not in props  # not unioned into public schema
    # ...but projection still recognises it from the inner's real schema.
    inner = facade.action_map["x"]
    projected = facade._project_args(inner, {"action": "x", "rg_flag_xyz": True})
    assert projected == {"rg_flag_xyz": True}


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


def test_search_facade_batch_description_documents_query_item_shape() -> None:
    """#569: schema-reading agents must see batch query items use pattern."""
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    definition = build_search_facade(project_root=None).get_tool_definition()
    description = definition["description"]
    assert "action=batch" in description
    assert "queries (required array of 2-10 items" in description
    assert "each item requires `pattern`" in description
    assert "output_format" in description


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


def test_search_facade_schema_declares_kind_with_enum() -> None:
    """#640: ``kind`` worked at runtime (additionalProperties) but was absent
    from the search facade's public inputSchema — schema-reading agents could
    not discover kind=constant filtering. The facade must declare ``kind``
    with the authoritative enum, sourced from the symbol-search inner tool so
    facade/inner/CLI can never drift apart."""
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade
    from tree_sitter_analyzer.mcp.tools.symbol_search_tool import SYMBOL_SEARCH_KINDS

    # The authoritative enum: exactly the kinds _extract_symbols emits into
    # ast_symbol_rows (function/method/class/enum/variable/import/constant) plus
    # the "any" no-filter default. Exact pin — extraction changes must re-pin.
    assert SYMBOL_SEARCH_KINDS == (
        "function",
        "method",
        "class",
        "enum",
        "variable",
        "import",
        "constant",
        "any",
    )

    facade = build_search_facade(project_root=None)
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "kind" in props
    assert props["kind"]["enum"] == list(SYMBOL_SEARCH_KINDS)
    assert props["kind"]["type"] == "string"
    # LOCKED facade convention (#397 family): required is exactly ["action"]
    # — runtime-resolved params are NEVER added to required.
    assert schema["required"] == ["action"]
    # The inner symbol tool's own enum must carry the same authoritative set.
    inner = facade.action_map["symbol"]
    inner_kind = inner.get_tool_schema()["properties"]["kind"]
    assert inner_kind["enum"] == list(SYMBOL_SEARCH_KINDS)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
