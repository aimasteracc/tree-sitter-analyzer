"""Comment Quality Tool — MCP Tool.

Analyzes comment quality across codebases to detect stale/misleading
documentation, missing param docs, and TODO tracking.

Supports: Python (docstrings), JavaScript/TypeScript (JSDoc), Java (JavaDoc), Go (doc comments)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.comment_quality import (
    CommentIssue,
    CommentQualityAnalyzer,
    CommentQualityResult,
    IssueType,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CommentQualityTool(BaseMCPTool):
    """
    MCP tool for analyzing comment quality.

    Detects parameter mismatches between code and documentation,
    missing return documentation, stale TODOs, and comment rot risk.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "comment_quality",
            "description": (
                "Analyze comment quality to detect stale/misleading documentation. "
                "\n\n"
                "Detects:\n"
                "- Parameter mismatches (docstring params vs actual params)\n"
                "- Missing return documentation\n"
                "- Stale TODO/FIXME/HACK comments\n"
                "- Extra documentation for removed parameters\n"
                "\n"
                "Supported Languages:\n"
                "- Python: Sphinx, Google, Numpy-style docstrings\n"
                "- JavaScript/TypeScript: JSDoc\n"
                "- Java: JavaDoc\n"
                "- Go: doc comments\n"
                "\n"
                "WHEN TO USE:\n"
                "- Before code review to verify doc accuracy\n"
                "- After refactoring to catch stale documentation\n"
                "- To track and manage TODO/FIXME items\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For documentation coverage (use doc_coverage)\n"
                "- For code smell detection (use code_smell_detector)"
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
                    "issue_types": {
                        "type": "string",
                        "description": (
                            "Comma-separated issue types to filter: "
                            "param_mismatch, missing_return_doc, extra_doc_param, "
                            "stale_todo, missing_param_doc. Default: all types."
                        ),
                    },
                    "min_severity": {
                        "type": "string",
                        "description": (
                            "Minimum severity to report: low, medium, high. "
                            "Default: low (all issues)."
                        ),
                        "enum": ["low", "medium", "high"],
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
        file_path = arguments.get("file_path", "")
        project_root = arguments.get(
            "project_root", self.project_root or ""
        )
        issue_types_str = arguments.get("issue_types", "")
        min_severity = arguments.get("min_severity", "low")
        output_format = arguments.get("format", "toon")

        if not file_path and not project_root:
            return {
                "error": "Either file_path or project_root must be provided",
                "format": output_format,
            }

        issue_types: set[str] | None = None
        if issue_types_str:
            issue_types = {t.strip() for t in issue_types_str.split(",")}

        severity_order = {"low": 0, "medium": 1, "high": 2}
        min_sev_level = severity_order.get(min_severity, 0)

        analyzer = CommentQualityAnalyzer()

        if file_path:
            result = analyzer.analyze_file(file_path)
        else:
            result = analyzer.analyze_directory(project_root)

        if issue_types or min_sev_level > 0:
            filtered = tuple(
                i for i in result.issues
                if (not issue_types or i.issue_type in issue_types)
                and severity_order.get(i.severity, 0) >= min_sev_level
            )
            result = CommentQualityResult(
                issues=filtered,
                total_elements=result.total_elements,
                elements_with_docs=result.elements_with_docs,
                issue_count=len(filtered),
                quality_score=result.quality_score,
            )

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: CommentQualityResult) -> dict[str, Any]:
        return {
            "total_elements": result.total_elements,
            "elements_with_docs": result.elements_with_docs,
            "quality_score": result.quality_score,
            "issue_count": result.issue_count,
            "issues": [
                {
                    "type": i.issue_type,
                    "severity": i.severity,
                    "message": i.message,
                    "file": i.file_path,
                    "line": i.line_number,
                    "element": i.element_name,
                    "detail": i.detail,
                }
                for i in result.issues
            ],
        }

    def _format_toon(self, result: CommentQualityResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Comment Quality Analysis")
        lines.append(f"Total elements: {result.total_elements}")
        lines.append(f"With documentation: {result.elements_with_docs}")
        lines.append(f"Quality score: {result.quality_score:.1f}/100")
        lines.append(f"Issues found: {result.issue_count}")
        lines.append("")

        if result.issues:
            # Group by type
            by_type: dict[str, list[CommentIssue]] = {}
            for issue in result.issues:
                by_type.setdefault(issue.issue_type, []).append(issue)

            type_labels: dict[str, str] = {
                IssueType.PARAM_MISMATCH: "Parameter Mismatches",
                IssueType.MISSING_PARAM_DOC: "Missing Param Docs",
                IssueType.EXTRA_DOC_PARAM: "Stale Doc Params",
                IssueType.MISSING_RETURN_DOC: "Missing Return Docs",
                IssueType.STALE_TODO: "TODOs/FIXMEs",
                IssueType.ROT_RISK: "Comment Rot Risk",
            }

            for itype, label in type_labels.items():
                items = by_type.get(itype, [])
                if not items:
                    continue
                lines.append(f"{label} ({len(items)}):")
                for i in items[:20]:
                    sev = i.severity[0].upper()
                    fname = Path(i.file_path).name
                    lines.append(f"  [{sev}] {fname}:{i.line_number} {i.element_name}")
                    lines.append(f"      {i.message}")
                if len(items) > 20:
                    lines.append(f"  ... and {len(items) - 20} more")
                lines.append("")
        else:
            lines.append("No comment quality issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_elements": result.total_elements,
            "quality_score": result.quality_score,
            "issue_count": result.issue_count,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root", "")
        if not file_path and not project_root:
            raise ValueError("Either file_path or project_root must be provided")

        return True
