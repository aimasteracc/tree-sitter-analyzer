# Refactoring suggestions with precise extraction targets
#!/usr/bin/env python3
"""
Refactoring Suggestions MCP Tool

Analyzes files and returns concrete, actionable refactoring suggestions
with exact function names, line ranges, extraction targets, and code skeletons.

Uses tree-sitter for cross-language element extraction (all 15 languages),
with Python-AST enhanced analysis (nesting, params, static detection) as bonus.
"""

import ast
from pathlib import Path
from typing import Any

from ...utils import setup_logger
from ._refactoring_plan_builder import build_precise_plans
from .base_tool import BaseMCPTool
from .utils.element_extractor import (
    extract_elements,
    get_classes,
    get_functions,
)

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
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the source file to analyze",
                },
                "language": {
                    "type": "string",
                    "description": "Programming language (auto-detected if omitted)",
                },
                "max_suggestions": {
                    "type": "integer",
                    "description": "Maximum suggestions to return (default: 10)",
                    "default": 10,
                },
                # Tool execution pipeline
                "include_extractions": {
                    "type": "boolean",
                    "description": "Include specific extraction targets (default: true)",
                    "default": True,
                },
                "include_skeleton": {
                    "type": "boolean",
                    "description": "Include code skeletons in extraction plans (default: false, saves ~50% tokens)",
                    "default": False,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "'toon' (default) saves ~60% tokens vs 'json'",
                    "default": "toon",
                },
            },
            "required": ["file_path"],
        }

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
            return self._error_response(
                file_path, "File not found or outside project boundary"
            )

        try:
            source = Path(resolved).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return self._error_response(file_path, f"Cannot read file: {e}")

        analysis = extract_elements(resolved, self.project_root)
        # Tree-sitter based pattern analysis
        suggestions = self._analyze_via_treesitter(
            resolved, source, analysis, max_suggestions, include_extractions
        )

        ext = Path(resolved).suffix.lower()
        if ext == ".py" and analysis:
            self._python_bonus_analysis(source, suggestions, include_extractions)

        build_precise_plans(resolved, source, analysis, suggestions)

        if not include_skeleton:
            for s in suggestions:
                plan = s.get("precise_plan")
                if plan:
                    for ext_target in plan.get("extractions", []):
                        ext_target.pop("skeleton", None)

        suggestions.sort(key=lambda s: s.get("priority_score", 0), reverse=True)
        suggestions = suggestions[:max_suggestions]

        # File-level oversized detection
        result = {
            "file": resolved,
            "total_suggestions": len(suggestions),
            "summary": self._make_summary(suggestions),
            "suggestions": suggestions,
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _analyze_via_treesitter(
        self,
        file_path: str,
        source: str,
        analysis: Any,
        max_suggestions: int,
        include_extractions: bool,
    ) -> list[dict[str, Any]]:
        """Analyze file using tree-sitter extracted elements for pattern detection."""
        # Function-level length detection
        suggestions: list[dict[str, Any]] = []
        line_count = len(source.splitlines())

        if line_count > _PATTERN_RULES[0]["threshold"]:
            suggestions.append(
                self._make_pattern(
                    _PATTERN_RULES[0],
                    actual=line_count,
                    priority_score=min(100, line_count // 10),
                )
            )

        if not analysis:
            return suggestions

        for func in get_functions(analysis):
            if func["lines"] > _PATTERN_RULES[1]["threshold"]:
                suggestions.append(
                    self._make_pattern(
                        _PATTERN_RULES[1],
                        # Class extraction pattern detection
                        name=func["name"],
                        actual=func["lines"],
                        line_range=(func["line"], func["end_line"]),
                        priority_score=min(90, func["lines"]),
                    )
                )

        if include_extractions:
            self._find_class_extractions(analysis, suggestions)

        return suggestions

    def _find_class_extractions(
        self, analysis: Any, suggestions: list[dict[str, Any]]
    ) -> None:
        """Find extractable class-level patterns (large classes, prefix groups)."""
        rule_e4 = _EXTRACTABLE_PATTERNS[3]
        for cls in get_classes(analysis):
            if cls["method_count"] > rule_e4["threshold"]:
                suggestions.append(
                    # Method prefix grouping for class extraction
                    self._make_extraction(
                        rule_e4,
                        name=cls["name"],
                        actual=cls["method_count"],
                        threshold=rule_e4["threshold"],
                        line_range=(cls["line"], cls["end_line"]),
                        priority_score=50,
                    )
                )
            if len(cls["method_names"]) >= 3:
                self._find_prefix_groups(cls, suggestions)

    def _find_prefix_groups(
        self, cls: dict[str, Any], suggestions: list[dict[str, Any]]
    ) -> None:
        """Find method groups sharing a common prefix (suggest class extraction)."""
        prefixes: dict[str, list[str]] = {}
        for m in cls["method_names"]:
            if "_" in m and not m.startswith("_"):
                prefixes.setdefault(m.split("_")[0], []).append(m)
        # Python AST bonus analysis
        for prefix, group in prefixes.items():
            if len(group) >= 3:
                suggestions.append(
                    self._make_extraction(
                        _EXTRACTABLE_PATTERNS[1],
                        methods=group[:5],
                        class_name=cls["name"],
                        prefix=prefix,
                        line_range=(cls["line"], cls["end_line"]),
                        priority_score=35,
                    )
                )

    # Python AST enhanced analysis for nesting and params
    def _python_bonus_analysis(
        self, source: str, suggestions: list[dict[str, Any]], include_extractions: bool
    ) -> None:
        """Python-specific bonus analysis using AST for nesting, params, static methods."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    child.parent = node  # type: ignore

            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            name = node.name
            start, end = node.lineno, node.end_lineno or node.lineno

            self._check_depth(node, name, start, end, suggestions)
            self._check_param_count(node, name, start, suggestions)

            if include_extractions and isinstance(node, ast.FunctionDef):
                self._check_static_extraction(node, name, start, end, suggestions)

    # Nesting depth and parameter count checks

    def _check_depth(
        self,
        node: ast.AST,
        name: str,
        start: int,
        end: int,
        suggestions: list[dict[str, Any]],
    ) -> None:
        """Check and flag functions exceeding nesting depth threshold."""
        depth = self._get_nesting_depth(node)
        if depth > _PATTERN_RULES[2]["threshold"]:
            suggestions.append(
                self._make_pattern(
                    _PATTERN_RULES[2],
                    name=name,
                    actual=depth,
                    line_range=(start, end),
                    priority_score=40 + depth * 5,
                )
            )

    # Flag functions with too many parameters
    def _check_param_count(
        self,
        node: ast.AST,
        name: str,
        start: int,
        suggestions: list[dict[str, Any]],
    ) -> None:
        """Check and flag functions with too many parameters."""
        params = (
            len(node.args.args)
            + len(node.args.kwonlyargs)
            + (1 if node.args.vararg else 0)
            + (1 if node.args.kwarg else 0)
        )
        if params > _PATTERN_RULES[3]["threshold"]:
            suggestions.append(
                self._make_pattern(
                    _PATTERN_RULES[3],
                    name=name,
                    actual=params,
                    line_range=(start, start),
                    priority_score=30,
                )
            )

    # Static method detection for extraction
    def _check_static_extraction(
        self,
        node: ast.FunctionDef,
        name: str,
        start: int,
        end: int,
        suggestions: list[dict[str, Any]],
    ) -> None:
        """Check and flag methods that don't use self (static extraction candidate)."""
        parent = getattr(node, "parent", None)
        if isinstance(parent, ast.ClassDef) and not name.startswith("__"):
            if self._is_static_method(node):
                suggestions.append(
                    self._make_extraction(
                        _EXTRACTABLE_PATTERNS[2],
                        method=name,
                        class_name=parent.name,
                        line_range=(start, end),
                        priority_score=25,
                    )
                )

    def _get_nesting_depth(self, node: ast.AST) -> int:
        """Calculate the maximum nesting depth of a function."""
        max_depth = 0

        def walk(n: ast.AST, depth: int) -> None:
            nonlocal max_depth
            is_control = isinstance(
                n, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)
            )
            current = depth + (1 if is_control else 0)
            max_depth = max(max_depth, current)
            for child in ast.iter_child_nodes(n):
                walk(child, current)

        walk(node, 0)
        return max_depth

    def _is_static_method(self, node: ast.FunctionDef) -> bool:
        """Detect if a method body never references self/cls."""
        if not node.args.args:
            return True
        first_arg = node.args.args[0].arg
        # Pattern and extraction dict builders
        if first_arg not in ("self", "cls"):
            return True
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id == first_arg:
                if isinstance(child.ctx, ast.Load):
                    return False
        return True

    # Build pattern suggestion from rule template
    def _make_pattern(
        self, rule: dict[str, Any], priority_score: int = 50, **kwargs: Any
    ) -> dict[str, Any]:
        """Build a pattern suggestion dict from a rule template."""
        fmt_kwargs = {"threshold": rule["threshold"], **kwargs}
        message = rule["message"].format(**fmt_kwargs)
        result: dict[str, Any] = {
            "type": "pattern",
            "id": rule["id"],
            "name": rule["name"],
            "severity": rule["severity"],
            "message": message,
            "priority_score": priority_score,
        }
        if "line_range" in kwargs:
            lr = kwargs["line_range"]
            result["line_range"] = {"start": lr[0], "end": lr[1]}
        return result

    # Build extraction suggestion from rule template
    def _make_extraction(
        self, rule: dict[str, Any], priority_score: int = 50, **kwargs: Any
    ) -> dict[str, Any]:
        # Summary and error response helpers
        """Build an extraction suggestion dict from a rule template."""
        fmt_kwargs = {"threshold": rule.get("threshold", 0), **kwargs}
        message = rule["message"].format(**fmt_kwargs)
        result: dict[str, Any] = {
            "type": "extraction",
            "id": rule["id"],
            "name": rule["name"],
            "message": message,
            "priority_score": priority_score,
        }
        if "line_range" in kwargs:
            lr = kwargs["line_range"]
            result["line_range"] = {"start": lr[0], "end": lr[1]}
        return result

    # Human-readable summary of all suggestions
    def _make_summary(self, suggestions: list[dict[str, Any]]) -> str:
        """Build a human-readable summary of all suggestions."""
        if not suggestions:
            return "No significant refactoring issues found."
        critical = sum(1 for s in suggestions if s.get("severity") == "critical")
        major = sum(1 for s in suggestions if s.get("severity") == "major")
        minor = len(suggestions) - critical - major
        parts = []
        if critical:
            parts.append(f"{critical} critical")
        if major:
            parts.append(f"{major} major")
        if minor:
            parts.append(f"{minor} minor")
        return f"Found {', '.join(parts)} refactoring suggestions."

    # Input validation - fail fast with clear error messages
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate file_path argument."""
        file_path = arguments.get("file_path", "")
        if not file_path or not isinstance(file_path, str):
            raise ValueError("file_path is required and must be a string")
        return True

    # Standardized error response
    def _error_response(self, file_path: str, error: str) -> dict[str, Any]:
        """Return a standardized error response."""
        return {"file": file_path, "error": error, "suggestions": []}



