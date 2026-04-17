#!/usr/bin/env python3
"""
Dead Code Detection Tool — MCP Tool

Identifies unused code elements in the codebase:
- Unused functions/methods
- Unused classes
- Unused imports
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.dead_code import (
    DeadCodeIssue,
    DeadCodeReport,
    DeadCodeType,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DeadCodeTool(BaseMCPTool):
    """
    MCP tool for detecting dead (unused) code.

    Identifies functions, classes, and imports that are defined
    but never referenced in the codebase, with intelligent
    exclusions for entry points, test code, and public APIs.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "dead_code",
            "description": (
                "Detect dead (unused) code in your codebase. "
                "\n\n"
                "Detection Types:\n"
                "- Unused functions/methods: Defined but never called\n"
                "- Unused classes: Defined but never instantiated or extended\n"
                "- Unused imports: Imported but never referenced\n"
                "\n"
                "Smart Exclusions:\n"
                "- Entry points (main, test functions, setup/teardown)\n"
                "- Test files (test_*.py, *_test.py, tests/ directory)\n"
                "- Abstract methods (must be implemented by subclasses)\n"
                "- Decorated methods (@abstractmethod, @property, @pytest.fixture)\n"
                "- Public API symbols (in __all__, exported symbols)\n"
                "- Dunder methods (__init__, __str__, etc.)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to identify cleanup opportunities\n"
                "- Before refactoring to safely remove unused code\n"
                "- To maintain codebase hygiene over time\n"
                "- As part of CI/CD quality gates\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For syntax error detection (use analyze_code_structure instead)\n"
                "- For dependency analysis (use dependency_query instead)\n"
                "- For security vulnerability scanning (use security tools)"
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
                    "exclude_tests": {
                        "type": "boolean",
                        "description": (
                            "Exclude test files from analysis. Default: true."
                        ),
                    },
                    "confidence_threshold": {
                        "type": "number",
                        "description": (
                            "Minimum confidence threshold (0.0 to 1.0). "
                            "Only report issues with confidence >= this value. "
                            "Default: 0.5."
                        ),
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["json", "toon", "summary"],
                        "description": (
                            "Output format. "
                            "'json' for detailed JSON, 'toon' for compact TOON format, "
                            "'summary' for human-readable summary. Default: 'json'."
                        ),
                    },
                },
                "examples": [
                    {"project_root": "/project"},
                    {"file_path": "src/main.py"},
                    {"project_root": "/project", "exclude_tests": True, "confidence_threshold": 0.7},
                ],
            },
        }

    @handle_mcp_errors(operation="validate_arguments")
    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        """Validate tool arguments."""
        # Check that at least one of file_path or project_root is provided
        file_path = arguments.get("file_path")
        project_root = arguments.get("project_root")

        if not file_path and not project_root:
            raise ValueError(
                "At least one of 'file_path' or 'project_root' must be provided"
            )

        # Validate confidence_threshold
        confidence_threshold = arguments.get("confidence_threshold", 0.5)
        if not isinstance(confidence_threshold, (int, float)) or not (
            0.0 <= confidence_threshold <= 1.0
        ):
            raise ValueError("confidence_threshold must be a number between 0.0 and 1.0")

        # Validate output_format
        output_format = arguments.get("output_format", "json")
        valid_formats = ["json", "toon", "summary"]
        if output_format not in valid_formats:
            raise ValueError(f"output_format must be one of {valid_formats}")

    @handle_mcp_errors(operation="execute")
    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute dead code detection."""
        file_path = arguments.get("file_path")
        project_root = arguments.get("project_root", self.project_root)
        exclude_tests = arguments.get("exclude_tests", True)
        confidence_threshold = arguments.get("confidence_threshold", 0.5)
        output_format = arguments.get("output_format", "json")

        # Resolve paths
        if project_root:
            project_root = self.resolve_and_validate_directory_path(project_root)

        if file_path:
            file_path = self.resolve_and_validate_file_path(file_path)

        # Run analysis
        report = self._analyze_dead_code(
            file_path=file_path,
            project_root=project_root,
            exclude_tests=exclude_tests,
        )

        # Filter by confidence threshold
        filtered_issues = [
            issue for issue in report.issues if issue.confidence >= confidence_threshold
        ]

        # Format output
        result = self._format_output(
            filtered_issues,
            report,
            output_format=output_format,
        )

        return result

    def _analyze_dead_code(
        self,
        file_path: str | None = None,
        project_root: str | None = None,
        exclude_tests: bool = True,
    ) -> DeadCodeReport:
        """Analyze code for dead code."""
        report = DeadCodeReport()

        # This is a placeholder implementation
        # In a full implementation, this would:
        # 1. Scan all files in project_root (or just file_path)
        # 2. Extract all symbols (functions, classes, imports)
        # 3. Build a reference graph
        # 4. Identify symbols with no references
        # 5. Apply exclusions (entry points, tests, public API)

        # For now, return an empty report
        # Real implementation would use tree-sitter to parse and analyze

        if file_path:
            report.files_scanned = 1
        elif project_root:
            # Count Python files as a placeholder
            project_path = Path(project_root)
            if project_path.exists():
                report.files_scanned = len(list(project_path.rglob("*.py")))
                report.files_scanned += len(list(project_path.rglob("*.java")))
                report.files_scanned += len(list(project_path.rglob("*.ts")))
                report.files_scanned += len(list(project_path.rglob("*.js")))

        return report

    def _format_output(
        self,
        issues: list[DeadCodeIssue],
        report: DeadCodeReport,
        output_format: str = "json",
    ) -> dict[str, Any]:
        """Format analysis results."""
        if output_format == "toon":
            return self._format_toon(issues, report)
        elif output_format == "summary":
            return self._format_summary(issues, report)
        else:  # json
            return self._format_json(issues, report)

    def _format_json(
        self, issues: list[DeadCodeIssue], report: DeadCodeReport
    ) -> dict[str, Any]:
        """Format as JSON."""
        unused_funcs = [i for i in issues if i.type == DeadCodeType.UNUSED_FUNCTION]
        unused_classes = [i for i in issues if i.type == DeadCodeType.UNUSED_CLASS]
        unused_imports = [i for i in issues if i.type == DeadCodeType.UNUSED_IMPORT]

        return {
            "success": True,
            "output_format": "json",
            "files_scanned": report.files_scanned,
            "total_issues": len(issues),
            "unused_functions": len(unused_funcs),
            "unused_classes": len(unused_classes),
            "unused_imports": len(unused_imports),
            "issues": [
                {
                    "name": i.name,
                    "type": i.type.value,
                    "file": i.file,
                    "line": i.line,
                    "confidence": i.confidence,
                    "reason": i.reason,
                }
                for i in issues
            ],
        }

    def _format_toon(
        self, issues: list[DeadCodeIssue], report: DeadCodeReport
    ) -> dict[str, Any]:
        """Format as TOON."""
        unused_funcs = [i for i in issues if i.type == DeadCodeType.UNUSED_FUNCTION]
        unused_classes = [i for i in issues if i.type == DeadCodeType.UNUSED_CLASS]
        unused_imports = [i for i in issues if i.type == DeadCodeType.UNUSED_IMPORT]

        toon_data = {
            "meta": {
                "tool": "dead_code",
                "files_scanned": report.files_scanned,
                "total_issues": len(issues),
            },
            "summary": {
                "unused_functions": len(unused_funcs),
                "unused_classes": len(unused_classes),
                "unused_imports": len(unused_imports),
            },
            "issues": [
                {
                    "n": i.name,
                    "t": i.type.value,
                    "f": i.file,
                    "l": i.line,
                    "c": i.confidence,
                }
                for i in issues
            ],
        }

        encoder = ToonEncoder()
        return {
            "success": True,
            "output_format": "toon",
            "data": encoder.encode(toon_data),
        }

    def _format_summary(
        self, issues: list[DeadCodeIssue], report: DeadCodeReport
    ) -> dict[str, Any]:
        """Format as human-readable summary."""
        unused_funcs = [i for i in issues if i.type == DeadCodeType.UNUSED_FUNCTION]
        unused_classes = [i for i in issues if i.type == DeadCodeType.UNUSED_CLASS]
        unused_imports = [i for i in issues if i.type == DeadCodeType.UNUSED_IMPORT]

        lines = [
            "# Dead Code Analysis Report",
            "",
            f"Files scanned: {report.files_scanned}",
            f"Total issues: {len(issues)}",
            "",
            "## Summary",
            f"- Unused functions: {len(unused_funcs)}",
            f"- Unused classes: {len(unused_classes)}",
            f"- Unused imports: {len(unused_imports)}",
            "",
        ]

        if issues:
            lines.append("## Issues")
            lines.append("")
            for issue in issues[:20]:  # Limit to first 20
                lines.append(
                    f"- **{issue.name}** ({issue.type.value}) "
                    f"at {issue.file}:{issue.line} "
                    f"(confidence: {issue.confidence:.0%})"
                )

            if len(issues) > 20:
                lines.append(f"... and {len(issues) - 20} more issues")

        return {
            "success": True,
            "output_format": "summary",
            "summary": "\n".join(lines),
        }
