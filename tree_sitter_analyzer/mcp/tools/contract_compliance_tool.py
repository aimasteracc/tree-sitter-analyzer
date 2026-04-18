"""Contract Compliance Tool — MCP Tool.

Analyzes code for contract violations: functions whose implementations
violate their declared type contracts (return type mismatches, boolean
traps, type contradictions, signature divergence).

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from typing import Any

from ...analysis.contract_compliance import (
    ContractComplianceAnalyzer,
    ContractComplianceResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ContractComplianceTool(BaseMCPTool):
    """MCP tool for analyzing contract compliance of code."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "contract_compliance",
            "description": (
                "Analyze code for contract violations where function "
                "implementations don't match their declared type contracts."
                "\n\n"
                "Detects return type violations, boolean traps, type "
                "contradictions, and signature divergence."
                "\n\n"
                "Supported Languages:\n"
                "- Python: return type annotations vs actual returns\n"
                "- JavaScript/TypeScript: return type annotations vs values\n"
                "- Java: return types vs actual return values\n"
                "- Go: result types vs return values\n"
                "\n"
                "Issue Types:\n"
                "- return_type_violation: returns value inconsistent with annotation\n"
                "- boolean_trap: annotated bool but returns non-bool\n"
                "- type_contradiction: parameter type conflicts with usage\n"
                "- signature_divergence: override differs from parent signature\n"
                "\n"
                "WHEN TO USE:\n"
                "- During refactoring to verify contracts still hold\n"
                "- Before modifying functions to understand their constraints\n"
                "- To catch silent type mismatches that tests might miss\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For type annotation existence (use type_annotation_coverage)\n"
                "- For return path completeness (use return_path)\n"
                "- For null safety (use null_safety)"
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
                    "severity": {
                        "type": "string",
                        "description": (
                            "Minimum severity to report: "
                            "high, medium, or low. Default: medium."
                        ),
                        "enum": ["high", "medium", "low"],
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: toon (default), json, or text",
                        "enum": ["toon", "json", "text"],
                    },
                },
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        min_severity = arguments.get("severity", "medium")
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = ContractComplianceAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result, min_severity)
        if output_format == "text":
            return self._format_text(result, min_severity)
        return self._format_toon(result, min_severity)

    def _filter_issues(
        self,
        result: ContractComplianceResult,
        min_severity: str,
    ) -> list[dict[str, Any]]:
        severity_order = {"high": 0, "medium": 1, "low": 2}
        min_level = severity_order.get(min_severity, 1)
        return [
            {
                "line": i.line,
                "issue_type": i.issue_type,
                "severity": i.severity,
                "element_name": i.element_name,
                "description": i.description,
                "detail": i.detail,
            }
            for i in result.issues
            if severity_order.get(i.severity, 1) <= min_level
        ]

    def _format_json(
        self,
        result: ContractComplianceResult,
        min_severity: str,
    ) -> dict[str, Any]:
        filtered = self._filter_issues(result, min_severity)
        return {
            "file": result.file_path,
            "language": result.language,
            "total_issues": result.total_issues,
            "high_severity": result.high_severity,
            "medium_severity": result.medium_severity,
            "low_severity": result.low_severity,
            "filtered_count": len(filtered),
            "issues": filtered,
        }

    def _format_text(
        self,
        result: ContractComplianceResult,
        min_severity: str,
    ) -> dict[str, Any]:
        filtered = self._filter_issues(result, min_severity)
        lines: list[str] = []
        lines.append(f"Contract Compliance Analysis: {result.file_path}")
        lines.append(f"Language: {result.language}")
        lines.append(f"Issues: {len(filtered)} (of {result.total_issues})")
        lines.append("")

        if filtered:
            for issue in filtered:
                lines.append(
                    f"L{issue['line']}: [{issue['severity'].upper()}] "
                    f"{issue['issue_type']}"
                )
                lines.append(f"  {issue['description']}")
                lines.append(f"  Detail: {issue['detail']}")
                lines.append("")
        else:
            lines.append("No contract compliance issues found.")

        return {
            "content": "\n".join(lines),
            "total_issues": result.total_issues,
            "filtered_count": len(filtered),
        }

    def _format_toon(
        self,
        result: ContractComplianceResult,
        min_severity: str,
    ) -> dict[str, Any]:
        filtered = self._filter_issues(result, min_severity)
        lines: list[str] = []
        lines.append("Contract Compliance Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Language: {result.language}")
        lines.append(
            f"Issues: {result.total_issues} "
            f"(H:{result.high_severity} M:{result.medium_severity} "
            f"L:{result.low_severity})"
        )
        lines.append("")

        if filtered:
            for issue in filtered:
                icon = {"high": "!!", "medium": "!", "low": "~"}.get(
                    issue["severity"], "?"
                )
                lines.append(
                    f"  [{icon}] L{issue['line']}: "
                    f"{issue['issue_type']} — {issue['element_name']}"
                )
                lines.append(f"      {issue['description']}")
                lines.append(f"      {issue['detail']}")
        else:
            lines.append("No contract compliance issues found at this severity level.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_issues": result.total_issues,
            "filtered_count": len(filtered),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json", "text"):
            raise ValueError("format must be 'toon', 'json', or 'text'")

        severity = arguments.get("severity", "medium")
        if severity not in ("high", "medium", "low"):
            raise ValueError("severity must be 'high', 'medium', or 'low'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
