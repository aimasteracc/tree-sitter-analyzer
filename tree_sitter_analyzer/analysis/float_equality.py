"""Float Equality Comparison Detector.

Detects exact equality comparisons (`==`/`!=`) involving floating-point
literals, which can produce incorrect results due to IEEE 754 rounding.

Examples of caught patterns:
  - x == 0.1         (0.1 is not exactly representable)
  - result != 3.14   (float comparison is unreliable)
  - x == 0.1 + 0.2   (would be False despite math expectation)

Supports Python, JavaScript/TypeScript, Java, and Go.
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
SEVERITY_HIGH = "high"

ISSUE_FLOAT_EQ = "float_equality"
ISSUE_FLOAT_NEQ = "float_inequality"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_FLOAT_EQ: SEVERITY_HIGH,
    ISSUE_FLOAT_NEQ: SEVERITY_HIGH,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_FLOAT_EQ: (
        "Exact float comparison: IEEE 754 rounding makes == unreliable "
        "for floating-point values — use abs(a - b) < epsilon or math.isclose()"
    ),
    ISSUE_FLOAT_NEQ: (
        "Exact float comparison: IEEE 754 rounding makes != unreliable "
        "for floating-point values — use abs(a - b) >= epsilon"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_FLOAT_EQ: "Use abs(x - expected) < epsilon or math.isclose(x, expected).",
    ISSUE_FLOAT_NEQ: "Use abs(x - expected) >= epsilon or not math.isclose(x, expected).",
}

_FLOAT_TYPES_PY: frozenset[str] = frozenset({"float"})
_INT_TYPES_PY: frozenset[str] = frozenset({"integer"})

_JS_FLOAT_TYPES: frozenset[str] = frozenset({"number"})
_JAVA_FLOAT_TYPES: frozenset[str] = frozenset({"decimal_floating_point_literal"})
_JAVA_INT_TYPES: frozenset[str] = frozenset({"decimal_integer_literal"})
_GO_FLOAT_TYPES: frozenset[str] = frozenset({"float_literal"})
_GO_INT_TYPES: frozenset[str] = frozenset({"int_literal"})

_PY_EXT = frozenset({".py"})
_JS_EXT = frozenset({".js", ".jsx", ".ts", ".tsx"})
_JAVA_EXT = frozenset({".java"})
_GO_EXT = frozenset({".go"})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


def _has_dot_or_exponent(text: str) -> bool:
    return "." in text or "e" in text or "E" in text


def _is_float_literal_py(node: tree_sitter.Node) -> bool:
    if node.type == "float":
        return True
    if node.type == "integer":
        text = _safe_text(node)
        return _has_dot_or_exponent(text)
    if node.type == "unary_operator":
        children = [c for c in node.children if c.is_named]
        if len(children) == 1:
            return _is_float_literal_py(children[0])
    if node.type == "parenthesized_expression":
        children = [c for c in node.children if c.is_named]
        if len(children) == 1:
            return _is_float_literal_py(children[0])
    return False


def _is_float_literal_js(node: tree_sitter.Node) -> bool:
    if node.type == "number":
        text = _safe_text(node)
        return _has_dot_or_exponent(text)
    if node.type == "unary_operator" or node.type == "binary_operator":
        pass
    if node.type == "parenthesized_expression":
        children = [c for c in node.children if c.is_named]
        if len(children) == 1:
            return _is_float_literal_js(children[0])
    return False


def _is_float_literal_java(node: tree_sitter.Node) -> bool:
    if node.type == "decimal_floating_point_literal":
        return True
    return False


def _is_float_literal_go(node: tree_sitter.Node) -> bool:
    if node.type == "float_literal":
        return True
    if node.type == "int_literal":
        text = _safe_text(node)
        if "." in text:
            return True
    return False


def _is_float_literal(node: tree_sitter.Node, ext: str) -> bool:
    if ext in _PY_EXT:
        return _is_float_literal_py(node)
    if ext in _JS_EXT:
        return _is_float_literal_js(node)
    if ext in _JAVA_EXT:
        return _is_float_literal_java(node)
    if ext in _GO_EXT:
        return _is_float_literal_go(node)
    return False


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


@dataclass(frozen=True)
class FloatEqualityIssue:
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
class FloatEqualityResult:
    file_path: str
    total_float_comparisons: int
    issues: list[FloatEqualityIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_float_comparisons": self.total_float_comparisons,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class FloatEqualityAnalyzer(BaseAnalyzer):
    """Detects exact equality comparisons with floating-point literals."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = set(_PY_EXT | _JS_EXT | _JAVA_EXT | _GO_EXT)

    def analyze_file(
        self, file_path: str | Path,
    ) -> FloatEqualityResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return FloatEqualityResult(
                file_path=str(path),
                total_float_comparisons=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return FloatEqualityResult(
                file_path=str(path),
                total_float_comparisons=0,
            )

        try:
            source = path.read_bytes()
        except OSError:
            return FloatEqualityResult(
                file_path=str(path),
                total_float_comparisons=0,
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return FloatEqualityResult(
                file_path=str(path),
                total_float_comparisons=0,
            )

        issues: list[FloatEqualityIssue] = []
        total_float_comparisons = 0

        comparison_type = self._comparison_node_type(ext)
        eq_ops = self._eq_operators(ext)

        for node in _walk(tree.root_node):
            if node.type != comparison_type:
                continue
            for issue in self._check_comparison(node, ext, eq_ops):
                total_float_comparisons += 1
                if issue is not None:
                    issues.append(issue)

        return FloatEqualityResult(
            file_path=str(path),
            total_float_comparisons=total_float_comparisons,
            issues=issues,
        )

    def _comparison_node_type(self, ext: str) -> str:
        if ext in _PY_EXT:
            return "comparison_operator"
        if ext in _JS_EXT | _JAVA_EXT | _GO_EXT:
            return "binary_expression"
        return "comparison_operator"

    def _eq_operators(self, ext: str) -> frozenset[str]:
        if ext in _PY_EXT:
            return frozenset({"==", "!="})
        if ext in _JS_EXT:
            return frozenset({"==", "!=", "===", "!=="})
        if ext in _JAVA_EXT:
            return frozenset({"==", "!="})
        if ext in _GO_EXT:
            return frozenset({"==", "!="})
        return frozenset({"==", "!="})

    def _get_operator_text(self, node: tree_sitter.Node) -> str:
        for child in node.children:
            if not child.is_named:
                text = _safe_text(child)
                if text in ("==", "!=", "===", "!=="):
                    return text
        return ""

    def _check_comparison(
        self,
        node: tree_sitter.Node,
        ext: str,
        eq_ops: frozenset[str],
    ) -> list[FloatEqualityIssue | None]:
        op_text = self._get_operator_text(node)
        if op_text not in eq_ops:
            return []

        named_children = [c for c in node.children if c.is_named]
        if len(named_children) < 2:
            return []

        left = named_children[0]
        right = named_children[1]

        left_is_float = _is_float_literal(left, ext)
        right_is_float = _is_float_literal(right, ext)

        if not left_is_float and not right_is_float:
            return []

        issue_type = ISSUE_FLOAT_EQ if op_text in ("==", "===") else ISSUE_FLOAT_NEQ
        context = _safe_text(node)

        return [FloatEqualityIssue(
            issue_type=issue_type,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            severity=_SEVERITY_MAP[issue_type],
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=context[:200],
        )]
