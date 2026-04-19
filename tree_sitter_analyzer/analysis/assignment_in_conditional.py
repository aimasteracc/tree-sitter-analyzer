"""Assignment in Conditional Detector.

Detects assignments used as conditions in if/while statements,
which are commonly `=` vs `==` typos.

Supports JavaScript, TypeScript, Java, C, C++.
(Python does not allow `if x = 5` syntax.)
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


SUPPORTED_EXTENSIONS: set[str] = {
    ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cpp", ".hpp", ".h",
}

SEVERITY_HIGH = "high"

ISSUE_ASSIGNMENT_IN_CONDITIONAL = "assignment_in_conditional"

_SUGGESTION = (
    "Did you mean '==' (comparison) instead of '=' (assignment)? "
    "If intentional, extract to a variable before the if statement."
)

_IF_TYPES: frozenset[str] = frozenset({"if_statement"})
_WHILE_TYPES: frozenset[str] = frozenset({"while_statement"})


@dataclass(frozen=True)
class AssignmentInConditionalIssue:
    issue_type: str
    line: int
    message: str
    severity: str
    statement_type: str
    suggestion: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
            "statement_type": self.statement_type,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class AssignmentInConditionalResult:
    issues: tuple[AssignmentInConditionalIssue, ...]
    total_issues: int
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "total_issues": self.total_issues,
            "issues": [i.to_dict() for i in self.issues],
        }


class AssignmentInConditionalAnalyzer(BaseAnalyzer):
    """Detects assignments used as conditions in if/while statements."""

    SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS

    def __init__(self) -> None:
        super().__init__()

    def analyze_file(self, file_path: str) -> AssignmentInConditionalResult:
        path = Path(file_path)
        ext = path.suffix
        if ext not in SUPPORTED_EXTENSIONS:
            return AssignmentInConditionalResult(
                issues=(), total_issues=0, file_path=file_path,
            )

        source = path.read_bytes()
        _, parser = self._get_parser(ext)
        if parser is None:
            return AssignmentInConditionalResult(
                issues=(), total_issues=0, file_path=file_path,
            )
        tree = parser.parse(source)
        root = tree.root_node

        issues: list[AssignmentInConditionalIssue] = []

        def _walk(node: tree_sitter.Node) -> None:
            if node.type in _IF_TYPES or node.type in _WHILE_TYPES:
                issues.extend(self._check_condition(node))
            for child in node.children:
                _walk(child)

        _walk(root)

        return AssignmentInConditionalResult(
            issues=tuple(issues),
            total_issues=len(issues),
            file_path=file_path,
        )

    def _check_condition(
        self, stmt_node: tree_sitter.Node,
    ) -> list[AssignmentInConditionalIssue]:
        condition = stmt_node.child_by_field_name("condition")
        if condition is None:
            return []

        return self._find_assignments(condition, stmt_node.type)

    def _find_assignments(
        self, node: tree_sitter.Node, stmt_type: str,
    ) -> list[AssignmentInConditionalIssue]:
        issues: list[AssignmentInConditionalIssue] = []

        if node.type == "assignment_expression":
            snippet = _txt(node)
            if len(snippet) > 60:
                snippet = snippet[:57] + "..."
            stmt_label = "if" if stmt_type in _IF_TYPES else "while"
            issues.append(AssignmentInConditionalIssue(
                issue_type=ISSUE_ASSIGNMENT_IN_CONDITIONAL,
                line=node.start_point[0] + 1,
                message=(
                    f"Assignment in {stmt_label} condition: "
                    f"'{snippet}' (likely '==' typo)"
                ),
                severity=SEVERITY_HIGH,
                statement_type=stmt_label,
                suggestion=_SUGGESTION,
            ))

        for child in node.children:
            issues.extend(self._find_assignments(child, stmt_type))

        return issues
