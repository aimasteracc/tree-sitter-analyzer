"""Unreachable Code Detector.

Detects code that appears after unconditional termination statements
(return/break/continue/raise/throw), which can never execute:

  - unreachable_after_return: code after return
  - unreachable_after_break: code after break
  - unreachable_after_continue: code after continue
  - unreachable_after_raise: code after raise (Python)
  - unreachable_after_throw: code after throw (Java/JS/TS)

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

ISSUE_AFTER_RETURN = "unreachable_after_return"
ISSUE_AFTER_BREAK = "unreachable_after_break"
ISSUE_AFTER_CONTINUE = "unreachable_after_continue"
ISSUE_AFTER_RAISE = "unreachable_after_raise"
ISSUE_AFTER_THROW = "unreachable_after_throw"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_AFTER_RETURN: "Code after return statement is unreachable",
    ISSUE_AFTER_BREAK: "Code after break statement is unreachable",
    ISSUE_AFTER_CONTINUE: "Code after continue statement is unreachable",
    ISSUE_AFTER_RAISE: "Code after raise statement is unreachable",
    ISSUE_AFTER_THROW: "Code after throw statement is unreachable",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_AFTER_RETURN: "Remove the unreachable code after the return statement.",
    ISSUE_AFTER_BREAK: "Remove the unreachable code after the break statement.",
    ISSUE_AFTER_CONTINUE: "Remove the unreachable code after the continue statement.",
    ISSUE_AFTER_RAISE: "Remove the unreachable code after the raise statement.",
    ISSUE_AFTER_THROW: "Remove the unreachable code after the throw statement.",
}

_TERMINAL_NODES: dict[str, dict[str, str]] = {
    ".py": {
        "return_statement": ISSUE_AFTER_RETURN,
        "break_statement": ISSUE_AFTER_BREAK,
        "continue_statement": ISSUE_AFTER_CONTINUE,
        "raise_statement": ISSUE_AFTER_RAISE,
    },
    ".java": {
        "return_statement": ISSUE_AFTER_RETURN,
        "break_statement": ISSUE_AFTER_BREAK,
        "continue_statement": ISSUE_AFTER_CONTINUE,
        "throw_statement": ISSUE_AFTER_THROW,
    },
    ".js": {
        "return_statement": ISSUE_AFTER_RETURN,
        "break_statement": ISSUE_AFTER_BREAK,
        "continue_statement": ISSUE_AFTER_CONTINUE,
        "throw_statement": ISSUE_AFTER_THROW,
    },
    ".jsx": {
        "return_statement": ISSUE_AFTER_RETURN,
        "break_statement": ISSUE_AFTER_BREAK,
        "continue_statement": ISSUE_AFTER_CONTINUE,
        "throw_statement": ISSUE_AFTER_THROW,
    },
    ".ts": {
        "return_statement": ISSUE_AFTER_RETURN,
        "break_statement": ISSUE_AFTER_BREAK,
        "continue_statement": ISSUE_AFTER_CONTINUE,
        "throw_statement": ISSUE_AFTER_THROW,
    },
    ".tsx": {
        "return_statement": ISSUE_AFTER_RETURN,
        "break_statement": ISSUE_AFTER_BREAK,
        "continue_statement": ISSUE_AFTER_CONTINUE,
        "throw_statement": ISSUE_AFTER_THROW,
    },
    ".go": {
        "return_statement": ISSUE_AFTER_RETURN,
        "break_statement": ISSUE_AFTER_BREAK,
        "continue_statement": ISSUE_AFTER_CONTINUE,
    },
}

_BLOCK_TYPES: frozenset[str] = frozenset({
    "block", "statement_block", "function_body",
    "module", "expression_statement",
})


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


@dataclass(frozen=True)
class UnreachableCodeIssue:
    line: int
    issue_type: str
    severity: str
    description: str
    suggestion: str
    context: str
    terminal_line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
            "terminal_line": self.terminal_line,
        }


@dataclass
class UnreachableCodeResult:
    file_path: str
    total_blocks: int
    issues: list[UnreachableCodeIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_blocks": self.total_blocks,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class UnreachableCodeAnalyzer(BaseAnalyzer):
    """Detects unreachable code after terminal statements."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
        }

    def analyze_file(
        self, file_path: str | Path,
    ) -> UnreachableCodeResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return UnreachableCodeResult(
                file_path=str(path),
                total_blocks=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return UnreachableCodeResult(
                file_path=str(path),
                total_blocks=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)
        terminal_map = _TERMINAL_NODES.get(ext, {})
        issues: list[UnreachableCodeIssue] = []
        total_blocks = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total_blocks

            if node.type in _BLOCK_TYPES or node.child_by_field_name("body") is not None:
                total_blocks += 1
                self._scan_block(node, terminal_map, issues)

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return UnreachableCodeResult(
            file_path=str(path),
            total_blocks=total_blocks,
            issues=issues,
        )

    def _scan_block(
        self,
        node: tree_sitter.Node,
        terminal_map: dict[str, str],
        issues: list[UnreachableCodeIssue],
    ) -> None:
        children = node.children
        found_terminal = False
        terminal_issue_type = ""
        terminal_line = 0

        for child in children:
            if found_terminal:
                if child.is_named:
                    issues.append(UnreachableCodeIssue(
                        line=child.start_point[0] + 1,
                        issue_type=terminal_issue_type,
                        severity=SEVERITY_MEDIUM,
                        description=_DESCRIPTIONS.get(terminal_issue_type, ""),
                        suggestion=_SUGGESTIONS.get(terminal_issue_type, ""),
                        context=_txt(child),
                        terminal_line=terminal_line,
                    ))
                continue

            if child.type in terminal_map:
                terminal_issue_type = terminal_map[child.type]
                terminal_line = child.start_point[0] + 1
                found_terminal = True
