#!/usr/bin/env python3
"""Tests for the ``health`` facade (Wave B, P0 geode layer).

Covered behaviours (mirrors test_facade_tool.py §5 contract):
1.  builds & routes — factory returns FacadeTool; all 11 actions present
    (uml/graph/similarity moved to ``viz`` facade).
2.  action routing — {"action": X, ...} reaches the right inner.
3.  arg projection — ``action`` is NOT in the args the inner received.
4.  sibling-param drop — param for action A doesn't reach action B's inner.
5.  R3 normalize — ``symbol`` -> ``function_name`` for inners that declare it
    (heatmap inner uses ``function_name``).
6.  deps mode sub-routing (R5) — ``mode`` is kept by the projection filter
    because DependencyAnalysisTool declares ``mode`` in its schema.
7.  envelope preserved — ``verdict`` / ``agent_summary`` come through verbatim.
8.  missing / unknown action — error envelope with available_actions listed.
9.  rebind — set_project_path propagates to every action_map inner.
10. no override — factory returns a FacadeTool (set_project_path not overridden).
11. end-to-end no strict leak — route one action through the REAL inner with a
    tmp_path project root; no ValueError mentioning ``action`` escapes (F4 guard).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
from tree_sitter_analyzer.mcp.tools.health_facade import build_health_facade

# ---------------------------------------------------------------------------
# Expected actions
# ---------------------------------------------------------------------------

_ALL_ACTIONS = frozenset(
    {
        "project",
        "file",
        "scale",
        "patterns",
        "heatmap",
        "imports",
        "matrix",
        "dead",
        "routes",
        "overview",
        "deps",
    }
)

# Actions that moved to the ``viz`` facade — must NOT appear in health.
_VIZ_ACTIONS = frozenset({"uml", "graph", "similarity"})

# ---------------------------------------------------------------------------
# Minimal fake inner for isolation tests
# ---------------------------------------------------------------------------


class _FakeInner(BaseMCPTool):
    """Lightweight BaseMCPTool that records the args it receives."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self.last_args: dict[str, Any] | None = None
        self.rebound_to: list[str | None] = []

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "mode": {"type": "string"},
            },
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {"name": "fake_inner", "inputSchema": self.get_tool_schema()}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    def _on_project_root_changed(self, project_root: str | None) -> None:
        # Skip the __init__ call; only record explicit rebinds.
        if hasattr(self, "_tracking"):
            self.rebound_to.append(project_root)

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.last_args = dict(arguments)
        return {
            "success": True,
            "verdict": "INFO",
            "agent_summary": {
                "verdict": "INFO",
                "summary_line": "fake ok",
                "next_step": "n/a",
            },
        }


class _FakeFunctionNameInner(BaseMCPTool):
    """Inner that declares ``function_name`` — used to test R3 normalize."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self.last_args: dict[str, Any] | None = None

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"function_name": {"type": "string"}},
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {"name": "fake_fn", "inputSchema": self.get_tool_schema()}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.last_args = dict(arguments)
        return {"success": True, "verdict": "INFO"}


# ---------------------------------------------------------------------------
# 1. builds & routes
# ---------------------------------------------------------------------------


def test_health_facade_builds_and_has_all_actions() -> None:
    facade = build_health_facade(project_root=None)
    assert isinstance(facade, FacadeTool)
    assert facade.facade_name == "health"
    present = set(facade.action_map) | set(facade.bespoke_map)
    assert present == _ALL_ACTIONS, (
        f"Missing: {_ALL_ACTIONS - present}, Extra: {present - _ALL_ACTIONS}"
    )


def test_health_facade_total_action_count() -> None:
    """11 actions total — uml/graph/similarity moved to the ``viz`` facade."""
    facade = build_health_facade(project_root=None)
    total = len(facade.action_map) + len(facade.bespoke_map)
    assert total == 11


def test_health_facade_does_not_contain_viz_actions() -> None:
    """uml/graph/similarity must not appear in health — they live in viz."""
    facade = build_health_facade(project_root=None)
    present = set(facade.action_map) | set(facade.bespoke_map)
    leaked = _VIZ_ACTIONS & present
    assert not leaked, f"viz actions leaked into health facade: {leaked}"


def test_health_facade_annotations_read_only() -> None:
    """All health actions are read-only — annotation honesty per spec §6."""
    facade = build_health_facade(project_root=None)
    ann = facade._annotations
    assert ann is not None
    assert ann["readOnlyHint"] is True
    assert ann["destructiveHint"] is False
    assert ann["idempotentHint"] is True
    assert ann["openWorldHint"] is False


# ---------------------------------------------------------------------------
# 2 & 3. action routing + arg projection (F4)
# ---------------------------------------------------------------------------


def test_project_action_routes_and_strips_action_key() -> None:
    """action=project should not forward ``action`` to the inner."""
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["project"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(facade.execute({"action": "project", "min_grade": "B"}))
        mock_exec.assert_called_once()
        called_args = mock_exec.call_args[0][0]
        assert "action" not in called_args
        assert called_args.get("min_grade") == "B"


def test_file_action_routes_and_strips_action_key() -> None:
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["file"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute(
                {"action": "file", "file_path": "src/foo.py", "language": "python"}
            )
        )
        called_args = mock_exec.call_args[0][0]
        assert "action" not in called_args
        assert called_args.get("file_path") == "src/foo.py"


def test_deps_action_routes_and_preserves_mode() -> None:
    """R5: deps maps to DependencyAnalysisTool; ``mode`` must reach the inner
    because the inner declares ``mode`` in its schema (projection keeps it)."""
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["deps"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute(
                {"action": "deps", "mode": "cycles", "file_path": "src/a.py"}
            )
        )
        called_args = mock_exec.call_args[0][0]
        assert "action" not in called_args
        assert called_args.get("mode") == "cycles"


def test_deps_mode_summary() -> None:
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["deps"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(facade.execute({"action": "deps", "mode": "summary"}))
        called_args = mock_exec.call_args[0][0]
        assert called_args.get("mode") == "summary"


def test_deps_mode_blast() -> None:
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["deps"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute({"action": "deps", "mode": "blast", "file_path": "src/a.py"})
        )
        called_args = mock_exec.call_args[0][0]
        assert called_args.get("mode") == "blast"


def test_deps_mode_file_deps() -> None:
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["deps"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute(
                {"action": "deps", "mode": "file_deps", "file_path": "src/a.py"}
            )
        )
        called_args = mock_exec.call_args[0][0]
        assert called_args.get("mode") == "file_deps"


# ---------------------------------------------------------------------------
# 4. sibling-param drop
# ---------------------------------------------------------------------------


def test_sibling_param_does_not_reach_project_inner() -> None:
    """A param for action=file (file_path) must not leak to project inner."""
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["project"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute(
                {"action": "project", "file_path": "src/foo.py", "min_grade": "A"}
            )
        )
        called_args = mock_exec.call_args[0][0]
        # file_path is NOT in ProjectHealthTool's schema => must be dropped
        assert "file_path" not in called_args
        assert called_args.get("min_grade") == "A"


def test_sibling_param_does_not_reach_scale_inner() -> None:
    """Param for action=dead (include_test_files) must not leak to scale inner."""
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["scale"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute(
                {
                    "action": "scale",
                    "file_path": "src/x.py",
                    "include_test_files": True,
                }
            )
        )
        called_args = mock_exec.call_args[0][0]
        assert "include_test_files" not in called_args


# ---------------------------------------------------------------------------
# 5. R3 normalize: symbol -> function_name (heatmap inner declares function_name)
# ---------------------------------------------------------------------------


def test_r3_normalize_symbol_to_function_name_for_heatmap() -> None:
    """heatmap inner (CodeGraphComplexityHeatmapTool) declares ``function_name``.
    Passing ``symbol`` should be copied to ``function_name`` before projection."""
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["heatmap"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(facade.execute({"action": "heatmap", "symbol": "my_func"}))
        called_args = mock_exec.call_args[0][0]
        assert called_args.get("function_name") == "my_func"


def test_r3_explicit_function_name_wins_over_symbol() -> None:
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["heatmap"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute(
                {
                    "action": "heatmap",
                    "symbol": "from_symbol",
                    "function_name": "explicit",
                }
            )
        )
        called_args = mock_exec.call_args[0][0]
        assert called_args.get("function_name") == "explicit"


# ---------------------------------------------------------------------------
# 7. envelope preservation
# ---------------------------------------------------------------------------


def test_envelope_preserved_verbatim() -> None:
    facade = build_health_facade(project_root=None)
    inner = facade.action_map["overview"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "success": True,
            "verdict": "HEALTHY",
            "agent_summary": {
                "verdict": "HEALTHY",
                "summary_line": "all good",
                "next_step": "nothing",
            },
        }
        result = asyncio.run(facade.execute({"action": "overview"}))
    assert result["verdict"] == "HEALTHY"
    assert result["agent_summary"]["summary_line"] == "all good"


# ---------------------------------------------------------------------------
# 8. missing / unknown action -> error envelope
# ---------------------------------------------------------------------------


def test_missing_action_returns_error_envelope() -> None:
    facade = build_health_facade(project_root=None)
    result = asyncio.run(facade.execute({"min_grade": "A"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    result_str = str(result)
    for action in _ALL_ACTIONS:
        assert action in result_str, f"available_actions missing {action!r}"


def test_unknown_action_returns_error_envelope() -> None:
    facade = build_health_facade(project_root=None)
    result = asyncio.run(
        facade.execute({"action": "nonexistent_action", "file_path": "x.py"})
    )
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    assert "nonexistent_action" in str(result) or "unknown" in str(result).lower()


# ---------------------------------------------------------------------------
# 9. rebind propagation (G3)
# ---------------------------------------------------------------------------


def test_set_project_path_rebinds_all_action_map_inners(tmp_path: Any) -> None:
    """G3: set_project_path on the facade must propagate to every action_map inner."""
    facade = build_health_facade(project_root=None)
    target = str(tmp_path)
    facade.set_project_path(target)
    for action, inner in facade.action_map.items():
        assert inner.project_root == target, (
            f"inner for action={action!r} not rebound (project_root={inner.project_root!r})"
        )


# ---------------------------------------------------------------------------
# 10. no override — factory returns FacadeTool (set_project_path not overridden)
# ---------------------------------------------------------------------------


def test_health_facade_factory_returns_facade_tool() -> None:
    facade = build_health_facade(project_root=None)
    assert isinstance(facade, FacadeTool)
    # FacadeTool itself must not override set_project_path (framework contract)
    assert "set_project_path" not in FacadeTool.__dict__


# ---------------------------------------------------------------------------
# 11. end-to-end no strict leak (F4 guard)
# ---------------------------------------------------------------------------


def test_project_action_no_strict_leak(tmp_path: Any) -> None:
    """Route action=project through the REAL ProjectHealthTool. Verify that
    no ValueError mentioning 'action' escapes — guarding the F4 regression."""
    facade = build_health_facade(project_root=str(tmp_path))
    try:
        result = asyncio.run(facade.execute({"action": "project"}))
    except ValueError as exc:  # pragma: no cover
        assert "action" not in str(exc), (
            "facade leaked 'action' to the inner strict-param guard (F4 regression)"
        )
        raise
    assert isinstance(result, dict)
    assert "success" in result


def test_deps_action_no_strict_leak(tmp_path: Any) -> None:
    """Route action=deps through the REAL DependencyAnalysisTool."""
    facade = build_health_facade(project_root=str(tmp_path))
    try:
        result = asyncio.run(facade.execute({"action": "deps", "mode": "summary"}))
    except ValueError as exc:  # pragma: no cover
        assert "action" not in str(exc), (
            "facade leaked 'action' to DependencyAnalysisTool (F4 regression)"
        )
        raise
    assert isinstance(result, dict)
    assert "success" in result


def test_schema_lists_action_and_core_params() -> None:
    """Wave D slim schema: ``action`` (required) + core shared params only.

    The facade no longer unions every inner param into its public schema (that
    re-imported ~50 rg flags into ``search`` and blew the tool-def token
    budget). Inner-specific params like ``min_grade`` are accepted via
    ``additionalProperties: True`` and surfaced in the description, not the
    schema body — projection still uses the inner's REAL schema (F4 intact).
    """
    facade = build_health_facade(project_root=None)
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "action" in props
    assert "action" in schema.get("required", [])
    # Core shared params are declared explicitly on every facade.
    assert "file_path" in props  # core
    assert "mode" in props  # core
    assert "scope" in props  # core facade control key
    # Inner-specific params are NOT unioned into the public schema anymore...
    assert "min_grade" not in props
    # ...but remain discoverable via the facade description (and accepted via
    # additionalProperties + internal projection).
    assert "min_grade" in facade._description
    # Lenient at facade level so inner-specific params still flow through;
    # inner tools remain strict.
    assert schema.get("additionalProperties") is True


def test_facade_description_mentions_all_actions() -> None:
    """Every action name should appear in the description string."""
    facade = build_health_facade(project_root=None)
    desc = facade._description
    for action in _ALL_ACTIONS:
        assert f"action={action}" in desc, f"Description missing action={action!r}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
