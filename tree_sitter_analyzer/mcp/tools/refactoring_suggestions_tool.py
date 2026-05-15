#!/usr/bin/env python3
"""
Refactoring Suggestions MCP Tool

Analyzes files and returns concrete, actionable refactoring suggestions
with exact function names, line ranges, and extraction targets.

Uses tree-sitter for cross-language element extraction (all 15 languages),
with Python-AST enhanced analysis (nesting, params, static detection) as bonus.
"""

import ast
from pathlib import Path
from typing import Any

from ...utils import setup_logger
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

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "refactoring_suggestions",
            "description": (
                "Analyze a file and return concrete, actionable refactoring suggestions "
                "with exact function names, line ranges, and extraction targets. "
                "Use this BEFORE editing to plan your refactoring, or AFTER editing to find remaining issues."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
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
                "include_extractions": {
                    "type": "boolean",
                    "description": "Include specific extraction targets (default: true)",
                    "default": True,
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        max_suggestions = arguments.get("max_suggestions", 10)
        include_extractions = arguments.get("include_extractions", True)

        resolved = self.resolve_and_validate_file_path(file_path)
        if not resolved:
            return self._error_response(
                file_path, "File not found or outside project boundary"
            )

        try:
            source = Path(resolved).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return self._error_response(file_path, f"Cannot read file: {e}")

        # Primary: tree-sitter based analysis (cross-language)
        analysis = extract_elements(resolved, self.project_root)

        suggestions = self._analyze_via_treesitter(
            resolved, source, analysis, max_suggestions, include_extractions
        )

        # Bonus: Python-AST enhanced analysis for deeper insights
        ext = Path(resolved).suffix.lower()
        if ext == ".py" and analysis:
            self._python_bonus_analysis(
                resolved, source, suggestions, include_extractions, max_suggestions
            )

        suggestions.sort(key=lambda s: s.get("priority_score", 0), reverse=True)
        suggestions = suggestions[:max_suggestions]

        return {
            "file": resolved,
            "total_suggestions": len(suggestions),
            "summary": self._make_summary(suggestions),
            "suggestions": suggestions,
        }

    def _analyze_via_treesitter(
        self,
        file_path: str,
        source: str,
        analysis: Any,
        max_suggestions: int,
        include_extractions: bool,
    ) -> list[dict[str, Any]]:
        """Cross-language analysis using tree-sitter extracted elements."""
        suggestions: list[dict[str, Any]] = []
        lines = source.splitlines()
        line_count = len(lines)

        # P001: God file
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

        # P002: Long functions — from tree-sitter elements
        functions = get_functions(analysis)
        rule = _PATTERN_RULES[1]
        for func in functions:
            if func["lines"] > rule["threshold"]:
                suggestions.append(
                    self._make_pattern(
                        rule,
                        name=func["name"],
                        actual=func["lines"],
                        line_range=(func["line"], func["end_line"]),
                        priority_score=min(90, func["lines"]),
                    )
                )

        # Extraction patterns from tree-sitter class data
        if include_extractions:
            classes = get_classes(analysis)
            for cls in classes:
                method_count = cls["method_count"]
                method_names = cls["method_names"]

                # E004: Large class
                rule_e4 = _EXTRACTABLE_PATTERNS[3]
                threshold = rule_e4["threshold"]
                if method_count > threshold:
                    suggestions.append(
                        self._make_extraction(
                            rule_e4,
                            name=cls["name"],
                            actual=method_count,
                            threshold=threshold,
                            line_range=(cls["line"], cls["end_line"]),
                            priority_score=50,
                        )
                    )

                # E002: Methods with common prefix
                if len(method_names) >= 3:
                    prefixes: dict[str, list[str]] = {}
                    for m in method_names:
                        if "_" in m and not m.startswith("_"):
                            prefix = m.split("_")[0]
                            prefixes.setdefault(prefix, []).append(m)

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

        return suggestions

    def _python_bonus_analysis(
        self,
        file_path: str,
        source: str,
        suggestions: list[dict[str, Any]],
        include_extractions: bool,
        max_suggestions: int,
    ) -> None:
        """Python-AST enhanced analysis for nesting, params, static detection."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                start_line = node.lineno
                end_line = node.end_lineno or start_line

                # P003: Deep nesting
                max_depth = self._get_nesting_depth(node)
                rule = _PATTERN_RULES[2]
                if max_depth > rule["threshold"]:
                    suggestions.append(
                        self._make_pattern(
                            rule,
                            name=name,
                            actual=max_depth,
                            line_range=(start_line, end_line),
                            priority_score=40 + max_depth * 5,
                        )
                    )

                # P004: Too many parameters
                param_count = len(node.args.args)
                if node.args.kwonlyargs:
                    param_count += len(node.args.kwonlyargs)
                if node.args.vararg:
                    param_count += 1
                if node.args.kwarg:
                    param_count += 1
                rule = _PATTERN_RULES[3]
                if param_count > rule["threshold"]:
                    suggestions.append(
                        self._make_pattern(
                            rule,
                            name=name,
                            actual=param_count,
                            line_range=(start_line, start_line),
                            priority_score=30,
                        )
                    )

                # E003: Method doesn't use self
                if include_extractions and isinstance(node, ast.FunctionDef):
                    parent = getattr(node, "parent", None)
                    if isinstance(parent, ast.ClassDef) and not name.startswith("__"):
                        if self._is_static_method(node):
                            suggestions.append(
                                self._make_extraction(
                                    _EXTRACTABLE_PATTERNS[2],
                                    method=name,
                                    class_name=parent.name,
                                    line_range=(start_line, end_line),
                                    priority_score=25,
                                )
                            )

            # Mark parent class for method detection
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    child.parent = node  # type: ignore

    def _get_nesting_depth(self, node: ast.AST) -> int:
        max_depth = 0

        def walk(n: ast.AST, depth: int) -> None:
            nonlocal max_depth
            is_control = isinstance(
                n,
                (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler),
            )
            current = depth + (1 if is_control else 0)
            max_depth = max(max_depth, current)
            for child in ast.iter_child_nodes(n):
                walk(child, current)

        walk(node, 0)
        return max_depth

    def _is_static_method(self, node: ast.FunctionDef) -> bool:
        if not node.args.args:
            return True
        first_arg = node.args.args[0].arg
        if first_arg not in ("self", "cls"):
            return True
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id == first_arg:
                if isinstance(child.ctx, ast.Load):
                    return False
        return True

    def _make_pattern(
        self, rule: dict[str, Any], priority_score: int = 50, **kwargs: Any
    ) -> dict[str, Any]:
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
        if "parent" in kwargs and kwargs["parent"]:
            result["parent"] = kwargs["parent"]
        return result

    def _make_extraction(
        self, rule: dict[str, Any], priority_score: int = 50, **kwargs: Any
    ) -> dict[str, Any]:
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

    def _make_summary(self, suggestions: list[dict[str, Any]]) -> str:
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

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        file_path = arguments.get("file_path", "")
        if not file_path or not isinstance(file_path, str):
            raise ValueError("file_path is required and must be a string")
        return True

    def _error_response(self, file_path: str, error: str) -> dict[str, Any]:
        return {
            "file": file_path,
            "error": error,
            "suggestions": [],
        }
