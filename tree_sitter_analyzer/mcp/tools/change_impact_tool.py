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
from .base_tool import BaseMCPTool, mirror_summary_line
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
                "and a risk verdict (CLEAN / REVIEW / WARN). Optionally "
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
                "- To see WHO calls a symbol — use trace_impact"
            ),
            "inputSchema": self.get_tool_schema(),
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
        """Analyze a GitHub PR's diff via gh CLI."""
        parsed = parse_pr_url(pr_url)
        if parsed is None:
            return apply_toon_format_to_response(
                {
                    "success": False,
                    "error": f"Invalid GitHub PR URL: {pr_url}",
                    "hint": "Expected format: https://github.com/owner/repo/pull/123",
                    "output_format": output_format,
                },
                output_format,
            )

        if not check_gh_available():
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
            result = build_no_changes_result("pr", scope_paths)
            result["pr_url"] = parsed.url
            result["pr_number"] = parsed.pr_number
            result["repo"] = parsed.slug
            result = attach_queue_ledger(
                result,
                mode="pr",
                scope_paths=scope_paths,
                scoped_changed_files=[],
                workspace_changed_files=[],
            )
            result = apply_scope_validation(result, scope_paths_invalid)
            if agent_summary_only:
                result = build_agent_summary_only_response(result)
            result["output_format"] = output_format
            # M5/M10: mirror summary_line + verdict between top-level and
            # agent_summary so direct callers see the same envelope shape.
            result = mirror_summary_line(result)
            return apply_toon_format_to_response(result, output_format)

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
        # M5/M10: mirror summary_line + verdict between top-level and
        # agent_summary so direct callers see the same envelope shape.
        result = mirror_summary_line(result)
        return apply_toon_format_to_response(result, output_format)
