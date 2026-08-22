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
plan_rename      ``codegraph_refactor``       Minimal rename edit set, PREVIEW ONLY
mutation_probe   ``MutationProbeTool``        Does this test constrain this code? (RFC-0029)
============  ==============================  ================================

RFC-0027 §L8: ``plan_rename`` wires the previously unreachable
``CodeGraphRefactorTool`` — a true minimal rename edit set with 15 passing
tests and no surface. The inner tool supports **both** preview and apply. A
surface named for *planning* must not be able to write, so the binding pins
``mode="preview"`` internally and **rejects** every apply-like argument
(:data:`_APPLY_LIKE_PARAMS`) with the stable error
``PLAN_RENAME_IS_PREVIEW_ONLY`` rather than forwarding it. The mode is not a
caller-supplied parameter at this surface at all — even ``mode="preview"`` is
rejected, because accepting it would advertise a parameter that is honoured and
invite ``mode="apply"`` next. Applying a rename is deliberately NOT exposed
here; that stays off the registered surface until a write-intent route exists.

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

#: Arguments that would (or would appear to) turn ``plan_rename`` into a write.
#: ``mode`` is the live hole: the inner tool declares it, so the facade's
#: schema projection would forward ``mode="apply"`` straight through.
_APPLY_LIKE_PARAMS: frozenset[str] = frozenset(
    {"mode", "dry_run", "apply", "write", "force"}
)

#: The inner tool's hint advertises a route this surface does not expose.
_APPLY_HINT = "Use mode=apply to execute."
_PREVIEW_HINT = "plan_rename never writes; apply is not exposed on this surface."


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

    from .codegraph_refactor_tool import CodeGraphRefactorTool

    class _PlanRenameViaFacade(CodeGraphRefactorTool):
        """Facade ``action=plan_rename`` pins ``mode="preview"``.

        Two independent guards, because one is a policy and the other is a
        property:

        * the facade **rejects** every apply-like argument before dispatch (see
          ``_StrictEditFacade``), so nothing reaches here to honour; and
        * ``FORCED_MODE`` makes the inner ignore ``mode`` entirely, so even a
          future refactor that loosens the facade guard cannot make this route
          write.
        """

        FORCED_MODE = "preview"

        def get_tool_schema(self) -> dict[str, Any]:
            """Drop ``mode`` from the advertised schema.

            The inner tool declares ``mode: preview|apply``. Leaving it in the
            schema would document a parameter this route rejects — and the
            generated ``docs/api/facade-actions.md`` reads exactly this schema,
            so the lie would ship into the reference an agent consults.
            """
            schema = super().get_tool_schema()
            properties = {
                key: value
                for key, value in schema.get("properties", {}).items()
                if key not in _APPLY_LIKE_PARAMS
            }
            return {**schema, "properties": properties}

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            result = await super().execute(dict(arguments))
            # The inner tool's own hint ends "Use mode=apply to execute." — a
            # next_step naming a route that does not exist on this surface
            # (RFC-0028 §3.1 item 2). Rewrite it on BOTH the JSON key and the
            # TOON body, or the two surfaces disagree about what is callable.
            for key in ("hint", "toon_content"):
                value = result.get(key)
                if isinstance(value, str) and _APPLY_HINT in value:
                    result[key] = value.replace(_APPLY_HINT, _PREVIEW_HINT)
            return result

    from .constraint_check_tool import ConstraintCheckTool
    from .modification_guard_tool import ModificationGuardTool
    from .mutation_probe_tool import MutationProbeTool
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
            if action == "plan_rename":
                # RFC-0027 §L8: reject, never forward. The mode is not a
                # caller-supplied parameter at this surface.
                smuggled = _APPLY_LIKE_PARAMS & set(arguments)
                if smuggled:
                    raise ValueError(
                        "PLAN_RENAME_IS_PREVIEW_ONLY: "
                        f"{sorted(smuggled)} not accepted; plan_rename never "
                        "writes. Apply is not exposed on this surface."
                    )
            if action in ("classify", "ast_diff") and arguments.get("diff_snapshot_id"):
                allowed = {
                    "action",
                    "access_mode",
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
            # RFC-0027 §L8: minimal rename edit set, preview-only.
            "plan_rename": _PlanRenameViaFacade(project_root),
            # RFC-0029: mutation probe — does this test constrain this code?
            "mutation_probe": MutationProbeTool(project_root),
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
            "access_mode": frozenset(
                {"safe", "impact", "constraints", "classify", "ast_diff"}
            ),
            "capture_diff_snapshot": frozenset({"impact"}),
            "diff_snapshot_id": frozenset(
                {"constraints", "classify", "ast_diff", "release_snapshot"}
            ),
            "persist": frozenset({"constraints"}),
            "route_lease_id": frozenset({"release_snapshot"}),
            "scope_paths": frozenset({"impact", "constraints"}),
            "snapshot_id": frozenset({"safe", "constraints"}),
            "source_generation": frozenset({"safe", "constraints"}),
        },
        extra_public_params={
            "access_mode": {
                "type": "string",
                "enum": ["read_existing"],
                "description": (
                    "Explicit P0.4 zero-write access mode for routed read adapters."
                ),
            },
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
            "snapshot_id": {
                "type": "string",
                "description": "Certified P0.1 index snapshot capability ID.",
            },
            "source_generation": {
                "type": "string",
                "description": "Certified P0.1/P0.2 source generation.",
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
