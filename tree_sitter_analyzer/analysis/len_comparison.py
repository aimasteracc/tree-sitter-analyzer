"""Len-Comparison Anti-pattern Detector.

Detects explicit len() comparisons that should use truthiness:
  - len_eq_zero: len(x) == 0 → use `not x`
  - len_ne_zero: len(x) != 0 → use `x`
  - len_gt_zero: len(x) > 0 → use `x`
  - len_ge_one: len(x) >= 1 → use `x`

Also detects .length/.size() equivalents in other languages.

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

SEVERITY_LOW = "low"

ISSUE_LEN_EQ_ZERO = "len_eq_zero"
ISSUE_LEN_NE_ZERO = "len_ne_zero"
ISSUE_LEN_GT_ZERO = "len_gt_zero"
ISSUE_LEN_GE_ONE = "len_ge_one"
ISSUE_LEN_LT_ONE = "len_lt_one"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_LEN_EQ_ZERO: "Use `not x` instead of `len(x) == 0`",
    ISSUE_LEN_NE_ZERO: "Use `x` instead of `len(x) != 0`",
    ISSUE_LEN_GT_ZERO: "Use `x` instead of `len(x) > 0`",
    ISSUE_LEN_GE_ONE: "Use `x` instead of `len(x) >= 1`",
    ISSUE_LEN_LT_ONE: "Use `not x` instead of `len(x) < 1`",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_LEN_EQ_ZERO: "Replace `len(x) == 0` with `not x`",
    ISSUE_LEN_NE_ZERO: "Replace `len(x) != 0` with `x`",
    ISSUE_LEN_GT_ZERO: "Replace `len(x) > 0` with `x`",
    ISSUE_LEN_GE_ONE: "Replace `len(x) >= 1` with `x`",
    ISSUE_LEN_LT_ONE: "Replace `len(x) < 1` with `not x`",
}

_PYTHON_LEN_TYPES = {"comparison_operator"}
_JS_COMPARISON = {"binary_expression"}
_GO_COMPARISON = {"binary_expression"}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


@dataclass(frozen=True)
class LenComparisonIssue:
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
class LenComparisonResult:
    file_path: str
    total_comparisons: int
    issues: list[LenComparisonIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_comparisons": self.total_comparisons,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


def _is_len_call_py(node: tree_sitter.Node) -> bool:
    """Check if node is `len(...)` call in Python."""
    if node.type != "call":
        return False
    func = node.child_by_field_name("function")
    if func is None:
        return False
    return func.type == "identifier" and _node_text(func) == "len"


def _is_length_access_js(node: tree_sitter.Node) -> bool:
    """Check if node is `.length` access in JS/TS."""
    if node.type == "member_expression":
        prop = node.child_by_field_name("property")
        if prop is not None and _node_text(prop) == "length":
            return True
    return False


def _is_size_call_java(node: tree_sitter.Node) -> bool:
    """Check if node is `.size()` or `.length()` call in Java."""
    if node.type != "method_invocation":
        return False
    name = node.child_by_field_name("name")
    if name is None:
        return False
    return _node_text(name) in ("size", "length")


def _is_len_call_go(node: tree_sitter.Node) -> bool:
    """Check if node is `len(...)` call in Go."""
    if node.type != "call_expression":
        return False
    func = node.child_by_field_name("function")
    if func is None:
        return False
    return _node_text(func) == "len"


def _classify_comparison(
    op: str,
    right_val: str | None,
) -> str | None:
    """Classify a len comparison pattern. Returns issue_type or None."""
    if op in ("==", "===") and right_val == "0":
        return ISSUE_LEN_EQ_ZERO
    if op in ("!=", "!==") and right_val == "0":
        return ISSUE_LEN_NE_ZERO
    if op == ">" and right_val == "0":
        return ISSUE_LEN_GT_ZERO
    if op == ">=" and right_val == "1":
        return ISSUE_LEN_GE_ONE
    if op == "<" and right_val == "1":
        return ISSUE_LEN_LT_ONE
    return None


class LenComparisonAnalyzer(BaseAnalyzer):
    """Detects len() comparison anti-patterns where truthiness is preferred."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".java", ".go"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> LenComparisonResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return LenComparisonResult(
                file_path=str(path),
                total_comparisons=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return LenComparisonResult(
                file_path=str(path),
                total_comparisons=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        total = 0
        issues: list[LenComparisonIssue] = []

        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()
            issue = self._check_node(node, ext)
            total += 1 if issue is not None else 0
            if issue is not None:
                issues.append(issue)
            for child in node.children:
                stack.append(child)

        return LenComparisonResult(
            file_path=str(path),
            total_comparisons=total,
            issues=issues,
        )

    def _check_node(
        self, node: tree_sitter.Node, ext: str,
    ) -> LenComparisonIssue | None:
        if ext == ".py":
            return self._check_python(node)
        if ext in (".js", ".ts"):
            return self._check_js(node)
        if ext == ".java":
            return self._check_java(node)
        if ext == ".go":
            return self._check_go(node)
        return None

    def _check_python(self, node: tree_sitter.Node) -> LenComparisonIssue | None:
        if node.type != "comparison_operator":
            return None
        children = node.children
        if len(children) < 3:
            return None
        left = children[0]
        op_node = children[1]
        right = children[2]
        if not _is_len_call_py(left):
            return None
        op = _node_text(op_node)
        right_text = _node_text(right).strip()
        issue_type = _classify_comparison(op, right_text)
        if issue_type is None:
            return None
        return LenComparisonIssue(
            line=node.start_point[0] + 1,
            issue_type=issue_type,
            severity=SEVERITY_LOW,
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=_txt(node),
        )

    def _check_js(self, node: tree_sitter.Node) -> LenComparisonIssue | None:
        if node.type != "binary_expression":
            return None
        left = node.child_by_field_name("left")
        op_node = node.child_by_field_name("operator")
        right = node.child_by_field_name("right")
        if left is None or op_node is None or right is None:
            return None
        if not _is_length_access_js(left):
            return None
        op = _node_text(op_node)
        right_text = _node_text(right).strip()
        issue_type = _classify_comparison(op, right_text)
        if issue_type is None:
            return None
        return LenComparisonIssue(
            line=node.start_point[0] + 1,
            issue_type=issue_type,
            severity=SEVERITY_LOW,
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=_txt(node),
        )

    def _check_java(self, node: tree_sitter.Node) -> LenComparisonIssue | None:
        if node.type not in ("binary_expression", "method_invocation"):
            return None
        if node.type == "binary_expression":
            left = node.child_by_field_name("left")
            op_node = node.child_by_field_name("operator")
            right = node.child_by_field_name("right")
            if left is None or op_node is None or right is None:
                return None
            if not _is_size_call_java(left):
                return None
            op = _node_text(op_node)
            right_text = _node_text(right).strip()
            issue_type = _classify_comparison(op, right_text)
            if issue_type is None:
                return None
            return LenComparisonIssue(
                line=node.start_point[0] + 1,
                issue_type=issue_type,
                severity=SEVERITY_LOW,
                description=_DESCRIPTIONS[issue_type],
                suggestion=_SUGGESTIONS[issue_type],
                context=_txt(node),
            )
        return None

    def _check_go(self, node: tree_sitter.Node) -> LenComparisonIssue | None:
        if node.type != "binary_expression":
            return None
        left = node.child_by_field_name("left")
        op_node = node.child_by_field_name("operator")
        right = node.child_by_field_name("right")
        if left is None or op_node is None or right is None:
            return None
        if not _is_len_call_go(left):
            return None
        op = _node_text(op_node)
        right_text = _node_text(right).strip()
        issue_type = _classify_comparison(op, right_text)
        if issue_type is None:
            return None
        return LenComparisonIssue(
            line=node.start_point[0] + 1,
            issue_type=issue_type,
            severity=SEVERITY_LOW,
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=_txt(node),
        )
