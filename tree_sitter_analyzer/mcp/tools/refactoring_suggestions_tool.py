#!/usr/bin/env python3
"""
Refactoring Suggestions MCP Tool

Analyzes files and returns concrete, actionable refactoring suggestions
with exact function names, line ranges, and extraction targets.

This is the "killer feature" for AI agents — it tells them WHAT to do next,
not just that something is wrong.
"""

import ast
import re
from pathlib import Path
from typing import Any

from ...utils import setup_logger
from .base_tool import BaseMCPTool

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
    {
        "id": "P005",
        "name": "duplicate_import_pattern",
        "severity": "minor",
        "threshold": 3,
        "message": "Import '{module}' appears {actual} times. Consolidate.",
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

        ext = Path(resolved).suffix.lower()
        if ext != ".py":
            return self._generic_suggestions(
                resolved, source, ext, max_suggestions, include_extractions
            )

        return self._python_suggestions(
            resolved, source, max_suggestions, include_extractions
        )

    def _python_suggestions(
        self,
        file_path: str,
        source: str,
        max_suggestions: int,
        include_extractions: bool,
    ) -> dict[str, Any]:
        """Analyze Python file using AST for precise suggestions."""
        suggestions: list[dict[str, Any]] = []
        lines = source.splitlines()
        line_count = len(lines)

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return self._generic_suggestions(
                file_path, source, ".py", max_suggestions, include_extractions
            )

        # P001: God file
        if line_count > _PATTERN_RULES[0]["threshold"]:
            suggestions.append(
                self._make_pattern(
                    _PATTERN_RULES[0],
                    actual=line_count,
                    priority_score=min(100, line_count // 10),
                )
            )

        # Walk AST for function/class analysis
        class_info: dict[str, list[dict[str, Any]]] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._analyze_function(
                    node, lines, suggestions, class_info, include_extractions
                )
            elif isinstance(node, ast.ClassDef):
                self._analyze_class(node, suggestions, class_info, include_extractions)

        # Extraction suggestions
        if include_extractions:
            self._find_extraction_targets(tree, lines, suggestions, class_info)

        # Sort by priority and limit
        suggestions.sort(key=lambda s: s.get("priority_score", 0), reverse=True)
        suggestions = suggestions[:max_suggestions]

        return {
            "file": file_path,
            "total_suggestions": len(suggestions),
            "summary": self._make_summary(suggestions),
            "suggestions": suggestions,
        }

    def _analyze_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        lines: list[str],
        suggestions: list[dict[str, Any]],
        class_info: dict[str, list[dict[str, Any]]],
        include_extractions: bool = True,
    ) -> None:
        """Analyze a function for anti-patterns."""
        name = node.name
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        func_lines = end_line - start_line + 1

        # Find parent class
        parent_class = None
        if isinstance(getattr(node, "parent", None), ast.ClassDef):
            parent_class = node.parent.name  # type: ignore

        # P002: Long function
        rule = _PATTERN_RULES[1]
        if func_lines > rule["threshold"]:
            suggestions.append(
                self._make_pattern(
                    rule,
                    name=name,
                    actual=func_lines,
                    line_range=(start_line, end_line),
                    parent=parent_class,
                    priority_score=min(90, func_lines),
                )
            )

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
                    parent=parent_class,
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
                    parent=parent_class,
                    priority_score=30,
                )
            )

        # E003: Method doesn't use self → move to helper
        if (
            include_extractions
            and parent_class
            and isinstance(node, ast.FunctionDef)
            and not isinstance(node, ast.AsyncFunctionDef)
            and not name.startswith("__")
        ):
            if self._is_static_method(node):
                suggestions.append(
                    self._make_extraction(
                        _EXTRACTABLE_PATTERNS[2],
                        method=name,
                        class_name=parent_class,
                        line_range=(start_line, end_line),
                        priority_score=25,
                    )
                )

    def _analyze_class(
        self,
        node: ast.ClassDef,
        suggestions: list[dict[str, Any]],
        class_info: dict[str, list[dict[str, Any]]],
        include_extractions: bool = True,
    ) -> None:
        """Analyze a class for anti-patterns."""
        if not include_extractions:
            return

        methods = [
            n.name
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        # E004: Large class
        rule = _EXTRACTABLE_PATTERNS[3]
        threshold = rule["threshold"]
        if len(methods) > threshold:
            suggestions.append(
                self._make_extraction(
                    rule,
                    name=node.name,
                    actual=len(methods),
                    threshold=threshold,
                    line_range=(node.lineno, node.end_lineno or node.lineno),
                    priority_score=50,
                )
            )

        # E002: Methods with common prefix
        if len(methods) >= 3:
            prefixes: dict[str, list[str]] = {}
            for m in methods:
                if "_" in m and not m.startswith("_"):
                    prefix = m.split("_")[0]
                    prefixes.setdefault(prefix, []).append(m)

            for prefix, group in prefixes.items():
                if len(group) >= 3:
                    rule = _EXTRACTABLE_PATTERNS[1]
                    suggestions.append(
                        self._make_extraction(
                            rule,
                            methods=group[:5],
                            class_name=node.name,
                            prefix=prefix,
                            line_range=(node.lineno, node.end_lineno or node.lineno),
                            priority_score=35,
                        )
                    )

    def _find_extraction_targets(
        self,
        tree: ast.Module,
        lines: list[str],
        suggestions: list[dict[str, Any]],
        class_info: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Find specific extraction targets for helper files."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Mark parent info for nested functions
                for child in ast.walk(node):
                    if hasattr(child, "parent"):
                        pass
                    child.parent = node  # type: ignore

            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if hasattr(child, "parent"):
                        pass
                    child.parent = node  # type: ignore

    def _get_nesting_depth(self, node: ast.AST) -> int:
        """Calculate maximum nesting depth of control flow."""
        max_depth = 0

        def walk(n: ast.AST, depth: int) -> None:
            nonlocal max_depth
            is_control = isinstance(
                n,
                (
                    ast.If,
                    ast.For,
                    ast.While,
                    ast.With,
                    ast.Try,
                    ast.ExceptHandler,
                ),
            )
            current = depth + (1 if is_control else 0)
            max_depth = max(max_depth, current)
            for child in ast.iter_child_nodes(n):
                walk(child, current)

        walk(node, 0)
        return max_depth

    def _is_static_method(self, node: ast.FunctionDef) -> bool:
        """Check if a method never uses 'self'."""
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

    def _generic_suggestions(
        self,
        file_path: str,
        source: str,
        ext: str,
        max_suggestions: int,
        include_extractions: bool,
    ) -> dict[str, Any]:
        """Provide suggestions for non-Python files using heuristic analysis."""
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

        # Heuristic: detect long functions by indentation patterns
        func_starts: list[tuple[str, int]] = []
        if ext in (".java", ".kt", ".cs", ".cpp", ".c", ".go"):
            func_starts = self._detect_functions_regex(source, ext)

        for name, start in func_starts:
            end = self._find_function_end(lines, start, ext)
            func_lines = end - start + 1

            if func_lines > _PATTERN_RULES[1]["threshold"]:
                suggestions.append(
                    self._make_pattern(
                        _PATTERN_RULES[1],
                        name=name,
                        actual=func_lines,
                        line_range=(start, end),
                        priority_score=min(90, func_lines),
                    )
                )

        suggestions.sort(key=lambda s: s.get("priority_score", 0), reverse=True)
        suggestions = suggestions[:max_suggestions]

        return {
            "file": file_path,
            "total_suggestions": len(suggestions),
            "summary": self._make_summary(suggestions),
            "suggestions": suggestions,
        }

    _FUNC_PATTERNS: dict[str, str] = {
        ".java": r"^\s*(?:public|private|protected|static|\s)+[\w<>]+\s+(\w+)\s*\(",
        ".kt": r"^\s*(?:fun)\s+(\w+)\s*\(",
        ".cs": r"^\s*(?:public|private|protected|static|virtual|override|\s)+[\w<>]+\s+(\w+)\s*\(",
        ".cpp": r"^\s*[\w:*&<>]+\s+(\w+)\s*\(",
        ".c": r"^\s*[\w:*&]+\s+(\w+)\s*\(",
        ".go": r"^\s*func\s+(?:\([^)]*\)\s+)?(\w+)\s*\(",
    }

    def _detect_functions_regex(self, source: str, ext: str) -> list[tuple[str, int]]:
        """Detect function definitions using regex for non-Python files."""
        pattern = self._FUNC_PATTERNS.get(ext, "")
        if not pattern:
            return []

        results: list[tuple[str, int]] = []
        for i, line in enumerate(source.splitlines(), 1):
            match = re.match(pattern, line)
            if match:
                name = match.group(1)
                if name not in ("if", "for", "while", "switch", "catch", "return"):
                    results.append((name, i))
        return results

    def _find_function_end(self, lines: list[str], start: int, ext: str) -> int:
        """Find the end line of a function by brace matching."""
        brace_count = 0
        found_open = False

        for i in range(start - 1, len(lines)):
            for ch in lines[i]:
                if ch == "{":
                    brace_count += 1
                    found_open = True
                elif ch == "}":
                    brace_count -= 1
                    if found_open and brace_count == 0:
                        return i + 1

        return len(lines)

    def _make_pattern(
        self,
        rule: dict[str, Any],
        priority_score: int = 50,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a pattern detection result."""
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
        self,
        rule: dict[str, Any],
        priority_score: int = 50,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create an extraction suggestion result."""
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
        """Generate a one-line summary of findings."""
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
        """Validate tool arguments."""
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
