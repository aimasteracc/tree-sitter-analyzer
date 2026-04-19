"""String Format Consistency Detector.

Detects mixed string formatting styles within the same file:
  - mixed_format_styles: file uses multiple formatting approaches

Python has three main string formatting approaches:
  1. %-formatting: "Hello %s" % name
  2. .format(): "Hello {}".format(name)
  3. f-strings: f"Hello {name}"

Mixing styles within a file reduces readability and consistency.
Modern Python (3.6+) should prefer f-strings.

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
SEVERITY_INFO = "info"

ISSUE_MIXED_FORMAT = "mixed_format_styles"
ISSUE_LEGACY_FORMAT = "legacy_percent_format"
ISSUE_LEGACY_DOT_FORMAT = "legacy_dot_format"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_MIXED_FORMAT: "File uses multiple string formatting styles (%s, .format(), f-string)",
    ISSUE_LEGACY_FORMAT: "Uses %-formatting instead of f-strings",
    ISSUE_LEGACY_DOT_FORMAT: "Uses .format() instead of f-strings",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_MIXED_FORMAT: "Standardize on f-strings (Python 3.6+) for all string formatting.",
    ISSUE_LEGACY_FORMAT: "Replace %-formatting with f-strings for better readability.",
    ISSUE_LEGACY_DOT_FORMAT: "Replace .format() with f-strings for better readability.",
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _contains_placeholder(node: tree_sitter.Node) -> bool:
    text = node.text.decode("utf-8", errors="replace") if node.text else ""
    return "%s" in text or "%d" in text or "%r" in text or "%f" in text or "%i" in text


def _is_fstring(node: tree_sitter.Node) -> bool:
    if node.type != "string":
        return False
    for child in node.children:
        if child.type == "interpolation":
            return True
    return False


@dataclass(frozen=True)
class FormatConsistencyIssue:
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
class StringFormatConsistencyResult:
    file_path: str
    total_strings: int
    percent_format_count: int
    dot_format_count: int
    fstring_count: int
    issues: list[FormatConsistencyIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_strings": self.total_strings,
            "percent_format_count": self.percent_format_count,
            "dot_format_count": self.dot_format_count,
            "fstring_count": self.fstring_count,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class StringFormatConsistencyAnalyzer(BaseAnalyzer):
    """Detects mixed string formatting styles in Python."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> StringFormatConsistencyResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return StringFormatConsistencyResult(
                file_path=str(path),
                total_strings=0,
                percent_format_count=0,
                dot_format_count=0,
                fstring_count=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return StringFormatConsistencyResult(
                file_path=str(path),
                total_strings=0,
                percent_format_count=0,
                dot_format_count=0,
                fstring_count=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        percent_locs: list[tuple[int, str]] = []
        dot_format_locs: list[tuple[int, str]] = []
        fstring_locs: list[tuple[int, str]] = []
        total_strings = 0

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "string":
                total_strings += 1
                if _is_fstring(node):
                    fstring_locs.append((
                        node.start_point[0] + 1,
                        _txt(node),
                    ))
                elif _contains_placeholder(node):
                    parent = node.parent
                    if parent and parent.type == "binary_operator":
                        op = None
                        for child in parent.children:
                            if child.type == "%":
                                op = child
                                break
                        if op is not None:
                            percent_locs.append((
                                node.start_point[0] + 1,
                                _txt(node),
                            ))

            if node.type == "call":
                func = node.child_by_field_name("function")
                if func:
                    func_text = func.text.decode("utf-8", errors="replace") if func.text else ""
                    if func_text.endswith(".format"):
                        args = node.child_by_field_name("arguments")
                        if args:
                            total_strings += 1
                            dot_format_locs.append((
                                node.start_point[0] + 1,
                                _txt(node),
                            ))

            for child in node.children:
                stack.append(child)

        issues: list[FormatConsistencyIssue] = []
        styles_used = 0
        if percent_locs:
            styles_used += 1
        if dot_format_locs:
            styles_used += 1
        if fstring_locs:
            styles_used += 1

        if styles_used >= 2:
            for line, ctx in percent_locs:
                issues.append(FormatConsistencyIssue(
                    line=line,
                    issue_type=ISSUE_MIXED_FORMAT,
                    severity=SEVERITY_LOW,
                    description=_DESCRIPTIONS[ISSUE_MIXED_FORMAT],
                    suggestion=_SUGGESTIONS[ISSUE_MIXED_FORMAT],
                    context=ctx,
                ))
            for line, ctx in dot_format_locs:
                issues.append(FormatConsistencyIssue(
                    line=line,
                    issue_type=ISSUE_MIXED_FORMAT,
                    severity=SEVERITY_LOW,
                    description=_DESCRIPTIONS[ISSUE_MIXED_FORMAT],
                    suggestion=_SUGGESTIONS[ISSUE_MIXED_FORMAT],
                    context=ctx,
                ))
        elif percent_locs and not fstring_locs and not dot_format_locs:
            for line, ctx in percent_locs:
                issues.append(FormatConsistencyIssue(
                    line=line,
                    issue_type=ISSUE_LEGACY_FORMAT,
                    severity=SEVERITY_INFO,
                    description=_DESCRIPTIONS[ISSUE_LEGACY_FORMAT],
                    suggestion=_SUGGESTIONS[ISSUE_LEGACY_FORMAT],
                    context=ctx,
                ))
        elif dot_format_locs and not fstring_locs and not percent_locs:
            for line, ctx in dot_format_locs:
                issues.append(FormatConsistencyIssue(
                    line=line,
                    issue_type=ISSUE_LEGACY_DOT_FORMAT,
                    severity=SEVERITY_INFO,
                    description=_DESCRIPTIONS[ISSUE_LEGACY_DOT_FORMAT],
                    suggestion=_SUGGESTIONS[ISSUE_LEGACY_DOT_FORMAT],
                    context=ctx,
                ))

        return StringFormatConsistencyResult(
            file_path=str(path),
            total_strings=total_strings,
            percent_format_count=len(percent_locs),
            dot_format_count=len(dot_format_locs),
            fstring_count=len(fstring_locs),
            issues=issues,
        )
