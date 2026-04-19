"""Await-in-Loop Detector.

Detects `await` expressions inside for/while loop bodies:
  - await_in_for_loop: `for x in items: await f(x)` (use asyncio.gather / Promise.all)
  - await_in_while_loop: `while cond: await f()` (consider concurrent design)

Serial async operations in loops are a common performance anti-pattern.
Each iteration waits for the previous one to complete, when they could
run concurrently with asyncio.gather() (Python) or Promise.all() (JS/TS).

Supports Python and JavaScript/TypeScript.
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

ISSUE_AWAIT_IN_FOR = "await_in_for_loop"
ISSUE_AWAIT_IN_WHILE = "await_in_while_loop"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_AWAIT_IN_FOR: SEVERITY_MEDIUM,
    ISSUE_AWAIT_IN_WHILE: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_AWAIT_IN_FOR: (
        "Await inside for loop — sequential async; "
        "use asyncio.gather() or Promise.all() for parallel execution"
    ),
    ISSUE_AWAIT_IN_WHILE: (
        "Await inside while loop — sequential async; "
        "consider concurrent design (asyncio.gather / Promise.all)"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_AWAIT_IN_FOR: (
        "Collect coroutines and use asyncio.gather(*tasks) "
        "or Promise.all(tasks.map(f))"
    ),
    ISSUE_AWAIT_IN_WHILE: (
        "Consider redesigning to batch async operations "
        "instead of awaiting in each iteration"
    ),
}

_LOOP_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"for_statement", "while_statement"}),
    ".js": frozenset({"for_statement", "for_in_statement", "while_statement"}),
    ".jsx": frozenset({"for_statement", "for_in_statement", "while_statement"}),
    ".ts": frozenset({"for_statement", "for_in_statement", "while_statement"}),
    ".tsx": frozenset({"for_statement", "for_in_statement", "while_statement"}),
}

_AWAIT_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"await"}),
    ".js": frozenset({"await_expression"}),
    ".jsx": frozenset({"await_expression"}),
    ".ts": frozenset({"await_expression"}),
    ".tsx": frozenset({"await_expression"}),
}

_FUNCTION_TYPES: frozenset[str] = frozenset({
    "function_definition",
    "lambda",
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "generator_function_declaration",
    "generator_function",
})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


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
class AwaitInLoopIssue:
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
class AwaitInLoopResult:
    file_path: str
    total_loops: int
    issues: list[AwaitInLoopIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_loops": self.total_loops,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class AwaitInLoopAnalyzer(BaseAnalyzer):
    """Detects await expressions inside for/while loops."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> AwaitInLoopResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return AwaitInLoopResult(file_path=str(path), total_loops=0)
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return AwaitInLoopResult(file_path=str(path), total_loops=0)

        try:
            source = path.read_bytes()
        except OSError:
            return AwaitInLoopResult(file_path=str(path), total_loops=0)

        tree = parser.parse(source)
        if tree.root_node is None:
            return AwaitInLoopResult(file_path=str(path), total_loops=0)

        loop_types = _LOOP_TYPES.get(ext)
        await_types = _AWAIT_TYPES.get(ext)
        if loop_types is None or await_types is None:
            return AwaitInLoopResult(file_path=str(path), total_loops=0)

        issues: list[AwaitInLoopIssue] = []
        total_loops = 0

        for node in _walk(tree.root_node):
            if node.type not in loop_types:
                continue
            total_loops += 1
            for issue in self._check_loop(node, ext, await_types):
                issues.append(issue)

        return AwaitInLoopResult(
            file_path=str(path),
            total_loops=total_loops,
            issues=issues,
        )

    def _check_loop(
        self,
        loop_node: tree_sitter.Node,
        ext: str,
        await_types: frozenset[str],
    ) -> list[AwaitInLoopIssue]:
        issues: list[AwaitInLoopIssue] = []
        is_for = loop_node.type in (
            "for_statement", "for_in_statement",
        )
        issue_type = ISSUE_AWAIT_IN_FOR if is_for else ISSUE_AWAIT_IN_WHILE
        loop_types = _LOOP_TYPES.get(ext, frozenset())

        for child in _walk(loop_node):
            if child.id == loop_node.id:
                continue
            if child.type in _FUNCTION_TYPES:
                break
            if child.type in loop_types and child.id != loop_node.id:
                break
            if child.type in await_types and child.is_named:
                context = _safe_text(loop_node)
                issues.append(AwaitInLoopIssue(
                    issue_type=issue_type,
                    line=child.start_point[0] + 1,
                    column=child.start_point[1],
                    severity=_SEVERITY_MAP[issue_type],
                    description=_DESCRIPTIONS[issue_type],
                    suggestion=_SUGGESTIONS[issue_type],
                    context=context[:200],
                ))

        return issues
