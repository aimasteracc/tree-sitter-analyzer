"""Public schema metadata for the edit facade."""

from __future__ import annotations

from typing import Any

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
    "Returns SAFE/UNSAFE verdict. Params: file_path, edit_type, access_mode, "
    "snapshot_id, source_generation, output_format.\n"
    "- action=guard — blast-radius guard BEFORE touching a symbol: how many callers, "
    "what test coverage, what risk level. "
    "Params: symbol* (required), modification_type* (required), file_path.\n"
    "- action=impact — post-edit dependency blast-radius scan combining git diff + "
    "dependency graph: affected files, must-run tests, risk verdict (SAFE/REVIEW/WARN). "
    "Call after every non-trivial edit. Params: mode (diff|staged|branch|pr, "
    "default: diff), scope_paths, output_format, access_mode, "
    "capture_diff_snapshot (boolean; explicit opt-in, same-process POSIX "
    "producer only and forbidden with access_mode).\n"
    "- action=refactor — refactoring-opportunity analysis for a source file: extract "
    "candidates, complexity hotspots, skeleton. Params: file_path, language, "
    "max_suggestions, include_extractions, include_skeleton, output_format.\n"
    "- action=constraints — scan the project for constraint/rule violations. "
    "For RFC-0022 frozen read-only evaluation pass persist=false, "
    "diff_snapshot_id, and the impact-produced scope_paths. "
    "Params: severity_min, persist, diff_snapshot_id, scope_paths, access_mode, "
    "snapshot_id, source_generation, output_format.\n"
    "- action=pr — AI review of a PR diff via codegraph: structural issues, "
    "blast-radius, test-coverage gaps (codegraph_pr_review equivalent). "
    "Params: pr_url or diff (see inner schema).\n"
    "- action=classify — semantic change classification: classify a file's diff "
    "between git refs (file_path [+ old_ref/new_ref]) or two code strings "
    "(old_source + new_source + language). With only file_path, defaults to the "
    "file/git-ref mode. Params: file_path | old_source+new_source+language, "
    "access_mode, output_format.\n"
    "- action=ast_diff — structural AST diff between two snapshots/versions of "
    "a file: added/removed/changed nodes. Mode is inferred from args when omitted. "
    "Modes: diff_files (old_file + new_file), "
    "diff_strings (old_source + new_source + language), "
    "diff_git (old_ref + new_ref + file_path). "
    "Params: see inner schema; frozen consumption also accepts access_mode.\n"
    "- action=release_snapshot — idempotently release a process-local frozen diff. "
    "Params: diff_snapshot_id + route_lease_id.\n"
    "- action=plan_rename — the MINIMAL edit set for renaming a symbol project-wide "
    "(RFC-0027 §L8): every definition and reference site an AST-aware rename would "
    "touch, plus files_affected. PREVIEW ONLY — it never writes, and passing "
    "mode/dry_run/apply/write/force is REJECTED with PLAN_RENAME_IS_PREVIEW_ONLY "
    "rather than honoured. Params: symbol, new_name, output_format.\n"
    "- action=mutation_probe — on-demand query: does this test constrain this code? "
    "(RFC-0029). Applies one AST mutation at a source line in memory (never writes "
    "to disk), runs only the named test, and returns constrains/does_not_constrain/"
    "unknown. Fail-closed: unknown on any uncertainty; constrains only on "
    "AssertionError. Params: test_node_id* (required), source_path* (required), "
    "target_line* (required), timeout_seconds (default 60), output_format.\n"
    "NOTE: ``safe``/``impact``/``classify``/``constraints``/``pr``/``ast_diff``/"
    "``plan_rename``/``mutation_probe`` are "
    "read-only in practice; ``refactor``/``guard`` suggest changes but do not write "
    "files. readOnlyHint is False for the whole facade (mixed action set)."
)
