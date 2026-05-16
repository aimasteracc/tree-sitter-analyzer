#!/usr/bin/env python3
"""
Refactoring Suggestions MCP Tool

Analyzes files and returns concrete, actionable refactoring suggestions
with exact function names, line ranges, extraction targets, and code skeletons.

Uses tree-sitter for cross-language element extraction (all 15 languages),
with Python-AST enhanced analysis (nesting, params, static detection) as bonus.
"""

import ast
import textwrap
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
                "Refactoring plan: exact function names, line ranges, extraction targets. "
                "Use BEFORE editing to plan, or AFTER to find remaining issues."
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

        analysis = extract_elements(resolved, self.project_root)
        suggestions = self._analyze_via_treesitter(
            resolved, source, analysis, max_suggestions, include_extractions
        )

        ext = Path(resolved).suffix.lower()
        if ext == ".py" and analysis:
            self._python_bonus_analysis(source, suggestions, include_extractions)

        self._build_precise_plans(resolved, source, analysis, suggestions)

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
        rule_e4 = _EXTRACTABLE_PATTERNS[3]
        for cls in get_classes(analysis):
            if cls["method_count"] > rule_e4["threshold"]:
                suggestions.append(
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
        prefixes: dict[str, list[str]] = {}
        for m in cls["method_names"]:
            if "_" in m and not m.startswith("_"):
                prefixes.setdefault(m.split("_")[0], []).append(m)
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

    def _build_precise_plans(
        self,
        file_path: str,
        source: str,
        analysis: Any,
        suggestions: list[dict[str, Any]],
    ) -> None:
        """Attach precise extraction plans to long_function suggestions."""
        if not analysis:
            return

        lines = source.splitlines()
        functions = get_functions(analysis)
        func_by_line = {f["line"]: f for f in functions}

        for s in suggestions:
            if s.get("name") != "long_function" or "line_range" not in s:
                continue
            start = s["line_range"]["start"]
            func = func_by_line.get(start)
            if not func:
                continue

            plan = self._extract_plan_for_func(file_path, lines, func, source)
            if plan:
                s["precise_plan"] = plan

    def _extract_plan_for_func(
        self,
        file_path: str,
        lines: list[str],
        func: dict[str, Any],
        source: str,
    ) -> dict[str, Any] | None:
        """Build a precise extraction plan for one long function."""
        start = func["line"]
        end = func["end_line"]
        func_name = func["name"]
        func_lines = lines[start - 1 : end]

        blocks = self._find_extractable_blocks(func_lines, start)
        if not blocks:
            return None

        ext = Path(file_path).suffix.lower()
        stem = Path(file_path).stem
        parent = str(Path(file_path).parent)
        helper_module = (
            f"{parent}/_{stem}_helpers.py" if parent != "." else f"_{stem}_helpers.py"
        )

        func_src = "\n".join(func_lines)
        func_assigned = self._collect_assigned_names(func_src)
        func_params = func.get("parameters", [])

        targets = []
        for i, (b_start, b_end, hint) in enumerate(blocks[:3]):
            helper_name = self._suggest_helper_name(func_name, hint, i)
            block_src = "\n".join(lines[b_start - 1 : b_end])
            params = self._infer_params_for_block(block_src, func_assigned, func_params)
            returns = self._infer_returns(block_src)
            skeleton = self._make_skeleton(
                helper_name, params, returns, lines[b_start - 1 : b_end], ext
            )
            targets.append(
                {
                    "helper_name": helper_name,
                    "extract_lines": f"{b_start}-{b_end}",
                    "params": params,
                    "returns": returns,
                    "hint": hint,
                    "skeleton": skeleton,
                }
            )

        return {
            "function": func_name,
            "function_lines": f"{start}-{end}",
            "helper_module": helper_module,
            "extractions": targets,
            "steps": [
                f"1. Create {helper_module} with extracted helpers",
                f"2. In {Path(file_path).name}, add: from _{stem}_helpers import {', '.join(t['helper_name'] for t in targets)}",
                f"3. Replace lines in '{func_name}' with calls to extracted helpers",
                f"4. Re-run refactoring_suggestions(file_path='{file_path}') to verify",
            ],
        }

    def _find_extractable_blocks(
        self, func_lines: list[str], abs_start: int
    ) -> list[tuple[int, int, str]]:
        """Identify logical blocks within a function body that can be extracted.

        Returns list of (abs_start_line, abs_end_line, block_hint).
        """
        blocks: list[tuple[int, int, str]] = []
        n = len(func_lines)
        if n == 0:
            return blocks

        body_indent = self._body_indent(func_lines)
        if body_indent <= 0:
            return blocks

        i = 0
        while i < n:
            line = func_lines[i]
            stripped = line.strip()

            if not stripped or stripped.startswith("#"):
                i += 1
                continue

            cur_indent = len(line) - len(line.lstrip())
            if cur_indent < body_indent:
                i += 1
                continue

            if cur_indent == body_indent:
                block_start = i
                hint = self._classify_line(stripped)
                j = i + 1
                while j < n:
                    next_line = func_lines[j]
                    next_stripped = next_line.strip()
                    if not next_stripped:
                        j += 1
                        continue
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent < body_indent:
                        break
                    if next_indent == body_indent:
                        if self._is_block_continuation(next_stripped, stripped, hint):
                            j += 1
                            continue
                        break
                    j += 1

                block_len = j - block_start
                if block_len >= 5:
                    blocks.append((abs_start + block_start, abs_start + j - 1, hint))
                i = j
            else:
                i += 1

        blocks.sort(key=lambda b: -(b[1] - b[0]))
        return blocks

    def _body_indent(self, func_lines: list[str]) -> int:
        """Find the indentation level of the function body."""
        for line in func_lines[1:]:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            return len(line) - len(line.lstrip())
        return 0

    def _classify_line(self, stripped: str) -> str:
        """Classify a statement for extraction hint."""
        if stripped.startswith(("if ", "elif ", "else")):
            return "conditional"
        if stripped.startswith(("for ", "while ")):
            return "loop"
        if stripped.startswith(("try:", "with ")):
            return "resource"
        if "=" in stripped and not stripped.startswith(("def ", "class ", "return ")):
            return "computation"
        if stripped.startswith("return "):
            return "result_building"
        return "logic"

    def _is_block_continuation(
        self, next_stripped: str, _prev_stripped: str, hint: str
    ) -> bool:
        """Check if next line continues the current logical block.

        Keeps try/except/finally, if/elif/else together as one block.
        """
        if hint == "resource" and next_stripped.startswith(
            ("except", "else:", "finally:")
        ):
            return True
        if hint == "conditional" and next_stripped.startswith(
            ("elif ", "else:", "else:")
        ):
            return True
        return False

    def _suggest_helper_name(self, func_name: str, hint: str, index: int) -> str:
        """Generate a helper function name from the parent function and block type."""
        suffix_map = {
            "conditional": "check_conditions",
            "loop": "process_items",
            "resource": "handle_resource",
            "computation": "compute",
            "result_building": "build_result",
            "logic": "step",
        }
        suffix = suffix_map.get(hint, "step")
        if index == 0:
            return f"_{func_name}_{suffix}"
        return f"_{func_name}_{suffix}_{index + 1}"

    def _collect_assigned_names(self, source: str) -> set[str]:
        """Collect all names assigned in a function body (locals + params)."""
        try:
            tree = ast.parse(textwrap.dedent(source))
        except SyntaxError:
            return set()

        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.add(node.id)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
        return names

    def _infer_params_for_block(
        self,
        block_src: str,
        func_assigned: set[str],
        func_params: list[Any],
    ) -> list[str]:
        """Infer parameters needed by extracted block.

        A name needs to be a parameter if the block uses it but doesn't
        define it locally, AND it exists in the enclosing function's scope.
        """
        try:
            tree = ast.parse(textwrap.dedent(block_src))
        except SyntaxError:
            return []

        used: set[str] = set()
        block_assigned: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used.add(node.id)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                block_assigned.add(node.id)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                used.add(node.value.id)

        # Names used in block that come from the enclosing function's scope
        outer_deps = (used - block_assigned) & func_assigned
        # Exclude builtins and common globals
        excluded = {
            "self",
            "cls",
            "True",
            "False",
            "None",
            "print",
            "len",
            "range",
            "str",
            "int",
            "list",
            "dict",
            "set",
            "tuple",
            "type",
            "isinstance",
            "hasattr",
            "getattr",
            "setattr",
            "sorted",
            "max",
            "min",
            "enumerate",
            "zip",
            "map",
            "filter",
            "any",
            "all",
            "abs",
            "round",
            "reversed",
        }
        params = sorted(outer_deps - excluded)
        return params[:6]

    def _infer_returns(self, block_src: str) -> list[str]:
        """Infer what the extracted block produces (variable names assigned).

        Returns top-level assignments, plus assignments in the body of
        try/with/if blocks at the top level.
        """
        try:
            tree = ast.parse(textwrap.dedent(block_src))
        except SyntaxError:
            return []

        def _collect_from_statements(stmts: list[Any]) -> list[str]:
            assigned: list[str] = []
            for node in stmts:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            assigned.append(target.id)
                        elif isinstance(target, ast.Tuple):
                            for elt in target.elts:
                                if isinstance(elt, ast.Name):
                                    assigned.append(elt.id)
                elif isinstance(node, ast.AnnAssign) and isinstance(
                    node.target, ast.Name
                ):
                    assigned.append(node.target.id)
                elif isinstance(node, ast.AugAssign) and isinstance(
                    node.target, ast.Name
                ):
                    assigned.append(node.target.id)
            return assigned

        top_assigned: list[str] = []
        for node in ast.iter_child_nodes(tree):
            top_assigned.extend(_collect_from_statements([node]))
            if isinstance(node, ast.Try):
                top_assigned.extend(_collect_from_statements(node.body))
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                top_assigned.extend(_collect_from_statements(node.body))
            elif isinstance(node, ast.If):
                top_assigned.extend(_collect_from_statements(node.body))

        seen = set()
        unique = []
        for a in top_assigned:
            if a not in seen:
                seen.add(a)
                unique.append(a)
        return unique[:4]

    def _make_skeleton(
        self,
        name: str,
        params: list[str],
        returns: list[str],
        block_lines: list[str],
        ext: str,
    ) -> str:
        """Generate a code skeleton for the extracted helper."""
        if ext != ".py":
            return f"// TODO: extract {name}({', '.join(params)})"

        param_str = ", ".join(params)
        dedented = textwrap.dedent("\n".join(block_lines))
        clean = dedented.strip()

        lines = [f"def {name}({param_str}):"]
        for bl in clean.splitlines():
            lines.append(f"    {bl}")
        if returns:
            lines.append(f"    return {', '.join(returns)}")

        return "\n".join(lines)

    def _python_bonus_analysis(
        self, source: str, suggestions: list[dict[str, Any]], include_extractions: bool
    ) -> None:
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

            if include_extractions and isinstance(node, ast.FunctionDef):
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
        return {"file": file_path, "error": error, "suggestions": []}
