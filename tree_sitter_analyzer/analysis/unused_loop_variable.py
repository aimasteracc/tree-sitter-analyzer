"""Unused Loop Variable Detector.

Detects named loop variables that are never referenced inside the loop body:

  - unused_for_variable: `for x in items: process()` — x is never used
  - unused_for_in_variable: `for k in obj: obj[k]()` — (JS) k unused

These often indicate missing logic (forgot to use the variable) or that
the variable should be renamed to `_` to signal intentional non-use.

Supports Python and JavaScript/TypeScript.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"

ISSUE_UNUSED_FOR_VAR = "unused_for_variable"
ISSUE_UNUSED_FOR_OF_VAR = "unused_for_of_variable"
ISSUE_UNUSED_FOR_IN_VAR = "unused_for_in_variable"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_UNUSED_FOR_VAR: SEVERITY_LOW,
    ISSUE_UNUSED_FOR_OF_VAR: SEVERITY_LOW,
    ISSUE_UNUSED_FOR_IN_VAR: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_UNUSED_FOR_VAR: (
        "Loop variable is declared but never used in the loop body — "
        "rename to `_` or add the missing logic"
    ),
    ISSUE_UNUSED_FOR_OF_VAR: (
        "For-of loop variable is declared but never used — "
        "rename to `_` or add the missing logic"
    ),
    ISSUE_UNUSED_FOR_IN_VAR: (
        "For-in loop variable is declared but never used — "
        "rename to `_` or add the missing logic"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_UNUSED_FOR_VAR: "Rename the variable to `_` if intentionally unused, or use it in the body.",
    ISSUE_UNUSED_FOR_OF_VAR: "Rename the variable to `_` if intentionally unused, or use it in the body.",
    ISSUE_UNUSED_FOR_IN_VAR: "Rename the variable to `_` if intentionally unused, or use it in the body.",
}

_PY_EXT = frozenset({".py"})
_JS_EXT = frozenset({".js", ".jsx", ".ts", ".tsx"})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


def _is_underscore(name: str) -> bool:
    return name == "_" or name.startswith("_")


def _collect_identifiers(node: tree_sitter.Node) -> set[str]:
    names: set[str] = set()
    cursor = node.walk()
    reached_root = False
    while not reached_root:
        n = cursor.node
        if n is not None and n.type == "identifier":
            text = _safe_text(n)
            if text:
                names.add(text)
        if cursor.goto_first_child():
            continue
        if cursor.goto_next_sibling():
            continue
        retracing = True
        while retracing:
            if not cursor.goto_parent():
                retracing = False
                reached_root = True
            elif cursor.node == node:
                retracing = False
                reached_root = True
            elif cursor.goto_next_sibling():
                retracing = False
    return names


def _walk(node: tree_sitter.Node) -> Any:
    cursor = node.walk()
    reached_root = False
    while not reached_root:
        yield cursor.node
        if cursor.goto_first_child():
            continue
        if cursor.goto_next_sibling():
            continue
        retracing = True
        while retracing:
            if not cursor.goto_parent():
                retracing = False
                reached_root = True
            elif cursor.node == node:
                retracing = False
                reached_root = True
            elif cursor.goto_next_sibling():
                retracing = False


@dataclass(frozen=True)
class UnusedLoopVariableIssue:
    issue_type: str
    line: int
    column: int
    severity: str
    description: str
    suggestion: str
    context: str
    variable_name: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
            "variable_name": self.variable_name,
        }


@dataclass
class UnusedLoopVariableResult:
    file_path: str
    total_loops: int
    issues: list[UnusedLoopVariableIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_loops": self.total_loops,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class UnusedLoopVariableAnalyzer(BaseAnalyzer):
    """Detects named loop variables that are never used in the body."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = set(_PY_EXT | _JS_EXT)

    def analyze_file(
        self, file_path: str | Path,
    ) -> UnusedLoopVariableResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return UnusedLoopVariableResult(
                file_path=str(path),
                total_loops=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return UnusedLoopVariableResult(
                file_path=str(path),
                total_loops=0,
            )

        try:
            source = path.read_bytes()
        except OSError:
            return UnusedLoopVariableResult(
                file_path=str(path),
                total_loops=0,
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return UnusedLoopVariableResult(
                file_path=str(path),
                total_loops=0,
            )

        issues: list[UnusedLoopVariableIssue] = []
        total_loops = 0

        if ext in _PY_EXT:
            total_loops, issues = self._analyze_python(tree)
        elif ext in _JS_EXT:
            total_loops, issues = self._analyze_js(tree)

        return UnusedLoopVariableResult(
            file_path=str(path),
            total_loops=total_loops,
            issues=issues,
        )

    def _analyze_python(
        self, tree: tree_sitter.Tree,
    ) -> tuple[int, list[UnusedLoopVariableIssue]]:
        issues: list[UnusedLoopVariableIssue] = []
        total_loops = 0

        for node in _walk(tree.root_node):
            if node.type != "for_statement":
                continue
            total_loops += 1

            loop_var_nodes = self._get_py_for_variable(node)
            body_node = self._get_py_for_body(node)
            if not loop_var_nodes or body_node is None:
                continue

            body_idents = _collect_identifiers(body_node)

            for var_name, var_node in loop_var_nodes:
                if _is_underscore(var_name):
                    continue
                if var_name not in body_idents:
                    context = _safe_text(node)
                    issues.append(UnusedLoopVariableIssue(
                        issue_type=ISSUE_UNUSED_FOR_VAR,
                        line=var_node.start_point[0] + 1,
                        column=var_node.start_point[1],
                        severity=_SEVERITY_MAP[ISSUE_UNUSED_FOR_VAR],
                        description=_DESCRIPTIONS[ISSUE_UNUSED_FOR_VAR],
                        suggestion=_SUGGESTIONS[ISSUE_UNUSED_FOR_VAR],
                        context=context[:200],
                        variable_name=var_name,
                    ))

        return total_loops, issues

    def _get_py_for_variable(
        self, node: tree_sitter.Node,
    ) -> list[tuple[str, tree_sitter.Node]]:
        children = node.children
        in_idx = None
        for i, c in enumerate(children):
            if _safe_text(c) == "in":
                in_idx = i
                break
        if in_idx is None or in_idx < 2:
            return []

        vars_node = children[in_idx - 1]
        if vars_node.type == "identifier":
            return [(_safe_text(vars_node), vars_node)]
        if vars_node.type in ("pattern_list", "tuple_pattern", "pair"):
            result: list[tuple[str, tree_sitter.Node]] = []
            for child in vars_node.children:
                if child.type == "identifier":
                    result.append((_safe_text(child), child))
            return result
        return []

    def _get_py_for_body(
        self, node: tree_sitter.Node,
    ) -> tree_sitter.Node | None:
        for child in node.children:
            if child.type == "block":
                return child
        return None

    def _analyze_js(
        self, tree: tree_sitter.Tree,
    ) -> tuple[int, list[UnusedLoopVariableIssue]]:
        issues: list[UnusedLoopVariableIssue] = []
        total_loops = 0

        for node in _walk(tree.root_node):
            if node.type in ("for_statement", "for_in_statement"):
                total_loops += 1
                self._check_js_for(node, issues)

        return total_loops, issues

    def _check_js_for(
        self,
        node: tree_sitter.Node,
        issues: list[UnusedLoopVariableIssue],
    ) -> None:
        var_info = self._get_js_for_variable(node)
        body_node = self._get_js_for_body(node)
        if not var_info or body_node is None:
            return

        issue_type = ISSUE_UNUSED_FOR_OF_VAR
        body_idents = _collect_identifiers(body_node)

        for var_name, var_node in var_info:
            if _is_underscore(var_name):
                continue
            if var_name not in body_idents:
                context = _safe_text(node)
                issues.append(UnusedLoopVariableIssue(
                    issue_type=issue_type,
                    line=var_node.start_point[0] + 1,
                    column=var_node.start_point[1],
                    severity=_SEVERITY_MAP[issue_type],
                    description=_DESCRIPTIONS[issue_type],
                    suggestion=_SUGGESTIONS[issue_type],
                    context=context[:200],
                    variable_name=var_name,
                ))

    def _get_js_for_variable(
        self, node: tree_sitter.Node,
    ) -> list[tuple[str, tree_sitter.Node]]:
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node and name_node.type == "identifier":
                    return [(_safe_text(name_node), name_node)]
            if child.type == "identifier":
                return [(_safe_text(child), child)]
        return []

    def _get_js_for_body(
        self, node: tree_sitter.Node,
    ) -> tree_sitter.Node | None:
        for child in node.children:
            if child.type in ("statement_block", "block"):
                return child
        return None
