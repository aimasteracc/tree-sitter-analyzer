"""Useless Loop Else Detector.

Detects `for...else` and `while...else` blocks where the else clause
always executes because the loop body contains no `break` statement.

The else clause in Python loops only has meaning when paired with break:
  - With break: else runs only if break was NOT hit
  - Without break: else ALWAYS runs, making it useless and confusing

Issue types:
  - useless_for_else: for...else without break in loop body
  - useless_while_else: while...else without break in loop body

Supports Python only.
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

ISSUE_USELESS_FOR_ELSE = "useless_for_else"
ISSUE_USELESS_WHILE_ELSE = "useless_while_else"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_USELESS_FOR_ELSE: (
        "for...else without break: else clause always runs, "
        "making it misleading"
    ),
    ISSUE_USELESS_WHILE_ELSE: (
        "while...else without break: else clause always runs, "
        "making it misleading"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_USELESS_FOR_ELSE: (
        "Either add a `break` to the loop body or remove the `else` clause. "
        "Without `break`, the else block always runs."
    ),
    ISSUE_USELESS_WHILE_ELSE: (
        "Either add a `break` to the loop body or remove the `else` clause. "
        "Without `break`, the else block always runs."
    ),
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _has_break(node: tree_sitter.Node) -> bool:
    """Check if node contains a break_statement (not inside nested loops)."""
    stack: list[tree_sitter.Node] = [node]
    while stack:
        n = stack.pop()
        if n.type == "break_statement":
            return True
        if n.type in ("for_statement", "while_statement") and n is not node:
            continue
        for child in n.children:
            stack.append(child)
    return False


@dataclass(frozen=True)
class UselessLoopElseIssue:
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
class UselessLoopElseResult:
    file_path: str
    total_loop_else: int
    issues: list[UselessLoopElseIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_loop_else": self.total_loop_else,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class UselessLoopElseAnalyzer(BaseAnalyzer):
    """Detects for...else and while...else without break."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> UselessLoopElseResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return UselessLoopElseResult(
                file_path=str(path),
                total_loop_else=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return UselessLoopElseResult(
                file_path=str(path),
                total_loop_else=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        total = 0
        issues: list[UselessLoopElseIssue] = []

        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in ("for_statement", "while_statement"):
                self._check_loop(node, issues, total_ref=[total])
            for child in node.children:
                stack.append(child)

        return UselessLoopElseResult(
            file_path=str(path),
            total_loop_else=total,
            issues=issues,
        )

    def _check_loop(
        self,
        node: tree_sitter.Node,
        issues: list[UselessLoopElseIssue],
        total_ref: list[int],
    ) -> None:
        children = node.children
        body_node: tree_sitter.Node | None = None
        has_else = False
        for child in children:
            if child.type == "block":
                body_node = child
            elif child.type == "else_clause":
                has_else = True

        if not has_else or body_node is None:
            return

        total_ref[0] += 1

        if _has_break(body_node):
            return

        issue_type = (
            ISSUE_USELESS_FOR_ELSE
            if node.type == "for_statement"
            else ISSUE_USELESS_WHILE_ELSE
        )
        issues.append(UselessLoopElseIssue(
            line=node.start_point[0] + 1,
            issue_type=issue_type,
            severity=SEVERITY_LOW,
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=_txt(node),
        ))
