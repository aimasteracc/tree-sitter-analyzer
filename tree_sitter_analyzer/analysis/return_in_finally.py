"""Return in Finally Detector.

Detects `return` or `raise` statements inside `finally` blocks. These
silently swallow exceptions from the `try` block, causing hard-to-debug
issues where errors disappear without a trace.

Issue types:
  - return_in_finally: return statement inside finally block
  - raise_in_finally: raise statement inside finally block

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

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

ISSUE_RETURN_IN_FINALLY = "return_in_finally"
ISSUE_RAISE_IN_FINALLY = "raise_in_finally"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_RETURN_IN_FINALLY: (
        "Return in finally silently swallows exceptions from try block"
    ),
    ISSUE_RAISE_IN_FINALLY: (
        "Raise in finally replaces exceptions from try block"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_RETURN_IN_FINALLY: (
        "Move the return outside the finally block, or re-raise "
        "the exception explicitly."
    ),
    ISSUE_RAISE_IN_FINALLY: (
        "Move the raise outside the finally block, or ensure "
        "the original exception is preserved."
    ),
}

# Node types per language
_FINALLY_TYPES: dict[str, set[str]] = {
    ".py": {"finally_clause"},
    ".js": {"finally_clause"},
    ".ts": {"finally_clause"},
    ".java": {"finally_"},
    ".go": set(),
}

_TERMINAL_TYPES: dict[str, dict[str, str]] = {
    ".py": {"return_statement": ISSUE_RETURN_IN_FINALLY, "raise_statement": ISSUE_RAISE_IN_FINALLY},
    ".js": {"return_statement": ISSUE_RETURN_IN_FINALLY, "throw_statement": ISSUE_RAISE_IN_FINALLY},
    ".ts": {"return_statement": ISSUE_RETURN_IN_FINALLY, "throw_statement": ISSUE_RAISE_IN_FINALLY},
    ".java": {"return_statement": ISSUE_RETURN_IN_FINALLY, "throw_statement": ISSUE_RAISE_IN_FINALLY},
    ".go": {"return_statement": ISSUE_RETURN_IN_FINALLY},
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


@dataclass(frozen=True)
class ReturnInFinallyIssue:
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
class ReturnInFinallyResult:
    file_path: str
    total_finally_blocks: int
    issues: list[ReturnInFinallyIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_finally_blocks": self.total_finally_blocks,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class ReturnInFinallyAnalyzer(BaseAnalyzer):
    """Detects return/raise statements inside finally blocks."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".java", ".go"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> ReturnInFinallyResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return ReturnInFinallyResult(
                file_path=str(path),
                total_finally_blocks=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ReturnInFinallyResult(
                file_path=str(path),
                total_finally_blocks=0,
            )

        finally_types = _FINALLY_TYPES.get(ext, set())
        terminal_map = _TERMINAL_TYPES.get(ext, {})
        if not finally_types or not terminal_map:
            return ReturnInFinallyResult(
                file_path=str(path),
                total_finally_blocks=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        total_finally = 0
        issues: list[ReturnInFinallyIssue] = []

        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in finally_types:
                total_finally += 1
                self._scan_finally(node, terminal_map, issues)
            else:
                for child in node.children:
                    stack.append(child)

        return ReturnInFinallyResult(
            file_path=str(path),
            total_finally_blocks=total_finally,
            issues=issues,
        )

    def _scan_finally(
        self,
        finally_node: tree_sitter.Node,
        terminal_map: dict[str, str],
        issues: list[ReturnInFinallyIssue],
    ) -> None:
        stack: list[tree_sitter.Node] = list(finally_node.children)
        while stack:
            node = stack.pop()
            if node.type in terminal_map:
                issue_type = terminal_map[node.type]
                severity = (
                    SEVERITY_HIGH
                    if issue_type == ISSUE_RETURN_IN_FINALLY
                    else SEVERITY_MEDIUM
                )
                issues.append(ReturnInFinallyIssue(
                    line=node.start_point[0] + 1,
                    issue_type=issue_type,
                    severity=severity,
                    description=_DESCRIPTIONS[issue_type],
                    suggestion=_SUGGESTIONS[issue_type],
                    context=_txt(node),
                ))
            for child in node.children:
                stack.append(child)
