#!/usr/bin/env python3
"""
Environment Variable Tracker Tool — MCP Tool

Tracks environment variable usage across codebases to help developers
understand configuration requirements and avoid missing deployment configs.

Supports: Python, JavaScript/TypeScript, Java, Go
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.env_tracker import (
    EnvTrackingResult,
    EnvVarTracker,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class EnvTrackerTool(BaseMCPTool):
    """
    MCP tool for tracking environment variable usage.

    Detects env var references across Python, JavaScript/TypeScript,
    Java, and Go codebases.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "env_tracker",
            "description": (
                "Track environment variable usage across your codebase. "
                "\n\n"
                "Supported Languages:\n"
                "- Python: os.getenv(), os.environ[], os.environ.get()\n"
                "- JavaScript/TypeScript: process.env.VAR, process.env['VAR']\n"
                "- Java: System.getenv(), System.getProperty()\n"
                "- Go: os.Getenv()\n"
                "\n"
                "WHEN TO USE:\n"
                "- Before deployment to verify all env vars are configured\n"
                "- When documenting configuration requirements\n"
                "- During code review to understand config dependencies\n"
                "- To find unused or missing env var declarations\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For security vulnerability scanning (use security_scan)\n"
                "- For dependency analysis (use dependency_query)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze. "
                            "If provided, analyzes only this file."
                        ),
                    },
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory. "
                            "If provided without file_path, scans entire project."
                        ),
                    },
                    "group_by_var": {
                        "type": "boolean",
                        "description": (
                            "Group results by variable name. Default: true."
                        ),
                    },
                    "include_defaults": {
                        "type": "boolean",
                        "description": (
                            "Include env var calls that have default values. "
                            "Default: true."
                        ),
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: toon (default) or json",
                        "enum": ["toon", "json"],
                    },
                },
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute the environment variable tracking."""
        file_path = arguments.get("file_path", "")
        project_root = arguments.get(
            "project_root", self.project_root or ""
        )
        group_by_var = arguments.get("group_by_var", True)
        include_defaults = arguments.get("include_defaults", True)
        output_format = arguments.get("format", "toon")

        if not file_path and not project_root:
            return {
                "error": "Either file_path or project_root must be provided",
                "format": output_format,
            }

        root = project_root or str(Path(file_path).parent)
        tracker = EnvVarTracker(root, include_defaults)

        if file_path:
            result = tracker.track_file(file_path)
        else:
            result = tracker.track_directory(project_root)

        if output_format == "json":
            return self._format_json(result, group_by_var)
        else:
            return self._format_toon(result, group_by_var)

    def _format_json(
        self,
        result: EnvTrackingResult,
        group_by_var: bool,
    ) -> dict[str, Any]:
        """Format results as JSON."""
        output: dict[str, Any] = {
            "total_references": result.total_references,
            "unique_vars": result.unique_vars,
            "files_analyzed": len(result.by_file),
        }

        if group_by_var:
            output["variables"] = {
                name: {
                    "total_references": usage.total_references,
                    "file_count": usage.file_count,
                    "has_default_count": usage.has_default_count,
                    "access_types": usage.access_types,
                    "references": [
                        {
                            "file": ref.file_path,
                            "line": ref.line,
                            "column": ref.column,
                            "access_type": ref.access_type,
                            "has_default": ref.has_default,
                        }
                        for ref in usage.references
                    ],
                }
                for name, usage in result.by_var.items()
            }
        else:
            output["references"] = []
            for usage in result.by_var.values():
                for ref in usage.references:
                    output["references"].append({
                        "var_name": ref.var_name,
                        "file": ref.file_path,
                        "line": ref.line,
                        "column": ref.column,
                        "access_type": ref.access_type,
                        "has_default": ref.has_default,
                    })

        return output

    def _format_toon(
        self,
        result: EnvTrackingResult,
        group_by_var: bool,
    ) -> dict[str, Any]:
        """Format results as TOON."""
        lines: list[str] = []
        lines.append("Environment Variable Analysis")
        lines.append(f"Total references: {result.total_references}")
        lines.append(f"Unique variables: {result.unique_vars}")
        lines.append(f"Files analyzed: {len(result.by_file)}")
        lines.append("")

        if group_by_var:
            for name, usage in result.by_var.items():
                default_marker = (
                    f" (has_default: {usage.has_default_count})"
                    if usage.has_default_count > 0
                    else ""
                )
                lines.append(
                    f"  {name}: {usage.total_references} refs "
                    f"across {usage.file_count} files"
                    f"{default_marker}"
                )
                for ref in usage.references:
                    lines.append(
                        f"    - {Path(ref.file_path).name}:{ref.line} "
                        f"[{ref.access_type}]"
                    )
        else:
            for usage in result.by_var.values():
                for ref in usage.references:
                    lines.append(
                        f"  {ref.var_name} @ "
                        f"{Path(ref.file_path).name}:{ref.line} "
                        f"[{ref.access_type}]"
                    )

        encoder = ToonEncoder()
        toon = encoder.encode("\n".join(lines))
        return {"result": toon, "format": "toon"}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments."""
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root", "")
        if not file_path and not project_root:
            raise ValueError("Either file_path or project_root must be provided")

        return True
