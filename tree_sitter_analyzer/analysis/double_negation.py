"""Double Negation Detector.

Detects unnecessary double negation patterns that hurt readability:
  - double_not: not not x (Python) — use bool(x)
  - double_bang: !!x (JS/TS/Java) — use Boolean(x) or explicit cast
  - not_not_parens: not (not x) (Python) — use bool(x)

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

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"

ISSUE_DOUBLE_NOT = "double_not"
ISSUE_DOUBLE_BANG = "double_bang"
ISSUE_NOT_NOT_PARENS = "not_not_parens"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_DOUBLE_NOT: SEVERITY_LOW,
    ISSUE_DOUBLE_BANG: SEVERITY_LOW,
    ISSUE_NOT_NOT_PARENS: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_DOUBLE_NOT: "Double 'not' operator — use bool(x) instead",
    ISSUE_DOUBLE_BANG: "Double bang (!!) — use Boolean(x) or explicit cast",
    ISSUE_NOT_NOT_PARENS: "Negated inner negation 'not (not x)' — use bool(x)",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_DOUBLE_NOT: "Replace 'not not x' with 'bool(x)'.",
    ISSUE_DOUBLE_BANG: "Replace '!!x' with 'Boolean(x)' or an explicit cast.",
    ISSUE_NOT_NOT_PARENS: "Replace 'not (not x)' with 'bool(x)'.",
}

# Unary operator node types per language
_UNARY_NOT_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"not_operator"}),
    ".js": frozenset({"unary_expression"}),
    ".jsx": frozenset({"unary_expression"}),
    ".ts": frozenset({"unary_expression"}),
    ".tsx": frozenset({"unary_expression"}),
    ".java": frozenset({"unary_expression"}),
    ".go": frozenset({"unary_expression"}),
}


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


@dataclass(frozen=True)
class DoubleNegationIssue:
    """A single double negation issue."""

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
class DoubleNegationResult:
    """Result of double negation analysis."""

    file_path: str
    total_unary_ops: int
    issues: list[DoubleNegationIssue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_unary_ops": self.total_unary_ops,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class DoubleNegationAnalyzer(BaseAnalyzer):
    """Detects double negation patterns."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
        }

    def analyze_file(self, file_path: str | Path) -> DoubleNegationResult:
        """Analyze a single file for double negation patterns."""
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return DoubleNegationResult(
                file_path=str(path), total_unary_ops=0, issues=[],
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return DoubleNegationResult(
                file_path=str(path), total_unary_ops=0, issues=[],
            )

        try:
            source = path.read_bytes()
        except OSError:
            return DoubleNegationResult(
                file_path=str(path), total_unary_ops=0, issues=[],
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return DoubleNegationResult(
                file_path=str(path), total_unary_ops=0, issues=[],
            )

        issues: list[DoubleNegationIssue] = []
        total_unary_ops = 0

        unary_types = _UNARY_NOT_TYPES.get(ext, frozenset())

        for node in _walk(tree.root_node):
            if node.type not in unary_types:
                continue
            total_unary_ops += 1

            issue = self._check_node(node, source, ext)
            if issue is not None:
                issues.append(issue)

        return DoubleNegationResult(
            file_path=str(path),
            total_unary_ops=total_unary_ops,
            issues=issues,
        )

    def _check_node(
        self,
        node: tree_sitter.Node,
        source: bytes,
        ext: str,
    ) -> DoubleNegationIssue | None:
        """Check a unary node for double negation."""
        if ext == ".py":
            return self._check_python(node, source)
        if ext in (".js", ".jsx", ".ts", ".tsx"):
            return self._check_js(node, source)
        if ext == ".java":
            return self._check_java(node, source)
        if ext == ".go":
            return self._check_go(node, source)
        return None

    def _check_python(
        self, node: tree_sitter.Node, source: bytes,
    ) -> DoubleNegationIssue | None:
        """Check Python 'not not x' and 'not (not x)'."""
        # Pattern: not_operator → not_operator → ...
        children = list(node.children)
        # not_operator has "not" keyword + operand
        if len(children) < 2:
            return None

        operand = children[-1]  # last child is the operand
        if operand.type == "not_operator":
            return self._make_issue(
                ISSUE_DOUBLE_NOT, node, source,
            )

        # Pattern: not (not x) — parenthesized expression containing not
        if operand.type == "parenthesized_expression":
            inner = [c for c in operand.children if c.is_named]
            if len(inner) == 1 and inner[0].type == "not_operator":
                return self._make_issue(
                    ISSUE_NOT_NOT_PARENS, node, source,
                )

        return None

    def _check_js(
        self, node: tree_sitter.Node, source: bytes,
    ) -> DoubleNegationIssue | None:
        """Check JS/TS !!x pattern."""
        text = _safe_text(node)
        if text.startswith("!!"):
            return self._make_issue(
                ISSUE_DOUBLE_BANG, node, source,
            )
        return None

    def _check_java(
        self, node: tree_sitter.Node, source: bytes,
    ) -> DoubleNegationIssue | None:
        """Check Java !!x pattern."""
        text = _safe_text(node)
        if text.startswith("!!"):
            return self._make_issue(
                ISSUE_DOUBLE_BANG, node, source,
            )
        return None

    def _check_go(
        self, node: tree_sitter.Node, source: bytes,
    ) -> DoubleNegationIssue | None:
        """Check Go !!x pattern (unusual in Go)."""
        text = _safe_text(node)
        if text.startswith("!!"):
            return self._make_issue(
                ISSUE_DOUBLE_BANG, node, source,
            )
        return None

    def _make_issue(
        self,
        issue_type: str,
        node: tree_sitter.Node,
        source: bytes,
    ) -> DoubleNegationIssue:
        context = _safe_text(node)
        return DoubleNegationIssue(
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
