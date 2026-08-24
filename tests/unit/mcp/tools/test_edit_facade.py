#!/usr/bin/env python3
"""Tests for the ``edit`` facade (Wave B).

Covers all §5 required cases from ``.recon/p0-facade-framework-spec.md``:

1.  builds & routes — factory returns FacadeTool, all 8 actions present.
2.  action routing — each action reaches the right inner.
3.  arg projection — ``action`` is NOT in args received by the inner.
4.  sibling-param drop — param for action A doesn't reach action B's inner.
5.  R3 normalize — NOT applicable: only ``guard`` uses ``symbol``, but its
    inner schema declares ``symbol`` directly (not ``function_name``), so R3
    does not trigger. Test confirms ``symbol`` passes through unchanged.
6.  no bespoke routes — all actions go through action_map (no bespoke routes).
7.  envelope preserved — ``verdict`` / ``agent_summary`` come through verbatim.
8.  missing/unknown action — returns error envelope with available_actions.
9.  rebind — ``set_project_path`` propagates to all action_map inners.
10. factory returns FacadeTool (no set_project_path override).
11. end-to-end no strict leak — route through REAL inner, no ValueError on
    ``action`` key (F4 regression guard).
12. annotations correctness — edit facade must NOT declare readOnlyHint=True
    (annotation honesty: mixed read+mutating-intent action set).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool

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
#   - action routing to each of the 8 named actions (safe/guard/impact/refactor/
#     constraints/pr/classify/ast_diff)
#   - sibling-param drop between actions
#   - R3 normalize (symbol -> function_name) for inners that declare function_name
#   - annotation honesty (readOnlyHint must be False for mixed action set)
#   - end-to-end no strict leak (F4 regression guard with real inner tools)
#   - set_project_path rebind propagation (G3)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Fake inner tool — minimal BaseMCPTool to test routing in isolation.
# ---------------------------------------------------------------------------


class _FakeInner(BaseMCPTool):
    """Minimal inner that records the args it receives."""

    def __init__(self, name: str = "fake", project_root: str | None = None) -> None:
        self._tool_name = name
        super().__init__(project_root)
        self.last_args: dict[str, Any] | None = None
        self.rebound_to: list[str] = []

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "symbol": {"type": "string"},
                "output_format": {"type": "string"},
            },
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {"name": self._tool_name, "inputSchema": self.get_tool_schema()}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    def _on_project_root_changed(self, project_root: str | None) -> None:
        if project_root is not None:
            self.rebound_to.append(project_root)

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.last_args = dict(arguments)
        return {
            "success": True,
            "verdict": "INFO",
            "tool": self._tool_name,
            "agent_summary": {
                "verdict": "INFO",
                "summary_line": f"{self._tool_name} ok",
                "next_step": "n/a",
            },
        }


def _make_fake_facade(**kwargs: Any) -> tuple[FacadeTool, dict[str, _FakeInner]]:
    """Build a facade with all 8 edit actions wired to fake inners."""
    inners: dict[str, _FakeInner] = {
        "safe": _FakeInner("safe"),
        "guard": _FakeInner("guard"),
        "impact": _FakeInner("impact"),
        "refactor": _FakeInner("refactor"),
        "constraints": _FakeInner("constraints"),
        "pr": _FakeInner("pr"),
        "classify": _FakeInner("classify"),
        "ast_diff": _FakeInner("ast_diff"),
    }
    facade = FacadeTool(
        facade_name="edit",
        action_map=dict(inners),
        bespoke_map={},
        **kwargs,
    )
    return facade, inners


# ---------------------------------------------------------------------------
# 1. Builds & routes — factory returns FacadeTool, all 8 actions present
# ---------------------------------------------------------------------------


def test_edit_facade_builds() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    assert isinstance(facade, FacadeTool)
    assert facade.facade_name == "edit"


def test_impact_action_description_documents_mode_param() -> None:
    """#998: action=impact supports a ``mode`` param (diff|staged|branch|pr).

    Skills (tsa-edit-safety, tsa-pr-review, tsa-landing) pass mode=staged /
    branch, so the facade description must advertise the param + its values.
    """
    from tree_sitter_analyzer.mcp.tools.edit_facade import _EDIT_DESCRIPTION

    assert "mode (diff|staged|branch|pr" in _EDIT_DESCRIPTION


def test_impact_snapshot_producer_is_publicly_discoverable() -> None:
    # PR #1252 review thread 3751415929: schema clients must find the producer.
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    properties = build_edit_facade(None).get_tool_definition()["inputSchema"][
        "properties"
    ]

    assert properties["capture_diff_snapshot"] == {
        "type": "boolean",
        "description": (
            "Explicitly produce a frozen diff ID for same-process consumers; "
            "supported only on POSIX."
        ),
    }


def test_edit_facade_all_actions_present() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    expected = {
        "safe",
        "guard",
        "impact",
        "refactor",
        "constraints",
        "pr",
        "classify",
        "ast_diff",
        "release_snapshot",
        # RFC-0027 §L8: preview-only minimal rename edit set, wired from the
        # previously orphaned CodeGraphRefactorTool.
        "plan_rename",
    }
    registered = set(facade.action_map) | set(facade.bespoke_map)
    assert expected == registered


# ---------------------------------------------------------------------------
# 2. Action routing — each action reaches the right inner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action",
    [
        "safe",
        "guard",
        "impact",
        "refactor",
        "constraints",
        "pr",
        "classify",
        "ast_diff",
    ],
)
def test_action_routes_to_correct_inner(action: str) -> None:
    facade, inners = _make_fake_facade()
    asyncio.run(facade.execute({"action": action, "file_path": "src/foo.py"}))
    assert inners[action].last_args is not None, (
        f"action={action!r} did not reach its inner"
    )
    # Sibling inners must NOT have been called.
    for other_action, other_inner in inners.items():
        if other_action != action:
            assert other_inner.last_args is None, (
                f"action={action!r} spuriously routed to inner {other_action!r}"
            )
    # Reset for next parametrize iteration isolation (each call is a new facade anyway).


# ---------------------------------------------------------------------------
# 3. Arg projection — ``action`` must be stripped before reaching inner
# ---------------------------------------------------------------------------


def test_arg_projection_strips_action_key() -> None:
    facade, inners = _make_fake_facade()
    asyncio.run(facade.execute({"action": "safe", "file_path": "a.py"}))
    inner = inners["safe"]
    assert inner.last_args is not None
    assert "action" not in inner.last_args
    assert "file_path" in inner.last_args


def test_arg_projection_passes_known_params() -> None:
    facade, inners = _make_fake_facade()
    asyncio.run(
        facade.execute(
            {"action": "classify", "symbol": "MyClass", "output_format": "toon"}
        )
    )
    inner = inners["classify"]
    assert inner.last_args is not None
    assert inner.last_args.get("symbol") == "MyClass"
    assert inner.last_args.get("output_format") == "toon"
    assert "action" not in inner.last_args


# ---------------------------------------------------------------------------
# 4. Sibling-param drop — param for action A doesn't reach action B's inner
# ---------------------------------------------------------------------------


def test_sibling_param_is_dropped() -> None:
    """``file_path`` param routed to 'safe'; must NOT appear in 'impact' inner
    unless 'impact' also declares it. Here both fake inners declare file_path,
    but only the targeted action is called; the sibling inner stays untouched."""
    facade, inners = _make_fake_facade()
    asyncio.run(
        facade.execute({"action": "safe", "file_path": "x.py", "symbol": "Foo"})
    )
    # guard inner (sibling) was NOT called at all.
    assert inners["guard"].last_args is None
    # safe inner got called; ``symbol`` is in its schema so it passes through.
    assert inners["safe"].last_args is not None
    assert "action" not in inners["safe"].last_args


# ---------------------------------------------------------------------------
# 5. R3 normalize — guard uses ``symbol`` natively (no function_name rename)
# ---------------------------------------------------------------------------


def test_guard_symbol_passes_through_unchanged() -> None:
    """ModificationGuardTool declares ``symbol`` in its schema (NOT function_name).
    R3 normalize only fires for inners that declare ``function_name``. Here
    ``symbol`` must reach the inner as-is without being renamed."""
    facade, inners = _make_fake_facade()
    asyncio.run(facade.execute({"action": "guard", "symbol": "processPayment"}))
    inner = inners["guard"]
    assert inner.last_args is not None
    assert inner.last_args.get("symbol") == "processPayment"
    # function_name must NOT be injected (guard inner doesn't declare it).
    assert "function_name" not in inner.last_args


# ---------------------------------------------------------------------------
# 6. No bespoke routes — all 8 actions are in action_map
# ---------------------------------------------------------------------------


def test_release_snapshot_is_the_only_bespoke_route() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    assert set(facade.bespoke_map) == {"release_snapshot"}
    assert len(facade.action_map) == 10


# ---------------------------------------------------------------------------
# 7. Envelope preserved — verdict / agent_summary come through verbatim
# ---------------------------------------------------------------------------


def test_verdict_preserved_verbatim() -> None:
    facade, _ = _make_fake_facade()
    result = asyncio.run(facade.execute({"action": "safe", "file_path": "a.py"}))
    assert result["success"] is True
    assert result["verdict"] == "INFO"
    assert result["agent_summary"]["summary_line"] == "safe ok"
    assert result["agent_summary"]["verdict"] == "INFO"


def test_verdict_not_overwritten() -> None:
    """Facade must not re-wrap / overwrite the inner's verdict envelope."""
    facade, inners = _make_fake_facade()

    async def _execute_with_custom_verdict() -> dict[str, Any]:
        inners["impact"].execute = AsyncMock(
            return_value={  # type: ignore[method-assign]
                "success": True,
                "verdict": "WARN",
                "agent_summary": {
                    "verdict": "WARN",
                    "summary_line": "custom",
                    "next_step": "fix",
                },
            }
        )
        return await facade.execute({"action": "impact"})

    result = asyncio.run(_execute_with_custom_verdict())
    assert result["verdict"] == "WARN"
    assert result["agent_summary"]["summary_line"] == "custom"


# ---------------------------------------------------------------------------
# 8. Missing / unknown action — error envelope with available_actions
# ---------------------------------------------------------------------------


def test_missing_action_returns_error_envelope() -> None:
    facade, _ = _make_fake_facade()
    result = asyncio.run(facade.execute({"file_path": "a.py"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    # Available actions must be surfaced.
    body = str(result)
    for action in (
        "safe",
        "guard",
        "impact",
        "refactor",
        "constraints",
        "pr",
        "classify",
        "ast_diff",
    ):
        assert action in body, f"action {action!r} not listed in error envelope"


def test_unknown_action_returns_error_envelope() -> None:
    facade, _ = _make_fake_facade()
    result = asyncio.run(facade.execute({"action": "does_not_exist"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    assert "available_actions" in result
    assert "safe" in result["available_actions"]


# ---------------------------------------------------------------------------
# 9. Rebind — set_project_path propagates to action_map inners
# ---------------------------------------------------------------------------


def test_set_project_path_rebinds_all_inners(tmp_path: Any) -> None:
    """G3: facade.set_project_path must forward to every action_map inner."""
    facade, inners = _make_fake_facade()
    # Clear init-time rebind records.
    for inner in inners.values():
        inner.rebound_to.clear()

    target = str(tmp_path)
    facade.set_project_path(target)

    for action, inner in inners.items():
        assert inner.project_root == target, (
            f"inner {action!r} was not rebound to {target!r}"
        )
        assert target in inner.rebound_to, (
            f"inner {action!r} _on_project_root_changed not called"
        )


# ---------------------------------------------------------------------------
# 10. Factory returns FacadeTool (no set_project_path override)
# ---------------------------------------------------------------------------


def test_facade_does_not_override_set_project_path() -> None:
    """FacadeTool must inherit set_project_path; edit facade must not override it."""
    assert "set_project_path" not in FacadeTool.__dict__


def test_build_edit_facade_returns_facade_tool() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    assert isinstance(facade, FacadeTool)


# ---------------------------------------------------------------------------
# 11. End-to-end no strict leak — real inner, no ValueError on 'action' (F4)
# ---------------------------------------------------------------------------


def test_safe_action_does_not_leak_action_to_inner_strict_guard(tmp_path: Any) -> None:
    """Route 'safe' through the REAL SafeToEditTool. The inner's strict-param
    guard must NOT raise ValueError mentioning 'action' (F4 regression).

    SafeToEditTool raises ValueError for missing files — use a real file so the
    tool gets past its path-validation gate and we can confirm ``action`` was
    stripped before the inner's strict-param guard ran.
    """
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    # Create a real file so SafeToEditTool does not abort at path-validation.
    real_file = tmp_path / "sample.py"
    real_file.write_text("def hello(): pass\n")

    facade = build_edit_facade(project_root=str(tmp_path))
    try:
        result = asyncio.run(
            facade.execute({"action": "safe", "file_path": str(real_file)})
        )
    except ValueError as exc:  # pragma: no cover — guards F4 regression
        assert "action" not in str(exc), (
            "facade leaked 'action' to SafeToEditTool strict-param guard (F4 regression)"
        )
        raise
    # Result must be a dict (error envelope or success).
    assert isinstance(result, dict)
    assert "success" in result


def test_constraints_action_does_not_leak_action_to_inner(tmp_path: Any) -> None:
    """F4 regression guard for ConstraintCheckTool (no required file_path)."""
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=str(tmp_path))
    try:
        result = asyncio.run(facade.execute({"action": "constraints"}))
    except ValueError as exc:  # pragma: no cover — guards F4 regression
        assert "action" not in str(exc), (
            "facade leaked 'action' to ConstraintCheckTool strict-param guard (F4)"
        )
        raise
    assert isinstance(result, dict)
    assert "success" in result


def test_scope_paths_is_rejected_outside_impact_and_constraints() -> None:
    # PR #1254 review 3769281322: explicit facade scope must never be dropped.
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    result = asyncio.run(facade.execute({"action": "safe", "scope_paths": ["src"]}))

    assert result["success"] is False
    assert result["error"] == (
        "parameter 'scope_paths' applies only to action(s): constraints, impact"
    )


# ---------------------------------------------------------------------------
# 13. RFC-0027 §L8 — ``plan_rename`` is preview-only, and provably so
# ---------------------------------------------------------------------------

#: Arguments a caller might use to smuggle an apply through a planning surface.
#: ``mode="preview"`` is in the list on purpose: accepting it would advertise
#: that the parameter is honoured, and the next caller would try ``"apply"``.
_APPLY_LIKE_ARGS: tuple[tuple[str, Any], ...] = (
    ("mode", "apply"),
    ("mode", "preview"),
    ("dry_run", False),
    ("apply", True),
    ("write", True),
    ("force", True),
)

_AST_CACHE_DIR = ".ast-cache"


def _plan_rename_project(tmp_path: Any) -> Any:
    """A tiny two-file python project with a symbol worth renaming."""
    (tmp_path / "mod.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    (tmp_path / "caller.py").write_text(
        "from mod import target\n\n\ndef go():\n    return target()\n",
        encoding="utf-8",
    )
    return tmp_path


def _snapshot(root: Any) -> dict[str, tuple[int, bytes]]:
    """Every file under ``root`` as ``{relative_posix_path: (mtime_ns, bytes)}``."""
    return {
        p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.mark.parametrize(("key", "value"), _APPLY_LIKE_ARGS)
def test_plan_rename_rejects_apply_like_arguments(key: str, value: Any) -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    with pytest.raises(ValueError, match="PLAN_RENAME_IS_PREVIEW_ONLY"):
        asyncio.run(
            facade.execute(
                {
                    "action": "plan_rename",
                    "symbol": "target",
                    "new_name": "renamed",
                    key: value,
                }
            )
        )


def test_plan_rename_pins_dry_run_true_on_the_engine(tmp_path: Any) -> None:
    """The binding pins preview internally — ``rename_symbol(dry_run=True)``."""
    from unittest.mock import patch

    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    class _EmptyResult:
        errors: list[str] = []
        sites: list[Any] = []
        sites_renamed = 0

        def to_dict(self) -> dict[str, Any]:
            return {"symbol": "target", "new_name": "renamed", "dry_run": True}

    root = _plan_rename_project(tmp_path)
    facade = build_edit_facade(project_root=str(root))
    inner = facade.action_map["plan_rename"]
    assert inner.FORCED_MODE == "preview"
    with (
        patch.object(inner, "_get_cache", return_value=object()),
        patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_refactor_tool.rename_symbol",
            return_value=_EmptyResult(),
        ) as mock_rename,
    ):
        asyncio.run(
            facade.execute(
                {
                    "action": "plan_rename",
                    "symbol": "target",
                    "new_name": "renamed",
                    "output_format": "json",
                }
            )
        )
    assert mock_rename.call_args.kwargs["dry_run"] is True


@pytest.mark.parametrize(("key", "value"), _APPLY_LIKE_ARGS)
def test_plan_rename_adversarial_input_writes_nothing_at_all(
    tmp_path: Any, key: str, value: Any
) -> None:
    """Zero filesystem writes on adversarial input — bytes AND mtime_ns pinned.

    The rejection happens at the facade boundary, before any work, so *every*
    path under the project is unchanged — not just the source files.
    """
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    root = _plan_rename_project(tmp_path)
    facade = build_edit_facade(project_root=str(root))
    before = _snapshot(root)

    with pytest.raises(ValueError, match="PLAN_RENAME_IS_PREVIEW_ONLY"):
        asyncio.run(
            facade.execute(
                {
                    "action": "plan_rename",
                    "symbol": "target",
                    "new_name": "renamed",
                    "output_format": "json",
                    key: value,
                }
            )
        )

    assert _snapshot(root) == before


def test_plan_rename_preview_leaves_every_pre_existing_file_untouched(
    tmp_path: Any,
) -> None:
    """A real (unmocked) preview call mutates no file that existed before it.

    The only paths it may *add* are under ``.ast-cache/`` — analysis
    infrastructure the auto-index guard builds, never caller source. That
    boundary is asserted rather than assumed: a rename that leaked into
    ``mod.py`` would show up as a changed pre-existing entry, and a stray
    artefact anywhere else would show up as an unexpected new path.
    """
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    root = _plan_rename_project(tmp_path)
    facade = build_edit_facade(project_root=str(root))
    before = _snapshot(root)

    asyncio.run(
        facade.execute(
            {
                "action": "plan_rename",
                "symbol": "target",
                "new_name": "renamed",
                "output_format": "json",
            }
        )
    )

    after = _snapshot(root)
    assert {k: v for k, v in after.items() if k in before} == before
    added = sorted(set(after) - set(before))
    assert [p for p in added if not p.startswith(f"{_AST_CACHE_DIR}/")] == []
