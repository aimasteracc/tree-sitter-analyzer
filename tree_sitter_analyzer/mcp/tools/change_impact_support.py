#!/usr/bin/env python3
"""
Change-impact schemas and response helpers.

Combines git diff with dependency graph to provide change impact analysis.
Tells AI agents: what changed, what's affected, what tests to run.

Supports GitHub PR URL analysis: pass pr_url to fetch diff via gh CLI.
"""

from pathlib import Path
from typing import Any

from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import _canonicalize_verdict, mirror_summary_line
from .utils.change_impact_response import (
    apply_scope_validation,
    attach_queue_ledger,
    build_agent_summary_only_response,
)


def _canonicalize_change_impact_verdict(result: dict[str, Any]) -> None:
    """Fold both verdict surfaces back to the shared legal vocabulary.

    F1 (round-37f7): the change-impact response builder previously
    stamped ``verdict="CLEAN"`` for the no-changes path — a token
    outside :data:`base_tool._LEGAL_VERDICTS`.
    ``CHANGE_IMPACT_VERDICT_CLEAN`` now stores the canonical
    ``"SAFE"``, but we also apply :func:`_canonicalize_verdict` at the
    tool boundary as a belt-and-braces measure: any future helper
    that re-introduces ``"CLEAN"`` (or any other drift value) gets
    normalised here before it leaves the tool.

    Mutates in place — the tool's flow uses the same dict reference
    across the queue-ledger / scope-validation / mirror pipeline, so
    returning a new dict here would silently drop subsequent
    updates.
    """
    agent_summary = result.get("agent_summary")
    if isinstance(agent_summary, dict):
        nested = agent_summary.get("verdict")
        if isinstance(nested, str) or nested is None:
            agent_summary["verdict"] = _canonicalize_verdict(nested)
    top = result.get("verdict")
    if isinstance(top, str):
        # Only stamp the top-level when there's already something
        # there (so we don't manufacture a verdict the response
        # builder didn't set). The no-changes path leaves the
        # top-level blank; the ``mirror_summary_line`` helper will
        # copy from ``agent_summary``.
        result["verdict"] = _canonicalize_verdict(top)


_JOURNAL_VERDICT_RANK: dict[str, int] = {
    "SAFE": 0,
    "INFO": 0,
    "NOT_FOUND": 0,
    "CAUTION": 1,
    "REVIEW": 2,
    "WARN": 3,
    "ERROR": 4,
    "UNSAFE": 5,
}


def _enrich_with_journal_decisions(
    result: dict[str, Any],
    project_root: str | None,
    changed_files: list[str],
) -> None:
    """Phase 3 (r37fG): surface related decision_journal entries.

    For every file in ``changed_files``, search the project's decision
    journal for entries whose ``scope_paths`` covers that file. Attach
    matches to ``result["related_decisions"]`` and — if any matched
    verdict is more severe than the current change_impact verdict —
    upgrade the envelope verdict so the calling agent cannot silently
    bypass a recorded REVIEW / UNSAFE / WARN decision.

    Mutates ``result`` in place. Never downgrades. Never raises — a
    journal-side failure must not block change_impact's primary output.
    """
    if not project_root or not changed_files:
        return
    try:
        from ...decision_journal import DecisionJournal

        journal = DecisionJournal(project_root)
        matches: dict[str, dict[str, Any]] = {}
        for fp in changed_files[:32]:
            for rec in journal.search(path_scope=fp, limit=10):
                matches[rec.id] = rec.to_dict()
        if not matches:
            return
        related = list(matches.values())
        result["related_decisions"] = related
        strongest = max(
            (_JOURNAL_VERDICT_RANK.get(d.get("verdict", ""), 0) for d in related),
            default=0,
        )
        if strongest <= 0:
            return
        strongest_label = next(
            lbl for lbl, rank in _JOURNAL_VERDICT_RANK.items() if rank == strongest
        )
        agent_summary = result.get("agent_summary")
        current_verdict = (
            agent_summary.get("verdict") if isinstance(agent_summary, dict) else None
        )
        current_rank = _JOURNAL_VERDICT_RANK.get(current_verdict or "", 0)
        if strongest <= current_rank:
            return
        if isinstance(agent_summary, dict):
            agent_summary["verdict"] = strongest_label
            existing_next = agent_summary.get("next_step") or ""
            agent_summary["next_step"] = (
                f"⚠ {len(related)} recorded decision(s) match the changed "
                f"files — strongest verdict={strongest_label}. Surface "
                "related_decisions verbatim; do NOT reframe. " + str(existing_next)
            ).strip()
        result["verdict"] = strongest_label
    except Exception:
        return


def _resolve_scope_path(project_root: str | None, raw: str) -> Path:
    """Resolve a user-supplied scope path against the project root.

    Absolute paths are kept as-is; relative paths are interpreted relative
    to ``project_root`` so the existence check matches what git diff
    consumes downstream. When ``project_root`` is ``None`` we fall back
    to the current working directory — git diff would do the same.
    """
    p = Path(raw)
    if p.is_absolute():
        return p
    base = Path(project_root) if project_root else Path.cwd()
    return base / p


def _scope_paths_invalid(project_root: str | None, scope_paths: list[str]) -> list[str]:
    """Return the subset of ``scope_paths`` that do not exist on disk.

    Empty input → empty list. Pure helper so it can be unit-tested in
    isolation.
    """
    return [
        raw
        for raw in scope_paths
        if not _resolve_scope_path(project_root, raw).exists()
    ]


TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["diff", "staged", "branch", "pr"],
            "default": "diff",
            "description": "diff=unstaged, staged=staged, branch=vs main, pr=from GitHub PR URL",
        },
        "pr_url": {
            "type": "string",
            "default": "",
            "description": "GitHub PR URL (e.g. https://github.com/owner/repo/pull/123). Overrides local diff modes.",
        },
        "include_tests": {
            "type": "boolean",
            "default": True,
            "description": "Find related test files",
        },
        "scope_paths": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
            "description": (
                "Optional scopes limiting diff, impact, and test mapping to the "
                "current queue scope. Frozen snapshot Phase 0 accepts literal "
                "repository-relative paths only; leading-colon Git magic "
                "pathspecs return DIFF_SNAPSHOT_UNSUPPORTED_SCOPE."
            ),
        },
        "scope_mode": {
            "type": "string",
            "enum": ["report", "strict"],
            "default": "report",
            "description": (
                "How out-of-scope dirty files (relative to scope_paths) are "
                "surfaced. report=list them in the queue ledger preview "
                "(default); strict=fully mute the list so a large dirty "
                "worktree cannot bury the scoped result (an honest count is "
                "still kept). No effect without scope_paths."
            ),
        },
        "resource_profile": {
            "type": "string",
            "enum": ["default", "local_low_impact"],
            "default": "local_low_impact",
            "description": (
                "Verification command resource profile. "
                "local_low_impact (MCP default): emits nice/xdist-capped local pytest "
                "commands plus a ci_verification_command for CI or queue boundaries — "
                "safe for AI-agent sessions where aggressive parallelism stalls the machine. "
                "default: preserves the original broad verification command unchanged."
            ),
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
        "agent_summary_only": {
            "type": "boolean",
            "default": False,
            "description": "Return only the compact agent decision surface instead of full impact details",
        },
        "capture_diff_snapshot": {
            "type": "boolean",
            "default": False,
            "description": (
                "RFC-0022 P0.2: atomically freeze workspace/staged patch and bytes. "
                "Explicit opt-in and POSIX-only; Windows fails closed with "
                "DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED. Legacy staged change-impact "
                "without capture remains Windows-supported."
            ),
        },
        "compact_only": {
            "type": "boolean",
            "default": False,
            "description": (
                "RFC-0012: with output_format=toon, return only the control "
                "surface alongside toon_content, dropping metadata already "
                "encoded in the blob."
            ),
        },
    },
    "additionalProperties": False,
}


def _pr_invalid_url_envelope(pr_url: str, output_format: str) -> dict[str, Any]:
    """Pre-flight failure envelope when ``pr_url`` cannot be parsed.

    r37em (dogfood): lifted from ``_execute_pr_analysis`` to keep the
    main body focused on the happy path.
    """
    return apply_toon_format_to_response(
        {
            "success": False,
            "error": f"Invalid GitHub PR URL: {pr_url}",
            "hint": "Expected format: https://github.com/owner/repo/pull/123",
            "output_format": output_format,
        },
        output_format,
    )


def _pr_gh_unavailable_envelope(parsed: Any, output_format: str) -> dict[str, Any]:
    """Pre-flight failure envelope when ``gh`` CLI is missing or unauthenticated."""
    return apply_toon_format_to_response(
        {
            "success": False,
            "error": "gh CLI not available or not authenticated",
            "hint": "Install gh CLI and run 'gh auth login'",
            "pr_url": parsed.url,
            "output_format": output_format,
        },
        output_format,
    )


def _snapshot_records(frozen: dict[str, object] | None) -> list[dict[str, object]]:
    """Return only structurally valid frozen changed records."""
    if frozen is None:
        return []
    raw = frozen.get("changed_records", [])
    if not isinstance(raw, list):
        return []
    return [record for record in raw if isinstance(record, dict)]


def _finalize_pr_result(
    result: dict[str, Any],
    *,
    parsed: Any,
    scope_paths: list[str],
    scope_paths_invalid: Any,
    changed_files: list[str],
    agent_summary_only: bool,
    output_format: str,
    scope_mode: str = "report",
    compact_only: bool = False,
) -> dict[str, Any]:
    """Attach shared PR metadata, queue/scope controls, summary, and format."""
    result["pr_url"] = parsed.url
    result["pr_number"] = parsed.pr_number
    result["repo"] = parsed.slug
    result = attach_queue_ledger(
        result,
        mode="pr",
        scope_paths=scope_paths,
        scoped_changed_files=changed_files,
        workspace_changed_files=changed_files,
        scope_mode=scope_mode,
    )
    result = apply_scope_validation(result, scope_paths_invalid)
    if agent_summary_only:
        result = build_agent_summary_only_response(result)
    result["output_format"] = output_format
    _canonicalize_change_impact_verdict(result)
    result = mirror_summary_line(result)
    return apply_toon_format_to_response(
        result, output_format, compact_only=compact_only
    )
