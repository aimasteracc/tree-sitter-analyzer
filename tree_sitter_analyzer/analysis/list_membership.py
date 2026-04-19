"""List-in-Membership Performance Detector.

Detects membership tests using list literals where a set literal would
be more efficient:

  - list_in_membership: `x in [1, 2, 3]` → use `{1, 2, 3}` for O(1) lookup
  - list_not_in_membership: `x not in [...]` → use set

List membership is O(n); set membership is O(1). For small lists the
difference is negligible, but using sets is a consistent best practice.

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

ISSUE_LIST_IN = "list_in_membership"
ISSUE_LIST_NOT_IN = "list_not_in_membership"
ISSUE_ARRAY_INCLUDES = "array_includes_literal"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_LIST_IN: SEVERITY_LOW,
    ISSUE_LIST_NOT_IN: SEVERITY_LOW,
    ISSUE_ARRAY_INCLUDES: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_LIST_IN: (
        "Membership test using list literal: `x in [...]` is O(n) — "
        "use `x in {...}` for O(1) set lookup"
    ),
    ISSUE_LIST_NOT_IN: (
        "Membership test using list literal: `x not in [...]` is O(n) — "
        "use `x not in {...}` for O(1) set lookup"
    ),
    ISSUE_ARRAY_INCLUDES: (
        "Array includes with array literal: `[...].includes(x)` creates "
        "a temporary array — use `new Set([...]).has(x)` for repeated checks"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_LIST_IN: "Replace `[...]` with `{...}` for O(1) membership test.",
    ISSUE_LIST_NOT_IN: "Replace `[...]` with `{...}` for O(1) membership test.",
    ISSUE_ARRAY_INCLUDES: "Use `new Set([...]).has(x)` for efficient membership.",
}

_PY_EXT = frozenset({".py"})
_JS_EXT = frozenset({".js", ".jsx", ".ts", ".tsx"})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


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
class ListMembershipIssue:
    issue_type: str
    line: int
    column: int
    severity: str
    description: str
    suggestion: str
    context: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
        }


@dataclass
class ListMembershipResult:
    file_path: str
    total_membership_tests: int
    issues: list[ListMembershipIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_membership_tests": self.total_membership_tests,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class ListMembershipAnalyzer(BaseAnalyzer):
    """Detects membership tests using list literals instead of sets."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = set(_PY_EXT | _JS_EXT)

    def analyze_file(
        self, file_path: str | Path,
    ) -> ListMembershipResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return ListMembershipResult(
                file_path=str(path),
                total_membership_tests=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ListMembershipResult(
                file_path=str(path),
                total_membership_tests=0,
            )

        try:
            source = path.read_bytes()
        except OSError:
            return ListMembershipResult(
                file_path=str(path),
                total_membership_tests=0,
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return ListMembershipResult(
                file_path=str(path),
                total_membership_tests=0,
            )

        issues: list[ListMembershipIssue] = []
        total_membership_tests = 0

        if ext in _PY_EXT:
            total_membership_tests, issues = self._analyze_python(tree)
        elif ext in _JS_EXT:
            total_membership_tests, issues = self._analyze_js(tree)

        return ListMembershipResult(
            file_path=str(path),
            total_membership_tests=total_membership_tests,
            issues=issues,
        )

    def _analyze_python(
        self, tree: tree_sitter.Tree,
    ) -> tuple[int, list[ListMembershipIssue]]:
        issues: list[ListMembershipIssue] = []
        total_membership_tests = 0

        for node in _walk(tree.root_node):
            if node.type != "comparison_operator":
                continue

            in_type = None
            for child in node.children:
                child_text = _safe_text(child)
                if child_text == "in" or child.type == "in":
                    in_type = "in"
                    break
                if child.type == "not in" or child_text == "not in":
                    in_type = "not in"
                    break

            if in_type is None:
                continue

            total_membership_tests += 1

            for child in node.children:
                if child.type == "list":
                    issue_type = ISSUE_LIST_NOT_IN if in_type == "not in" else ISSUE_LIST_IN
                    context = _safe_text(node)
                    issues.append(ListMembershipIssue(
                        issue_type=issue_type,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                        severity=_SEVERITY_MAP[issue_type],
                        description=_DESCRIPTIONS[issue_type],
                        suggestion=_SUGGESTIONS[issue_type],
                        context=context[:200],
                    ))
                    break

        return total_membership_tests, issues

    def _analyze_js(
        self, tree: tree_sitter.Tree,
    ) -> tuple[int, list[ListMembershipIssue]]:
        issues: list[ListMembershipIssue] = []
        total_membership_tests = 0

        for node in _walk(tree.root_node):
            if node.type != "call_expression":
                continue

            func = node.child_by_field_name("function")
            if func is None:
                continue

            func_text = _safe_text(func)
            if not func_text.endswith(".includes"):
                continue

            total_membership_tests += 1

            obj_node = func.child_by_field_name("object")
            if obj_node is None:
                named_children = [c for c in func.children if c.is_named]
                if named_children:
                    obj_node = named_children[0]

            if obj_node is not None and obj_node.type == "array":
                context = _safe_text(node)
                issues.append(ListMembershipIssue(
                    issue_type=ISSUE_ARRAY_INCLUDES,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    severity=_SEVERITY_MAP[ISSUE_ARRAY_INCLUDES],
                    description=_DESCRIPTIONS[ISSUE_ARRAY_INCLUDES],
                    suggestion=_SUGGESTIONS[ISSUE_ARRAY_INCLUDES],
                    context=context[:200],
                ))

        return total_membership_tests, issues
