"""Len Anti-pattern Detector.

Detects unidiomatic len() usage patterns:
  - len_eq_zero: len(x) == 0 → use `not x`
  - len_ne_zero: len(x) != 0 → use `x`
  - len_gt_zero: len(x) > 0 → use `x`
  - len_ge_one: len(x) >= 1 → use `x`
  - len_lt_one: len(x) < 1 → use `not x`
  - range_len_for: for i in range(len(x)) → use direct iteration or enumerate

Comparison checks support Python, JavaScript/TypeScript, Java, Go.
range_len_for is Python-only (range/len are Python builtins).
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

# Comparison issue types
ISSUE_LEN_EQ_ZERO = "len_eq_zero"
ISSUE_LEN_NE_ZERO = "len_ne_zero"
ISSUE_LEN_GT_ZERO = "len_gt_zero"
ISSUE_LEN_GE_ONE = "len_ge_one"
ISSUE_LEN_LT_ONE = "len_lt_one"

# Range-len issue type
ISSUE_RANGE_LEN_FOR = "range_len_for"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_LEN_EQ_ZERO: "Use `not x` instead of `len(x) == 0`",
    ISSUE_LEN_NE_ZERO: "Use `x` instead of `len(x) != 0`",
    ISSUE_LEN_GT_ZERO: "Use `x` instead of `len(x) > 0`",
    ISSUE_LEN_GE_ONE: "Use `x` instead of `len(x) >= 1`",
    ISSUE_LEN_LT_ONE: "Use `not x` instead of `len(x) < 1`",
    ISSUE_RANGE_LEN_FOR: (
        "Use `for item in x` or `for i, item in enumerate(x)` "
        "instead of `for i in range(len(x))`"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_LEN_EQ_ZERO: "Replace `len(x) == 0` with `not x`",
    ISSUE_LEN_NE_ZERO: "Replace `len(x) != 0` with `x`",
    ISSUE_LEN_GT_ZERO: "Replace `len(x) > 0` with `x`",
    ISSUE_LEN_GE_ONE: "Replace `len(x) >= 1` with `x`",
    ISSUE_LEN_LT_ONE: "Replace `len(x) < 1` with `not x`",
    ISSUE_RANGE_LEN_FOR: (
        "Replace `for i in range(len(x))` with direct iteration "
        "`for item in x` or indexed `for i, item in enumerate(x)`"
    ),
}


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _txt(node: tree_sitter.Node) -> str:
    return _node_text(node)[:80]


# --- Len-comparison helpers ---


def _is_len_call_py(node: tree_sitter.Node) -> bool:
    if node.type != "call":
        return False
    func = node.child_by_field_name("function")
    if func is None:
        return False
    return func.type == "identifier" and _node_text(func) == "len"


def _is_length_access_js(node: tree_sitter.Node) -> bool:
    if node.type == "member_expression":
        prop = node.child_by_field_name("property")
        if prop is not None and _node_text(prop) == "length":
            return True
    return False


def _is_size_call_java(node: tree_sitter.Node) -> bool:
    if node.type != "method_invocation":
        return False
    name = node.child_by_field_name("name")
    if name is None:
        return False
    return _node_text(name) in ("size", "length")


def _is_len_call_go(node: tree_sitter.Node) -> bool:
    if node.type != "call_expression":
        return False
    func = node.child_by_field_name("function")
    if func is None:
        return False
    return _node_text(func) == "len"


def _classify_comparison(op: str, right_val: str | None) -> str | None:
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


# --- Range-len helper ---


def _is_range_len_call(node: tree_sitter.Node) -> bool:
    if node.type != "call":
        return False
    func = node.child_by_field_name("function")
    if func is None or _node_text(func) != "range":
        return False
    args = node.child_by_field_name("arguments")
    if args is None:
        return False
    for child in args.children:
        if child.type == "call":
            inner_func = child.child_by_field_name("function")
            if inner_func is not None and _node_text(inner_func) == "len":
                return True
    return False


# --- Data model ---


@dataclass(frozen=True)
class LenAntiPatternIssue:
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
class LenAntiPatternResult:
    file_path: str
    total_checks: int
    issues: list[LenAntiPatternIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_checks": self.total_checks,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


# --- Analyzer ---


class LenAntiPatternAnalyzer(BaseAnalyzer):
    """Detects unidiomatic len() usage: comparison anti-patterns and range(len(x))."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"}

    def analyze_file(self, file_path: str | Path) -> LenAntiPatternResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return LenAntiPatternResult(file_path=str(path), total_checks=0)
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return LenAntiPatternResult(file_path=str(path), total_checks=0)

        source = path.read_bytes()
        tree = parser.parse(source)

        total = 0
        issues: list[LenAntiPatternIssue] = []

        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()

            # Check comparison patterns
            comp_issue = self._check_comparison(node, ext)
            if comp_issue is not None:
                total += 1
                issues.append(comp_issue)

            # Check range-len for loops (Python only)
            if ext == ".py" and node.type == "for_statement":
                total += 1
                self._check_range_len(node, issues)

            for child in node.children:
                stack.append(child)

        return LenAntiPatternResult(
            file_path=str(path), total_checks=total, issues=issues,
        )

    # --- Comparison checks per language ---

    def _check_comparison(
        self, node: tree_sitter.Node, ext: str,
    ) -> LenAntiPatternIssue | None:
        if ext == ".py":
            return self._check_python(node)
        if ext in (".js", ".ts", ".jsx", ".tsx"):
            return self._check_js(node)
        if ext == ".java":
            return self._check_java(node)
        if ext == ".go":
            return self._check_go(node)
        return None

    def _check_python(self, node: tree_sitter.Node) -> LenAntiPatternIssue | None:
        if node.type != "comparison_operator":
            return None
        children = node.children
        if len(children) < 3:
            return None
        left, op_node, right = children[0], children[1], children[2]
        if not _is_len_call_py(left):
            return None
        issue_type = _classify_comparison(_node_text(op_node), _node_text(right).strip())
        if issue_type is None:
            return None
        return LenAntiPatternIssue(
            line=node.start_point[0] + 1,
            issue_type=issue_type,
            severity=SEVERITY_LOW,
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=_txt(node),
        )

    def _check_js(self, node: tree_sitter.Node) -> LenAntiPatternIssue | None:
        if node.type != "binary_expression":
            return None
        left = node.child_by_field_name("left")
        op_node = node.child_by_field_name("operator")
        right = node.child_by_field_name("right")
        if left is None or op_node is None or right is None:
            return None
        if not _is_length_access_js(left):
            return None
        issue_type = _classify_comparison(_node_text(op_node), _node_text(right).strip())
        if issue_type is None:
            return None
        return LenAntiPatternIssue(
            line=node.start_point[0] + 1,
            issue_type=issue_type,
            severity=SEVERITY_LOW,
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=_txt(node),
        )

    def _check_java(self, node: tree_sitter.Node) -> LenAntiPatternIssue | None:
        if node.type != "binary_expression":
            return None
        left = node.child_by_field_name("left")
        op_node = node.child_by_field_name("operator")
        right = node.child_by_field_name("right")
        if left is None or op_node is None or right is None:
            return None
        if not _is_size_call_java(left):
            return None
        issue_type = _classify_comparison(_node_text(op_node), _node_text(right).strip())
        if issue_type is None:
            return None
        return LenAntiPatternIssue(
            line=node.start_point[0] + 1,
            issue_type=issue_type,
            severity=SEVERITY_LOW,
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=_txt(node),
        )

    def _check_go(self, node: tree_sitter.Node) -> LenAntiPatternIssue | None:
        if node.type != "binary_expression":
            return None
        left = node.child_by_field_name("left")
        op_node = node.child_by_field_name("operator")
        right = node.child_by_field_name("right")
        if left is None or op_node is None or right is None:
            return None
        if not _is_len_call_go(left):
            return None
        issue_type = _classify_comparison(_node_text(op_node), _node_text(right).strip())
        if issue_type is None:
            return None
        return LenAntiPatternIssue(
            line=node.start_point[0] + 1,
            issue_type=issue_type,
            severity=SEVERITY_LOW,
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=_txt(node),
        )

    # --- Range-len check ---

    def _check_range_len(
        self, node: tree_sitter.Node, issues: list[LenAntiPatternIssue],
    ) -> None:
        children = node.children
        for i, child in enumerate(children):
            if child.type == "in" and i + 1 < len(children):
                iterable = children[i + 1]
                if _is_range_len_call(iterable):
                    issues.append(LenAntiPatternIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_RANGE_LEN_FOR,
                        severity=SEVERITY_LOW,
                        description=_DESCRIPTIONS[ISSUE_RANGE_LEN_FOR],
                        suggestion=_SUGGESTIONS[ISSUE_RANGE_LEN_FOR],
                        context=_txt(node),
                    ))
                break
