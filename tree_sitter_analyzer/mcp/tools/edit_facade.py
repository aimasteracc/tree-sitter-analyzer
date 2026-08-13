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
classify      ``semantic_classify``           Semantic change classification (file git-diff or code strings)
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

from .edit_facade_schema import _EDIT_ANNOTATIONS, _EDIT_DESCRIPTION
from .edit_facade_snapshot_routes import release_snapshot
from .facade_tool import FacadeTool


def build_edit_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``edit`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention in
    ``_tool_registry.py``).
    """

    from .ast_diff_tool import ASTDiffTool
    from .change_impact_tool import ChangeImpactTool
    from .codegraph_pr_review_tool import CodeGraphPRReviewTool
    from .modification_guard_tool import MODIFICATION_TYPES

    impact_tool = ChangeImpactTool(project_root)

    class _PRReviewViaFacade(CodeGraphPRReviewTool):
        """Facade ``action=pr`` implies ``mode=pr``.

        The inner tool's mode default is ``diff`` (for direct callers
        reviewing local changes); routed through the facade's pr action,
        an absent mode must mean PR review — otherwise ``edit action=pr``
        without pr_url silently falls into diff mode and returns an empty
        success (issue #451, Codex P1)."""

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            args = dict(arguments)
            args.setdefault("mode", "pr")
            return await super().execute(args)

    from .constraint_check_tool import ConstraintCheckTool
    from .modification_guard_tool import ModificationGuardTool
    from .refactoring_suggestions_tool import RefactoringSuggestionsTool
    from .safe_to_edit_tool import SafeToEditTool
    from .semantic_classify_tool import SemanticClassifyTool

    class _StrictEditFacade(FacadeTool):
        async def execute(self, arguments: dict[str, Any]) -> Any:
            action = arguments.get("action")
            if action == "release_snapshot":
                allowed = {
                    "action",
                    "diff_snapshot_id",
                    "route_lease_id",
                    "output_format",
                }
                if set(arguments) - allowed:
                    raise ValueError("DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS")
            if action in ("classify", "ast_diff") and arguments.get("diff_snapshot_id"):
                allowed = {
                    "action",
                    "diff_snapshot_id",
                    "file_path",
                    "language",
                    "include_node_bodies",
                    "include_ast_nodes",
                    "hunk_cap",
                    "output_format",
                }
                if set(arguments) - allowed:
                    raise ValueError("DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS")
            return await super().execute(arguments)

    facade = _StrictEditFacade(
        facade_name="edit",
        action_map={
            "safe": SafeToEditTool(project_root),
            "guard": ModificationGuardTool(project_root),
            "impact": impact_tool,
            "refactor": RefactoringSuggestionsTool(project_root),
            "constraints": ConstraintCheckTool(project_root),
            "pr": _PRReviewViaFacade(project_root),
            "classify": SemanticClassifyTool(project_root),
            "ast_diff": ASTDiffTool(project_root),
        },
        bespoke_map={"release_snapshot": release_snapshot},
        description=_EDIT_DESCRIPTION,
        annotations=_EDIT_ANNOTATIONS,
        project_root=project_root,
        # #641: modification_type is required for action=guard but was only
        # reachable via additionalProperties — invisible to schema-reading
        # agents. Surface it with the authoritative enum from the inner tool
        # so facade/inner never drift. Never added to required[] (runtime-
        # resolved param convention, locked #397 family).
        action_scoped_params={
            "persist": frozenset({"constraints"}),
            "scope_paths": frozenset({"impact", "constraints"}),
        },
        extra_public_params={
            "capture_diff_snapshot": {
                "type": "boolean",
                "description": (
                    "Explicitly produce a frozen diff ID for same-process consumers; "
                    "supported only on POSIX."
                ),
            },
            "diff_snapshot_id": {
                "type": "string",
                "description": (
                    "RFC-0022 frozen diff ID for constraints/classify/ast_diff/"
                    "release_snapshot."
                ),
            },
            "persist": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Write evaluated violations through to the cache. Set false for "
                    "RFC-0022 read-only evaluation; no database or file is created."
                ),
            },
            "scope_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Primitive-issued frozen scope for action=constraints, or impact "
                    "capture scope for action=impact."
                ),
            },
            "route_lease_id": {
                "type": "string",
                "description": "Ownership token required by action=release_snapshot.",
            },
            "modification_type": {
                "type": "string",
                "enum": list(MODIFICATION_TYPES),
                "description": (
                    "Required for action=guard: type of planned modification. "
                    "One of: " + ", ".join(MODIFICATION_TYPES) + "."
                ),
            },
        },
    )
    # No bespoke inners to register (G3 rebind is automatic for action_map).
    return facade
