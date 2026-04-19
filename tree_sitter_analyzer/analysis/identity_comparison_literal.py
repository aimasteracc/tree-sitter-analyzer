"""Identity Comparison with Literals Detector.

Detects `is`/`is not` used with non-singleton literals:
  - is_literal: x is 5 (use x == 5)
  - is_not_literal: x is not "hello" (use x != "hello")

Python 3.8+ emits SyntaxWarning for these patterns.
Python 3.12+ emits DeprecationWarning.
Future versions will raise SyntaxError.

`is` checks object identity, not value equality.
While CPython caches small integers/strings, this is implementation-specific
and can lead to subtle bugs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

ISSUE_IS_LITERAL = "is_literal"
ISSUE_IS_NOT_LITERAL = "is_not_literal"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_IS_LITERAL: SEVERITY_HIGH,
    ISSUE_IS_NOT_LITERAL: SEVERITY_HIGH,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_IS_LITERAL: (
        "Identity comparison with literal: `is` checks identity, not value — "
        "use == for value comparison (SyntaxWarning in Python 3.8+)"
    ),
    ISSUE_IS_NOT_LITERAL: (
        "Identity comparison with literal: `is not` checks identity, not value — "
        "use != for value comparison (SyntaxWarning in Python 3.8+)"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_IS_LITERAL: "Replace `x is literal` with `x == literal`.",
    ISSUE_IS_NOT_LITERAL: "Replace `x is not literal` with `x != literal`.",
}

_SINGLETON_TYPES: frozenset[str] = frozenset({
    "none",
    "true",
    "false",
    "ellipsis",
})

_LITERAL_TYPES: frozenset[str] = frozenset({
    "integer",
    "float",
    "string",
    "list",
    "dictionary",
    "set",
    "tuple",
    "concatenated_string",
    "parenthesized_expression",
    "unary_operator",
})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


def _is_singleton(node: tree_sitter.Node) -> bool:
    return node.type in _SINGLETON_TYPES


def _is_literal(node: tree_sitter.Node) -> bool:
    if node.type in _LITERAL_TYPES:
        if node.type == "unary_operator":
            operand = node.child_by_field_name("argument")
            if operand is None:
                children = [c for c in node.children if c.is_named]
                operand = children[0] if children else None
            return operand is not None and operand.type in ("integer", "float")
        return True
    if node.type == "parenthesized_expression":
        children = [c for c in node.children if c.is_named]
        if len(children) == 1:
            return _is_literal(children[0])
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
class IdentityComparisonLiteralIssue:
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
class IdentityComparisonLiteralResult:
    file_path: str
    total_identity_comparisons: int
    issues: list[IdentityComparisonLiteralIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_identity_comparisons": self.total_identity_comparisons,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class IdentityComparisonLiteralAnalyzer(BaseAnalyzer):
    """Detects identity comparisons with non-singleton literals."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> IdentityComparisonLiteralResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return IdentityComparisonLiteralResult(
                file_path=str(path),
                total_identity_comparisons=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return IdentityComparisonLiteralResult(
                file_path=str(path),
                total_identity_comparisons=0,
            )

        try:
            source = path.read_bytes()
        except OSError:
            return IdentityComparisonLiteralResult(
                file_path=str(path),
                total_identity_comparisons=0,
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return IdentityComparisonLiteralResult(
                file_path=str(path),
                total_identity_comparisons=0,
            )

        issues: list[IdentityComparisonLiteralIssue] = []
        total_identity_comparisons = 0

        for node in _walk(tree.root_node):
            if node.type != "comparison_operator":
                continue
            for issue in self._check_comparison(node):
                total_identity_comparisons += 1
                if issue is not None:
                    issues.append(issue)

        return IdentityComparisonLiteralResult(
            file_path=str(path),
            total_identity_comparisons=total_identity_comparisons,
            issues=issues,
        )

    def _check_comparison(
        self, node: tree_sitter.Node,
    ) -> list[IdentityComparisonLiteralIssue | None]:
        children = node.children
        results: list[IdentityComparisonLiteralIssue | None] = []

        i = 0
        while i < len(children):
            child = children[i]
            if child.type in ("is", "is not"):
                left = children[i - 1] if i > 0 else None
                right = children[i + 1] if i + 1 < len(children) else None

                if left is not None and right is not None:
                    issue = self._check_operands(
                        left, right, child.type, node,
                    )
                    results.append(issue)
                i += 2
            else:
                i += 1

        return results

    def _check_operands(
        self,
        left: tree_sitter.Node,
        right: tree_sitter.Node,
        op_type: str,
        parent: tree_sitter.Node,
    ) -> IdentityComparisonLiteralIssue | None:
        left_is_literal = _is_literal(left) and not _is_singleton(left)
        right_is_literal = _is_literal(right) and not _is_singleton(right)

        if not left_is_literal and not right_is_literal:
            return None

        issue_type = ISSUE_IS_LITERAL if op_type == "is" else ISSUE_IS_NOT_LITERAL
        context = _safe_text(parent)
        return IdentityComparisonLiteralIssue(
            issue_type=issue_type,
            line=parent.start_point[0] + 1,
            column=parent.start_point[1],
            severity=_SEVERITY_MAP[issue_type],
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=context[:200],
        )
