#!/usr/bin/env python3
"""``edit`` facade — Wave B facade for edit/safety/impact capabilities.

Folds eight code-safety and change-management capabilities behind one
``action`` parameter:

============  ==============================  ================================
action        inner tool                      when to use
============  ==============================  ================================
safe          ``safe_to_edit``                Pre-edit safety gate (SAFE/UNSAFE)
guard         ``modification_guard``          Blast-radius guard before touching a symbol
impact        ``analyze_change_impact``       Post-edit dependency blast-radius scan
refactor      ``refactoring_suggestions``     Refactoring opportunities for a file
constraints   ``check_constraints``           Constraint violations in the project
pr            ``codegraph_pr_review``         AI review of a PR diff via CodeGraph
classify      ``semantic_classify``           Semantic classification of a symbol/file
ast_diff      ``ast_diff``                    Structural diff of two AST snapshots
============  ==============================  ================================

Annotation honesty (spec §6 / review §8 F-extra-3):
    This facade spans READ-ONLY actions (``safe``, ``impact``, ``classify``,
    ``constraints``, ``pr``, ``ast_diff``) and MUTATING-INTENT actions
    (``refactor`` suggests changes; ``guard`` checks before a write). A single
    honest ``readOnlyHint=True`` is IMPOSSIBLE for this facade — doing so would
    violate the ``test_every_tool_declares_mcp_annotations`` contract which
    forbids ``readOnly AND destructive``. We therefore set
    ``readOnlyHint=False, destructiveHint=False`` (it suggests / analyses,
    does not actually write files), ``idempotentHint=False`` (analysis results
    may differ as the index updates), ``openWorldHint=False``. Read actions lose
    the read-safe signal — accepted tradeoff per PRD §4. If a strict read-only
    sub-facade is later needed, split ``safe``/``impact``/``classify`` into a
    separate read-only facade (out of scope for Wave B).

Not registered in ``_tool_registry.py`` at P0; Wave C handles cutover.
"""

from __future__ import annotations

from typing import Any

from .facade_tool import FacadeTool

# Annotation honesty — see module docstring above.
# readOnlyHint=False because the facade includes mutating-intent actions
# (refactor/guard). We cannot claim read-only across a mixed action set.
_EDIT_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": False,
    "destructiveHint": False,  # suggests / analyses; never writes files
    "idempotentHint": False,  # analysis results can change as index updates
    "openWorldHint": False,
}

_EDIT_DESCRIPTION = (
    "Code-intelligence (codegraph-compatible) safety and change-management facade. "
    "Covers codegraph_pr_review (PR analysis via codegraph), safe-to-edit gates, "
    "blast-radius guards, change impact scanning, refactoring suggestions, "
    "constraint checks, semantic classification, and AST diff in one tool. "
    "Pick a capability via `action`:\n"
    "- action=safe — pre-edit safety gate: is this file safe to edit right now? "
    "Returns SAFE/UNSAFE verdict. Params: file_path, edit_type, output_format.\n"
    "- action=guard — blast-radius guard BEFORE touching a symbol: how many callers, "
    "what test coverage, what risk level. Params: symbol, modification_type, file_path.\n"
    "- action=impact — post-edit dependency blast-radius scan combining git diff + "
    "dependency graph: affected files, must-run tests, risk verdict (SAFE/REVIEW/WARN). "
    "Call after every non-trivial edit. Params: scope_paths, output_format.\n"
    "- action=refactor — refactoring-opportunity analysis for a source file: extract "
    "candidates, complexity hotspots, skeleton. Params: file_path, language, "
    "max_suggestions, include_extractions, include_skeleton, output_format.\n"
    "- action=constraints — scan the project for constraint/rule violations "
    "(architecture, naming, coupling). Params: severity_min, output_format.\n"
    "- action=pr — AI review of a PR diff via codegraph: structural issues, "
    "blast-radius, test-coverage gaps (codegraph_pr_review equivalent). "
    "Params: pr_url or diff (see inner schema).\n"
    "- action=classify — semantic classification of a symbol or file: domain, "
    "layer, responsibility. Params: file_path or symbol, output_format.\n"
    "- action=ast_diff — structural AST diff between two snapshots/versions of "
    "a file: added/removed/changed nodes. Params: file_path, before, after or "
    "git ref params (see inner schema).\n"
    "NOTE: ``safe``/``impact``/``classify``/``constraints``/``pr``/``ast_diff`` are "
    "read-only in practice; ``refactor``/``guard`` suggest changes but do not write "
    "files. readOnlyHint is False for the whole facade (mixed action set)."
)


def build_edit_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``edit`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention in
    ``_tool_registry.py``).
    """
    from .ast_diff_tool import ASTDiffTool
    from .change_impact_tool import ChangeImpactTool
    from .codegraph_pr_review_tool import CodeGraphPRReviewTool
    from .constraint_check_tool import ConstraintCheckTool
    from .modification_guard_tool import ModificationGuardTool
    from .refactoring_suggestions_tool import RefactoringSuggestionsTool
    from .safe_to_edit_tool import SafeToEditTool
    from .semantic_classify_tool import SemanticClassifyTool

    facade = FacadeTool(
        facade_name="edit",
        action_map={
            "safe": SafeToEditTool(project_root),
            "guard": ModificationGuardTool(project_root),
            "impact": ChangeImpactTool(project_root),
            "refactor": RefactoringSuggestionsTool(project_root),
            "constraints": ConstraintCheckTool(project_root),
            "pr": CodeGraphPRReviewTool(project_root),
            "classify": SemanticClassifyTool(project_root),
            "ast_diff": ASTDiffTool(project_root),
        },
        # No bespoke routes: all eight inners follow the normal action_map
        # pattern (dict return, schema-projectable args, no union return type).
        bespoke_map={},
        description=_EDIT_DESCRIPTION,
        annotations=_EDIT_ANNOTATIONS,
        project_root=project_root,
    )
    # No bespoke inners to register (G3 rebind is automatic for action_map).
    return facade
