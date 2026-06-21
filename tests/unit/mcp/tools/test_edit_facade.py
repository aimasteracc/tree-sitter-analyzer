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


def test_no_bespoke_routes() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    assert facade.bespoke_map == {}, "edit facade should have no bespoke routes"
    assert len(facade.action_map) == 8


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
    assert type(facade) is FacadeTool


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


# ---------------------------------------------------------------------------
# 12. Annotations correctness — edit facade must NOT declare readOnlyHint=True
# ---------------------------------------------------------------------------


def test_edit_annotations_not_read_only() -> None:
    """edit facade spans mutating-intent actions — readOnlyHint must be False."""
    from tree_sitter_analyzer.mcp.tools.edit_facade import _EDIT_ANNOTATIONS

    assert _EDIT_ANNOTATIONS["readOnlyHint"] is False, (
        "edit facade cannot claim readOnlyHint=True (mixed read+mutating-intent actions)"
    )


def test_edit_annotations_not_destructive() -> None:
    """edit facade suggests/analyses; it does not write files."""
    from tree_sitter_analyzer.mcp.tools.edit_facade import _EDIT_ANNOTATIONS

    assert _EDIT_ANNOTATIONS["destructiveHint"] is False


def test_edit_annotations_all_four_hints_present() -> None:
    """test_every_tool_declares_mcp_annotations requires all 4 hint keys."""
    from tree_sitter_analyzer.mcp.tools.edit_facade import _EDIT_ANNOTATIONS

    required = {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
    assert required.issubset(_EDIT_ANNOTATIONS.keys())


def test_edit_facade_definition_includes_annotations() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    defn = facade.get_tool_definition()
    assert "annotations" in defn
    annot = defn["annotations"]
    assert annot["readOnlyHint"] is False
    assert annot["destructiveHint"] is False


# ---------------------------------------------------------------------------
# 13. Facade description honesty — ast_diff description uses REAL mode params
#     (Leg D of issue #529 triple-fix)
# ---------------------------------------------------------------------------


def test_ast_diff_facade_description_uses_real_mode_params() -> None:
    """Leg D: the ast_diff description in the edit facade must reference the
    REAL mode signatures (old_file/new_file | old_source/new_source |
    old_ref/new_ref) and must NOT use the nonexistent 'before, after' params.
    """
    from tree_sitter_analyzer.mcp.tools.edit_facade import _EDIT_DESCRIPTION

    # Must contain real param names
    assert "old_ref" in _EDIT_DESCRIPTION, (
        "ast_diff facade description must mention 'old_ref' (diff_git signature)"
    )
    assert "old_file" in _EDIT_DESCRIPTION or "new_file" in _EDIT_DESCRIPTION, (
        "ast_diff facade description must mention 'old_file'/'new_file' (diff_files signature)"
    )
    assert "old_source" in _EDIT_DESCRIPTION or "new_source" in _EDIT_DESCRIPTION, (
        "ast_diff facade description must mention 'old_source'/'new_source' (diff_strings signature)"
    )

    # Must NOT use the nonexistent 'before, after' params
    assert "before, after" not in _EDIT_DESCRIPTION, (
        "ast_diff facade description must NOT use nonexistent 'before, after' params"
    )


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_edit_facade_schema_includes_action_and_required() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "action" in props
    assert "action" in schema.get("required", [])
    # action enum must list all 8 actions.
    enum_vals = set(props["action"].get("enum", []))
    expected = {
        "safe",
        "guard",
        "impact",
        "refactor",
        "constraints",
        "pr",
        "classify",
        "ast_diff",
    }
    assert expected == enum_vals


def test_edit_facade_schema_lenient_additional_properties() -> None:
    """The merged facade schema must be lenient (additionalProperties not False)."""
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    schema = facade.get_tool_schema()
    # The schema must be additionalProperties: True (lenient), not False (strict).
    assert schema.get("additionalProperties") is True


# ---------------------------------------------------------------------------
# Issue #451 — edit action=pr without pr_url must fail loudly via the facade
# ---------------------------------------------------------------------------


def test_edit_pr_action_missing_pr_url_fails_loudly() -> None:
    """action=pr without pr_url → success:False, ERROR verdict, not 'No changed files'.

    Regression guard for issue #451: an agent that misnames the param (e.g.
    uses query= instead of pr_url=) would have the extra param stripped by
    facade projection, leaving only {mode:pr}. The inner must return an error
    envelope, not silently fall through to an empty local diff review.
    """
    facade, inners = _make_fake_facade()
    # Replace the fake 'pr' inner with a real CodeGraphPRReviewTool
    from tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool import (
        CodeGraphPRReviewTool,
    )

    real_pr_inner = CodeGraphPRReviewTool(project_root=None)
    facade.action_map["pr"] = real_pr_inner

    # mode=pr but no pr_url (simulates post-projection args)
    result = asyncio.run(facade.execute({"action": "pr", "mode": "pr"}))
    assert result["success"] is False
    assert result.get("verdict") == "ERROR"
    assert "pr_url" in result.get("error", "")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ---------------------------------------------------------------------------
# Issue #641 — edit facade schema must expose modification_type with enum
# for action=guard discoverability (extra_public_params, NOT required:[])
# ---------------------------------------------------------------------------


def test_edit_facade_schema_has_modification_type_property() -> None:
    """Schema must declare modification_type so schema-reading agents see it.

    Before fix: modification_type was only reachable via additionalProperties
    (invisible to schema inspection). After fix: it appears in properties with
    the authoritative enum — matching the inner ModificationGuardTool schema.
    """
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "modification_type" in props, (
        "modification_type must be declared in the edit facade's public schema "
        "(not hidden behind additionalProperties)"
    )


def test_edit_facade_modification_type_has_enum() -> None:
    """modification_type property must carry the full authoritative enum."""
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade
    from tree_sitter_analyzer.mcp.tools.modification_guard_tool import (
        MODIFICATION_TYPES,
    )

    facade = build_edit_facade(project_root=None)
    schema = facade.get_tool_schema()
    prop = schema["properties"]["modification_type"]
    assert "enum" in prop, "modification_type must declare an enum"
    assert set(prop["enum"]) == set(MODIFICATION_TYPES), (
        "facade modification_type enum must match the inner tool's MODIFICATION_TYPES constant"
    )


def test_edit_facade_modification_type_NOT_in_required() -> None:
    """modification_type must NOT be in facade required[] (runtime-resolved param).

    LOCKED convention: runtime-required params are described in the description
    text, not in schema required: [] — this prevents the facade validator from
    rejecting calls before routing (facade required only lists 'action').
    """
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    schema = facade.get_tool_schema()
    assert "modification_type" not in schema.get("required", []), (
        "modification_type must NOT appear in facade required[] "
        "(runtime-resolved param — locked convention, #397 family)"
    )


def test_edit_facade_guard_description_marks_modification_type_required() -> None:
    """action=guard description must mark modification_type as required (e.g. with *).

    Before fix: the description listed 'Params: symbol, modification_type,
    file_path' without any required marker — agents had no signal that omitting
    modification_type triggers an error on the first call.
    """
    from tree_sitter_analyzer.mcp.tools.edit_facade import _EDIT_DESCRIPTION

    # The guard line must mark modification_type as required (trailing * or explicit note)
    guard_lines = [
        line for line in _EDIT_DESCRIPTION.splitlines() if "action=guard" in line
    ]
    assert guard_lines, "edit facade description must have an action=guard line"
    guard_line = guard_lines[0]
    assert (
        "modification_type*" in guard_line
        or "modification_type (required" in guard_line
    ), (
        f"action=guard description line must mark modification_type as required "
        f"(e.g. 'modification_type*'); got: {guard_line!r}"
    )


def test_action_pr_without_mode_or_pr_url_fails_loudly() -> None:
    """Codex P1 (#483): facade action=pr with NO explicit mode must not
    fall back to the inner's diff default and return empty success.

    ``edit({"action": "pr", "query": "<url>"})`` (typoed param) previously
    reached the inner without mode → diff mode → success "No changed files".
    The facade pr route now implies mode=pr, so the pr_url guard fires."""
    import asyncio

    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(".")
    result = asyncio.run(
        facade.execute({"action": "pr", "query": "https://github.com/o/r/pull/1"})
    )
    assert result["success"] is False
    assert "pr_url" in result["error"]


def test_action_pr_explicit_diff_mode_still_reaches_diff() -> None:
    """Direct sub-mode selection stays available through the facade."""
    import asyncio

    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(".")
    result = asyncio.run(facade.execute({"action": "pr", "mode": "diff"}))
    # diff mode reviews local changes — must not demand pr_url
    assert result.get("error") is None or "pr_url" not in str(result.get("error"))
