"""Range-Len Anti-pattern Detector.

Detects `for i in range(len(x))` patterns that should use direct
iteration or enumerate:
  - range_len_for: `for i in range(len(x))` → `for item in x`
    or `for i, item in enumerate(x)`

Supports Python only (range/len are Python builtins).
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

ISSUE_RANGE_LEN_FOR = "range_len_for"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_RANGE_LEN_FOR: (
        "Use `for item in x` or `for i, item in enumerate(x)` "
        "instead of `for i in range(len(x))`"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_RANGE_LEN_FOR: (
        "Replace `for i in range(len(x))` with direct iteration "
        "`for item in x` or indexed `for i, item in enumerate(x)`"
    ),
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _is_range_len_call(node: tree_sitter.Node) -> bool:
    """Check if node is `range(len(...))` call."""
    if node.type != "call":
        return False
    func = node.child_by_field_name("function")
    if func is None or _node_text(func) != "range":
        return False
    args = node.child_by_field_name("arguments")
    if args is None:
        return False
    for child in args.children:
        if child.type == "call":
            inner_func = child.child_by_field_name("function")
            if inner_func is not None and _node_text(inner_func) == "len":
                return True
    return False


@dataclass(frozen=True)
class RangeLenIssue:
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
class RangeLenResult:
    file_path: str
    total_for_loops: int
    issues: list[RangeLenIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_for_loops": self.total_for_loops,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class RangeLenAnalyzer(BaseAnalyzer):
    """Detects range(len(x)) anti-pattern in for loops."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> RangeLenResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return RangeLenResult(
                file_path=str(path),
                total_for_loops=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return RangeLenResult(
                file_path=str(path),
                total_for_loops=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        total = 0
        issues: list[RangeLenIssue] = []

        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "for_statement":
                total += 1
                self._check_for_statement(node, issues)
            for child in node.children:
                stack.append(child)

        return RangeLenResult(
            file_path=str(path),
            total_for_loops=total,
            issues=issues,
        )

    def _check_for_statement(
        self,
        node: tree_sitter.Node,
        issues: list[RangeLenIssue],
    ) -> None:
        children = node.children
        for i, child in enumerate(children):
            if child.type == "in" and i + 1 < len(children):
                iterable = children[i + 1]
                if _is_range_len_call(iterable):
                    issues.append(RangeLenIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_RANGE_LEN_FOR,
                        severity=SEVERITY_LOW,
                        description=_DESCRIPTIONS[ISSUE_RANGE_LEN_FOR],
                        suggestion=_SUGGESTIONS[ISSUE_RANGE_LEN_FOR],
                        context=_txt(node),
                    ))
                break
