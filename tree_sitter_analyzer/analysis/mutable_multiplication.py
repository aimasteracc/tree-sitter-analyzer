"""Mutable Multiplication Alias Detector.

Detects list/tuple multiplication with mutable elements:
  - mutable_list_mult: `[[]] * n` creates shared references (use list comprehension)
  - mutable_tuple_mult: `([[]],) * n` creates shared references

`[[]] * n` creates n references to the SAME inner list. Modifying one
modifies all — a classic Python gotcha. Use `[[] for _ in range(n)]` instead.

Only triggers when the multiplied container has mutable children
(list, dictionary, set). Immutable values like `[1, 2, 3] * 2` are safe.

Python-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"

ISSUE_MUTABLE_LIST_MULT = "mutable_list_mult"
ISSUE_MUTABLE_TUPLE_MULT = "mutable_tuple_mult"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_MUTABLE_LIST_MULT: SEVERITY_HIGH,
    ISSUE_MUTABLE_TUPLE_MULT: SEVERITY_HIGH,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_MUTABLE_LIST_MULT: (
        "List multiplication with mutable elements creates shared references — "
        "modifying one element affects all copies"
    ),
    ISSUE_MUTABLE_TUPLE_MULT: (
        "Tuple multiplication with mutable elements creates shared references — "
        "modifying one element affects all copies"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_MUTABLE_LIST_MULT: (
        "Use a list comprehension: `[[] for _ in range(n)]` "
        "to create independent copies"
    ),
    ISSUE_MUTABLE_TUPLE_MULT: (
        "Use a tuple comprehension: `tuple([] for _ in range(n))` "
        "or construct independently"
    ),
}

_MUTABLE_CHILD_TYPES: frozenset[str] = frozenset({
    "list",
    "dictionary",
    "set",
})

_MUTABLE_CONSTRUCTORS: frozenset[str] = frozenset({
    "set",
    "dict",
    "list",
    "defaultdict",
    "OrderedDict",
    "Counter",
    "deque",
})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


def _has_mutable_children(node: tree_sitter.Node) -> bool:
    for child in node.children:
        if not child.is_named:
            continue
        if child.type in _MUTABLE_CHILD_TYPES:
            return True
        if child.type == "call":
            func = child.child_by_field_name("function")
            if func is None:
                named = [c for c in child.children if c.is_named]
                func = named[0] if named else None
            if func is not None and func.type == "identifier":
                if _safe_text(func) in _MUTABLE_CONSTRUCTORS:
                    return True
    return False


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
class MutableMultiplicationIssue:
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
class MutableMultiplicationResult:
    file_path: str
    total_multiplications: int
    issues: list[MutableMultiplicationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_multiplications": self.total_multiplications,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class MutableMultiplicationAnalyzer(BaseAnalyzer):
    """Detects list/tuple multiplication with mutable elements."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> MutableMultiplicationResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return MutableMultiplicationResult(
                file_path=str(path), total_multiplications=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return MutableMultiplicationResult(
                file_path=str(path), total_multiplications=0,
            )

        try:
            source = path.read_bytes()
        except OSError:
            return MutableMultiplicationResult(
                file_path=str(path), total_multiplications=0,
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return MutableMultiplicationResult(
                file_path=str(path), total_multiplications=0,
            )

        issues: list[MutableMultiplicationIssue] = []
        total_multiplications = 0

        for node in _walk(tree.root_node):
            if node.type != "binary_operator":
                continue
            issue = self._check_multiplication(node)
            if issue is not None:
                issues.append(issue)
                total_multiplications += 1

        return MutableMultiplicationResult(
            file_path=str(path),
            total_multiplications=total_multiplications,
            issues=issues,
        )

    def _check_multiplication(
        self, node: tree_sitter.Node,
    ) -> MutableMultiplicationIssue | None:
        children = node.children
        if len(children) < 3:
            return None

        left = children[0]
        op = children[1]

        op_text = _safe_text(op).strip()
        if op_text != "*":
            return None

        if left.type == "list" and _has_mutable_children(left):
            return self._make_issue(ISSUE_MUTABLE_LIST_MULT, node)
        if left.type == "tuple" and _has_mutable_children(left):
            return self._make_issue(ISSUE_MUTABLE_TUPLE_MULT, node)

        return None

    def _make_issue(
        self, issue_type: str, node: tree_sitter.Node,
    ) -> MutableMultiplicationIssue:
        context = _safe_text(node)
        return MutableMultiplicationIssue(
            issue_type=issue_type,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            severity=_SEVERITY_MAP[issue_type],
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=context[:200],
        )
