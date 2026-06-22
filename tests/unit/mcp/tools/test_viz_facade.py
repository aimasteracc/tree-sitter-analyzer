#!/usr/bin/env python3
"""Tests for the ``viz`` facade (Wave B, P0 geode layer).

Covered behaviours (mirrors test_facade_tool.py §5 contract):
1.  builds & routes — factory returns FacadeTool; all 4 actions present.
2.  action routing — {"action": X, ...} reaches the right inner.
3.  arg projection — ``action`` is NOT in the args the inner received.
4.  sibling-param drop — param for action A doesn't reach action B's inner.
5.  envelope preserved — ``verdict`` / ``agent_summary`` come through verbatim.
6.  missing / unknown action — error envelope with available_actions listed.
7.  rebind — set_project_path propagates to every action_map inner.
8.  no override — factory returns a FacadeTool (set_project_path not overridden).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

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
#   - action routing to uml/graph/similarity/knowledge actions
#   - sibling-param drop between actions
#   - annotation honesty (readOnlyHint=True valid for all-read-only viz facade)
#   - end-to-end no strict leak (F4 regression guard with real inner tools)
#   - set_project_path rebind propagation (G3)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Expected actions
# ---------------------------------------------------------------------------

_ALL_ACTIONS = frozenset({"uml", "graph", "similarity", "knowledge"})

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
                "mode": {"type": "string"},
                "file_path": {"type": "string"},
            },
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {"name": "fake_inner", "inputSchema": self.get_tool_schema()}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    def _on_project_root_changed(self, project_root: str | None) -> None:
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


# ---------------------------------------------------------------------------
# 1. builds & routes
# ---------------------------------------------------------------------------


def test_viz_facade_builds_and_has_all_actions() -> None:
    facade = build_viz_facade(project_root=None)
    assert isinstance(facade, FacadeTool)
    assert facade.facade_name == "viz"
    present = set(facade.action_map) | set(facade.bespoke_map)
    assert present == _ALL_ACTIONS, (
        f"Missing: {_ALL_ACTIONS - present}, Extra: {present - _ALL_ACTIONS}"
    )


def test_viz_facade_total_action_count() -> None:
    """4 actions total: uml, graph, similarity, knowledge."""
    facade = build_viz_facade(project_root=None)
    total = len(facade.action_map) + len(facade.bespoke_map)
    assert total == 4


def test_viz_facade_annotations_read_only() -> None:
    """All viz actions are read-only — pure generation/analysis, no mutations."""
    facade = build_viz_facade(project_root=None)
    ann = facade._annotations
    assert ann is not None
    assert ann["readOnlyHint"] is True
    assert ann["destructiveHint"] is False
    assert ann["idempotentHint"] is True
    assert ann["openWorldHint"] is False


# ---------------------------------------------------------------------------
# 2 & 3. action routing + arg projection (F4)
# ---------------------------------------------------------------------------


def test_uml_action_routes_and_strips_action_key() -> None:
    """action=uml should not forward ``action`` to the inner."""
    facade = build_viz_facade(project_root=None)
    inner = facade.action_map["uml"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute({"action": "uml", "diagram": "class", "source": "Foo"})
        )
        mock_exec.assert_called_once()
        called_args = mock_exec.call_args[0][0]
        assert "action" not in called_args
        assert called_args.get("diagram") == "class"


def test_graph_action_routes_and_strips_action_key() -> None:
    """action=graph should not forward ``action`` to the inner."""
    facade = build_viz_facade(project_root=None)
    inner = facade.action_map["graph"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute(
                {
                    "action": "graph",
                    "mode": "call",
                    "file_path": "src/foo.py",
                    "depth": 2,
                }
            )
        )
        called_args = mock_exec.call_args[0][0]
        assert "action" not in called_args
        assert called_args.get("mode") == "call"


def test_similarity_action_routes_and_strips_action_key() -> None:
    """action=similarity should not forward ``action`` to the inner."""
    facade = build_viz_facade(project_root=None)
    inner = facade.action_map["similarity"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute({"action": "similarity", "min_lines": 10, "max_groups": 5})
        )
        called_args = mock_exec.call_args[0][0]
        assert "action" not in called_args
        assert called_args.get("min_lines") == 10


# ---------------------------------------------------------------------------
# 4. sibling-param drop
# ---------------------------------------------------------------------------


def test_sibling_param_does_not_reach_uml_inner() -> None:
    """Param for action=graph (depth) must not leak to uml inner."""
    facade = build_viz_facade(project_root=None)
    inner = facade.action_map["uml"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(facade.execute({"action": "uml", "diagram": "class", "depth": 3}))
        called_args = mock_exec.call_args[0][0]
        # depth is NOT in CodeGraphUMLTool's schema => must be dropped
        assert "depth" not in called_args
        assert called_args.get("diagram") == "class"


def test_sibling_param_does_not_reach_similarity_inner() -> None:
    """Param for action=uml (source) must not leak to similarity inner."""
    facade = build_viz_facade(project_root=None)
    inner = facade.action_map["similarity"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "verdict": "INFO"}
        asyncio.run(
            facade.execute({"action": "similarity", "min_lines": 5, "source": "Foo"})
        )
        called_args = mock_exec.call_args[0][0]
        # source is NOT in CodeGraphSimilarityTool's schema => must be dropped
        assert "source" not in called_args
        assert called_args.get("min_lines") == 5


# ---------------------------------------------------------------------------
# 5. envelope preservation
# ---------------------------------------------------------------------------


def test_envelope_preserved_verbatim() -> None:
    facade = build_viz_facade(project_root=None)
    inner = facade.action_map["graph"]
    with patch.object(inner, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "success": True,
            "verdict": "HEALTHY",
            "agent_summary": {
                "verdict": "HEALTHY",
                "summary_line": "graph rendered",
                "next_step": "nothing",
            },
        }
        result = asyncio.run(facade.execute({"action": "graph"}))
    assert result["verdict"] == "HEALTHY"
    assert result["agent_summary"]["summary_line"] == "graph rendered"


# ---------------------------------------------------------------------------
# 6. missing / unknown action -> error envelope
# ---------------------------------------------------------------------------


def test_missing_action_returns_error_envelope() -> None:
    facade = build_viz_facade(project_root=None)
    result = asyncio.run(facade.execute({"diagram": "class"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    result_str = str(result)
    for action in _ALL_ACTIONS:
        assert action in result_str, f"available_actions missing {action!r}"


def test_unknown_action_returns_error_envelope() -> None:
    facade = build_viz_facade(project_root=None)
    result = asyncio.run(
        facade.execute({"action": "nonexistent_action", "file_path": "x.py"})
    )
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    assert "nonexistent_action" in str(result) or "unknown" in str(result).lower()


# ---------------------------------------------------------------------------
# 7. rebind propagation (G3)
# ---------------------------------------------------------------------------


def test_set_project_path_rebinds_all_action_map_inners(tmp_path: Any) -> None:
    """G3: set_project_path on the facade must propagate to every action_map inner."""
    facade = build_viz_facade(project_root=None)
    target = str(tmp_path)
    facade.set_project_path(target)
    for action, inner in facade.action_map.items():
        assert inner.project_root == target, (
            f"inner for action={action!r} not rebound (project_root={inner.project_root!r})"
        )


# ---------------------------------------------------------------------------
# 8. no override — factory returns FacadeTool (set_project_path not overridden)
# ---------------------------------------------------------------------------


def test_viz_facade_factory_returns_facade_tool() -> None:
    facade = build_viz_facade(project_root=None)
    assert isinstance(facade, FacadeTool)
    # FacadeTool itself must not override set_project_path (framework contract)
    assert "set_project_path" not in FacadeTool.__dict__


# ---------------------------------------------------------------------------
# Schema + description sanity checks
# ---------------------------------------------------------------------------


def test_schema_lists_action_as_required_with_all_actions() -> None:
    """Facade schema must list ``action`` as required with the 3 viz actions."""
    facade = build_viz_facade(project_root=None)
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "action" in props
    assert "action" in schema.get("required", [])
    action_enum = props["action"].get("enum", [])
    for action in _ALL_ACTIONS:
        assert action in action_enum, f"action enum missing {action!r}"
    # Not strict at facade level (inner tools remain strict)
    assert schema.get("additionalProperties") is not False


def test_facade_description_mentions_all_actions() -> None:
    """Every action name should appear in the description string."""
    facade = build_viz_facade(project_root=None)
    desc = facade._description
    for action in _ALL_ACTIONS:
        assert f"action={action}" in desc, f"Description missing action={action!r}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
