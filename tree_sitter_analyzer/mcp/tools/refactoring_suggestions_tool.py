# Refactoring suggestions with precise extraction targets
#!/usr/bin/env python3
"""
Refactoring Suggestions MCP Tool

Analyzes files and returns concrete, actionable refactoring suggestions
with exact function names, line ranges, extraction targets, and code skeletons.

Uses tree-sitter for cross-language element extraction (all 15 languages),
with Python-AST enhanced analysis (nesting, params, static detection) as bonus.
"""

from pathlib import Path
from typing import Any

from ...utils import setup_logger
from ._refactoring_plan_builder import build_precise_plans
from .base_tool import BaseMCPTool
from .utils.element_extractor import extract_elements
from .utils.refactoring_suggestions_helpers import (
    build_success_response,
    error_response,
    get_refactoring_tool_schema,
)
from .utils.refactoring_suggestions_python import python_bonus_analysis
from .utils.refactoring_suggestions_treesitter import analyze_treesitter_patterns

logger = setup_logger(__name__)

_PATTERN_RULES: list[dict[str, Any]] = [
    {
        "id": "P001",
        # Pattern rules for code smell detection
        "name": "god_file",
        "severity": "critical",
        "threshold": 800,
        "message": "File exceeds {threshold} lines ({actual} lines). Split by responsibility.",
    },
    {
        "id": "P002",
        "name": "long_function",
        "severity": "major",
        "threshold": 50,
        "message": "Function '{name}' is {actual} lines (>{threshold}). Extract sub-operations.",
    },
    {
        "id": "P003",
        "name": "deep_nesting",
        "severity": "major",
        "threshold": 4,
        "message": "Function '{name}' has {actual} levels of nesting (>{threshold}). Flatten with early returns or guard clauses.",
    },
    {
        "id": "P004",
        "name": "too_many_params",
        "severity": "minor",
        "threshold": 5,
        "message": "Function '{name}' has {actual} parameters (>{threshold}). Introduce a parameter object.",
    },
]

_EXTRACTABLE_PATTERNS: list[dict[str, Any]] = [
    {
        # Extractable patterns for refactoring suggestions
        "id": "E001",
        "name": "extract_method",
        "detect": "block_after_assignment",
        "message": "Lines {start}-{end} in '{function}' compute a value then use it once. Extract as a helper function.",
    },
    {
        "id": "E002",
        "name": "extract_class",
        "detect": "methods_with_common_prefix",
        "message": "Methods {methods} in '{class_name}' share prefix '{prefix}'. Extract a new class.",
    },
    {
        "id": "E003",
        "name": "move_to_helpers",
        "detect": "pure_function_in_class",
        "message": "Method '{method}' in '{class_name}' doesn't use self. Move to module-level helper.",
    },
    {
        "id": "E004",
        "name": "reduce_class_size",
        "detect": "large_class",
        "threshold": 15,
        "message": "Class '{name}' has {actual} methods (>{threshold}). Consider splitting responsibilities.",
    },
]


class RefactoringSuggestionsTool(BaseMCPTool):
    """MCP Tool that provides concrete refactoring suggestions for source files."""

    # Tool definition and schema
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "refactoring_suggestions",
            "description": (
                "Refactoring plan with precise extraction targets. "
                "Returns helper names, line ranges, params, returns, code skeletons. "
                "No built-in tool provides this."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return get_refactoring_tool_schema()

    # Source file reading and analysis
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute refactoring analysis on a source file."""
        file_path = arguments.get("file_path", "")
        max_suggestions = arguments.get("max_suggestions", 10)
        include_extractions = arguments.get("include_extractions", True)
        include_skeleton = arguments.get("include_skeleton", False)
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        if not resolved:
            return error_response(
                file_path,
                "File not found or outside project boundary",
                project_root=self.project_root,
            )

        try:
            source = Path(resolved).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return error_response(
                file_path,
                f"Cannot read file: {e}",
                project_root=self.project_root,
            )

        analysis = extract_elements(resolved, self.project_root)
        # Tree-sitter based pattern analysis
        suggestions = analyze_treesitter_patterns(
            source,
            analysis,
            include_extractions,
            _PATTERN_RULES,
            _EXTRACTABLE_PATTERNS,
            resolved,
        )

        ext = Path(resolved).suffix.lower()
        if ext == ".py" and analysis:
            python_bonus_analysis(
                source,
                suggestions,
                include_extractions,
                _PATTERN_RULES,
                _EXTRACTABLE_PATTERNS,
            )

        build_precise_plans(resolved, source, analysis, suggestions)

        result = build_success_response(
            resolved,
            suggestions,
            max_suggestions,
            include_skeleton,
            project_root=self.project_root,
        )

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    # Input validation - fail fast with clear error messages
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate file_path argument."""
        file_path = arguments.get("file_path", "")
        if not file_path or not isinstance(file_path, str):
            raise ValueError("file_path is required and must be a string")
        return True
