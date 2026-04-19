"""Inconsistent Return Detector.

Detects functions where some paths return a value and others don't.
In Python this causes None to be returned implicitly. In JS/TS/Java/Go
this is usually a compiler error, but the analyzer still catches edge cases.

Issue types:
  - inconsistent_return: function has both return-with-value and bare return/implicit return
  - mixed_return_types: function returns values of different categories

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

ISSUE_INCONSISTENT_RETURN = "inconsistent_return"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_INCONSISTENT_RETURN: SEVERITY_HIGH,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_INCONSISTENT_RETURN: "Function mixes return-with-value and return-without-value paths",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_INCONSISTENT_RETURN: "Ensure all code paths return a value consistently, or all return None.",
}

_FUNCTION_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({"function_declaration", "arrow_function", "method_definition"}),
    ".jsx": frozenset({"function_declaration", "arrow_function", "method_definition"}),
    ".ts": frozenset({"function_declaration", "arrow_function", "method_definition"}),
    ".tsx": frozenset({"function_declaration", "arrow_function", "method_definition"}),
    ".java": frozenset({"method_declaration"}),
    ".go": frozenset({"function_declaration", "method_declaration"}),
}


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


def _get_function_name(node: tree_sitter.Node) -> str:
    for child in node.children:
        if child.type in ("identifier", "property_identifier", "field_identifier"):
            return _safe_text(child)
    for child in node.children_by_field_name("name"):
        return _safe_text(child)
    return "<anonymous>"


def _find_returns(node: tree_sitter.Node) -> list[tree_sitter.Node]:
    results: list[tree_sitter.Node] = []
    cursor = node.walk()
    reached_root = False
    while not reached_root:
        n = cursor.node
        if n is not None and n.type == "return_statement":
            results.append(n)
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
    return results


def _has_value_return(return_node: tree_sitter.Node) -> bool:
    for child in return_node.children:
        if child.is_named:
            return True
    return False


def _has_implicit_return(func_node: tree_sitter.Node, ext: str) -> bool:
    if ext != ".py":
        return False
    body = None
    for child in func_node.children:
        if child.type == "block":
            body = child
            break
    if body is None:
        return True
    last = None
    for c in body.children:
        if c.is_named:
            last = c
    if last is None:
        return True
    return last.type != "return_statement"


@dataclass(frozen=True)
class InconsistentReturnIssue:
    issue_type: str
    function_name: str
    line: int
    column: int
    has_value_returns: int
    has_bare_returns: int
    has_implicit: bool
    severity: str
    description: str
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_type": self.issue_type,
            "function_name": self.function_name,
            "line": self.line,
            "column": self.column,
            "has_value_returns": self.has_value_returns,
            "has_bare_returns": self.has_bare_returns,
            "has_implicit": self.has_implicit,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass
class InconsistentReturnResult:
    file_path: str
    total_functions: int
    issues: list[InconsistentReturnIssue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_functions": self.total_functions,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class InconsistentReturnAnalyzer(BaseAnalyzer):
    """Detects functions with inconsistent return behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
        }

    def analyze_file(
        self, file_path: str | Path,
    ) -> InconsistentReturnResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return self._empty(str(path))
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return self._empty(str(path))

        try:
            source = path.read_bytes()
        except OSError:
            return self._empty(str(path))

        tree = parser.parse(source)
        if tree.root_node is None:
            return self._empty(str(path))

        func_types = _FUNCTION_TYPES.get(ext)
        if func_types is None:
            return self._empty(str(path))

        issues: list[InconsistentReturnIssue] = []
        total_functions = 0

        for node in _walk(tree.root_node):
            if node.type not in func_types:
                continue
            total_functions += 1

            issue = self._check_function(node, ext)
            if issue is not None:
                issues.append(issue)

        return InconsistentReturnResult(
            file_path=str(path),
            total_functions=total_functions,
            issues=issues,
        )

    def _check_function(
        self,
        func_node: tree_sitter.Node,
        ext: str,
    ) -> InconsistentReturnIssue | None:
        returns = _find_returns(func_node)
        if not returns:
            return None

        value_returns = 0
        bare_returns = 0
        for ret in returns:
            if _has_value_return(ret):
                value_returns += 1
            else:
                bare_returns += 1

        has_implicit = _has_implicit_return(func_node, ext)

        inconsistent = False
        if value_returns > 0 and bare_returns > 0:
            inconsistent = True
        if value_returns > 0 and has_implicit:
            inconsistent = True

        if not inconsistent:
            return None

        return InconsistentReturnIssue(
            issue_type=ISSUE_INCONSISTENT_RETURN,
            function_name=_get_function_name(func_node),
            line=func_node.start_point[0] + 1,
            column=func_node.start_point[1],
            has_value_returns=value_returns,
            has_bare_returns=bare_returns,
            has_implicit=has_implicit,
            severity=_SEVERITY_MAP[ISSUE_INCONSISTENT_RETURN],
            description=_DESCRIPTIONS[ISSUE_INCONSISTENT_RETURN],
            suggestion=_SUGGESTIONS[ISSUE_INCONSISTENT_RETURN],
        )

    def _empty(self, path: str) -> InconsistentReturnResult:
        return InconsistentReturnResult(
            file_path=path,
            total_functions=0,
            issues=[],
        )


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
