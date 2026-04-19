"""Loose Equality Comparison Detector.

Detects use of loose equality operators in JavaScript/TypeScript:
  - loose_eq: x == y (use === instead)
  - loose_neq: x != y (use !== instead)

JavaScript/TypeScript only. Python, Java, and Go use strict
comparison by default (no loose/strict distinction).

Excludes comparisons with null/undefined (covered by
literal_boolean_comparison analyzer).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"

ISSUE_LOOSE_EQ = "loose_eq"
ISSUE_LOOSE_NEQ = "loose_neq"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_LOOSE_EQ: SEVERITY_MEDIUM,
    ISSUE_LOOSE_NEQ: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_LOOSE_EQ: "Loose equality (==) — use strict equality (===) to avoid type coercion bugs",
    ISSUE_LOOSE_NEQ: "Loose inequality (!=) — use strict inequality (!==) to avoid type coercion bugs",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_LOOSE_EQ: "Replace '==' with '===' for strict comparison.",
    ISSUE_LOOSE_NEQ: "Replace '!=' with '!==' for strict comparison.",
}

_BINARY_TYPES: dict[str, frozenset[str]] = {
    ".js": frozenset({"binary_expression"}),
    ".jsx": frozenset({"binary_expression"}),
    ".ts": frozenset({"binary_expression"}),
    ".tsx": frozenset({"binary_expression"}),
}

_LOOSE_EQ_OPS: frozenset[str] = frozenset({"=="})
_LOOSE_NEQ_OPS: frozenset[str] = frozenset({"!="})

_NULL_LITERALS: frozenset[str] = frozenset({"null", "undefined"})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


@dataclass(frozen=True)
class LooseEqualityIssue:
    """A single loose equality issue."""

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
class LooseEqualityResult:
    """Result of loose equality analysis."""

    file_path: str
    total_comparisons: int
    issues: list[LooseEqualityIssue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_comparisons": self.total_comparisons,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class LooseEqualityAnalyzer(BaseAnalyzer):
    """Detects loose equality (==, !=) in JavaScript/TypeScript."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> LooseEqualityResult:
        """Analyze a single file for loose equality comparisons."""
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return LooseEqualityResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return LooseEqualityResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )

        try:
            source = path.read_bytes()
        except OSError:
            return LooseEqualityResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return LooseEqualityResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )

        issues: list[LooseEqualityIssue] = []
        total_comparisons = 0
        binary_types = _BINARY_TYPES.get(ext, frozenset())

        for node in _walk(tree.root_node):
            if node.type not in binary_types:
                continue
            total_comparisons += 1

            issue = self._check_binary(node, ext)
            if issue is not None:
                issues.append(issue)

        return LooseEqualityResult(
            file_path=str(path),
            total_comparisons=total_comparisons,
            issues=issues,
        )

    def _check_binary(
        self,
        node: tree_sitter.Node,
        ext: str,
    ) -> LooseEqualityIssue | None:
        """Check a binary_expression for loose equality operators."""
        children = [c for c in node.children if c.is_named]
        if len(children) < 2:
            return None

        op = ""
        for child in node.children:
            if not child.is_named:
                op = _safe_text(child)
                break

        if op not in _LOOSE_EQ_OPS and op not in _LOOSE_NEQ_OPS:
            return None

        left, right = children[0], children[-1]
        left_text = _safe_text(left)
        right_text = _safe_text(right)

        # Skip null/undefined comparisons (covered by literal_boolean_comparison)
        if left_text in _NULL_LITERALS or right_text in _NULL_LITERALS:
            return None

        issue_type = ISSUE_LOOSE_EQ if op in _LOOSE_EQ_OPS else ISSUE_LOOSE_NEQ
        return self._make_issue(issue_type, node)

    def _make_issue(
        self,
        issue_type: str,
        node: tree_sitter.Node,
    ) -> LooseEqualityIssue:
        context = _safe_text(node)
        return LooseEqualityIssue(
            issue_type=issue_type,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            severity=_SEVERITY_MAP[issue_type],
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=context[:200],
        )


def _walk(node: tree_sitter.Node) -> Any:
    """Depth-first traversal of all nodes."""
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
