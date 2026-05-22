#!/usr/bin/env python3
"""
Semantic Classify MCP Tool — Standalone semantic change classification.

Classifies code changes into semantic categories (api_change, refactor,
feature_addition, etc.) with risk assessment and confidence scores.

Can operate in two modes:
- classify_strings: Compare two code strings
- classify_git: Compare a file between two git refs
"""

from typing import Any

from ...ast_diff import ASTDiffer
from ...project_graph import _language_from_ext
from ...semantic_change_classifier import SemanticChangeClassifier
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SemanticClassifyTool(BaseMCPTool):
    """MCP Tool for semantic change classification."""

    def __init__(self, project_root: str | None = None) -> None:
        self._differ: ASTDiffer | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._differ = None

    def _get_differ(self) -> ASTDiffer:
        if self._differ is None:
            self._differ = ASTDiffer()
        return self._differ

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "semantic_classify",
            "description": (
                "Classify code changes into semantic categories with risk assessment. "
                "Modes: classify_strings (two code strings), classify_git (file between git refs). "
                "Returns dominant category, risk level, confidence, and per-hunk classification. "
                "No other tool provides semantic change understanding."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["classify_strings", "classify_git"],
                    "description": "Classification mode",
                    "default": "classify_strings",
                },
                "old_source": {
                    "type": "string",
                    "description": "Old source code string (for classify_strings mode)",
                },
                "new_source": {
                    "type": "string",
                    "description": "New source code string (for classify_strings mode)",
                },
                "language": {
                    "type": "string",
                    "description": "Language for classify_strings mode (auto-detected for classify_git)",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path (for classify_git mode or as context for classify_strings)",
                },
                "old_ref": {
                    "type": "string",
                    "description": "Old git ref (default: HEAD~1)",
                    "default": "HEAD~1",
                },
                "new_ref": {
                    "type": "string",
                    "description": "New git ref (default: HEAD)",
                    "default": "HEAD",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format",
                    "default": "toon",
                },
            },
            "required": ["mode"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "classify_strings")
        if mode == "classify_strings":
            if (
                arguments.get("old_source") is None
                or arguments.get("new_source") is None
            ):
                raise ValueError(
                    "old_source and new_source are required for classify_strings mode"
                )
            if not arguments.get("language"):
                raise ValueError("language is required for classify_strings mode")
        elif mode == "classify_git":
            if not arguments.get("file_path"):
                raise ValueError("file_path is required for classify_git mode")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "classify_strings")
        output_format = arguments.get("output_format", "toon")
        differ = self._get_differ()

        if mode == "classify_strings":
            diff_result = differ.diff_strings(
                old_source=arguments["old_source"],
                new_source=arguments["new_source"],
                language=arguments["language"],
            )
            file_path = arguments.get("file_path")
        elif mode == "classify_git":
            file_path = arguments["file_path"]
            diff_result = self._diff_git(differ, arguments)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        classifier = SemanticChangeClassifier(file_path=file_path)
        classification = classifier.classify(diff_result)
        class_dict = classification.to_dict()

        # Map risk_level to canonical verdict vocabulary (pain-01 tsa-landing contract).
        risk_level = class_dict.get("risk_level", "medium")
        verdict = (
            "CAUTION"
            if risk_level == "high"
            else ("REVIEW" if risk_level == "medium" else "INFO")
        )

        response: dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "diff_hunks": len(diff_result.hunks),
            "verdict": verdict,
            **class_dict,
        }

        return apply_toon_format_to_response(response, output_format)

    def _diff_git(self, differ: ASTDiffer, arguments: dict[str, Any]) -> Any:
        import subprocess

        file_path = arguments["file_path"]
        old_ref = arguments.get("old_ref", "HEAD~1")
        new_ref = arguments.get("new_ref", "HEAD")

        language = arguments.get("language") or _language_from_ext(file_path) or ""

        try:
            old_result = subprocess.run(  # nosec B603,B607
                ["git", "show", f"{old_ref}:{file_path}"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            old_source = old_result.stdout if old_result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            old_source = ""

        try:
            new_result = subprocess.run(  # nosec B603,B607
                ["git", "show", f"{new_ref}:{file_path}"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            new_source = new_result.stdout if new_result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            new_source = ""

        return differ.diff_strings(
            old_source=old_source,
            new_source=new_source,
            language=language,
            old_file=f"{old_ref}:{file_path}",
            new_file=f"{new_ref}:{file_path}",
        )
