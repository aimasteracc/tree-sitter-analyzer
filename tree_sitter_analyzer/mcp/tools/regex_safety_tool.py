"""Regex Safety Tool — MCP Tool.

Detects regex patterns vulnerable to ReDoS (Regular Expression Denial
of Service). Finds nested quantifiers, overlapping alternations, and
other patterns that can cause catastrophic backtracking.
"""
from __future__ import annotations

from typing import Any

from ...analysis.regex_safety import RegexSafetyAnalyzer, RegexSafetyResult
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class RegexSafetyTool(BaseMCPTool):
    """MCP tool for detecting ReDoS-vulnerable regex patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "regex_safety",
            "description": (
                "Detect regex patterns vulnerable to ReDoS "
                "(Regular Expression Denial of Service). "
                "\n\n"
                "Finds nested quantifiers like (x+)+, overlapping "
                "alternations, and other patterns that cause "
                "catastrophic backtracking."
                "\n\n"
                "Supported Languages:\n"
                "- Python: re.compile, re.match, re.search, etc.\n"
                "- JavaScript/TypeScript: /pattern/, new RegExp()\n"
                "- Java: Pattern.compile()\n"
                "- Go: regexp.MustCompile(), regexp.Compile()\n"
                "\n"
                "Vulnerability Types:\n"
                "- nested_quantifier (HIGH): (x+)+ causes exponential backtracking\n"
                "- overlapping_alternation (MEDIUM): (a|ab) causes excessive backtracking\n"
                "- quantified_alternation (LOW): quantified group with alternation\n"
                "\n"
                "WHEN TO USE:\n"
                "- Security audit of regex-heavy code\n"
                "- Before deploying regex that processes user input\n"
                "- Code review of input validation logic\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For general code quality (use code_smells)\n"
                "- For security scanning of secrets (use security_scan)"
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
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = RegexSafetyAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: RegexSafetyResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_regex_patterns": result.total_regex_patterns,
            "vulnerable_count": result.vulnerable_count,
            "is_safe": result.is_safe,
            "vulnerabilities": [
                {
                    "line": v.line_number,
                    "pattern": v.pattern,
                    "type": v.vulnerability_type,
                    "severity": v.severity,
                    "explanation": v.explanation,
                }
                for v in result.vulnerabilities
            ],
        }

    def _format_toon(self, result: RegexSafetyResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Regex Safety Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total regex patterns: {result.total_regex_patterns}")
        lines.append(f"Vulnerabilities: {result.vulnerable_count}")
        lines.append("")

        if result.vulnerabilities:
            lines.append("Vulnerable patterns:")
            for v in result.vulnerabilities:
                lines.append(
                    f"  L{v.line_number} [{v.severity.upper()}] "
                    f"{v.vulnerability_type}"
                )
                lines.append(f"    Pattern: {v.pattern}")
                lines.append(f"    {v.explanation}")
        else:
            lines.append("No ReDoS vulnerabilities detected.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_regex_patterns": result.total_regex_patterns,
            "vulnerable_count": result.vulnerable_count,
            "is_safe": result.is_safe,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
