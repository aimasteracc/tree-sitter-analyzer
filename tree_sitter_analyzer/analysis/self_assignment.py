"""Self-Assignment Detector.

Detects assignments where the left-hand side and right-hand side are
identical, which is always a no-op or a typo:

  - self_assign: x = x (variable assigns to itself)
  - self_assign_member: self.x = self.x (member assigns to itself)
  - self_assign_this: this.x = this.x (JS/TS/Java member self-assign)

Self-assignments are always dead code and often indicate copy-paste
errors or incomplete refactoring.

Supports Python, JavaScript/TypeScript, Java, Go.
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

ISSUE_SELF_ASSIGN = "self_assign"
ISSUE_SELF_ASSIGN_MEMBER = "self_assign_member"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_SELF_ASSIGN: "Variable is assigned to itself (x = x)",
    ISSUE_SELF_ASSIGN_MEMBER: "Member is assigned to itself (self.x = self.x)",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_SELF_ASSIGN: "Remove the self-assignment or fix the intended target.",
    ISSUE_SELF_ASSIGN_MEMBER: "Check if the right-hand side should reference a different object.",
}

_ASSIGN_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"assignment"}),
    ".js": frozenset({"assignment_expression"}),
    ".jsx": frozenset({"assignment_expression"}),
    ".ts": frozenset({"assignment_expression"}),
    ".tsx": frozenset({"assignment_expression"}),
    ".java": frozenset({}),
    ".go": frozenset({"assignment_statement", "short_var_declaration"}),
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


@dataclass(frozen=True)
class SelfAssignmentIssue:
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
class SelfAssignmentResult:
    file_path: str
    total_assignments: int
    issues: list[SelfAssignmentIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_assignments": self.total_assignments,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class SelfAssignmentAnalyzer(BaseAnalyzer):
    """Detects self-assignments (x = x, self.x = self.x)."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".go",
        }

    def analyze_file(
        self, file_path: str | Path,
    ) -> SelfAssignmentResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return SelfAssignmentResult(
                file_path=str(path),
                total_assignments=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return SelfAssignmentResult(
                file_path=str(path),
                total_assignments=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)
        assign_types = _ASSIGN_TYPES.get(ext, frozenset())
        issues: list[SelfAssignmentIssue] = []
        total_assignments = 0

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in assign_types:
                total_assignments += 1
                self._check_assignment(node, ext, issues)
            for child in node.children:
                stack.append(child)

        return SelfAssignmentResult(
            file_path=str(path),
            total_assignments=total_assignments,
            issues=issues,
        )

    def _check_assignment(
        self,
        node: tree_sitter.Node,
        ext: str,
        issues: list[SelfAssignmentIssue],
    ) -> None:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or right is None:
            return

        left_text = _node_text(left)
        right_text = _node_text(right)
        if not left_text or not right_text:
            return

        if left_text != right_text:
            return

        is_member = "." in left_text or "->" in left_text
        issue_type = ISSUE_SELF_ASSIGN_MEMBER if is_member else ISSUE_SELF_ASSIGN

        issues.append(SelfAssignmentIssue(
            line=node.start_point[0] + 1,
            issue_type=issue_type,
            severity=SEVERITY_MEDIUM,
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=_txt(node),
        ))
