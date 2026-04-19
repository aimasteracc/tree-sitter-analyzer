"""Statement-with-No-Effect Detector.

Detects expression statements that evaluate to a value but discard it
silently. The most dangerous pattern is `x == 5;` where `x = 5;` was
intended.

Issue types:
  - comparison_as_statement: comparison used as statement (x == 5;)
  - arithmetic_as_statement: arithmetic expression as statement (a + b;)
  - literal_as_statement: standalone literal as statement ("text")
  - string_literal_as_statement: string literal as statement (Python)

Supports Python, JavaScript, TypeScript, Java, Go.
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
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_COMPARISON = "comparison_as_statement"
ISSUE_ARITHMETIC = "arithmetic_as_statement"
ISSUE_LITERAL = "literal_as_statement"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_COMPARISON: (
        "Comparison expression used as statement — likely meant assignment"
    ),
    ISSUE_ARITHMETIC: (
        "Arithmetic expression used as statement — result is discarded"
    ),
    ISSUE_LITERAL: (
        "Literal value used as statement — has no effect"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_COMPARISON: "If this is an assignment, use = instead of ==.",
    ISSUE_ARITHMETIC: "Assign the result to a variable or remove the expression.",
    ISSUE_LITERAL: "Remove the unused literal or use it in an expression.",
}

_COMPARISON_OPS: set[str] = {"==", "!=", "<", ">", "<=", ">=", "===",
                              "!==", "is", "is not", "in", "not in"}
_ARITHMETIC_OPS: set[str] = {"+", "-", "*", "/", "//", "%", "**",
                              "<<", ">>", "&", "|", "^"}
_LITERAL_TYPES: set[str] = {
    "string", "number", "integer", "float", "true", "false", "null",
    "None", "boolean",
}
_COMPARISON_TYPES: set[str] = {
    "comparison_operator", "boolean_operation", "is_expression",
    "not_is_expression", "in_expression", "not_in_expression",
}
_ARITHMETIC_TYPES: set[str] = {
    "binary_expression", "augmented_assignment",
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _classify_expression(
    node: tree_sitter.Node,
) -> str | None:
    """Classify an expression node as comparison, arithmetic, or literal."""
    if node.type in _COMPARISON_TYPES:
        return ISSUE_COMPARISON

    if node.type == "binary_operator" or node.type == "binary_expression":
        for child in node.children:
            if child.is_named:
                continue
            op = _node_text(child)
            if op in _COMPARISON_OPS:
                return ISSUE_COMPARISON
            if op in _ARITHMETIC_OPS:
                return ISSUE_ARITHMETIC

    if node.type in _LITERAL_TYPES:
        return ISSUE_LITERAL

    if node.type == "string_literal":
        return ISSUE_LITERAL

    if node.type == "encapsed_string":
        return ISSUE_LITERAL

    if node.type == "identifier":
        return ISSUE_LITERAL

    return None


@dataclass(frozen=True)
class NoEffectIssue:
    line: int
    issue_type: str
    severity: str
    description: str
    suggestion: str
    context: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
        }


@dataclass
class StatementNoEffectResult:
    file_path: str
    total_statements: int
    issues: list[NoEffectIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_statements": self.total_statements,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class StatementNoEffectAnalyzer(BaseAnalyzer):
    """Detects expression statements that have no effect."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
        }

    def analyze_file(
        self, file_path: str | Path,
    ) -> StatementNoEffectResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return StatementNoEffectResult(
                file_path=str(path),
                total_statements=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return StatementNoEffectResult(
                file_path=str(path),
                total_statements=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        issues: list[NoEffectIssue] = []
        total = 0

        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()

            if node.type == "expression_statement":
                total += 1
                expr = None
                for child in node.children:
                    if child.is_named:
                        expr = child
                        break
                if expr is not None:
                    self._check_expression(expr, issues)
            elif node.type == "expression_list":
                pass
            else:
                for child in node.children:
                    stack.append(child)

        return StatementNoEffectResult(
            file_path=str(path),
            total_statements=total,
            issues=issues,
        )

    def _check_expression(
        self,
        expr: tree_sitter.Node,
        issues: list[NoEffectIssue],
    ) -> None:
        issue_type = _classify_expression(expr)
        if issue_type is not None:
            severity = (
                SEVERITY_HIGH
                if issue_type == ISSUE_COMPARISON
                else SEVERITY_LOW
            )
            issues.append(NoEffectIssue(
                line=expr.start_point[0] + 1,
                issue_type=issue_type,
                severity=severity,
                description=_DESCRIPTIONS[issue_type],
                suggestion=_SUGGESTIONS[issue_type],
                context=_txt(expr),
            ))
