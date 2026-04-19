"""Constant Boolean Operand Detector.

Detects non-boolean constant operands in boolean expressions (and/or):
  - constant_bool_operand: string/number/list/dict used in or/and (medium)

Classic Python pitfall: `if x == "a" or "b":` is always True because
"b" is truthy. The programmer likely meant `if x == "a" or x == "b":`.

Supports Python.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"

ISSUE_CONSTANT_BOOL_OPERAND = "constant_bool_operand"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_CONSTANT_BOOL_OPERAND: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_CONSTANT_BOOL_OPERAND: (
        "Non-boolean constant used as operand in boolean expression — "
        "condition may always evaluate to True/False"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_CONSTANT_BOOL_OPERAND: (
        "Use explicit comparison: `x == a or x == b` instead of `x == a or b`."
    ),
}

# Node types that are non-boolean constants
_CONSTANT_TYPES: frozenset[str] = frozenset({
    "string",
    "string_content",
    "concatenated_string",
    "integer",
    "float",
    "true",
    "false",
    "none",
    "list",
    "dictionary",
    "set",
    "tuple",
    "fstring",
    "escape_sequence",
})

# Boolean operator strings
_BOOL_OPS: frozenset[str] = frozenset({"and", "or"})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


def _is_constant_node(node: tree_sitter.Node) -> bool:
    """Check if a node is a non-boolean constant value."""
    if node.type in _CONSTANT_TYPES:
        return True
    # Negative numbers: unary operator + number
    if node.type == "unary_operator":
        child = node.child_by_field_name("argument")
        if child is not None and child.type in ("integer", "float"):
            return True
    # Parenthesized constant
    if node.type == "parenthesized_expression" and node.child_count >= 3:
        inner = node.children[1] if len(node.children) > 1 else None
        if inner is not None and _is_constant_node(inner):
            return True
    return False


def _is_bool_constant(node: tree_sitter.Node) -> bool:
    """Check if a node is True, False, or None."""
    return node.type in ("true", "false", "none", "True", "False", "None")


@dataclass(frozen=True)
class ConstantBoolOperandIssue:
    line_number: int
    issue_type: str
    severity: str
    description: str
    operand_snippet: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "operand_snippet": self.operand_snippet,
        }


@dataclass(frozen=True)
class ConstantBoolOperandResult:
    total_boolean_expressions: int
    issues: tuple[ConstantBoolOperandIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_boolean_expressions": self.total_boolean_expressions,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


def _check_binary_expr(
    node: tree_sitter.Node,
    issues: list[ConstantBoolOperandIssue],
) -> None:
    """Check a boolean binary expression for constant operands."""
    if node.type != "boolean_operator":
        return
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if left is None or right is None:
        return
    for operand in (left, right):
        if _is_constant_node(operand) and not _is_bool_constant(operand):
            snippet = _safe_text(operand)
            if len(snippet) > 50:
                snippet = snippet[:47] + "..."
            issues.append(ConstantBoolOperandIssue(
                line_number=operand.start_point[0] + 1,
                issue_type=ISSUE_CONSTANT_BOOL_OPERAND,
                severity=_SEVERITY_MAP[ISSUE_CONSTANT_BOOL_OPERAND],
                description=_DESCRIPTIONS[ISSUE_CONSTANT_BOOL_OPERAND],
                operand_snippet=snippet,
            ))


def _analyze_python(
    node: tree_sitter.Node,
    issues: list[ConstantBoolOperandIssue],
) -> int:
    """Analyze Python AST for constant boolean operands."""
    bool_expr_count = 0

    def visit(n: tree_sitter.Node) -> None:
        nonlocal bool_expr_count
        if n.type == "boolean_operator":
            bool_expr_count += 1
            _check_binary_expr(n, issues)
        for child in n.children:
            visit(child)

    visit(node)
    return bool_expr_count


class ConstantBoolOperandAnalyzer(BaseAnalyzer):
    """Detects non-boolean constant operands in boolean expressions."""

    SUPPORTED_EXTENSIONS: set[str] = {".py"}

    def analyze_file(self, file_path: Path | str) -> ConstantBoolOperandResult:
        path = Path(file_path)
        if not path.exists():
            return ConstantBoolOperandResult(
                total_boolean_expressions=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return ConstantBoolOperandResult(
                total_boolean_expressions=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> ConstantBoolOperandResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ConstantBoolOperandResult(
                total_boolean_expressions=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        issues: list[ConstantBoolOperandIssue] = []
        total_boolean_expressions = 0

        if ext == ".py":
            total_boolean_expressions = _analyze_python(tree.root_node, issues)

        return ConstantBoolOperandResult(
            total_boolean_expressions=total_boolean_expressions,
            issues=tuple(issues),
            file_path=str(path),
        )
