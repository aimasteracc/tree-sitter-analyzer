"""Callback Hell Detector.

Detects deeply nested callback patterns that make code unreadable:
  - callback_hell: 4+ levels of nested callbacks (critical)
  - deep_callback: 3 levels of nested callbacks (warning)
  - promise_chain_hell: 4+ chained .then() calls in JS/TS

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"

ISSUE_CALLBACK_HELL = "callback_hell"
ISSUE_DEEP_CALLBACK = "deep_callback"
ISSUE_PROMISE_CHAIN_HELL = "promise_chain_hell"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_CALLBACK_HELL: SEVERITY_CRITICAL,
    ISSUE_DEEP_CALLBACK: SEVERITY_WARNING,
    ISSUE_PROMISE_CHAIN_HELL: SEVERITY_CRITICAL,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_CALLBACK_HELL: "4+ levels of nested callbacks — refactor to async/await or flatten",
    ISSUE_DEEP_CALLBACK: "3 levels of nested callbacks — consider refactoring for readability",
    ISSUE_PROMISE_CHAIN_HELL: "4+ chained .then() calls — use async/await for better readability",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_CALLBACK_HELL: "Refactor to async/await or use named functions to reduce nesting.",
    ISSUE_DEEP_CALLBACK: "Extract inner callbacks into named functions to improve readability.",
    ISSUE_PROMISE_CHAIN_HELL: "Replace .then() chain with async/await syntax.",
}

_THRESHOLD_WARNING = 3
_THRESHOLD_CRITICAL = 4
_PROMISE_CHAIN_THRESHOLD = 4

# Node types that represent callbacks/closures per language extension
_CALLBACK_NODES: dict[str, frozenset[str]] = {
    ".py": frozenset({
        "lambda",
        "function_definition",
    }),
    ".js": frozenset({
        "function_expression",
        "arrow_function",
    }),
    ".jsx": frozenset({
        "function_expression",
        "arrow_function",
    }),
    ".ts": frozenset({
        "function_expression",
        "arrow_function",
    }),
    ".tsx": frozenset({
        "function_expression",
        "arrow_function",
    }),
    ".java": frozenset({
        "lambda_expression",
    }),
    ".go": frozenset({
        "func_literal",
    }),
}

# Node types that represent function/method argument lists
_ARGUMENT_LIST_TYPES: frozenset[str] = frozenset({
    "argument_list",
    "arguments",
})

# Node types that represent a method call (for .then() detection)
_MEMBER_EXPRESSION_TYPES: frozenset[str] = frozenset({
    "member_expression",
    "attribute",
    "field_access",
    "selector_expression",
})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class CallbackHellIssue:
    line_number: int
    issue_type: str
    depth: int
    severity: str
    description: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "depth": self.depth,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class CallbackHellResult:
    total_callbacks: int
    max_depth: int
    issues: tuple[CallbackHellIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_callbacks": self.total_callbacks,
            "max_depth": self.max_depth,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


def _is_callback_argument(node: tree_sitter.Node) -> bool:
    """Check if a callback node is passed as an argument to a function call."""
    parent = node.parent
    if parent is None:
        return False
    if parent.type in _ARGUMENT_LIST_TYPES:
        return True
    # Check if parent is a pair (key: value) in dict/object — e.g., { success: function() {} }
    if parent.type in ("pair",):
        grandparent = parent.parent
        if grandparent is not None and grandparent.type in ("dictionary", "object"):
            return True
    return False


def _is_keyword_child(child: tree_sitter.Node, parent: tree_sitter.Node) -> bool:
    """Check if a node is a keyword leaf of its parent (e.g., 'lambda' keyword inside lambda expression)."""
    return child.child_count == 0 and child.type == parent.type


def _measure_callback_depth(
    node: tree_sitter.Node,
    callback_types: frozenset[str],
    current_depth: int,
    issues: list[CallbackHellIssue],
) -> int:
    """Recursively measure callback nesting depth and collect issues."""
    max_child_depth = current_depth

    for child in node.children:
        # Skip keyword children (e.g., 'lambda' keyword inside lambda expression)
        if _is_keyword_child(child, node):
            continue

        if child.type in callback_types:
            child_depth = current_depth + 1

            if child_depth >= _THRESHOLD_CRITICAL:
                issues.append(CallbackHellIssue(
                    line_number=child.start_point[0] + 1,
                    issue_type=ISSUE_CALLBACK_HELL,
                    depth=child_depth,
                    severity=_SEVERITY_MAP[ISSUE_CALLBACK_HELL],
                    description=_DESCRIPTIONS[ISSUE_CALLBACK_HELL],
                ))
            elif child_depth >= _THRESHOLD_WARNING:
                issues.append(CallbackHellIssue(
                    line_number=child.start_point[0] + 1,
                    issue_type=ISSUE_DEEP_CALLBACK,
                    depth=child_depth,
                    severity=_SEVERITY_MAP[ISSUE_DEEP_CALLBACK],
                    description=_DESCRIPTIONS[ISSUE_DEEP_CALLBACK],
                ))

            inner_depth = _measure_callback_depth(
                child, callback_types, child_depth, issues,
            )
            if inner_depth > max_child_depth:
                max_child_depth = inner_depth
        else:
            inner_depth = _measure_callback_depth(
                child, callback_types, current_depth, issues,
            )
            if inner_depth > max_child_depth:
                max_child_depth = inner_depth

    return max_child_depth


def _detect_promise_chains(
    node: tree_sitter.Node,
    ext: str,
    issues: list[CallbackHellIssue],
) -> None:
    """Detect chained .then() calls in JS/TS code."""
    if ext not in (".js", ".jsx", ".ts", ".tsx"):
        return

    _walk_for_promise_chains(node, issues)


def _walk_for_promise_chains(
    node: tree_sitter.Node,
    issues: list[CallbackHellIssue],
) -> None:
    """Walk AST looking for .then() chains."""
    if node.type == "call_expression":
        chain_count = _count_then_chain(node)
        if chain_count >= _PROMISE_CHAIN_THRESHOLD:
            issues.append(CallbackHellIssue(
                line_number=node.start_point[0] + 1,
                issue_type=ISSUE_PROMISE_CHAIN_HELL,
                depth=chain_count,
                severity=_SEVERITY_MAP[ISSUE_PROMISE_CHAIN_HELL],
                description=_DESCRIPTIONS[ISSUE_PROMISE_CHAIN_HELL],
            ))
            return  # Don't report sub-chains

    for child in node.children:
        _walk_for_promise_chains(child, issues)


def _count_then_chain(node: tree_sitter.Node) -> int:
    """Count consecutive .then() calls starting from a call_expression."""
    count = 0
    current: tree_sitter.Node | None = node

    while current is not None and current.type == "call_expression":
        func = current.child_by_field_name("function")
        if func is not None and func.type == "member_expression":
            prop = func.child_by_field_name("property")
            if prop is not None and _safe_text(prop) == "then":
                count += 1
                # The object being called .then() on is the function's object
                obj = func.child_by_field_name("object")
                if obj is not None and obj.type == "call_expression":
                    current = obj
                    continue
        break

    return count


def _count_callbacks(
    node: tree_sitter.Node,
    callback_types: frozenset[str],
) -> int:
    """Count total callback nodes in the tree."""
    count = 0
    if node.type in callback_types:
        count = 1
    for child in node.children:
        count += _count_callbacks(child, callback_types)
    return count


def _analyze_root_callback(
    node: tree_sitter.Node,
    callback_types: frozenset[str],
    issues: list[CallbackHellIssue],
) -> int:
    """Measure max nesting depth of callback-type nodes from root."""
    return _measure_callback_depth(node, callback_types, 0, issues)


class CallbackHellAnalyzer(BaseAnalyzer):
    """Analyzes code for callback hell patterns."""

    def analyze_file(self, file_path: Path | str) -> CallbackHellResult:
        path = Path(file_path)
        if not path.exists():
            return CallbackHellResult(
                total_callbacks=0,
                max_depth=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return CallbackHellResult(
                total_callbacks=0,
                max_depth=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> CallbackHellResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return CallbackHellResult(
                total_callbacks=0,
                max_depth=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        callback_types = _CALLBACK_NODES.get(ext, frozenset())
        if not callback_types:
            return CallbackHellResult(
                total_callbacks=0,
                max_depth=0,
                issues=(),
                file_path=str(path),
            )

        issues: list[CallbackHellIssue] = []

        # Detect callback nesting depth
        max_depth = _analyze_root_callback(
            tree.root_node, callback_types, issues,
        )

        # Detect promise chains (JS/TS only)
        _detect_promise_chains(tree.root_node, ext, issues)

        # Count total callbacks
        total_callbacks = _count_callbacks(tree.root_node, callback_types)

        return CallbackHellResult(
            total_callbacks=total_callbacks,
            max_depth=max_depth,
            issues=tuple(issues),
            file_path=str(path),
        )
