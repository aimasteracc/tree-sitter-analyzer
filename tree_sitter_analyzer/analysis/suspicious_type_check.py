"""Suspicious Type Check Detector.

Detects type comparisons using == or != instead of isinstance():

  - eq_type_check: type(x) == Y → use isinstance(x, Y)
  - ne_type_check: type(x) != Y → use not isinstance(x, Y)

Using type() == for type checking ignores subclasses, which can cause
subtle bugs when using inheritance. isinstance() is the Pythonic way.

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

SEVERITY_MEDIUM = "medium"

ISSUE_EQ_TYPE_CHECK = "eq_type_check"
ISSUE_NE_TYPE_CHECK = "ne_type_check"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_EQ_TYPE_CHECK: "type(x) == Y comparison ignores subclasses — use isinstance(x, Y)",
    ISSUE_NE_TYPE_CHECK: "type(x) != Y comparison ignores subclasses — use not isinstance(x, Y)",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_EQ_TYPE_CHECK: "Replace type(x) == Y with isinstance(x, Y) to support subclasses.",
    ISSUE_NE_TYPE_CHECK: "Replace type(x) != Y with not isinstance(x, Y) to support subclasses.",
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _is_type_call(node: tree_sitter.Node) -> bool:
    if node.type != "call":
        return False
    func = node.child_by_field_name("function")
    if func is None:
        return False
    return func.text == b"type" if func.text else False


@dataclass(frozen=True)
class SuspiciousTypeCheckIssue:
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
class SuspiciousTypeCheckResult:
    file_path: str
    total_comparisons: int
    issues: list[SuspiciousTypeCheckIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_comparisons": self.total_comparisons,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class SuspiciousTypeCheckAnalyzer(BaseAnalyzer):
    """Detects type() == comparisons that should use isinstance()."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> SuspiciousTypeCheckResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return SuspiciousTypeCheckResult(
                file_path=str(path),
                total_comparisons=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return SuspiciousTypeCheckResult(
                file_path=str(path),
                total_comparisons=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)
        issues: list[SuspiciousTypeCheckIssue] = []
        total_comparisons = 0

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "comparison_operator":
                total_comparisons += 1
                self._check_comparison(node, issues)
            for child in node.children:
                stack.append(child)

        return SuspiciousTypeCheckResult(
            file_path=str(path),
            total_comparisons=total_comparisons,
            issues=issues,
        )

    def _check_comparison(
        self,
        node: tree_sitter.Node,
        issues: list[SuspiciousTypeCheckIssue],
    ) -> None:
        named_children = [c for c in node.children if c.is_named]
        if len(named_children) < 2:
            return

        operators = [
            c for c in node.children
            if not c.is_named and c.type in ("==", "!=")
        ]
        if not operators:
            return

        op = operators[0]
        left = named_children[0]
        right = named_children[1]

        issue_type = (
            ISSUE_EQ_TYPE_CHECK if op.type == "==" else ISSUE_NE_TYPE_CHECK
        )

        if _is_type_call(left) or _is_type_call(right):
            issues.append(SuspiciousTypeCheckIssue(
                line=node.start_point[0] + 1,
                issue_type=issue_type,
                severity=SEVERITY_MEDIUM,
                description=_DESCRIPTIONS[issue_type],
                suggestion=_SUGGESTIONS[issue_type],
                context=_txt(node),
            ))
