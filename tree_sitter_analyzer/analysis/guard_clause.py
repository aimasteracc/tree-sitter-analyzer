"""Guard Clause Opportunity Detector.

Detects if/else blocks where the else branch only contains a terminal
statement (return/raise/throw/break/continue) while the if branch has
substantial work. These are candidates for guard clause refactoring:
invert the condition and return early, flattening the code.

Example:
    if condition:           if not condition:
        ...do work...           return
        ...more work...         ...do work...
    else:           →       ...more work...
        return

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

ISSUE_GUARD_CLAUSE = "guard_clause_opportunity"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_GUARD_CLAUSE: (
        "else branch only exits while if branch does substantial work. "
        "Consider inverting the condition and returning early."
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_GUARD_CLAUSE: (
        "Invert the condition and move the return/raise to the top. "
        "This flattens the code and makes the happy path more visible."
    ),
}

MIN_IF_BODY_STATEMENTS = 3

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
    }),
}

_IF_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"if_statement"}),
    ".js": frozenset({"if_statement"}),
    ".jsx": frozenset({"if_statement"}),
    ".ts": frozenset({"if_statement"}),
    ".tsx": frozenset({"if_statement"}),
    ".java": frozenset({"if_statement"}),
    ".go": frozenset({"if_statement"}),
}

_BLOCK_TYPES: frozenset[str] = frozenset({
    "block", "body", "statement_block", "compound_statement",
})

# Node types that are "trivial" and shouldn't count toward statement count
_TRIVIAL_TYPES: frozenset[str] = frozenset({
    "pass_statement", "comment", "empty_statement",
})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class GuardClauseIssue:
    line_number: int
    issue_type: str
    variable_name: str
    severity: str
    description: str
    if_body_lines: int

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
            "if_body_lines": self.if_body_lines,
        }


@dataclass(frozen=True)
class GuardClauseResult:
    total_ifs: int
    issues: tuple[GuardClauseIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_ifs": self.total_ifs,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


def _count_meaningful_statements(node: tree_sitter.Node) -> int:
    """Count named children that are not trivial statements."""
    count = 0
    for child in node.children:
        if not child.is_named:
            continue
        if child.type in _TRIVIAL_TYPES:
            continue
        count += 1
    return count


def _is_single_terminal(
    node: tree_sitter.Node,
    terminators: frozenset[str],
) -> bool:
    """Check if a node contains exactly one terminal statement and nothing else."""
    named_children = [c for c in node.children if c.is_named]

    if len(named_children) == 0:
        return False

    if len(named_children) == 1:
        child = named_children[0]
        if child.type in terminators:
            return True
        # Some languages wrap return in a block
        if child.type in _BLOCK_TYPES:
            return _is_single_terminal(child, terminators)

    return False


def _has_elif_chain(if_node: tree_sitter.Node) -> bool:
    """Check if this if is part of an elif chain (parent else contains this if)."""
    parent = if_node.parent
    if parent is None:
        return False
    # Python: elif_clause is a separate node type
    if parent.type in ("elif_clause", "else_clause"):
        return True
    # JS/TS/Java: else if is an if_statement inside else_clause
    if parent.type == "else_clause":
        return True
    return False


def _get_if_body(if_node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Get the consequence (if-body) node."""
    consequence = if_node.child_by_field_name("consequence")
    return consequence


def _get_else_body(if_node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Get the alternative (else-body) node, unwrapping else_clause if needed."""
    alternative = if_node.child_by_field_name("alternative")
    if alternative is None:
        return None
    # Some languages have else_clause wrapper
    if alternative.type == "else_clause":
        named_children = [c for c in alternative.children if c.is_named]
        if not named_children:
            return None
        inner = named_children[0]
        # If the inner is another if_statement, this is an elif chain
        if inner.type in ("if_statement", "elif_clause"):
            return None
        return inner
    return alternative


class GuardClauseAnalyzer(BaseAnalyzer):
    """Analyzes code for guard clause refactoring opportunities."""

    def analyze_file(self, file_path: Path | str) -> GuardClauseResult:
        path = Path(file_path)
        if not path.exists():
            return GuardClauseResult(
                total_ifs=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return GuardClauseResult(
                total_ifs=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> GuardClauseResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return GuardClauseResult(
                total_ifs=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        if_types = _IF_TYPES.get(ext, frozenset())
        terminators = _TERMINATORS.get(ext, frozenset())
        issues: list[GuardClauseIssue] = []
        total_ifs = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total_ifs

            if node.type in if_types:
                total_ifs += 1
                self._check_if(node, terminators, issues, ext)

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return GuardClauseResult(
            total_ifs=total_ifs,
            issues=tuple(issues),
            file_path=str(path),
        )

    def _check_if(
        self,
        if_node: tree_sitter.Node,
        terminators: frozenset[str],
        issues: list[GuardClauseIssue],
        ext: str,
    ) -> None:
        """Check a single if statement for guard clause opportunity."""
        if _has_elif_chain(if_node):
            return

        consequence = _get_if_body(if_node)
        alternative = _get_else_body(if_node)

        if consequence is None or alternative is None:
            return

        # Check: else body is a single terminal statement
        if not _is_single_terminal(alternative, terminators):
            return

        # Check: if body has substantial work (3+ meaningful statements)
        if_body_node = consequence
        if consequence.type in _BLOCK_TYPES:
            if_body_node = consequence

        stmt_count = _count_meaningful_statements(if_body_node)
        if stmt_count < MIN_IF_BODY_STATEMENTS:
            return

        issues.append(GuardClauseIssue(
            line_number=if_node.start_point[0] + 1,
            issue_type=ISSUE_GUARD_CLAUSE,
            variable_name=_safe_text(if_node).split("\n")[0][:40],
            severity=SEVERITY_LOW,
            description=_DESCRIPTIONS[ISSUE_GUARD_CLAUSE],
            if_body_lines=stmt_count,
        ))
