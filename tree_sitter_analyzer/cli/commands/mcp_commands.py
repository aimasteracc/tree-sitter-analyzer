#!/usr/bin/env python3
"""MCP-equivalent CLI command handlers."""

import asyncio
import os
from collections.abc import Callable, Mapping
from typing import Any

from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool
from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
    DependencyAnalysisTool,
)
from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool
from tree_sitter_analyzer.mcp.tools.project_health_tool import ProjectHealthTool
from tree_sitter_analyzer.mcp.tools.project_overview_tool import ProjectOverviewTool
from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
    RefactoringSuggestionsTool,
)
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool
from tree_sitter_analyzer.mcp.tools.smart_context_tool import SmartContextTool


def _run_tool(
    args: Any,
    tool_cls: Callable[..., Any],
    tool_args: Mapping[str, Any],
    label: str,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    output_format_fn: Callable[[], str],
) -> int:
    """Helper: instantiate tool, run execute(), print output."""
    try:
        project_root = getattr(args, "project_root", None) or os.getcwd()
        tool = tool_cls(project_root=project_root)
        result: dict[str, Any] = asyncio.run(tool.execute(dict(tool_args)))
        fmt = output_format_fn()
        if fmt == "toon":
            print(result.get("toon_content", ""))
        else:
            output_json_fn(result)
        return 0 if result.get("success", False) else 1
    except Exception as e:
        output_error_fn(f"{label} failed: {e}")
        return 1


def handle_mcp_commands(
    args: Any,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    output_format_fn: Callable[[], str],
) -> int | None:
    """Handle MCP-equivalent CLI commands. Returns exit code or None if not handled."""

    # --file-health: single file health check
    if getattr(args, "file_health", False):
        if not args.file_path:
            output_error_fn("--file-health requires a file path")
            return 1
        return _run_tool(
            args,
            FileHealthTool,
            {
                "file_path": args.file_path,
                "output_format": output_format_fn(),
            },
            "File health check",
            output_json_fn,
            output_error_fn,
            output_format_fn,
        )

    # --project-health: bulk project scoring
    if getattr(args, "project_health", False):
        return _run_tool(
            args,
            ProjectHealthTool,
            {
                "min_grade": getattr(args, "min_grade", "D"),
                "max_files": 30,
                "output_format": output_format_fn(),
            },
            "Project health check",
            output_json_fn,
            output_error_fn,
            output_format_fn,
        )

    # --overview: project portrait
    if getattr(args, "overview", False):
        return _run_tool(
            args,
            ProjectOverviewTool,
            {
                "include_health": True,
                "output_format": output_format_fn(),
            },
            "Project overview",
            output_json_fn,
            output_error_fn,
            output_format_fn,
        )

    # --safe-to-edit: edit risk assessment
    if getattr(args, "safe_to_edit", False):
        if not args.file_path:
            output_error_fn("--safe-to-edit requires a file path")
            return 1
        return _run_tool(
            args,
            SafeToEditTool,
            {
                "file_path": args.file_path,
                "edit_type": "modify",
                "output_format": output_format_fn(),
            },
            "Safe to edit",
            output_json_fn,
            output_error_fn,
            output_format_fn,
        )

    # --change-impact: git diff impact analysis
    if getattr(args, "change_impact", False):
        if not args.file_path:
            output_error_fn("--change-impact requires a file path")
            return 1
        return _run_tool(
            args,
            ChangeImpactTool,
            {
                "file_path": args.file_path,
                "output_format": output_format_fn(),
            },
            "Change impact analysis",
            output_json_fn,
            output_error_fn,
            output_format_fn,
        )

    # --dependencies: dependency graph analysis
    if getattr(args, "dependencies", None):
        if not args.file_path:
            output_error_fn("--dependencies requires a file path")
            return 1
        return _run_tool(
            args,
            DependencyAnalysisTool,
            {
                "file_path": args.file_path,
                "mode": args.dependencies,
                "output_format": output_format_fn(),
            },
            "Dependency analysis",
            output_json_fn,
            output_error_fn,
            output_format_fn,
        )

    # --refactor: refactoring suggestions
    if getattr(args, "refactor", False):
        if not args.file_path:
            output_error_fn("--refactor requires a file path")
            return 1
        return _run_tool(
            args,
            RefactoringSuggestionsTool,
            {
                "file_path": args.file_path,
                "output_format": output_format_fn(),
            },
            "Refactoring suggestions",
            output_json_fn,
            output_error_fn,
            output_format_fn,
        )

    # --smart-context: one-call file profile
    if getattr(args, "smart_context", False):
        if not args.file_path:
            output_error_fn("--smart-context requires a file path")
            return 1
        return _run_tool(
            args,
            SmartContextTool,
            {
                "file_path": args.file_path,
                "output_format": output_format_fn(),
            },
            "Smart context",
            output_json_fn,
            output_error_fn,
            output_format_fn,
        )

    return None
