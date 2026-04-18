#!/usr/bin/env python3
"""
Type Annotation Coverage Tool — MCP Tool

Analyzes type annotation coverage in Python codebases to identify
functions and methods missing parameter or return type annotations.

Supports: Python only (type annotations are a Python-specific feature)
"""

from __future__ import annotations

from typing import Any

from ...analysis.type_annotation_coverage import TypeAnnotationAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class TypeAnnotationCoverageTool(BaseMCPTool):
    """MCP tool for analyzing type annotation coverage."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "type_annotation_coverage",
            "description": (
                "Analyze type annotation coverage in Python code.\n\n"
                "Detects:\n"
                "- Parameters without type annotations\n"
                "- Functions without return type annotations\n"
                "- Variable annotations (x: int = 42)\n\n"
                "Reports coverage percentage and per-element details.\n\n"
                "WHEN TO USE:\n"
                "- During code review to enforce annotation discipline\n"
                "- To track annotation coverage trends over time\n"
                "- Before enabling strict mypy on a module\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a specific Python file to analyze.",
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Project root for directory scan.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "description": "Output format (default: toon).",
                        "default": "toon",
                    },
                },
            },
        }

    @handle_mcp_errors()
    def execute(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        file_path = args.get("file_path")
        project_root = args.get("project_root") or self.project_root
        fmt = args.get("format", "toon")

        analyzer = TypeAnnotationAnalyzer()
        results = []

        if file_path:
            results = [analyzer.analyze(file_path)]
        elif project_root:
            results = analyzer.analyze_directory(project_root)

        if fmt == "json":
            return [r.to_dict() for r in results]

        encoder = ToonEncoder()
        lines: list[str] = ["Type Annotation Coverage Report", "=" * 40]
        for r in results:
            pct = f"{r.coverage_pct:.1f}%"
            lines.append(f"\n  {r.file_path}")
            lines.append(f"  Coverage: {pct} ({r.annotated_elements}/{r.total_elements})")
            for s in r.stats:
                status = "+" if s.has_annotation else "-"
                lines.append(f"    [{status}] L{s.line} {s.kind}: {s.name}")
                if s.annotation_type:
                    lines.append(f"        type: {s.annotation_type}")
            if not r.stats:
                lines.append("    (no elements found)")
        return [{"content": encoder.encode("\n".join(lines))}]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            return False
        return True
