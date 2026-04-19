"""Literal Boolean Comparison Detector.

Detects improper comparisons with boolean/None/null literals:
  - eq_true: x == True (use just x)
  - eq_false: x == False (use not x)
  - eq_none: x == None (use x is None, Python)
  - ne_none: x != None (use x is not None, Python)
  - eq_null_loose: x == null (use x === null, JS/TS)
  - ne_null_loose: x != null (use x !== null, JS/TS)

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

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_EQ_TRUE = "eq_true"
ISSUE_EQ_FALSE = "eq_false"
ISSUE_EQ_NONE = "eq_none"
ISSUE_NE_NONE = "ne_none"
ISSUE_EQ_NULL_LOOSE = "eq_null_loose"
ISSUE_NE_NULL_LOOSE = "ne_null_loose"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_EQ_TRUE: SEVERITY_LOW,
    ISSUE_EQ_FALSE: SEVERITY_LOW,
    ISSUE_EQ_NONE: SEVERITY_HIGH,
    ISSUE_NE_NONE: SEVERITY_HIGH,
    ISSUE_EQ_NULL_LOOSE: SEVERITY_MEDIUM,
    ISSUE_NE_NULL_LOOSE: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_EQ_TRUE: "Comparison with True literal — use the value directly",
    ISSUE_EQ_FALSE: "Comparison with False literal — use 'not' operator",
    ISSUE_EQ_NONE: "Equality check with None — use 'is None' for identity check",
    ISSUE_NE_NONE: "Inequality check with None — use 'is not None'",
    ISSUE_EQ_NULL_LOOSE: "Loose equality with null — use === for strict comparison",
    ISSUE_NE_NULL_LOOSE: "Loose inequality with null — use !== for strict comparison",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_EQ_TRUE: "Replace 'x == True' with just 'x'.",
    ISSUE_EQ_FALSE: "Replace 'x == False' with 'not x'.",
    ISSUE_EQ_NONE: "Replace 'x == None' with 'x is None'.",
    ISSUE_NE_NONE: "Replace 'x != None' with 'x is not None'.",
    ISSUE_EQ_NULL_LOOSE: "Replace 'x == null' with 'x === null'.",
    ISSUE_NE_NULL_LOOSE: "Replace 'x != null' with 'x !== null'.",
}

# Comparison operator node types per language
_COMPARISON_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"comparison_operator"}),
    ".js": frozenset({"binary_expression"}),
    ".jsx": frozenset({"binary_expression"}),
    ".ts": frozenset({"binary_expression"}),
    ".tsx": frozenset({"binary_expression"}),
    ".java": frozenset({"binary_expression", "method_invocation"}),
    ".go": frozenset({"binary_expression"}),
}

# Boolean/None/null literal node types
_TRUE_LITERALS: frozenset[str] = frozenset({"true", "True"})
_FALSE_LITERALS: frozenset[str] = frozenset({"false", "False"})
_NONE_LITERALS: frozenset[str] = frozenset({"none", "None"})
_NULL_LITERALS: frozenset[str] = frozenset({"null", "undefined"})

# Operators for equality/inequality
_EQ_OPS: frozenset[str] = frozenset({"==", "==="})
_NE_OPS: frozenset[str] = frozenset({"!=", "!=="})
_IS_OPS: frozenset[str] = frozenset({"is", "is not"})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


@dataclass(frozen=True)
class LiteralBooleanComparisonIssue:
    """A single literal boolean comparison issue."""

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
class LiteralBooleanComparisonResult:
    """Result of literal boolean comparison analysis."""

    file_path: str
    total_comparisons: int
    issues: list[LiteralBooleanComparisonIssue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_comparisons": self.total_comparisons,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class LiteralBooleanComparisonAnalyzer(BaseAnalyzer):
    """Detects improper comparisons with boolean/None/null literals."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
        }

    def analyze_file(
        self, file_path: str | Path,
    ) -> LiteralBooleanComparisonResult:
        """Analyze a single file for literal boolean comparisons."""
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return LiteralBooleanComparisonResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return LiteralBooleanComparisonResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )

        try:
            source = path.read_bytes()
        except OSError:
            return LiteralBooleanComparisonResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return LiteralBooleanComparisonResult(
                file_path=str(path),
                total_comparisons=0,
                issues=[],
            )

        issues: list[LiteralBooleanComparisonIssue] = []
        total_comparisons = 0

        comparison_types = _COMPARISON_TYPES.get(ext, frozenset())

        for node in _walk(tree.root_node):
            if node.type not in comparison_types:
                continue
            total_comparisons += 1

            issue = self._check_comparison(node, source, ext)
            if issue is not None:
                issues.append(issue)

        return LiteralBooleanComparisonResult(
            file_path=str(path),
            total_comparisons=total_comparisons,
            issues=issues,
        )

    def _check_comparison(
        self,
        node: tree_sitter.Node,
        source: bytes,
        ext: str,
    ) -> LiteralBooleanComparisonIssue | None:
        """Check a single comparison node for literal boolean issues."""
        children = [c for c in node.children if c.is_named]
        if len(children) < 2:
            return None

        # Get operator
        op = ""
        for child in node.children:
            if not child.is_named:
                op = _safe_text(child)
                break

        if not op:
            # Python comparison_operator may have "is" or "is not" differently
            text = _safe_text(node)
            for o in _IS_OPS:
                if o in text:
                    return None  # Already using identity check
            return None

        left, right = children[0], children[-1]

        # Check each side for literal values
        for side in (left, right):
            side_text = _safe_text(side)

            if side_text in _TRUE_LITERALS:
                if op in _EQ_OPS:
                    return self._make_issue(
                        ISSUE_EQ_TRUE, node, source,
                    )

            if side_text in _FALSE_LITERALS:
                if op in _EQ_OPS:
                    return self._make_issue(
                        ISSUE_EQ_FALSE, node, source,
                    )

            if ext == ".py" and side_text in _NONE_LITERALS:
                if op == "==":
                    return self._make_issue(
                        ISSUE_EQ_NONE, node, source,
                    )
                if op == "!=":
                    return self._make_issue(
                        ISSUE_NE_NONE, node, source,
                    )

            if ext in (".js", ".jsx", ".ts", ".tsx"):
                if side_text in _NULL_LITERALS:
                    if op == "==":
                        return self._make_issue(
                            ISSUE_EQ_NULL_LOOSE, node, source,
                        )
                    if op == "!=":
                        return self._make_issue(
                            ISSUE_NE_NULL_LOOSE, node, source,
                        )

        return None

    def _make_issue(
        self,
        issue_type: str,
        node: tree_sitter.Node,
        source: bytes,
    ) -> LiteralBooleanComparisonIssue:
        context = _safe_text(node)
        return LiteralBooleanComparisonIssue(
            issue_type=issue_type,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            severity=_SEVERITY_MAP[issue_type],
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
            context=context[:200],
        )


def _walk(node: tree_sitter.Node) -> Any:
    """Depth-first traversal of all nodes."""
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
