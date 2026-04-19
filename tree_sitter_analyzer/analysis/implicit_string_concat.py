"""Implicit String Concatenation Detector.

Detects Python's implicit string literal concatenation where adjacent
string literals are silently joined without an explicit operator:

  - implicit_string_concat: "hello" "world" → "helloworld"
  - implicit_paren_concat: multi-line strings in parens
  - implicit_list_concat: ["a" "b"] → ["ab"] (one element, not two)
  - implicit_tuple_concat: ("a" "b",) → ("ab",)

This is a common source of silent bugs when commas are accidentally
omitted in collection literals, e.g. ["a" "b"] vs ["a", "b"].

Supports Python only (this is a Python-specific language quirk).
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
SEVERITY_LOW = "low"

ISSUE_IMPLICIT_CONCAT = "implicit_string_concat"
ISSUE_MISSING_COMMA = "implicit_concat_missing_comma"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_IMPLICIT_CONCAT: "Adjacent string literals are implicitly concatenated",
    ISSUE_MISSING_COMMA: (
        "Possible missing comma: strings in collection appear "
        "to be implicitly concatenated"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_IMPLICIT_CONCAT: (
        "Use explicit + for string concatenation, or use a single "
        "multi-line string with triple quotes."
    ),
    ISSUE_MISSING_COMMA: (
        "Add a comma between strings if they should be separate "
        "elements, or use explicit + if concatenation is intended."
    ),
}

_STRING_TYPES: frozenset[str] = frozenset({
    "string",
    "string_start",
    "concatenated_string",
    "fstring",
})

_COLLECTION_TYPES: frozenset[str] = frozenset({
    "list",
    "set",
    "dictionary",
    "tuple",
    "argument_list",
    "parenthesized_expression",
})


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _is_string_like(node: tree_sitter.Node) -> bool:
    if node.type in _STRING_TYPES:
        return True
    if node.type == "parenthesized_expression":
        children = [c for c in node.children if c.is_named]
        if len(children) == 1 and children[0].type in _STRING_TYPES:
            return True
    return False


@dataclass(frozen=True)
class ImplicitConcatIssue:
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
class ImplicitStringConcatResult:
    file_path: str
    total_checked: int
    issues: list[ImplicitConcatIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_checked": self.total_checked,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class ImplicitStringConcatAnalyzer(BaseAnalyzer):
    """Detects implicit string literal concatenation in Python."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> ImplicitStringConcatResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return ImplicitStringConcatResult(
                file_path=str(path),
                total_checked=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ImplicitStringConcatResult(
                file_path=str(path),
                total_checked=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)
        issues: list[ImplicitConcatIssue] = []
        total_checked = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total_checked
            if node.type == "concatenated_string":
                total_checked += 1
                self._check_concatenated(node, issues)

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return ImplicitStringConcatResult(
            file_path=str(path),
            total_checked=total_checked,
            issues=issues,
        )

    def _check_concatenated(
        self,
        node: tree_sitter.Node,
        issues: list[ImplicitConcatIssue],
    ) -> None:
        parent = node.parent
        in_collection = parent is not None and parent.type in _COLLECTION_TYPES
        issue_type = ISSUE_MISSING_COMMA if in_collection else ISSUE_IMPLICIT_CONCAT
        severity = SEVERITY_MEDIUM if in_collection else SEVERITY_LOW

        issues.append(ImplicitConcatIssue(
            line=node.start_point[0] + 1,
            issue_type=issue_type,
            severity=severity,
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=_txt(node),
        ))
