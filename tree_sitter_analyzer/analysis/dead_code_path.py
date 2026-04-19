"""Dead Code Path Analyzer.

Detects code that can never execute within a function body:
  - unreachable_code: statements after return/raise/break/continue/throw/panic
  - dead_branch: if False body, if True else branch

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_UNREACHABLE_CODE = "unreachable_code"
ISSUE_DEAD_BRANCH = "dead_branch"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_UNREACHABLE_CODE: SEVERITY_HIGH,
    ISSUE_DEAD_BRANCH: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_UNREACHABLE_CODE: "Code after a terminal statement can never execute",
    ISSUE_DEAD_BRANCH: "Branch condition is always false (or always true, making else dead)",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_UNREACHABLE_CODE: "Remove the unreachable code or fix the control flow logic",
    ISSUE_DEAD_BRANCH: "Remove the dead branch or correct the condition expression",
}

_FUNCTION_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({"function_declaration", "method_definition", "arrow_function"}),
    ".jsx": frozenset({"function_declaration", "method_definition", "arrow_function"}),
    ".ts": frozenset({"function_declaration", "method_definition", "arrow_function"}),
    ".tsx": frozenset({"function_declaration", "method_definition", "arrow_function"}),
    ".java": frozenset({"method_declaration", "constructor_declaration"}),
    ".go": frozenset({"function_declaration", "method_declaration"}),
}

_TERMINAL_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"return_statement", "raise_statement", "break_statement", "continue_statement"}),
    ".js": frozenset({"return_statement", "throw_statement", "break_statement", "continue_statement"}),
    ".jsx": frozenset({"return_statement", "throw_statement", "break_statement", "continue_statement"}),
    ".ts": frozenset({"return_statement", "throw_statement", "break_statement", "continue_statement"}),
    ".tsx": frozenset({"return_statement", "throw_statement", "break_statement", "continue_statement"}),
    ".java": frozenset({"return_statement", "throw_statement", "break_statement", "continue_statement"}),
    ".go": frozenset({"return_statement", "call_expression"}),
}

_IF_TYPES: frozenset[str] = frozenset({"if_statement"})

_BLOCK_TYPES: frozenset[str] = frozenset({
    "block", "statement_block", "class_body",
    "declaration_list", "function_body",
})

_LOOP_BODY_TYPES: frozenset[str] = frozenset({
    "for_statement", "while_statement", "for_in_statement",
    "do_statement",
})

_FALSE_LITERALS: frozenset[str] = frozenset({
    "False", "0", "false", "null", "undefined", "nil", "None",
})

_TRUE_LITERALS: frozenset[str] = frozenset({
    "True", "1", "true",
})

@dataclass(frozen=True)
class DeadCodePathIssue:
    """A single unreachable code issue."""

    line_number: int
    issue_type: str
    description: str
    severity: str
    context: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "description": self.description,
            "severity": self.severity,
            "context": self.context,
            "suggestion": self.suggestion,
        }

@dataclass(frozen=True)
class DeadCodePathResult:
    """Aggregated dead code path analysis result."""

    total_functions: int
    issues: tuple[DeadCodePathIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_functions": self.total_functions,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }

def _is_go_panic(node: tree_sitter.Node, content: bytes) -> bool:
    """Check if a Go call_expression is panic()."""
    func_node = node.child_by_field_name("function")
    if func_node is None:
        return False
    name = content[func_node.start_byte:func_node.end_byte].decode(
        "utf-8", errors="replace"
    )
    return name == "panic"

def _is_terminal_statement(
    node: tree_sitter.Node, ext: str, content: bytes
) -> bool:
    """Check if a node is a terminal statement for the given language."""
    terminals = _TERMINAL_TYPES.get(ext, frozenset())
    if node.type in terminals:
        if ext == ".go" and node.type == "call_expression":
            return _is_go_panic(node, content)
        return True
    if ext == ".go" and node.type == "expression_statement":
        for child in node.children:
            if child.type == "call_expression" and _is_go_panic(child, content):
                return True
    return False

def _extract_condition_text(
    cond: tree_sitter.Node, content: bytes
) -> str:
    """Extract condition text, stripping parenthesized_expression wrappers."""
    text = content[cond.start_byte:cond.end_byte].decode(
        "utf-8", errors="replace"
    ).strip()
    while text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    return text

def _is_always_false_condition(
    node: tree_sitter.Node, content: bytes
) -> bool:
    """Check if an if condition is always False (e.g., if False:, if 0)."""
    cond = node.child_by_field_name("condition")
    if cond is None:
        return False
    text = _extract_condition_text(cond, content)
    return text in _FALSE_LITERALS

def _is_always_true_condition(
    node: tree_sitter.Node, content: bytes
) -> bool:
    """Check if an if condition is always True (e.g., if True:, if 1)."""
    cond = node.child_by_field_name("condition")
    if cond is None:
        return False
    text = _extract_condition_text(cond, content)
    return text in _TRUE_LITERALS

class DeadCodePathAnalyzer(BaseAnalyzer):
    """Analyzes functions for unreachable code paths."""

    def analyze_file(self, file_path: Path | str) -> DeadCodePathResult:
        path = Path(file_path)
        if not path.exists():
            return DeadCodePathResult(
                total_functions=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return DeadCodePathResult(
                total_functions=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> DeadCodePathResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return DeadCodePathResult(
                total_functions=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        func_types = _FUNCTION_TYPES.get(ext, frozenset())

        issues: list[DeadCodePathIssue] = []
        total = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total

            if node.type in func_types:
                total += 1
                self._check_function(node, ext, content, issues)
                return

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return DeadCodePathResult(
            total_functions=total,
            issues=tuple(issues),
            file_path=str(path),
        )

    def _check_function(
        self,
        func_node: tree_sitter.Node,
        ext: str,
        content: bytes,
        issues: list[DeadCodePathIssue],
    ) -> None:
        """Check a single function for unreachable code."""
        body = func_node.child_by_field_name("body")
        if body is None:
            return
        self._scan_block(body, ext, content, issues)

    def _scan_block(
        self,
        block: tree_sitter.Node,
        ext: str,
        content: bytes,
        issues: list[DeadCodePathIssue],
    ) -> None:
        """Scan a block for unreachable code patterns."""
        children = block.children
        terminal_found = False

        for i, child in enumerate(children):
            if terminal_found:
                if child.is_named and child.type != "comment":
                    issues.append(DeadCodePathIssue(
                        line_number=child.start_point[0] + 1,
                        issue_type=ISSUE_UNREACHABLE_CODE,
                        description=f"Code after terminal statement on line {children[i - 1].start_point[0] + 1}",
                        severity=SEVERITY_HIGH,
                        context=content[
                            child.start_byte:child.end_byte
                        ].decode("utf-8", errors="replace")[:80],
                    ))
                continue

            if not child.is_named:
                continue

            if _is_terminal_statement(child, ext, content):
                terminal_found = True
                continue

            if child.type in _IF_TYPES:
                self._check_if_statement(child, ext, content, issues)

            if child.type in _BLOCK_TYPES:
                self._scan_block(child, ext, content, issues)

            if child.type in _LOOP_BODY_TYPES:
                self._scan_loop(child, ext, content, issues)

    def _scan_loop(
        self,
        loop_node: tree_sitter.Node,
        ext: str,
        content: bytes,
        issues: list[DeadCodePathIssue],
    ) -> None:
        """Scan a loop body for unreachable code."""
        body = loop_node.child_by_field_name("body")
        if body is not None:
            self._scan_block(body, ext, content, issues)

    def _check_if_statement(
        self,
        if_node: tree_sitter.Node,
        ext: str,
        content: bytes,
        issues: list[DeadCodePathIssue],
    ) -> None:
        """Check if statement for dead branches."""
        if _is_always_false_condition(if_node, content):
            consequence = if_node.child_by_field_name("consequence")
            if consequence is not None:
                start_line = consequence.start_point[0] + 1
                end_line = consequence.end_point[0] + 1
                issues.append(DeadCodePathIssue(
                    line_number=start_line,
                    issue_type=ISSUE_DEAD_BRANCH,
                    description=f"Branch condition is always false (lines {start_line}-{end_line})",
                    severity=SEVERITY_MEDIUM,
                    context=content[
                        consequence.start_byte:consequence.end_byte
                    ].decode("utf-8", errors="replace")[:80],
                ))

        if _is_always_true_condition(if_node, content):
            alternative = if_node.child_by_field_name("alternative")
            if alternative is not None:
                start_line = alternative.start_point[0] + 1
                issues.append(DeadCodePathIssue(
                    line_number=start_line,
                    issue_type=ISSUE_DEAD_BRANCH,
                    description="Else branch is dead because condition is always true",
                    severity=SEVERITY_MEDIUM,
                    context=content[
                        alternative.start_byte:alternative.end_byte
                    ].decode("utf-8", errors="replace")[:80],
                ))

        consequence = if_node.child_by_field_name("consequence")
        if consequence is not None:
            self._scan_block(consequence, ext, content, issues)

        alternative = if_node.child_by_field_name("alternative")
        if alternative is not None:
            if alternative.type in _BLOCK_TYPES:
                self._scan_block(alternative, ext, content, issues)
            elif alternative.type in _IF_TYPES:
                self._check_if_statement(alternative, ext, content, issues)
