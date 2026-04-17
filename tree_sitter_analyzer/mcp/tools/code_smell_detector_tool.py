#!/usr/bin/env python3
"""
Code Smell Detector Tool — MCP Tool

Detects code smells and anti-patterns in source files.
Uses the CodeSmellDetector analysis engine to find issues like
God Class, Long Method, Deep Nesting, Magic Numbers, etc.

Part of the analysis toolset.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.code_smells import CodeSmellDetector, SmellSeverity
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeSmellDetectorTool(BaseMCPTool):
    """
    MCP tool for detecting code smells and anti-patterns.

    Analyzes source files for common code smells including God Class,
    Long Method, Deep Nesting, Magic Numbers, excessive imports, and
    large classes. Returns structured results with severity levels,
    suggestions, and actionable metrics.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "detect_code_smells",
            "description": (
                "Detect code smells and anti-patterns in source files. "
                "\n\n"
                "Finds: God Class, Long Method, Deep Nesting, Magic Numbers, "
                "Excessive Imports, Large Classes. "
                "\n\n"
                "WHEN TO USE:\n"
                "- During code review to identify refactoring targets\n"
                "- Before refactoring to prioritize which smells to fix first\n"
                "- To track code quality trends over time\n"
                "- To find files that need immediate attention\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For syntax error detection (use analyze_code_structure instead)\n"
                "- For security vulnerability scanning (use security tools)\n"
                "- For performance profiling"
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
                    "min_severity": {
                        "type": "string",
                        "enum": ["info", "warning", "critical"],
                        "description": (
                            "Minimum severity level to report. "
                            "Default: 'info' (all smells)."
                        ),
                    },
                    "smell_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Filter to specific smell types. "
                            "Options: 'god_class', 'long_method', "
                            "'deep_nesting', 'magic_number', 'many_imports', "
                            "'large_class'. Default: all types."
                        ),
                    },
                    "thresholds": {
                        "type": "object",
                        "description": (
                            "Custom thresholds. Keys: "
                            "'god_class_methods', 'long_method_lines', "
                            "'deep_nesting_levels', 'many_imports', "
                            "'god_class_lines'. Values are integers."
                        ),
                    },
                },
                "examples": [
                    {"file_path": "src/main/java/com/example/Service.java"},
                    {"project_root": "/project", "min_severity": "warning"},
                    {"file_path": "src/app.py", "smell_types": ["long_method", "deep_nesting"]},
                ],
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        file_path = arguments.get("file_path")
        if file_path is not None and not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

        project_root = arguments.get("project_root")
        if project_root is not None and not isinstance(project_root, str):
            raise ValueError("project_root must be a string")

        min_severity = arguments.get("min_severity")
        if min_severity is not None:
            valid = {s.value for s in SmellSeverity}
            if min_severity not in valid:
                raise ValueError(
                    f"min_severity must be one of {valid}, got '{min_severity}'"
                )

        smell_types = arguments.get("smell_types")
        if smell_types is not None:
            if not isinstance(smell_types, list):
                raise ValueError("smell_types must be an array")
            valid_types = {
                "god_class", "long_method", "deep_nesting",
                "magic_number", "many_imports", "large_class",
            }
            for st in smell_types:
                if st not in valid_types:
                    raise ValueError(
                        f"Invalid smell type '{st}'. Valid: {valid_types}"
                    )

        thresholds = arguments.get("thresholds")
        if thresholds is not None:
            if not isinstance(thresholds, dict):
                raise ValueError("thresholds must be an object")
            for key, value in thresholds.items():
                if not isinstance(value, int) or value <= 0:
                    raise ValueError(
                        f"Threshold '{key}' must be a positive integer"
                    )

        return True

    @handle_mcp_errors("detect_code_smells")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        file_path = arguments.get("file_path")
        project_root_arg = arguments.get("project_root")
        min_severity = arguments.get("min_severity", "info")
        smell_types = arguments.get("smell_types")
        thresholds = arguments.get("thresholds")

        # Determine project root
        root = project_root_arg or self.project_root or str(Path.cwd())

        # Validate file path if provided
        if file_path:
            resolved = self.resolve_and_validate_file_path(file_path)
            # Use parent as project root for single file analysis
            root = str(Path(resolved).parent)
            file_path = str(Path(resolved).relative_to(root))
        else:
            root = self.resolve_and_validate_directory_path(root)

        # Create detector with optional custom thresholds
        detector = CodeSmellDetector(root, thresholds=thresholds)

        # Run detection
        if file_path:
            result = detector.detect_file(file_path)
            results = [result]
        else:
            results = detector.detect_project()

        # Filter and format results
        severity_order = {"info": 0, "warning": 1, "critical": 2}
        min_level = severity_order.get(min_severity, 0)

        all_smells: list[dict[str, Any]] = []
        summary: dict[str, int] = {}
        files_with_smells = 0

        for file_result in results:
            file_smells = [
                s for s in file_result.smells
                if severity_order.get(s.severity, 0) >= min_level
                and (smell_types is None or s.smell_type in smell_types)
            ]
            if file_smells:
                files_with_smells += 1
                for smell in file_smells:
                    all_smells.append({
                        "type": smell.smell_type,
                        "severity": smell.severity,
                        "category": smell.category,
                        "file": smell.file_path,
                        "line": smell.line,
                        "description": smell.description,
                        "suggestion": smell.suggestion,
                        "metric": smell.metric_value,
                        "element": smell.element_name,
                    })
                    summary[smell.smell_type] = (
                        summary.get(smell.smell_type, 0) + 1
                    )

        total = len(all_smells)
        critical = sum(1 for s in all_smells if s["severity"] == "critical")
        warning = sum(1 for s in all_smells if s["severity"] == "warning")

        response: dict[str, Any] = {
            "success": True,
            "total_smells": total,
            "files_analyzed": len(results),
            "files_with_smells": files_with_smells,
            "summary": summary,
            "smells": all_smells,
        }

        if critical > 0:
            response["warning"] = (
                f"Found {critical} critical code smells. "
                "These indicate serious design issues that should be refactored."
            )

        if total == 0:
            response["message"] = (
                "No code smells detected. Code appears well-structured."
            )

        return response
