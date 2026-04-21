#!/usr/bin/env python3
"""
Dead Code Analysis Tool — MCP Tool.

Detects unreachable code paths in source files:
- Code after return/raise/break/continue statements
- Dead branches (if False, if True...else)

Delegates to DeadCodePathAnalyzer for AST-based detection.
Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.dead_code_path import (
    DeadCodePathAnalyzer,
    DeadCodePathResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_VALID_FORMATS: frozenset[str] = frozenset({"toon", "json"})


class DeadCodeAnalysisTool(BaseMCPTool):
    """
    MCP tool for detecting unreachable code paths.

    Finds dead code after return/raise/break/continue and dead branches
    (if False, if True...else) using AST-based analysis.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self._path_analyzer = DeadCodePathAnalyzer()

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "dead_code_analysis",
            "description": (
                "Detect unreachable code paths in your source files."
                "\n\n"
                "Detection Types:\n"
                "- Code after return/raise/break/continue\n"
                "- Dead branches (if False, if True...else)\n"
                "\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go"
                "\n\n"
                "WHEN TO USE:\n"
                "- During code review to find dead code paths\n"
                "- Before refactoring to identify unreachable code\n"
                "- As part of CI/CD quality gates"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze."
                        ),
                    },
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory. "
                            "If provided without file_path, scans entire project."
                        ),
                    },
                    "format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "description": (
                            "Output format: 'toon' (default) or 'json'."
                        ),
                    },
                },
                "examples": [
                    {"file_path": "src/main.py"},
                    {"file_path": "src/main.py", "format": "json"},
                    {"project_root": "/project"},
                ],
            },
        }

    @handle_mcp_errors(operation="validate_arguments")
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments."""
        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root")

        if not file_path and not project_root:
            raise ValueError(
                "At least one of 'file_path' or 'project_root' must be provided"
            )

        fmt = arguments.get("format", "toon")
        if fmt not in _VALID_FORMATS:
            raise ValueError(
                f"format must be one of {sorted(_VALID_FORMATS)}, got '{fmt}'"
            )

        return True

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute dead code path analysis."""
        output_format = arguments.get("format", "toon")
        file_path = arguments.get("file_path", "")

        resolved_path = self._resolve_target_path(
            file_path, arguments.get("project_root")
        )

        target = Path(resolved_path)

        if target.is_file():
            result = self._path_analyzer.analyze_file(resolved_path)
        else:
            result = self._analyze_directory(target)

        if output_format == "toon":
            return self._format_toon(result)
        return self._format_json(result)

    def _resolve_target_path(
        self,
        file_path: str,
        project_root: str | None,
    ) -> str:
        """Resolve and validate file_path or project_root."""
        if file_path:
            return self.resolve_and_validate_file_path(file_path)

        root = project_root or self.project_root
        if root:
            return self.resolve_and_validate_directory_path(root)

        raise ValueError(
            "At least one of 'file_path' or 'project_root' must be provided"
        )

    def _analyze_directory(self, directory: Path) -> DeadCodePathResult:
        """Analyze all supported files in a directory for unreachable paths."""
        extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"}
        all_issues: list[DeadCodePathResult] = []
        total_functions = 0

        for f in directory.rglob("*"):
            if f.is_file() and f.suffix.lower() in extensions:
                result = self._path_analyzer.analyze_file(str(f))
                total_functions += result.total_functions
                all_issues.append(result)

        combined_issues = tuple(
            issue
            for r in all_issues
            for issue in r.issues
        )

        return DeadCodePathResult(
            total_functions=total_functions,
            issues=combined_issues,
            file_path=str(directory),
        )

    def _format_json(self, result: DeadCodePathResult) -> dict[str, Any]:
        """Format results as JSON."""
        return {
            "success": True,
            "output_format": "json",
            "file": result.file_path,
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: DeadCodePathResult) -> dict[str, Any]:
        """Format results as TOON."""
        lines: list[str] = [
            "Dead Code Path Analysis",
            f"File: {result.file_path}",
            f"Total functions: {result.total_functions}",
            "",
        ]

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] [{i.severity}] "
                    f"{i.description}"
                )
        else:
            lines.append("No dead code path issues found.")

        encoder = ToonEncoder()
        return {
            "success": True,
            "output_format": "toon",
            "content": encoder.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
        }
