#!/usr/bin/env python3
"""
Change Impact Analysis MCP Tool.

Combines git diff with dependency graph to provide change impact analysis.
Tells AI agents: what changed, what's affected, what tests to run.

Supports GitHub PR URL analysis: pass pr_url to fetch diff via gh CLI.
"""

from pathlib import Path
from typing import Any

from ...pr_url import (
    check_gh_available,
    fetch_pr_changed_files,
    fetch_pr_diff_stat,
    parse_pr_url,
)
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool, _canonicalize_verdict, mirror_summary_line
from .utils.change_impact_analysis import (
    ChangeImpactRequest,
    _build_change_impact_result,
)
from .utils.change_impact_git import (
    _get_changed_files,
    _get_diff_stat,
)
from .utils.change_impact_response import (
    apply_scope_validation,
    attach_queue_ledger,
    build_agent_summary_only_response,
    build_no_changes_result,
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
            (lbl for lbl, rank in _JOURNAL_VERDICT_RANK.items() if rank == strongest),
            None,
        )
        if strongest_label is None:
            return
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
            "description": "Optional pathspecs limiting diff, impact, and test mapping to the current queue scope",
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


class ChangeImpactTool(BaseMCPTool):
    """Analyze the impact of code changes using git diff + dependency graph."""

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return TOOL_SCHEMA

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "analyze_change_impact",
            "description": (
                "Post-edit blast-radius scan: combines ``git diff`` (staged "
                "+ unstaged) with the project dependency graph to compute "
                "which files are affected, which test files must re-run, "
                "and a risk verdict (SAFE / REVIEW / WARN). Optionally "
                "accepts ``scope_paths`` to restrict the analysis to a "
                "subset of the diff. MUST be called after every non-trivial "
                "edit before declaring work done — the built-in tools have "
                "no view of dependency edges or test coverage.\n\n"
                "WHEN TO USE:\n"
                "- After ANY non-trivial edit before declaring 'done'\n"
                "- To pick which tests are worth running (vs the full suite)\n"
                "- To detect changes to high-fan-in files needing extra review\n"
                "- For PR risk summaries (diff against base branch)\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- Before editing — use safe_to_edit instead\n"
                "- For symbol-level rename — use modification_guard\n"
                "- To see WHO calls a symbol — use trace_impact\n"
                "\n"
                "VERDICT INTEGRITY: agent_summary.verdict is the blast-radius gate, "
                "not a tone signal. It is computed from the actual changed-file set, "
                "dependency edges, and impacted test count — not from the user's "
                "framing. If the user says 'just ship it' or 'is this safe to merge?' "
                "and this tool returns REVIEW / WARN / UNSAFE / ERROR, the calling "
                "agent MUST report that verdict verbatim and surface the impacted "
                "files. Do NOT rewrite a REVIEW/WARN as SAFE/INFO to keep the user "
                "moving. Legal vocabulary: SAFE / CAUTION / REVIEW / UNSAFE / INFO / "
                "WARN / ERROR / NOT_FOUND."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate mode argument."""
        if "mode" in arguments and arguments["mode"] not in (
            "diff",
            "staged",
            "branch",
            "pr",
        ):
            raise ValueError("mode must be diff|staged|branch|pr")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Analyze git diff + dependency graph for change impact."""
        pr_url = arguments.get("pr_url", "") or ""
        mode = "pr" if pr_url else arguments.get("mode", "diff")
        include_tests = arguments.get("include_tests", True)
        output_format = arguments.get("output_format", "toon")
        scope_paths = arguments.get("scope_paths") or []
        agent_summary_only = bool(arguments.get("agent_summary_only", False))

        # H8: validate scope paths against disk so a typo cannot silently
        # become "scope matched nothing". The analysis still runs on the
        # remaining valid scope (if any) — we only mark the invalid ones.
        scope_paths_invalid = _scope_paths_invalid(self.project_root, scope_paths)

        if mode == "pr" and pr_url:
            return self._execute_pr_analysis(
                pr_url, include_tests, output_format, scope_paths, agent_summary_only
            )

        changed_files = _get_changed_files(mode, self.project_root, scope_paths)
        workspace_changed_files = (
            _get_changed_files(mode, self.project_root, []) if scope_paths else []
        )

        if not changed_files:
            result = build_no_changes_result(mode, scope_paths)
            result["scope_paths"] = scope_paths
            result["scope_filtered"] = bool(scope_paths)
            result = attach_queue_ledger(
                result,
                mode=mode,
                scope_paths=scope_paths,
                scoped_changed_files=changed_files,
                workspace_changed_files=workspace_changed_files,
            )
            result = apply_scope_validation(result, scope_paths_invalid)
            if agent_summary_only:
                result = build_agent_summary_only_response(result)
            result["output_format"] = output_format
            # F1 (round-37f7): defensive verdict canonicalization in
            # the no-changes path. ``apply_scope_validation`` already
            # stamps ``CHANGE_IMPACT_VERDICT_CLEAN`` (now ``"SAFE"``)
            # but a legacy import path or future helper could
            # re-introduce the old ``"CLEAN"`` literal — fold any
            # drift back to the canonical vocabulary so the no-changes
            # envelope can never ship a non-canonical verdict.
            _canonicalize_change_impact_verdict(result)
            # M5/M10: mirror summary_line + verdict between top-level and
            # agent_summary so direct callers (tests, hive-mind workers)
            # see the same envelope shape as MCP-routed callers.
            result = mirror_summary_line(result)
            return apply_toon_format_to_response(result, output_format)

        diff_stat = _get_diff_stat(mode, self.project_root, scope_paths)
        result = _build_change_impact_result(
            ChangeImpactRequest(
                mode=mode,
                changed_files=changed_files,
                diff_stat=diff_stat,
                project_root=self.project_root,
                include_tests=include_tests,
                scope_paths=scope_paths,
            )
        )
        # r37fG phase 3: surface related decision_journal entries and
        # upgrade the envelope verdict if any matched decision is more
        # severe than the change-impact builder's primary verdict. The
        # journal stays advisory — never downgrades, never raises.
        _enrich_with_journal_decisions(result, self.project_root, changed_files)
        result = attach_queue_ledger(
            result,
            mode=mode,
            scope_paths=scope_paths,
            scoped_changed_files=changed_files,
            workspace_changed_files=workspace_changed_files,
        )
        result = apply_scope_validation(result, scope_paths_invalid)
        if agent_summary_only:
            result = build_agent_summary_only_response(result)
        result["output_format"] = output_format
        # F1 (round-37f7): same defensive canonicalization as the
        # no-changes path — guarantees the cross-tool envelope sees
        # only canonical verdict tokens regardless of which builder
        # helper populated them.
        _canonicalize_change_impact_verdict(result)
        # M5/M10: mirror summary_line + verdict between top-level and
        # agent_summary so direct callers see the same envelope shape as
        # MCP-routed callers.
        result = mirror_summary_line(result)
        return apply_toon_format_to_response(result, output_format)

    def _execute_pr_analysis(
        self,
        pr_url: str,
        include_tests: bool,
        output_format: str,
        scope_paths: list[str],
        agent_summary_only: bool,
    ) -> dict[str, Any]:
        """Analyze a GitHub PR's diff via gh CLI.

        r37em (dogfood): 95→~25 lines. Pre-flight envelopes moved to
        ``_pr_invalid_url_envelope`` / ``_pr_gh_unavailable_envelope``;
        shared postprocessing (PR fields → queue ledger → scope validation
        → summary-only → mirror → TOON) collapsed into ``_finalize_pr_result``.
        """
        parsed = parse_pr_url(pr_url)
        if parsed is None:
            return _pr_invalid_url_envelope(pr_url, output_format)

        if not check_gh_available():
            return _pr_gh_unavailable_envelope(parsed, output_format)

        # H8: validate scope paths against disk (PR mode treats them as
        # path prefixes from the local checkout).
        scope_paths_invalid = _scope_paths_invalid(self.project_root, scope_paths)

        changed_files = fetch_pr_changed_files(parsed)
        if scope_paths:
            changed_files = [
                f
                for f in changed_files
                if any(f.startswith(s.rstrip("/")) for s in scope_paths)
            ]

        if not changed_files:
            return self._finalize_pr_result(
                build_no_changes_result("pr", scope_paths),
                parsed=parsed,
                scope_paths=scope_paths,
                scope_paths_invalid=scope_paths_invalid,
                changed_files=[],
                agent_summary_only=agent_summary_only,
                output_format=output_format,
            )

        diff_stat = fetch_pr_diff_stat(parsed)
        result = _build_change_impact_result(
            ChangeImpactRequest(
                mode="pr",
                changed_files=changed_files,
                diff_stat=diff_stat,
                project_root=self.project_root,
                include_tests=include_tests,
                scope_paths=scope_paths,
            )
        )
        return self._finalize_pr_result(
            result,
            parsed=parsed,
            scope_paths=scope_paths,
            scope_paths_invalid=scope_paths_invalid,
            changed_files=changed_files,
            agent_summary_only=agent_summary_only,
            output_format=output_format,
        )

    @staticmethod
    def _finalize_pr_result(
        result: dict[str, Any],
        *,
        parsed: Any,
        scope_paths: list[str],
        scope_paths_invalid: Any,
        changed_files: list[str],
        agent_summary_only: bool,
        output_format: str,
    ) -> dict[str, Any]:
        """Attach PR metadata + queue ledger + scope validation, mirror, and TOON.

        Shared by both the no-changes and with-changes branches of
        ``_execute_pr_analysis``. ``changed_files`` doubles as both
        ``scoped_changed_files`` and ``workspace_changed_files`` because
        PR mode pulls them from the same gh-CLI source.

        M5/M10: ``mirror_summary_line`` syncs ``summary_line`` + ``verdict``
        between top-level and ``agent_summary`` so direct callers see the
        same envelope shape regardless of routing.
        """
        result["pr_url"] = parsed.url
        result["pr_number"] = parsed.pr_number
        result["repo"] = parsed.slug
        result = attach_queue_ledger(
            result,
            mode="pr",
            scope_paths=scope_paths,
            scoped_changed_files=changed_files,
            workspace_changed_files=changed_files,
        )
        result = apply_scope_validation(result, scope_paths_invalid)
        if agent_summary_only:
            result = build_agent_summary_only_response(result)
        result["output_format"] = output_format
        # F1 (round-37f7): defensive canonicalization for the PR-mode
        # path. Mirrors the same protection applied in the diff-mode
        # branches above — keeps the cross-tool envelope free of
        # non-canonical verdict tokens regardless of which mode the
        # caller used.
        _canonicalize_change_impact_verdict(result)
        result = mirror_summary_line(result)
        return apply_toon_format_to_response(result, output_format)
