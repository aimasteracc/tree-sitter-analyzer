#!/usr/bin/env python3
"""编辑 facade：通过九个 action 提供安全检查、影响分析及重命名。

refactor 只给出建议；rename 支持 Python 模块级函数、类与直接导入的安全重命名，
apply 模式会写入文件。因此整个 facade 必须标记 destructiveHint=True，
readOnlyHint=False；其他只读 action 保持原有行为。
"""

from __future__ import annotations

from typing import Any

from .facade_tool import FacadeTool

# Annotation honesty — see module docstring above.
# readOnlyHint=False because the facade includes mutating-intent actions
# (refactor/guard). We cannot claim read-only across a mixed action set.
_EDIT_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": False,
    # action=rename with mode=apply rewrites source files in place — the facade
    # must advertise that so MCP clients can prompt before invoking it.
    "destructiveHint": True,
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
    "what test coverage, what risk level. "
    "Params: symbol* (required), modification_type* (required), file_path.\n"
    "- action=impact — post-edit dependency blast-radius scan combining git diff + "
    "dependency graph: affected files, must-run tests, risk verdict (SAFE/REVIEW/WARN). "
    "Call after every non-trivial edit. Params: mode (diff|staged|branch|pr, "
    "default: diff), scope_paths, output_format.\n"
    "- action=refactor — READ-ONLY refactoring-opportunity analysis for a source "
    "file: extract candidates, complexity hotspots, skeleton. Suggests only; "
    "never writes. Params: file_path, language, "
    "max_suggestions, include_extractions, include_skeleton, output_format.\n"
    "- action=rename — rename a unique Python module-level function or class and "
    "its direct absolute from-import references, including aliases. Uses fresh "
    "AST identifier locations; preserves literals, comments, encoding and newlines. "
    "Ambiguous bindings, affected unsupported languages and dynamic references "
    "are rejected before writing. Params: symbol* (unqualified name), new_name*, "
    "mode (preview|apply, default: preview), output_format. "
    "mode=preview lists exact changes without writing; mode=apply WRITES files. "
    "This differs from action=refactor, which only suggests changes.\n"
    "- action=constraints — scan the project for constraint/rule violations "
    "(architecture, naming, coupling). Params: severity_min, output_format.\n"
    "- action=pr — AI review of a PR diff via codegraph: structural issues, "
    "blast-radius, test-coverage gaps (codegraph_pr_review equivalent). "
    "Params: pr_url or diff (see inner schema).\n"
    "- action=classify — semantic change classification: classify a file's diff "
    "between git refs (file_path [+ old_ref/new_ref]) or two code strings "
    "(old_source + new_source + language). With only file_path, defaults to the "
    "file/git-ref mode. Params: file_path | old_source+new_source+language, "
    "output_format.\n"
    "- action=ast_diff — structural AST diff between two snapshots/versions of "
    "a file: added/removed/changed nodes. Mode is inferred from args when omitted. "
    "Modes: diff_files (old_file + new_file), "
    "diff_strings (old_source + new_source + language), "
    "diff_git (old_ref + new_ref + file_path). "
    "Params: see inner schema.\n"
    "NOTE: ``safe``/``impact``/``classify``/``constraints``/``pr``/``ast_diff`` are "
    "read-only in practice; ``refactor``/``guard`` suggest changes but do not write "
    "files; ``rename`` with mode=apply DOES write files. readOnlyHint is False and "
    "destructiveHint is True for the whole facade (mixed action set)."
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
    from .modification_guard_tool import MODIFICATION_TYPES

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
            # Wiring fix: CodeGraphRefactorTool was implemented but never
            # registered, so project-wide AST rename was unreachable. It gets
            # its own action (``rename``) — it must NOT shadow ``refactor``,
            # which is the read-only suggestions tool.
            "rename": CodeGraphRefactorTool(project_root),
            "constraints": ConstraintCheckTool(project_root),
            "pr": _PRReviewViaFacade(project_root),
            "classify": SemanticClassifyTool(project_root),
            "ast_diff": ASTDiffTool(project_root),
        },
        # No bespoke routes: all nine inners follow the normal action_map
        # pattern (dict return, schema-projectable args, no union return type).
        bespoke_map={},
        description=_EDIT_DESCRIPTION,
        annotations=_EDIT_ANNOTATIONS,
        project_root=project_root,
        # #641: modification_type is required for action=guard but was only
        # reachable via additionalProperties — invisible to schema-reading
        # agents. Surface it with the authoritative enum from the inner tool
        # so facade/inner never drift. Never added to required[] (runtime-
        # resolved param convention, locked #397 family).
        extra_public_params={
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
