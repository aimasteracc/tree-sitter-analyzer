"""Schema and public-contract coverage for the edit facade."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from tests.unit.mcp.tools.test_edit_facade import _make_fake_facade


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


def test_edit_facade_schema_includes_action_and_required() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    schema = facade.get_tool_schema()
    props = schema["properties"]
    assert "action" in props
    assert "action" in schema.get("required", [])
    # action enum must list every action the facade exposes.
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
        "release_snapshot",
        # RFC-0027 §L8: preview-only minimal rename edit set.
        "plan_rename",
        # RFC-0029: mutation probe — does this test constrain this code?
        "mutation_probe",
    }
    assert expected == enum_vals


def test_edit_facade_schema_lenient_additional_properties() -> None:
    """The merged facade schema must be lenient (additionalProperties not False)."""
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(project_root=None)
    schema = facade.get_tool_schema()
    # The schema must be additionalProperties: True (lenient), not False (strict).
    assert schema.get("additionalProperties") is True


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
    with patch(
        "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_local_diff",
        return_value="",
    ) as get_local_diff:
        result = asyncio.run(facade.execute({"action": "pr", "mode": "diff"}))

    get_local_diff.assert_called_once_with("diff", ".")
    # diff mode reviews local changes — must not demand pr_url
    assert result["success"] is True
    assert result.get("error") is None or "pr_url" not in str(result.get("error"))
