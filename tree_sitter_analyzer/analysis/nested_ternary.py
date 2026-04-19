"""Nested Ternary Detector.

Detects deeply nested ternary/conditional expressions that hurt readability.
Python: `conditional_expression`, JS/TS/Java: `ternary_expression`.

A nesting depth of 2+ is flagged (configurable via MIN_DEPTH).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


def _txt(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


SUPPORTED_EXTENSIONS: set[str] = {".py", ".js", ".ts", ".tsx", ".jsx", ".java"}

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

MIN_DEPTH = 2

_TERNARY_TYPES: dict[str, str] = {
    ".py": "conditional_expression",
    ".js": "ternary_expression",
    ".jsx": "ternary_expression",
    ".ts": "ternary_expression",
    ".tsx": "ternary_expression",
    ".java": "ternary_expression",
}

_SUGGESTION = (
    "Replace nested ternary with if/elif/else statements or a lookup table "
    "for better readability"
)


@dataclass(frozen=True)
class NestedTernaryIssue:
    issue_type: str
    line: int
    depth: int
    message: str
    severity: str
    suggestion: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "depth": self.depth,
            "message": self.message,
            "severity": self.severity,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class NestedTernaryResult:
    issues: tuple[NestedTernaryIssue, ...]
    total_ternaries: int
    total_issues: int
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "total_ternaries": self.total_ternaries,
            "total_issues": self.total_issues,
            "issues": [i.to_dict() for i in self.issues],
        }


class NestedTernaryAnalyzer(BaseAnalyzer):
    """Detects deeply nested ternary/conditional expressions."""

    SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS

    def __init__(self, min_depth: int = MIN_DEPTH) -> None:
        super().__init__()
        self._min_depth = min_depth

    def analyze_file(self, file_path: str) -> NestedTernaryResult:
        path = Path(file_path)
        ext = path.suffix
        if ext not in self.SUPPORTED_EXTENSIONS:
            return NestedTernaryResult(
                issues=(), total_ternaries=0,
                total_issues=0, file_path=file_path,
            )

        source = path.read_bytes()
        _, parser = self._get_parser(ext)
        if parser is None:
            return NestedTernaryResult(
                issues=(), total_ternaries=0,
                total_issues=0, file_path=file_path,
            )
        tree = parser.parse(source)
        root = tree.root_node

        ternary_type = _TERNARY_TYPES.get(ext)
        if ternary_type is None:
            return NestedTernaryResult(
                issues=(), total_ternaries=0,
                total_issues=0, file_path=file_path,
            )

        issues: list[NestedTernaryIssue] = []
        total_ternaries = 0

        def _walk(node: tree_sitter.Node) -> None:
            nonlocal total_ternaries
            if node.type == ternary_type:
                total_ternaries += 1
                depth = self._measure_depth(node, ternary_type)
                if depth >= self._min_depth:
                    snippet = _txt(node)
                    if len(snippet) > 80:
                        snippet = snippet[:77] + "..."
                    issues.append(NestedTernaryIssue(
                        issue_type="nested_ternary",
                        line=node.start_point[0] + 1,
                        depth=depth,
                        message=(
                            f"Nested ternary (depth {depth}): "
                            f"'{snippet}'"
                        ),
                        severity=SEVERITY_HIGH if depth >= 3 else SEVERITY_MEDIUM,
                        suggestion=_SUGGESTION,
                    ))
            for child in node.children:
                _walk(child)

        _walk(root)

        return NestedTernaryResult(
            issues=tuple(issues),
            total_ternaries=total_ternaries,
            total_issues=len(issues),
            file_path=file_path,
        )

    def _measure_depth(
        self, node: tree_sitter.Node, ternary_type: str,
    ) -> int:
        """Measure the max nesting depth of ternary expressions."""
        max_child_depth = 0
        for child in node.children:
            if child.type == ternary_type:
                child_depth = self._measure_depth(child, ternary_type)
                if child_depth > max_child_depth:
                    max_child_depth = child_depth
        return 1 + max_child_depth
