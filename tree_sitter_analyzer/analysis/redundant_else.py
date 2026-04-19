"""Redundant Else Detector.

Detects else/elif blocks that are unnecessary because the corresponding if
block already terminates with return/break/continue/raise/throw/sys.exit.

Example:
    if x > 0:          if x > 0:
        return "pos"       return "pos"
    else:        →     return "non-pos"
        return "non"

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_LOW = "low"

ISSUE_REDUNDANT_ELSE = "redundant_else"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_REDUNDANT_ELSE: "else/elif block is unnecessary because the if block already terminates",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_REDUNDANT_ELSE: "Remove the else block and dedent its body. The if already returns/breaks.",
}

# Node types that represent a terminating statement
_TERMINATORS: dict[str, frozenset[str]] = {
    ".py": frozenset({
        "return_statement", "raise_statement", "break_statement",
        "continue_statement",
    }),
    ".js": frozenset({
        "return_statement", "throw_statement", "break_statement",
        "continue_statement",
    }),
    ".jsx": frozenset({
        "return_statement", "throw_statement", "break_statement",
        "continue_statement",
    }),
    ".ts": frozenset({
        "return_statement", "throw_statement", "break_statement",
        "continue_statement",
    }),
    ".tsx": frozenset({
        "return_statement", "throw_statement", "break_statement",
        "continue_statement",
    }),
    ".java": frozenset({
        "return_statement", "throw_statement", "break_statement",
        "continue_statement",
    }),
    ".go": frozenset({
        "return_statement", "break_statement", "continue_statement",
        "go_statement",
    }),
}

# If statement types per language
_IF_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"if_statement"}),
    ".js": frozenset({"if_statement"}),
    ".jsx": frozenset({"if_statement"}),
    ".ts": frozenset({"if_statement"}),
    ".tsx": frozenset({"if_statement"}),
    ".java": frozenset({"if_statement"}),
    ".go": frozenset({"if_statement"}),
}

# Block body types per language
_BLOCK_TYPES: frozenset[str] = frozenset({
    "block", "body", "statement_block", "compound_statement",
})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class RedundantElseIssue:
    line_number: int
    issue_type: str
    variable_name: str
    severity: str
    description: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "variable_name": self.variable_name,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class RedundantElseResult:
    total_ifs: int
    issues: tuple[RedundantElseIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_ifs": self.total_ifs,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


def _block_terminates(
    node: tree_sitter.Node,
    terminators: frozenset[str],
) -> bool:
    """Check if a block always terminates (ends with a terminating statement)."""
    children = [c for c in node.children if c.is_named]
    if not children:
        return False

    last = children[-1]

    if last.type in terminators:
        return True

    # Check if the last statement is an if/else where both branches terminate
    if last.type in ("if_statement",):
        return _if_both_branches_terminate(last, terminators)

    return False


def _if_both_branches_terminate(
    if_node: tree_sitter.Node,
    terminators: frozenset[str],
) -> bool:
    """Check if both if and else branches terminate."""
    consequence = if_node.child_by_field_name("consequence")
    alternative = if_node.child_by_field_name("alternative")

    if consequence is None or alternative is None:
        return False

    cons_terminates = False
    if consequence.type in _BLOCK_TYPES:
        cons_terminates = _block_terminates(consequence, terminators)
    elif consequence.type in terminators:
        cons_terminates = True

    alt_terminates = False
    if alternative.type == "else_clause":
        for child in alternative.children:
            if child.is_named:
                if child.type == "if_statement":
                    alt_terminates = _if_both_branches_terminate(child, terminators)
                elif child.type in _BLOCK_TYPES:
                    alt_terminates = _block_terminates(child, terminators)
                elif child.type in terminators:
                    alt_terminates = True
                break
    elif alternative.type in _BLOCK_TYPES:
        alt_terminates = _block_terminates(alternative, terminators)
    elif alternative.type in terminators:
        alt_terminates = True

    return cons_terminates and alt_terminates


class RedundantElseAnalyzer(BaseAnalyzer):
    """Analyzes code for redundant else blocks."""

    def analyze_file(self, file_path: Path | str) -> RedundantElseResult:
        path = Path(file_path)
        if not path.exists():
            return RedundantElseResult(
                total_ifs=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return RedundantElseResult(
                total_ifs=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> RedundantElseResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return RedundantElseResult(
                total_ifs=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        if_types = _IF_TYPES.get(ext, frozenset())
        terminators = _TERMINATORS.get(ext, frozenset())
        issues: list[RedundantElseIssue] = []
        total_ifs = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total_ifs

            if node.type in if_types:
                total_ifs += 1
                self._check_if(node, terminators, issues)

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return RedundantElseResult(
            total_ifs=total_ifs,
            issues=tuple(issues),
            file_path=str(path),
        )

    def _check_if(
        self,
        if_node: tree_sitter.Node,
        terminators: frozenset[str],
        issues: list[RedundantElseIssue],
    ) -> None:
        """Check a single if statement for redundant else."""
        consequence = if_node.child_by_field_name("consequence")
        alternative = if_node.child_by_field_name("alternative")

        if consequence is None or alternative is None:
            return

        # Check if consequence terminates
        cons_terminates = False
        if consequence.type in _BLOCK_TYPES:
            cons_terminates = _block_terminates(consequence, terminators)
        elif consequence.type in terminators:
            cons_terminates = True

        if not cons_terminates:
            return

        issues.append(RedundantElseIssue(
            line_number=alternative.start_point[0] + 1,
            issue_type=ISSUE_REDUNDANT_ELSE,
            variable_name=_safe_text(alternative).split("\n")[0][:40],
            severity=SEVERITY_LOW,
            description=_DESCRIPTIONS[ISSUE_REDUNDANT_ELSE],
        ))
