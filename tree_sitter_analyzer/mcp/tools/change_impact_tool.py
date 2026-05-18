#!/usr/bin/env python3
"""
Change Impact Analysis MCP Tool.

Combines git diff with dependency graph to provide change impact analysis.
Tells AI agents: what changed, what's affected, what tests to run.
"""

from typing import Any

from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool
from .utils.change_impact_analysis import (
    ChangeImpactRequest,
    _build_change_impact_result,
)
from .utils.change_impact_git import (
    _get_changed_files,
    _get_diff_stat,
)
from .utils.change_impact_response import (
    attach_queue_ledger,
    build_agent_summary_only_response,
    build_no_changes_result,
)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["diff", "staged", "branch"],
            "default": "diff",
            "description": "diff=unstaged, staged=staged, branch=vs main",
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
                "After editing: git diff + dep graph → affected files, tests to run, risk. "
                "MUST call after edits. No built-in tool provides this."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate mode argument."""
        if "mode" in arguments and arguments["mode"] not in (
            "diff",
            "staged",
            "branch",
        ):
            raise ValueError("mode must be diff|staged|branch")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Analyze git diff + dependency graph for change impact."""
        mode = arguments.get("mode", "diff")
        include_tests = arguments.get("include_tests", True)
        output_format = arguments.get("output_format", "toon")
        scope_paths = arguments.get("scope_paths") or []
        agent_summary_only = bool(arguments.get("agent_summary_only", False))

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
            if agent_summary_only:
                result = build_agent_summary_only_response(result)
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
        if agent_summary_only:
            result = build_agent_summary_only_response(result)
        return apply_toon_format_to_response(result, output_format)
