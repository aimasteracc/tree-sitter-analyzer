#!/usr/bin/env python3
"""
Test Coverage Gap MCP Tool — Maps production code to tests, identifies untested symbols.

Modes:
  - summary:  Coverage statistics + worst files (no individual gaps)
  - gaps:     Prioritized list of untested symbols (default)
  - file:     Gaps for a single production file

CodeGraph parity: CodeGraph has no equivalent; this is a unique capability
that combines AST-level symbol extraction with naming-convention-based
test matching and cyclomatic complexity prioritization.
"""

from typing import Any

from ...test_gap_analyzer import analyze_coverage_gaps
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["summary", "gaps", "file"],
            "description": (
                "Analysis mode: 'summary' for coverage statistics, "
                "'gaps' for prioritized untested symbols (default), "
                "'file' for gaps in a specific file."
            ),
            "default": "gaps",
        },
        "file_path": {
            "type": "string",
            "description": "File path for mode 'file' (relative to project root).",
        },
        "language": {
            "type": "string",
            "description": "Filter to a single language (e.g. 'python', 'java').",
        },
        "max_files": {
            "type": "integer",
            "description": "Max source files to scan (default: 1000).",
            "default": 1000,
        },
        "max_gaps": {
            "type": "integer",
            "description": "Max gap results to return (default: 50).",
            "default": 50,
        },
        "include_covered": {
            "type": "boolean",
            "description": "Include covered symbols in response (default: false).",
            "default": False,
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon", "summary", "total_only"],
            "default": "json",
        },
    },
    "required": [],
}


class CodeGraphTestGapTool(BaseMCPTool):
    """MCP Tool for test coverage gap analysis."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_test_gap",
            "description": (
                "Test coverage gap analysis: maps production symbols to test files, "
                "identifies untested functions/classes, and prioritizes gaps by "
                "cyclomatic complexity. Unique capability not in CodeGraph."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "gaps")
        if mode not in ("summary", "gaps", "file"):
            raise ValueError(f"Invalid mode: {mode!r}. Must be summary, gaps, or file.")
        if mode == "file" and not arguments.get("file_path"):
            raise ValueError("file_path is required for mode 'file'.")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        if not self.project_root:
            return {"success": False, "error": "project_root is required"}

        mode = arguments.get("mode", "gaps")
        language_filter = arguments.get("language") or None
        max_files = arguments.get("max_files", 1000)
        max_gaps = arguments.get("max_gaps", 50)
        include_covered = arguments.get("include_covered", False)
        output_format = arguments.get("output_format", "json")
        target_file = arguments.get("file_path") or None

        try:
            result = analyze_coverage_gaps(
                self.project_root,
                language_filter=language_filter,
                max_files=max_files,
                max_gaps=max_gaps,
                include_covered=include_covered,
            )
        except Exception as exc:
            logger.error("test_gap analysis failed: %s", exc)
            return {"success": False, "error": str(exc)}

        response = self._build_response(result, mode, target_file)
        return apply_toon_format_to_response(response, output_format)

    def _build_response(
        self,
        result: Any,
        mode: str,
        target_file: str | None,
    ) -> dict[str, Any]:
        if mode == "summary":
            return {
                "success": True,
                "coverage_pct": result.coverage_pct,
                "total_production_symbols": result.total_production_symbols,
                "total_test_symbols": result.total_test_symbols,
                "covered_count": result.covered_count,
                "gap_count": result.gap_count,
                "priority_distribution": result.summary.get("priority_distribution", {}),
                "worst_files": result.summary.get("worst_files", []),
                "by_language": result.summary.get("by_language", {}),
                "production_files": result.summary.get("production_files", 0),
                "test_files": result.summary.get("test_files", 0),
                "agent_summary": (
                    f"Test coverage: {result.coverage_pct}% "
                    f"({result.covered_count}/{result.total_production_symbols} symbols covered). "
                    f"{result.gap_count} gaps found. "
                    f"Priority: {result.summary.get('priority_distribution', {})}. "
                    f"Files: {result.summary.get('production_files', 0)} prod, "
                    f"{result.summary.get('test_files', 0)} test."
                ),
            }

        gaps = result.gaps
        if mode == "file" and target_file:
            gaps = [
                g for g in gaps
                if target_file in g.symbol.file_path
            ]

        gap_dicts = [
            {
                "name": g.symbol.name,
                "kind": g.symbol.kind,
                "file": g.symbol.file_path,
                "line": g.symbol.line,
                "class": g.symbol.class_name,
                "complexity": g.symbol.complexity,
                "risk": g.symbol.risk,
                "priority": g.priority,
                "reason": g.reason,
                "suggestion": g.suggestion,
            }
            for g in gaps
        ]

        critical = sum(1 for g in gaps if g.priority == "critical")
        high = sum(1 for g in gaps if g.priority == "high")
        medium = sum(1 for g in gaps if g.priority == "medium")

        response: dict[str, Any] = {
            "success": True,
            "coverage_pct": result.coverage_pct,
            "total_production_symbols": result.total_production_symbols,
            "covered_count": result.covered_count,
            "gap_count": result.gap_count,
            "returned_gaps": len(gap_dicts),
            "gaps": gap_dicts,
            "agent_summary": (
                f"Coverage: {result.coverage_pct}% "
                f"({result.covered_count}/{result.total_production_symbols}). "
                f"{result.gap_count} total gaps: "
                f"{critical} critical, {high} high, {medium} medium. "
                f"Top gap: {gaps[0].symbol.name} ({gaps[0].priority})" if gaps else
                f"Coverage: {result.coverage_pct}% "
                f"({result.covered_count}/{result.total_production_symbols}). No gaps."
            ),
        }

        return response
