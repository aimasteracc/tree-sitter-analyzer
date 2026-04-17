#!/usr/bin/env python3
"""
Security Scanner MCP Tool

Provides security vulnerability scanning for source code files.
Detects common security vulnerabilities using AST pattern matching.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...analysis.security_scan import (
    SARIF_OM_SUPPORTED,
    SecurityScanner,
)
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SecurityScanTool(BaseMCPTool):
    """
    Security Scanner Tool

    Scans source code files for security vulnerabilities including:
    - Hardcoded secrets (API keys, passwords, tokens)
    - SQL injection (string concatenation in queries)
    - Command injection (subprocess calls with user input)
    - XSS (unsafe innerHTML, eval in JavaScript)
    - Unsafe deserialization (pickle, yaml loads)
    - Weak cryptography (MD5, SHA1)
    - Path traversal (file operations with user input)

    Supports Python, JavaScript, TypeScript, Java, Go, and more.
    """

    def get_tool_definition(self) -> dict[str, Any]:
        """Get the MCP tool definition."""
        return {
            "name": "security_scan",
            "description": (
                "Scan source code for security vulnerabilities. "
                "Detects hardcoded secrets, SQL injection, command injection, XSS, "
                "unsafe deserialization, weak crypto, and path traversal. "
                "Supports Python, JavaScript, TypeScript, Java, Go, and more. "
                "Returns findings with severity levels, CWE IDs, and remediation advice. "
                "Output formats: TOON (default), SARIF (for CI/CD)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to scan",
                    },
                    "content": {
                        "type": "string",
                        "description": "File content (optional, reads from disk if not provided)",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["toon", "sarif", "json"],
                        "description": "Output format (default: toon)",
                        "default": "toon",
                    },
                    "severity_filter": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info"],
                        "description": "Minimum severity level to report (default: info)",
                        "default": "info",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language hint (auto-detected from extension if not provided)",
                        "enum": [
                            "python",
                            "javascript",
                            "typescript",
                            "java",
                            "go",
                            "csharp",
                            "ruby",
                        ],
                    },
                },
                "required": ["file_path"],
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments."""
        file_path = arguments.get("file_path")
        if not file_path:
            raise ValueError("file_path is required")

        output_format = arguments.get("output_format", "toon")
        if output_format not in ("toon", "sarif", "json"):
            raise ValueError(f"Invalid output_format: {output_format}")

        severity_filter = arguments.get("severity_filter", "info")
        valid_severities = ("critical", "high", "medium", "low", "info")
        if severity_filter not in valid_severities:
            raise ValueError(f"Invalid severity_filter: {severity_filter}")

        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the security scan.

        Args:
            arguments: Tool arguments from the MCP request

        Returns:
            Scan results in the requested format
        """
        self.validate_arguments(arguments)

        file_path = arguments["file_path"]
        content = arguments.get("content")
        output_format = arguments.get("output_format", "toon")
        severity_filter = arguments.get("severity_filter", "info")

        # Create scanner and scan file
        scanner = SecurityScanner()

        try:
            result = scanner.scan_file(file_path, content=content)
        except FileNotFoundError:
            return {
                "error": f"File not found: {file_path}",
                "success": False,
            }
        except Exception as e:
            logger.warning(f"Failed to scan {file_path}: {e}")
            return {
                "error": f"Scan failed: {e}",
                "success": False,
            }

        # Filter by severity
        if severity_filter != "info":
            severity_order = {
                "critical": 4,
                "high": 3,
                "medium": 2,
                "low": 1,
                "info": 0,
            }
            min_severity = severity_order.get(severity_filter, 0)
            result.findings = [
                f
                for f in result.findings
                if severity_order.get(f.severity, 0) >= min_severity
            ]
            result.total_findings = len(result.findings)

        # Format output
        if output_format == "sarif":
            return {
                "output": self._format_sarif(result, scanner),
                "format": "sarif",
                "success": True,
            }
        elif output_format == "json":
            return {
                "output": json.dumps(result.to_dict(), indent=2),
                "format": "json",
                "success": True,
                "summary": {
                    "total_findings": result.total_findings,
                    "by_severity": result.by_severity,
                    "by_type": result.by_type,
                },
            }
        else:  # toon
            return {
                "output": self._format_toon(result),
                "format": "toon",
                "success": True,
                "summary": {
                    "total_findings": result.total_findings,
                    "language": result.language,
                },
            }

    def _format_toon(self, result: Any) -> str:
        """Format results in TOON (Tree-sitter Optimized Object Notation)."""
        lines = [
            f"🔒 {Path(result.file_path).name}",
            f"Language: {result.language}",
            f"Findings: {result.total_findings}",
        ]

        if result.total_findings == 0:
            lines.append("Status: ✅ No security issues found")
            return "\n".join(lines)

        # Group findings by severity
        by_severity: dict[str, list[Any]] = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "info": [],
        }

        for finding in result.findings:
            by_severity[finding.severity].append(finding)

        # Severity emojis
        severity_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "🔵",
        }

        # Output findings by severity
        for severity in ["critical", "high", "medium", "low", "info"]:
            findings = by_severity[severity]
            if not findings:
                continue

            lines.append(f"\n{severity_emoji[severity]} {severity.upper()} ({len(findings)})")

            for finding in findings[:10]:  # Limit to 10 per severity
                lines.append(f"  [{finding.rule_id}]")
                lines.append(f"  Line {finding.line}: {finding.message}")
                if finding.code_snippet:
                    lines.append(f"  Code: {finding.code_snippet[:60]}...")
                lines.append(f"  Fix: {finding.remediation}")

            if len(findings) > 10:
                lines.append(f"  ... and {len(findings) - 10} more")

        return "\n".join(lines)

    def _format_sarif(self, result: Any, scanner: SecurityScanner) -> str:
        """Format results in SARIF 2.1.0 format for CI/CD integration."""
        # Check if sarif_om is available
        if not SARIF_OM_SUPPORTED:
            logger.warning("sarif_om not available, falling back to JSON")
            return json.dumps(result.to_dict(), indent=2)

        try:
            # Get the pattern for rule info
            patterns_dict = {p.rule_id: p for p in scanner.get_patterns()}

            # Build rules
            rules = []
            for pattern in patterns_dict.values():
                rule = {
                    "id": pattern.rule_id,
                    "name": pattern.name,
                    "shortDescription": {
                        "text": pattern.description,
                    },
                    "fullDescription": {
                        "text": f"{pattern.description}\n\nRemediation: {pattern.remediation}",
                    },
                    "properties": {
                        "tags": [pattern.vulnerability_type.value],
                        "precision": "medium",
                    },
                }
                if pattern.cwe_id:
                    cwe_num = pattern.cwe_id.replace("CWE-", "")
                    rule["helpUri"] = f"https://cwe.mitre.org/data/definitions/{cwe_num}"
                rules.append(rule)

            # Build results
            sarif_results = []
            for finding in result.findings:
                sarif_results.append(
                    {
                        "ruleId": finding.rule_id,
                        "level": {
                            "critical": "error",
                            "high": "error",
                            "medium": "warning",
                            "low": "note",
                            "info": "note",
                        }.get(finding.severity, "note"),
                        "message": {
                            "text": finding.message,
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": finding.file_path,
                                    },
                                    "region": {
                                        "startLine": finding.line,
                                        "startColumn": finding.column + 1,
                                        "endLine": finding.line,
                                        "endColumn": finding.column + 20,
                                    },
                                },
                            }
                        ],
                    }
                )

            # Build SARIF log
            sarif_log: dict[str, Any] = {
                "version": "2.1.0",
                "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
                "runs": [
                    {
                        "tool": {
                            "driver": {
                                "name": "tree-sitter-analyzer-security",
                                "version": "1.0.0",
                                "informationUri": "https://github.com/aimasteracc/tree-sitter-analyzer",
                                "rules": rules,
                            }
                        },
                        "results": sarif_results,
                    }
                ],
            }

            return json.dumps(sarif_log, indent=2)

        except Exception as e:
            logger.warning(f"SARIF formatting failed: {e}, falling back to JSON")
            return json.dumps(result.to_dict(), indent=2)
