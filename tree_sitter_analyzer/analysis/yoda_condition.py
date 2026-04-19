"""Yoda Condition Detector.

Detects comparisons where a literal appears on the left side:
  - yoda_eq: "literal" == variable (use variable == "literal")
  - yoda_neq: "literal" != variable (use variable != "literal")

Classic C-era habit from preventing accidental assignment (if (x = 5)).
Modern languages make this unnecessary. Yoda conditions hurt readability.

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"

ISSUE_YODA_EQ = "yoda_eq"
ISSUE_YODA_NEQ = "yoda_neq"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_YODA_EQ: SEVERITY_LOW,
    ISSUE_YODA_NEQ: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_YODA_EQ: "Yoda condition: literal on left of == — swap operand order for readability",
    ISSUE_YODA_NEQ: "Yoda condition: literal on left of != — swap operand order for readability",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_YODA_EQ: "Put the variable on the left: 'variable == literal' is easier to read.",
    ISSUE_YODA_NEQ: "Put the variable on the left: 'variable != literal' is easier to read.",
}

_COMPARISON_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"comparison_operator"}),
    ".js": frozenset({"binary_expression"}),
    ".jsx": frozenset({"binary_expression"}),
    ".ts": frozenset({"binary_expression"}),
    ".tsx": frozenset({"binary_expression"}),
    ".java": frozenset({"binary_expression"}),
    ".go": frozenset({"binary_expression"}),
}

_EQ_OPS: frozenset[str] = frozenset({"=="})
_NEQ_OPS: frozenset[str] = frozenset({"!="})

_LITERAL_NODE_TYPES: frozenset[str] = frozenset({
    "string",
    "string_literal",
    "interpreted_string_literal",
    "raw_string_literal",
    "template_string",
    "number",
    "integer",
    "float",
    "true",
    "false",
    "True",
    "False",
    "none",
    "None",
    "null",
    "null_literal",
    "undefined",
    "nil",
    "nil_literal",
    "character_literal",
    "number_literal",
    "decimal_integer_literal",
    "decimal_floating_point_literal",
    "int_literal",
    "float_literal",
    "imaginary_literal",
    "escape_interpolation",
    "boolean_literal",
})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


def _is_literal(node: tree_sitter.Node) -> bool:
    return node.type in _LITERAL_NODE_TYPES


def _get_operator(node: tree_sitter.Node, ext: str) -> str:
    if ext == ".py":
        for child in node.children:
            if not child.is_named:
                op = _safe_text(child).strip()
                if op in _EQ_OPS or op in _NEQ_OPS:
                    return op
    else:
        for child in node.children_by_field_name("operator"):
            return _safe_text(child).strip()
        for child in node.children:
            if not child.is_named:
                op = _safe_text(child).strip()
                if op in _EQ_OPS or op in _NEQ_OPS:
                    return op
    return ""


def _get_left_right(node: tree_sitter.Node, ext: str) -> tuple[tree_sitter.Node, tree_sitter.Node]:
    if ext == ".py":
        named = [c for c in node.children if c.is_named]
        if len(named) >= 2:
            return named[0], named[1]
    else:
        left_nodes = node.children_by_field_name("left")
        right_nodes = node.children_by_field_name("right")
        if left_nodes and right_nodes:
            return left_nodes[0], right_nodes[0]
        named = [c for c in node.children if c.is_named]
        if len(named) >= 2:
            return named[0], named[1]
    return node, node


@dataclass(frozen=True)
class YodaConditionIssue:
    issue_type: str
    line: int
    column: int
    severity: str
    description: str
    suggestion: str
    context: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
        }


@dataclass
class YodaConditionResult:
    file_path: str
    total_comparisons: int
    issues: list[YodaConditionIssue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_comparisons": self.total_comparisons,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class YodaConditionAnalyzer(BaseAnalyzer):
    """Detects Yoda conditions (literal on the left of comparisons)."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
        }

    def analyze_file(
        self, file_path: str | Path,
    ) -> YodaConditionResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return YodaConditionResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return YodaConditionResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )

        try:
            source = path.read_bytes()
        except OSError:
            return YodaConditionResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return YodaConditionResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )

        comp_types = _COMPARISON_TYPES.get(ext)
        if comp_types is None:
            return YodaConditionResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )

        issues: list[YodaConditionIssue] = []
        total_comparisons = 0

        for node in _walk(tree.root_node):
            if node.type not in comp_types:
                continue
            total_comparisons += 1

            issue = self._check_yoda(node, ext)
            if issue is not None:
                issues.append(issue)

        return YodaConditionResult(
            file_path=str(path),
            total_comparisons=total_comparisons,
            issues=issues,
        )

    def _check_yoda(
        self,
        node: tree_sitter.Node,
        ext: str,
    ) -> YodaConditionIssue | None:
        op = _get_operator(node, ext)
        if not op:
            return None

        left, right = _get_left_right(node, ext)
        if left == right:
            return None

        if not _is_literal(left):
            return None
        if _is_literal(right):
            return None

        if op in _EQ_OPS:
            issue_type = ISSUE_YODA_EQ
        elif op in _NEQ_OPS:
            issue_type = ISSUE_YODA_NEQ
        else:
            return None

        return self._make_issue(issue_type, node)

    def _make_issue(
        self,
        issue_type: str,
        node: tree_sitter.Node,
    ) -> YodaConditionIssue:
        context = _safe_text(node)
        return YodaConditionIssue(
            issue_type=issue_type,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            severity=_SEVERITY_MAP[issue_type],
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=context[:200],
        )


def _walk(node: tree_sitter.Node) -> Any:
    cursor = node.walk()
    reached_root = False
    while not reached_root:
        yield cursor.node
        if cursor.goto_first_child():
            continue
        if cursor.goto_next_sibling():
            continue
        retracing = True
        while retracing:
            if not cursor.goto_parent():
                retracing = False
                reached_root = True
            elif cursor.node == node:
                retracing = False
                reached_root = True
            elif cursor.goto_next_sibling():
                retracing = False
