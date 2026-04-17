#!/usr/bin/env python3
"""
Complexity Heatmap Tool — MCP Tool

Generates line-level complexity visualization for source code files.
Uses the ComplexityAnalyzer to create ASCII/ANSI heatmaps.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.complexity import (
    FileComplexityHeatmap,
    HeatmapFormatter,
    create_heatmap,
    format_heatmap,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ComplexityHeatmapTool(BaseMCPTool):
    """
    MCP tool for generating code complexity heatmaps.

    Provides line-by-line complexity visualization using ASCII
    or ANSI color codes. Helps identify complex code regions
    that may need refactoring.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "complexity_heatmap",
            "description": (
                "Generate line-level complexity heatmap for source code files.\n\n"
                "Complexity Levels:\n"
                "- Low (1-5): Simple code, easy to understand\n"
                "- Medium (6-10): Moderate complexity, acceptable\n"
                "- High (11-20): Complex code, consider refactoring\n"
                "- Critical (20+): Very complex code, high risk\n\n"
                "Output Format:\n"
                "- ASCII heatmap with complexity scores\n"
                "- Optional ANSI color codes for terminal display\n"
                "- Summary statistics (avg, max, distribution)\n\n"
                "WHEN TO USE:\n"
                "- During code review to identify complex regions\n"
                "- Before refactoring to prioritize work\n"
                "- To track code complexity trends over time\n"
                "- As part of code quality monitoring\n\n"
                "WHEN NOT TO USE:\n"
                "- For syntax error detection (use analyze_code_structure instead)\n"
                "- For security vulnerability scanning (use security tools)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to analyze.",
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Project root directory.",
                    },
                    "use_ansi": {
                        "type": "boolean",
                        "description": "Use ANSI color codes for output. Default: false.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["heatmap", "json"],
                        "description": "Output format. 'heatmap' for ASCII visualization, 'json' for structured data. Default: 'heatmap'.",
                    },
                },
                "examples": [
                    {"file_path": "src/main.py"},
                    {"file_path": "app.py", "use_ansi": True},
                    {"file_path": "lib.py", "format": "json"},
                ],
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        file_path = arguments.get("file_path")
        if file_path is None:
            raise ValueError("file_path is required")

        if not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

        project_root = arguments.get("project_root")
        if project_root is not None and not isinstance(project_root, str):
            raise ValueError("project_root must be a string")

        use_ansi = arguments.get("use_ansi")
        if use_ansi is not None and not isinstance(use_ansi, bool):
            raise ValueError("use_ansi must be a boolean")

        format_type = arguments.get("format")
        if format_type is not None:
            valid_formats = {"heatmap", "json"}
            if format_type not in valid_formats:
                raise ValueError(
                    f"format must be one of {valid_formats}, got '{format_type}'"
                )

        return True

    @handle_mcp_errors("complexity_heatmap")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        file_path = arguments["file_path"]
        project_root_arg = arguments.get("project_root")
        use_ansi = arguments.get("use_ansi", False)
        format_type = arguments.get("format", "heatmap")

        # Determine project root
        root = project_root_arg or self.project_root or str(Path.cwd())

        # Validate and resolve file path
        resolved = self.resolve_and_validate_file_path(file_path)
        root = str(Path(resolved).parent)
        file_path = str(Path(resolved).relative_to(root))

        # Create heatmap
        heatmap: FileComplexityHeatmap = create_heatmap(root, file_path)

        if format_type == "json":
            # Return JSON summary
            formatter = HeatmapFormatter()
            summary = formatter.format_summary(heatmap)

            return {
                "success": True,
                "format": "json",
                **summary,
            }

        # Return heatmap visualization
        output = format_heatmap(heatmap, use_ansi=use_ansi)

        return {
            "success": True,
            "format": "heatmap",
            "file": heatmap.file_path,
            "total_lines": heatmap.total_lines,
            "avg_complexity": heatmap.avg_complexity,
            "max_complexity": heatmap.max_complexity,
            "overall_level": heatmap.overall_level,
            "heatmap": output,
        }
