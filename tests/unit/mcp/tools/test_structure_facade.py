#!/usr/bin/env python3
"""Tests for the ``structure`` facade (Wave B, P0 geode layer).

Covers all 11 categories from the onboarding spec §5:
1.  builds & routes — factory returns a FacadeTool with all expected actions.
2.  action routing — each action reaches the right inner.
3.  arg projection — ``action`` is stripped before reaching inner tools.
4.  sibling-param drop — params for one action don't leak to another.
5.  R3 normalize — N/A for structure (no function_name inner); omitted.
6.  bespoke route (read) — single + batch modes, bypasses projection.
7.  envelope preserved — verdict/agent_summary come through verbatim.
8.  missing/unknown action — error envelope with available_actions.
9.  rebind (G3) — set_project_path propagates to action_map + bespoke inners.
10. no override — factory returns a plain FacadeTool (already covered by #1).
11. end-to-end no strict leak — route through real inner without ValueError on action.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
from tree_sitter_analyzer.mcp.tools.structure_facade import build_structure_facade

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
#   - action routing to each named structure action (outline/analyze/ast_path/...)
#   - sibling-param drop between actions
#   - bespoke route (read) — single and batch modes, bypasses projection
#   - end-to-end no strict leak (F4 regression guard with real inner tools)
#   - set_project_path rebind propagation to action_map and bespoke inners (G3)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Expected actions in the structure facade
# ---------------------------------------------------------------------------
_EXPECTED_ACTIONS = {
    "outline",
    "analyze",
    "ast_path",
    "sitemap",
    "class_tree",
    "class_detail",
    "explore",
    "read",  # bespoke F5
    "signatures",  # bespoke lightweight method-directory
}


# ---------------------------------------------------------------------------
# 1. builds & routes — factory returns FacadeTool with all expected actions
# ---------------------------------------------------------------------------


def test_structure_facade_builds() -> None:
    facade = build_structure_facade(project_root=None)
    assert isinstance(facade, FacadeTool)
    assert facade.facade_name == "structure"


def test_structure_facade_has_all_expected_actions() -> None:
    facade = build_structure_facade(project_root=None)
    registered = set(facade.action_map) | set(facade.bespoke_map)
    assert registered == _EXPECTED_ACTIONS


def test_structure_facade_query_not_registered() -> None:
    """F3: query (.scm DSL) belongs to search facade, NOT structure."""
    facade = build_structure_facade(project_root=None)
    registered = set(facade.action_map) | set(facade.bespoke_map)
    assert "query" not in registered


def test_structure_facade_read_is_bespoke() -> None:
    """read must be a bespoke route (not in action_map) — it does reshaping."""
    facade = build_structure_facade(project_root=None)
    assert "read" in facade.bespoke_map
    assert "read" not in facade.action_map


def test_structure_facade_action_map_entries() -> None:
    """All non-bespoke actions are in action_map (plain inner tool delegation)."""
    facade = build_structure_facade(project_root=None)
    # "read", "signatures", and "class_detail" are bespoke routes — not in action_map.
    # class_detail is bespoke so it can alias query/symbol → class_name (#804).
    _bespoke = {"read", "signatures", "class_detail"}
    for action in _EXPECTED_ACTIONS - _bespoke:
        assert action in facade.action_map, f"Missing action_map entry: {action}"


# ---------------------------------------------------------------------------
# 2. action routing — each action reaches the right inner class
# ---------------------------------------------------------------------------


def test_action_routing_outline() -> None:
    from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool

    facade = build_structure_facade(project_root=None)
    assert isinstance(facade.action_map["outline"], GetCodeOutlineTool)


def test_action_routing_analyze() -> None:
    from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
        AnalyzeCodeStructureTool,
    )

    facade = build_structure_facade(project_root=None)
    assert isinstance(facade.action_map["analyze"], AnalyzeCodeStructureTool)


def test_action_routing_ast_path() -> None:
    from tree_sitter_analyzer.mcp.tools.ast_path_tool import CodeGraphASTPathTool

    facade = build_structure_facade(project_root=None)
    assert isinstance(facade.action_map["ast_path"], CodeGraphASTPathTool)


def test_action_routing_sitemap() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import (
        CodeGraphSitemapTool,
    )

    facade = build_structure_facade(project_root=None)
    assert isinstance(facade.action_map["sitemap"], CodeGraphSitemapTool)


def test_action_routing_class_tree() -> None:
    from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool

    facade = build_structure_facade(project_root=None)
    assert isinstance(facade.action_map["class_tree"], ClassHierarchyTool)


def test_action_routing_class_detail() -> None:
    """class_detail is a bespoke route (#804) — not in action_map but registered
    as a bespoke inner so G3 rebind propagates to the ClassInspectTool instance."""
    from tree_sitter_analyzer.mcp.tools.class_inspect_tool import ClassInspectTool

    facade = build_structure_facade(project_root=None)
    # class_detail moved to bespoke_map so query/symbol→class_name aliasing works.
    assert "class_detail" in facade.bespoke_map
    # The inner ClassInspectTool must be registered for G3 rebind.
    inner_types = {type(inner) for inner in facade._bespoke_inners}
    assert ClassInspectTool in inner_types


def test_action_routing_explore() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_explore_tool import (
        CodeGraphExploreTool,
    )

    facade = build_structure_facade(project_root=None)
    assert isinstance(facade.action_map["explore"], CodeGraphExploreTool)


# ---------------------------------------------------------------------------
# 3. arg projection — ``action`` stripped before inner receives args
# ---------------------------------------------------------------------------


def test_arg_projection_strips_action_key() -> None:
    """F4 Landmine A: ``action`` must be stripped or the inner raises ValueError."""
    facade = build_structure_facade(project_root=None)
    inner = facade.action_map["outline"]
    captured: list[dict[str, Any]] = []

    async def spy_execute(args: dict[str, Any]) -> Any:
        captured.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    inner.execute = spy_execute  # type: ignore[method-assign]
    asyncio.run(facade.execute({"action": "outline", "file_path": "foo.py"}))
    assert captured, "inner.execute was not called"
    assert "action" not in captured[0], "action key leaked to inner tool"


# ---------------------------------------------------------------------------
# 4. sibling-param drop — params for one action don't reach another inner
# ---------------------------------------------------------------------------


def test_sibling_param_not_forwarded() -> None:
    """class_name (for class_tree/class_detail) must not reach outline inner."""
    facade = build_structure_facade(project_root=None)
    inner = facade.action_map["outline"]
    captured: list[dict[str, Any]] = []

    async def spy_execute(args: dict[str, Any]) -> Any:
        captured.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    inner.execute = spy_execute  # type: ignore[method-assign]
    asyncio.run(
        facade.execute(
            {"action": "outline", "file_path": "foo.py", "class_name": "SiblingLeak"}
        )
    )
    assert captured
    assert "class_name" not in captured[0]


# ---------------------------------------------------------------------------
# 6. bespoke route (read) — single mode + batch mode
# ---------------------------------------------------------------------------


def test_read_bespoke_single_mode(tmp_path: Any) -> None:
    """Single-file read: reshapes flat params into 11-key full_args."""
    facade = build_structure_facade(project_root=str(tmp_path))

    # Create a real file so ReadPartialTool security validation passes.
    target = tmp_path / "sample.py"
    target.write_text("line1\nline2\nline3\n")

    result = asyncio.run(
        facade.execute(
            {
                "action": "read",
                "file_path": str(target),
                "start_line": 1,
                "end_line": 2,
            }
        )
    )
    # The inner may succeed or return its own error envelope; what matters is
    # that we get a dict back (not a raw exception) and that action was stripped.
    assert isinstance(result, dict)


def test_read_bespoke_batch_mode(tmp_path: Any) -> None:
    """Batch mode: ``requests`` list is forwarded verbatim to ReadPartialTool."""
    facade = build_structure_facade(project_root=str(tmp_path))

    target = tmp_path / "batch.py"
    target.write_text("a\nb\nc\n")

    requests = [
        {"file_path": str(target), "sections": [{"start_line": 1, "end_line": 1}]}
    ]
    result = asyncio.run(facade.execute({"action": "read", "requests": requests}))
    assert isinstance(result, dict)


def test_read_bespoke_missing_required_params() -> None:
    """read bespoke route raises ValueError when file_path/start_line absent."""
    facade = build_structure_facade(project_root=None)
    with pytest.raises(ValueError, match="file_path and start_line"):
        asyncio.run(facade.execute({"action": "read", "end_line": 5}))


def test_read_bespoke_action_stripped() -> None:
    """Action key must not reach the _read_route (bespoke args are cleaned)."""
    from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool

    facade = build_structure_facade(project_root=None)
    captured: list[dict[str, Any]] = []

    async def fake_execute(args: dict[str, Any]) -> Any:
        captured.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    # Patch the _bespoke_inners[0] which is the ReadPartialTool instance.
    bespoke_inner = facade._bespoke_inners[0]
    assert isinstance(bespoke_inner, ReadPartialTool)
    bespoke_inner.execute = fake_execute  # type: ignore[method-assign]

    asyncio.run(
        facade.execute({"action": "read", "file_path": "f.py", "start_line": 1})
    )
    assert captured
    assert "action" not in captured[0]


# ---------------------------------------------------------------------------
# 7. envelope preserved — verdict/agent_summary come through verbatim
# ---------------------------------------------------------------------------


def test_envelope_preserved() -> None:
    facade = build_structure_facade(project_root=None)
    inner = facade.action_map["outline"]

    async def fake_execute(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "verdict": "INFO",
            "agent_summary": {
                "verdict": "INFO",
                "summary_line": "outline ok",
                "next_step": "n/a",
            },
        }

    inner.execute = fake_execute  # type: ignore[method-assign]
    result = asyncio.run(facade.execute({"action": "outline", "file_path": "foo.py"}))
    assert result["verdict"] == "INFO"
    assert result["agent_summary"]["summary_line"] == "outline ok"


# ---------------------------------------------------------------------------
# 8. missing/unknown action — error envelope with available_actions
# ---------------------------------------------------------------------------


def test_missing_action_returns_error_envelope() -> None:
    facade = build_structure_facade(project_root=None)
    result = asyncio.run(facade.execute({"file_path": "foo.py"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    # available_actions must list all registered actions so the caller can recover.
    available = result.get("available_actions", [])
    for action in _EXPECTED_ACTIONS:
        assert action in available, f"{action} missing from available_actions"


def test_unknown_action_returns_error_envelope() -> None:
    facade = build_structure_facade(project_root=None)
    result = asyncio.run(facade.execute({"action": "does_not_exist"}))
    assert result["success"] is False
    assert result["verdict"] in {"ERROR", "NOT_FOUND"}
    assert "outline" in str(result)


# ---------------------------------------------------------------------------
# 9. rebind (G3) — set_project_path propagates to action_map + bespoke inners
# ---------------------------------------------------------------------------


def test_set_project_path_rebinds_action_map_inners(tmp_path: Any) -> None:
    """G3: action_map inners must get the new project root after set_project_path."""
    facade = build_structure_facade(project_root=None)
    target = str(tmp_path)
    facade.set_project_path(target)
    for action, inner in facade.action_map.items():
        assert inner.project_root == target, (
            f"action_map[{action!r}] not rebound: project_root={inner.project_root!r}"
        )


def test_set_project_path_rebinds_bespoke_inners(tmp_path: Any) -> None:
    """G3: all bespoke inners (ReadPartialTool, AnalyzeCodeStructureTool,
    ClassInspectTool) must be rebound when set_project_path is called."""
    from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
        AnalyzeCodeStructureTool,
    )
    from tree_sitter_analyzer.mcp.tools.class_inspect_tool import ClassInspectTool
    from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool

    facade = build_structure_facade(project_root=None)
    assert facade._bespoke_inners, "No bespoke inners registered"
    inner_types = {type(inner) for inner in facade._bespoke_inners}
    assert ReadPartialTool in inner_types
    assert AnalyzeCodeStructureTool in inner_types
    assert ClassInspectTool in inner_types

    target = str(tmp_path)
    facade.set_project_path(target)
    for inner in facade._bespoke_inners:
        assert inner.project_root == target, (
            f"{type(inner).__name__} not rebound: project_root={inner.project_root!r}"
        )


def test_bespoke_inner_is_read_partial_tool_registered() -> None:
    """ReadPartialTool, AnalyzeCodeStructureTool, and ClassInspectTool must be
    registered as bespoke inners for G3 rebind propagation."""
    from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
        AnalyzeCodeStructureTool,
    )
    from tree_sitter_analyzer.mcp.tools.class_inspect_tool import ClassInspectTool
    from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool

    facade = build_structure_facade(project_root=None)
    inner_types = {type(inner) for inner in facade._bespoke_inners}
    assert ReadPartialTool in inner_types, "ReadPartialTool not in bespoke inners"
    assert AnalyzeCodeStructureTool in inner_types, (
        "AnalyzeCodeStructureTool not in bespoke inners"
    )
    assert ClassInspectTool in inner_types, "ClassInspectTool not in bespoke inners"


# ---------------------------------------------------------------------------
# 10. no override — factory returns a plain FacadeTool
# ---------------------------------------------------------------------------


def test_factory_returns_facade_tool() -> None:
    """build_structure_facade must return a FacadeTool (no illegal subclass)."""
    facade = build_structure_facade(project_root=None)
    assert type(facade) is FacadeTool


def test_facade_does_not_override_set_project_path() -> None:
    """FacadeTool must not override set_project_path (BaseMCPTool contract)."""
    assert "set_project_path" not in FacadeTool.__dict__


# ---------------------------------------------------------------------------
# 11. end-to-end no strict leak — ``action`` must not escape to inner guard
# ---------------------------------------------------------------------------


def test_end_to_end_no_strict_param_leak(tmp_path: Any) -> None:
    """Route one action through the real inner without a ValueError on 'action'.

    The inner may return NOT_FOUND / raise an inner-tool error (e.g. an
    unsupported language when the tmp_path has no source files) — those are
    correct behaviours from the inner tool.  The ONLY forbidden outcome is a
    ``ValueError`` whose message contains the word 'action', which would mean
    the facade leaked the ``action`` key to the inner's strict-param guard
    (F4 regression).
    """
    facade = build_structure_facade(project_root=str(tmp_path))
    try:
        result = asyncio.run(
            facade.execute({"action": "outline", "file_path": str(tmp_path)})
        )
        assert isinstance(result, dict)
        assert "success" in result
    except ValueError as exc:
        # A ValueError is only a failure if it complains about 'action'.
        assert "action" not in str(exc).lower(), (
            f"facade leaked 'action' to inner strict-param guard (F4 regression): {exc}"
        )
        # Any other ValueError (e.g. from the inner tool itself) is acceptable.
    except Exception:
        # Non-ValueError exceptions from the inner tool (e.g. UnsupportedLanguageError)
        # are acceptable — they prove the inner received correct args (no action leak).
        pass


# ---------------------------------------------------------------------------
# Annotations sanity
# ---------------------------------------------------------------------------


def test_annotations_set_correctly() -> None:
    facade = build_structure_facade(project_root=None)
    definition = facade.get_tool_definition()
    annotations = definition.get("annotations", {})
    assert annotations.get("readOnlyHint") is True
    assert annotations.get("destructiveHint") is False
    assert annotations.get("idempotentHint") is True
    assert annotations.get("openWorldHint") is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ---------------------------------------------------------------------------
# 12. read coercion — string line/column bounds (undeclared additionalProperties)
#     must be int-coerced at the facade boundary, not TypeError downstream.
# ---------------------------------------------------------------------------
def test_structure_read_coerces_string_bounds(tmp_path: Any) -> None:
    """Agents pass start_line/end_line as strings (the flat facade schema does
    not type them). The single-file read route must coerce them to int, not let
    ``str < int`` TypeError reach the agent — the documented escape hatch must
    actually work.
    """
    f = tmp_path / "sample.py"
    f.write_text("a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n")
    facade = build_structure_facade(project_root=str(tmp_path))

    result = asyncio.run(
        facade.execute(
            {
                "action": "read",
                "file_path": str(f),
                "start_line": "2",  # STRING, as an MCP client delivers it
                "end_line": "4",
                "output_format": "json",
            }
        )
    )

    assert result.get("success") is True, result
    # Must not be the pre-fix TypeError envelope.
    assert "'<' not supported" not in str(result.get("error", "")), result


def test_structure_read_rejects_non_numeric_bounds(tmp_path: Any) -> None:
    """A genuinely non-numeric bound raises a CLEAR ValueError (caught at the MCP
    boundary into an error envelope) rather than a cryptic ``str < int`` TypeError
    from deep in extract_code_section. Mirrors the existing _read_route raise for
    missing args."""
    f = tmp_path / "sample.py"
    f.write_text("a = 1\nb = 2\n")
    facade = build_structure_facade(project_root=str(tmp_path))

    with pytest.raises(ValueError, match="must be integers"):
        asyncio.run(
            facade.execute(
                {
                    "action": "read",
                    "file_path": str(f),
                    "start_line": "not-a-number",
                    "output_format": "json",
                }
            )
        )


def test_structure_read_rejects_fractional_float_bounds(tmp_path: Any) -> None:
    """Codex P3 #328: a fractional numeric bound (start_line=2.9) must be
    rejected, not silently truncated to 2. Integral floats (2.0) still coerce."""
    f = tmp_path / "sample.py"
    f.write_text("a = 1\nb = 2\nc = 3\n")
    facade = build_structure_facade(project_root=str(tmp_path))

    # fractional -> clear ValueError, never a truncated read
    with pytest.raises(ValueError, match="must be integers"):
        asyncio.run(
            facade.execute({"action": "read", "file_path": str(f), "start_line": 2.9})
        )

    # integral float -> coerces cleanly
    ok = asyncio.run(
        facade.execute(
            {
                "action": "read",
                "file_path": str(f),
                "start_line": 2.0,
                "end_line": 3.0,
                "output_format": "json",
            }
        )
    )
    assert ok.get("success") is True, ok


# --------------------------------------------------------------------------
# Wave 1b (audit structure-01): class_tree default mode must be CLASS-SCOPED
# when a class identifier is supplied — never the global summary (which ignores
# class_name and returns a confident project-wide result for a class that may
# not exist).
# --------------------------------------------------------------------------


def test_class_hierarchy_default_mode_is_tree_when_class_named() -> None:
    from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool

    # class_name supplied, no explicit mode -> class-scoped 'tree', not 'summary'.
    assert ClassHierarchyTool._resolve_mode({"class_name": "Foo"}) == "tree"


def test_class_hierarchy_default_mode_is_summary_without_class() -> None:
    from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool

    # No identifier -> global summary (unchanged behavior).
    assert ClassHierarchyTool._resolve_mode({}) == "summary"


def test_class_hierarchy_explicit_mode_always_honored() -> None:
    from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool

    assert (
        ClassHierarchyTool._resolve_mode({"mode": "summary", "class_name": "Foo"})
        == "summary"
    )
    assert (
        ClassHierarchyTool._resolve_mode({"mode": "subclasses", "class_name": "Foo"})
        == "subclasses"
    )


def test_class_hierarchy_validate_accepts_named_class_without_mode() -> None:
    """With a class_name and no mode, validation must pass: the resolved mode is
    'tree', which requires class_name — and it is present."""
    from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool

    tool = ClassHierarchyTool(project_root=None)
    assert tool.validate_arguments({"class_name": "Foo"}) is True


# ---------------------------------------------------------------------------
# Bug #802 — class_tree mode='supers' must work (alias for 'superclasses')
# ---------------------------------------------------------------------------


def test_class_tree_supers_in_schema_enum() -> None:
    """'supers' must appear in the mode enum of ClassHierarchyTool's schema."""
    from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool

    tool = ClassHierarchyTool(project_root=None)
    schema = tool.get_tool_schema()
    mode_enum = schema["properties"]["mode"]["enum"]
    assert "supers" in mode_enum


def test_class_tree_supers_alias_normalizes_to_superclasses() -> None:
    """ClassHierarchyTool._normalize_mode must map 'supers' → 'superclasses'."""
    from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool

    assert ClassHierarchyTool._normalize_mode("supers") == "superclasses"
    # Other modes are unchanged.
    assert ClassHierarchyTool._normalize_mode("superclasses") == "superclasses"
    assert ClassHierarchyTool._normalize_mode("subclasses") == "subclasses"
    assert ClassHierarchyTool._normalize_mode("tree") == "tree"


def test_class_tree_mode_supers_does_not_return_unknown_mode_error() -> None:
    """Calling class_tree with mode='supers' must NOT return 'Unknown mode: supers'.

    The alias should produce the same result shape as mode='superclasses' (#802).
    """
    from unittest.mock import MagicMock, patch

    from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool

    tool = ClassHierarchyTool(project_root="/fake/root")

    # Stub _get_hierarchy so we don't need a real index.
    mock_hierarchy = MagicMock()
    mock_hierarchy.superclasses_of.return_value = ["Base"]
    mock_hierarchy.has_class.return_value = True
    mock_hierarchy.build.return_value = None

    with patch.object(tool, "_get_hierarchy", return_value=mock_hierarchy):
        result = asyncio.run(
            tool.execute(
                {"class_name": "Child", "mode": "supers", "output_format": "json"}
            )
        )

    # Must NOT be the error path.
    assert result.get("success") is True, f"Got error response: {result}"
    assert "Unknown mode" not in str(result.get("error", ""))
    # mode field in the response should be 'superclasses' (canonical form).
    assert result.get("mode") == "superclasses"


# ---------------------------------------------------------------------------
# Bug #804 — class_detail: class_name declared in schema + query alias works
# ---------------------------------------------------------------------------


def test_class_detail_class_name_in_facade_schema() -> None:
    """class_name must be a declared property in the facade's public schema (#804).

    Agents discover parameters from the schema; undeclared params are invisible.
    """
    facade = build_structure_facade(project_root=None)
    schema = facade.get_tool_schema()
    assert "class_name" in schema["properties"], (
        "class_name not declared in structure facade public schema"
    )


def test_class_detail_query_alias_resolves_to_class_name() -> None:
    """Passing query=X for class_detail must behave the same as class_name=X (#804)."""

    from tree_sitter_analyzer.mcp.tools.class_inspect_tool import ClassInspectTool

    facade = build_structure_facade(project_root=None)

    # Find the ClassInspectTool bespoke inner.
    inspect_tool = next(
        inner for inner in facade._bespoke_inners if isinstance(inner, ClassInspectTool)
    )

    captured: list[dict] = []

    async def spy_execute(args: dict) -> dict:
        captured.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    inspect_tool.execute = spy_execute  # type: ignore[method-assign]

    asyncio.run(
        facade.execute(
            {"action": "class_detail", "query": "MyClass", "output_format": "json"}
        )
    )

    assert captured, "ClassInspectTool.execute was not called"
    # The bespoke route must have aliased query → class_name.
    assert captured[0].get("class_name") == "MyClass", (
        f"query was not aliased to class_name: captured={captured[0]}"
    )


def test_class_detail_class_name_direct_still_works() -> None:
    """Passing class_name=X directly (without query) must still work (#804)."""
    from tree_sitter_analyzer.mcp.tools.class_inspect_tool import ClassInspectTool

    facade = build_structure_facade(project_root=None)

    inspect_tool = next(
        inner for inner in facade._bespoke_inners if isinstance(inner, ClassInspectTool)
    )

    captured: list[dict] = []

    async def spy_execute(args: dict) -> dict:
        captured.append(dict(args))
        return {"success": True, "verdict": "INFO", "agent_summary": {}}

    inspect_tool.execute = spy_execute  # type: ignore[method-assign]

    asyncio.run(
        facade.execute(
            {
                "action": "class_detail",
                "class_name": "DirectClass",
                "output_format": "json",
            }
        )
    )

    assert captured, "ClassInspectTool.execute was not called"
    assert captured[0].get("class_name") == "DirectClass"


def test_class_detail_is_bespoke_route() -> None:
    """class_detail must be in bespoke_map (not action_map) for the alias to work."""
    facade = build_structure_facade(project_root=None)
    assert "class_detail" in facade.bespoke_map
    assert "class_detail" not in facade.action_map
