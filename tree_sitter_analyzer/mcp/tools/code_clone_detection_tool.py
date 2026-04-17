#!/usr/bin/env python3
"""
Code Clone Detection Tool — MCP Tool

Detects duplicate code patterns using AST fingerprinting.
Uses the CodeCloneDetector analysis engine to find Type 1/2/3 clones.

Part of the analysis toolset.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.code_clones import (
    DEFAULT_MIN_LINES,
    DEFAULT_MIN_SIMILARITY,
    CloneSeverity,
    CloneType,
    CodeCloneDetector,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeCloneDetectionTool(BaseMCPTool):
    """
    MCP tool for detecting code clones and duplications.

    Analyzes source files for duplicate code patterns using AST
    fingerprinting and similarity analysis. Identifies Type 1 (exact),
    Type 2 (structural), and Type 3 (functional) clones with severity
    ratings and refactoring suggestions.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "detect_code_clones",
            "description": (
                "Detect duplicate code patterns and clones. "
                "\n\n"
                "Clone Types:\n"
                "- Type 1: Exact copies (whitespace/comments ignored)\n"
                "- Type 2: Structurally similar (renamed variables)\n"
                "- Type 3: Functionally similar (different implementations)\n"
                "\n"
                "Severity Levels:\n"
                "- INFO: Small clones (< 5 lines)\n"
                "- WARNING: Medium clones (5-15 lines)\n"
                "- CRITICAL: Large clones (> 15 lines)\n"
                "\n"
                "WHEN TO USE:\n"
                "- Before refactoring to identify duplication hotspots\n"
                "- During code review to catch duplicated logic\n"
                "- To track technical debt from code duplication\n"
                "- When consolidating similar implementations\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For syntax comparison (use code_diff instead)\n"
                "- For pattern matching without duplication detection"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze. "
                            "If provided, analyzes only this file against project."
                        ),
                    },
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory. "
                            "If provided without file_path, scans entire project."
                        ),
                    },
                    "min_lines": {
                        "type": "integer",
                        "description": (
                            "Minimum lines to consider as a clone. "
                            f"Default: {DEFAULT_MIN_LINES}"
                        ),
                        "default": DEFAULT_MIN_LINES,
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": (
                            "Minimum similarity threshold (0.0-1.0). "
                            f"Default: {DEFAULT_MIN_SIMILARITY}"
                        ),
                        "default": DEFAULT_MIN_SIMILARITY,
                    },
                    "min_severity": {
                        "type": "string",
                        "enum": ["info", "warning", "critical"],
                        "description": (
                            "Minimum severity level to report. "
                            "Default: 'info' (all clones)."
                        ),
                    },
                    "clone_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Filter to specific clone types. "
                            "Options: 'type_1_exact', 'type_2_structure', "
                            "'type_3_function'. Default: all types."
                        ),
                    },
                },
                "examples": [
                    {"project_root": "/project"},
                    {"file_path": "src/main/java/com/example/Service.java"},
                    {"project_root": "/project", "min_severity": "warning"},
                    {"file_path": "src/app.py", "min_lines": 10, "min_similarity": 0.9},
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

        min_lines = arguments.get("min_lines")
        if min_lines is not None:
            if not isinstance(min_lines, int) or min_lines < 1:
                raise ValueError("min_lines must be a positive integer")

        min_similarity = arguments.get("min_similarity")
        if min_similarity is not None:
            if not isinstance(min_similarity, (int, float)):
                raise ValueError("min_similarity must be a number")
            if not 0.0 <= min_similarity <= 1.0:
                raise ValueError("min_similarity must be between 0.0 and 1.0")

        min_severity = arguments.get("min_severity")
        if min_severity is not None:
            valid = {s.value for s in CloneSeverity}
            if min_severity not in valid:
                raise ValueError(
                    f"min_severity must be one of {valid}, got '{min_severity}'"
                )

        clone_types = arguments.get("clone_types")
        if clone_types is not None:
            if not isinstance(clone_types, list):
                raise ValueError("clone_types must be an array")
            valid_types = {t.value for t in CloneType}
            for ct in clone_types:
                if ct not in valid_types:
                    raise ValueError(
                        f"Invalid clone type '{ct}'. Valid: {valid_types}"
                    )

        return True

    @handle_mcp_errors("detect_code_clones")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        file_path = arguments.get("file_path")
        project_root_arg = arguments.get("project_root")
        min_lines = arguments.get("min_lines", DEFAULT_MIN_LINES)
        min_similarity = arguments.get("min_similarity", DEFAULT_MIN_SIMILARITY)
        min_severity = arguments.get("min_severity", "info")
        clone_types = arguments.get("clone_types")

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

        # Create detector with custom thresholds
        detector = CodeCloneDetector(
            root,
            min_lines=min_lines,
            min_similarity=min_similarity,
        )

        # Run detection
        result = detector.detect_project()

        # Filter and format results
        severity_order = {"info": 0, "warning": 1, "critical": 2}
        min_level = severity_order.get(min_severity, 0)

        all_clones: list[dict[str, Any]] = []
        summary: dict[str, int] = {}
        files_involved: set[str] = set()

        for clone in result.clones:
            # Filter by severity
            if severity_order.get(clone.severity, 0) < min_level:
                continue

            # Filter by clone type
            if clone_types is not None and clone.clone_type not in clone_types:
                continue

            # Filter by file if specified
            if file_path:
                if clone.file_a != file_path and clone.file_b != file_path:
                    continue

            files_involved.add(clone.file_a)
            files_involved.add(clone.file_b)

            all_clones.append({
                "type": clone.clone_type,
                "severity": clone.severity,
                "file_a": clone.file_a,
                "line_a": clone.line_a,
                "file_b": clone.file_b,
                "line_b": clone.line_b,
                "length": clone.length_lines,
                "similarity": clone.similarity,
                "description": clone.description,
                "suggestion": clone.suggestion,
            })
            summary[clone.clone_type] = summary.get(clone.clone_type, 0) + 1

        total = len(all_clones)
        critical = sum(1 for c in all_clones if c["severity"] == "critical")

        response: dict[str, Any] = {
            "success": True,
            "total_clones": total,
            "files_involved": len(files_involved),
            "summary": summary,
            "clones": all_clones,
        }

        if critical > 0:
            response["warning"] = (
                f"Found {critical} critical code clones. "
                "These indicate significant duplication that should be refactored."
            )

        if total == 0:
            response["message"] = (
                "No code clones detected. Code appears to be DRY (Don't Repeat Yourself)."
            )

        return response
