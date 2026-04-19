"""Assert-on-Tuple Detector.

Detects `assert (condition, message)` patterns where the assertion always
passes because a non-empty tuple is truthy in Python.

The correct form is `assert condition, message` (comma separates the
condition from the message), NOT `assert (condition, message)` (which
creates a tuple that is always truthy).

Issue types:
  - assert_on_tuple: assert with a tuple literal as the condition

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

SEVERITY_HIGH = "high"

ISSUE_ASSERT_ON_TUPLE = "assert_on_tuple"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_ASSERT_ON_TUPLE: (
        "Assert on tuple always passes. Use `assert cond, msg` "
        "not `assert (cond, msg)`"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_ASSERT_ON_TUPLE: (
        "Replace `assert (cond, msg)` with `assert cond, msg`. "
        "The tuple form evaluates to True because non-empty tuples "
        "are truthy."
    ),
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


@dataclass(frozen=True)
class AssertOnTupleIssue:
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
class AssertOnTupleResult:
    file_path: str
    total_asserts: int
    issues: list[AssertOnTupleIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_asserts": self.total_asserts,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class AssertOnTupleAnalyzer(BaseAnalyzer):
    """Detects assert-on-tuple patterns where assert always passes."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> AssertOnTupleResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return AssertOnTupleResult(
                file_path=str(path),
                total_asserts=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return AssertOnTupleResult(
                file_path=str(path),
                total_asserts=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        total = 0
        issues: list[AssertOnTupleIssue] = []

        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "assert_statement":
                total += 1
                named = [c for c in node.children if c.is_named]
                if named:
                    first = named[0]
                    if first.type == "tuple":
                        issues.append(AssertOnTupleIssue(
                            line=node.start_point[0] + 1,
                            issue_type=ISSUE_ASSERT_ON_TUPLE,
                            severity=SEVERITY_HIGH,
                            description=_DESCRIPTIONS[ISSUE_ASSERT_ON_TUPLE],
                            suggestion=_SUGGESTIONS[ISSUE_ASSERT_ON_TUPLE],
                            context=_txt(node),
                        ))
            else:
                for child in node.children:
                    stack.append(child)

        return AssertOnTupleResult(
            file_path=str(path),
            total_asserts=total,
            issues=issues,
        )
