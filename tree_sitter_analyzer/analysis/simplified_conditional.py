"""Simplified Conditional Expression Detector.

Detects conditional/ternary expressions that can be simplified:
  - redundant_true_branch: cond ? true : false → cond (or !!cond)
  - redundant_false_branch: cond ? false : true → !cond (or !cond)
  - identical_branches: cond ? x : x → always x

Supports Python, JavaScript/TypeScript, Java.
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

ISSUE_REDUNDANT_TRUE = "redundant_true_branch"
ISSUE_REDUNDANT_FALSE = "redundant_false_branch"
ISSUE_IDENTICAL_BRANCHES = "identical_branches"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_REDUNDANT_TRUE: SEVERITY_LOW,
    ISSUE_REDUNDANT_FALSE: SEVERITY_LOW,
    ISSUE_IDENTICAL_BRANCHES: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_REDUNDANT_TRUE: "Ternary returns true/false — simplify to the condition itself",
    ISSUE_REDUNDANT_FALSE: "Ternary returns false/true — simplify to negated condition",
    ISSUE_IDENTICAL_BRANCHES: "Both branches of ternary are identical — always returns same value",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_REDUNDANT_TRUE: "Replace 'cond ? true : false' with just 'cond'.",
    ISSUE_REDUNDANT_FALSE: "Replace 'cond ? false : true' with '!cond' or 'not cond'.",
    ISSUE_IDENTICAL_BRANCHES: "Both branches are identical — remove the ternary and use the value directly.",
}

_TERNARY_TYPES: dict[str, str] = {
    ".py": "conditional_expression",
    ".js": "ternary_expression",
    ".jsx": "ternary_expression",
    ".ts": "ternary_expression",
    ".tsx": "ternary_expression",
    ".java": "ternary_expression",
}

_TRUE_LITERALS: frozenset[str] = frozenset({"true", "True"})
_FALSE_LITERALS: frozenset[str] = frozenset({"false", "False"})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


@dataclass(frozen=True)
class SimplifiedConditionalIssue:
    """A single simplified conditional issue."""

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
class SimplifiedConditionalResult:
    """Result of simplified conditional analysis."""

    file_path: str
    total_ternaries: int
    issues: list[SimplifiedConditionalIssue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_ternaries": self.total_ternaries,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class SimplifiedConditionalAnalyzer(BaseAnalyzer):
    """Detects ternary expressions that can be simplified."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> SimplifiedConditionalResult:
        """Analyze a single file for simplifiable conditional expressions."""
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return SimplifiedConditionalResult(
                file_path=str(path),
                total_ternaries=0,
                issues=[],
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return SimplifiedConditionalResult(
                file_path=str(path),
                total_ternaries=0,
                issues=[],
            )

        try:
            source = path.read_bytes()
        except OSError:
            return SimplifiedConditionalResult(
                file_path=str(path),
                total_ternaries=0,
                issues=[],
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return SimplifiedConditionalResult(
                file_path=str(path),
                total_ternaries=0,
                issues=[],
            )

        ternary_type = _TERNARY_TYPES.get(ext)
        if ternary_type is None:
            return SimplifiedConditionalResult(
                file_path=str(path),
                total_ternaries=0,
                issues=[],
            )

        issues: list[SimplifiedConditionalIssue] = []
        total_ternaries = 0

        for node in _walk(tree.root_node):
            if node.type != ternary_type:
                continue
            total_ternaries += 1

            issue = self._check_ternary(node, ext)
            if issue is not None:
                issues.append(issue)

        return SimplifiedConditionalResult(
            file_path=str(path),
            total_ternaries=total_ternaries,
            issues=issues,
        )

    def _check_ternary(
        self,
        node: tree_sitter.Node,
        ext: str,
    ) -> SimplifiedConditionalIssue | None:
        """Check a ternary/conditional expression for simplifiable patterns."""
        children = [c for c in node.children if c.is_named]
        if len(children) < 3:
            return None

        if ext == ".py":
            # Python: body if condition else orelse
            # children: [body, condition, orelse]
            body, _condition, orelse = children[0], children[1], children[2]
        else:
            # JS/TS/Java: condition ? consequence : alternative
            # children: [condition, consequence, alternative]
            _condition, body, orelse = children[0], children[1], children[2]

        body_text = _safe_text(body)
        orelse_text = _safe_text(orelse)

        # Check: cond ? true : false → cond
        if body_text in _TRUE_LITERALS and orelse_text in _FALSE_LITERALS:
            return self._make_issue(ISSUE_REDUNDANT_TRUE, node)

        # Check: cond ? false : true → !cond
        if body_text in _FALSE_LITERALS and orelse_text in _TRUE_LITERALS:
            return self._make_issue(ISSUE_REDUNDANT_FALSE, node)

        # Check: cond ? x : x → always x
        if body_text == orelse_text and body_text not in ("", ):
            return self._make_issue(ISSUE_IDENTICAL_BRANCHES, node)

        return None

    def _make_issue(
        self,
        issue_type: str,
        node: tree_sitter.Node,
    ) -> SimplifiedConditionalIssue:
        context = _safe_text(node)
        return SimplifiedConditionalIssue(
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
