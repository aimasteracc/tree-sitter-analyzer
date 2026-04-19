"""Empty Block Detector.

Detects empty code blocks that may hide bugs or indicate dead code:
  - empty_function: function/method with empty body
  - empty_catch: catch/except with empty body (hides bugs)
  - empty_loop: for/while with empty body
  - empty_block: other empty blocks (if/else/try/finally)

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_EMPTY_CATCH = "empty_catch"
ISSUE_EMPTY_FUNCTION = "empty_function"
ISSUE_EMPTY_LOOP = "empty_loop"
ISSUE_EMPTY_BLOCK = "empty_block"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_EMPTY_CATCH: SEVERITY_HIGH,
    ISSUE_EMPTY_FUNCTION: SEVERITY_MEDIUM,
    ISSUE_EMPTY_LOOP: SEVERITY_LOW,
    ISSUE_EMPTY_BLOCK: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_EMPTY_CATCH: "Empty catch/except block silently swallows errors",
    ISSUE_EMPTY_FUNCTION: "Function or method has an empty body",
    ISSUE_EMPTY_LOOP: "Loop has an empty body (possible no-op or bug)",
    ISSUE_EMPTY_BLOCK: "Empty code block found",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_EMPTY_CATCH: "Handle the error, log it, or re-raise it. Never silently ignore exceptions.",
    ISSUE_EMPTY_FUNCTION: "Add implementation or remove the function if unused.",
    ISSUE_EMPTY_LOOP: "Verify the loop body is intentionally empty or add the intended logic.",
    ISSUE_EMPTY_BLOCK: "Remove the empty block or add the intended logic.",
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

_CATCH_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"except_clause"}),
    ".js": frozenset({"catch_clause"}),
    ".jsx": frozenset({"catch_clause"}),
    ".ts": frozenset({"catch_clause"}),
    ".tsx": frozenset({"catch_clause"}),
    ".java": frozenset({"catch_clause"}),
    ".go": frozenset(),  # Go uses defer/recover, no catch
}

_LOOP_TYPES: frozenset[str] = frozenset({
    "for_statement", "while_statement", "for_in_statement",
    "do_statement",
})

_PYTHON_PASS = frozenset({"pass_statement"})

@dataclass(frozen=True)
class EmptyBlockIssue:
    """A single empty block issue."""

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
class EmptyBlockResult:
    """Aggregated empty block analysis result."""

    total_blocks: int
    issues: tuple[EmptyBlockIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_blocks": self.total_blocks,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }

def _is_empty_block(node: tree_sitter.Node, ext: str) -> bool:
    """Check if a block is effectively empty (no named children except comments/pass)."""
    named_children = [c for c in node.children if c.is_named]
    if ext == ".py":
        named_children = [
            c for c in named_children
            if c.type not in _PYTHON_PASS and c.type != "comment"
            and c.type != "expression_statement"
        ]
        pass_only = all(
            c.type in _PYTHON_PASS or c.type == "comment"
            for c in node.children
            if c.is_named
        )
        if pass_only and any(
            c.type in _PYTHON_PASS for c in node.children if c.is_named
        ):
            return True
    else:
        named_children = [
            c for c in named_children if c.type != "comment"
        ]

    return len(named_children) == 0

def _classify_context(
    parent_type: str,
    ext: str,
) -> str | None:
    """Classify what kind of empty block this is."""
    func_types = _FUNCTION_TYPES.get(ext, frozenset())
    catch_types = _CATCH_TYPES.get(ext, frozenset())

    if parent_type in func_types:
        return ISSUE_EMPTY_FUNCTION
    if parent_type in catch_types:
        return ISSUE_EMPTY_CATCH
    if parent_type in _LOOP_TYPES:
        return ISSUE_EMPTY_LOOP
    return ISSUE_EMPTY_BLOCK

class EmptyBlockAnalyzer(BaseAnalyzer):
    """Analyzes code for empty blocks."""

    def analyze_file(self, file_path: Path | str) -> EmptyBlockResult:
        path = Path(file_path)
        if not path.exists():
            return EmptyBlockResult(
                total_blocks=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return EmptyBlockResult(
                total_blocks=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> EmptyBlockResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return EmptyBlockResult(
                total_blocks=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        issues: list[EmptyBlockIssue] = []
        total = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total

            body: tree_sitter.Node | None = None

            if node.type in ("block", "statement_block", "function_body"):
                total += 1
                if _is_empty_block(node, ext):
                    parent = node.parent
                    parent_type = parent.type if parent is not None else ""
                    issue_type = _classify_context(parent_type, ext)
                    if issue_type is not None:
                        issues.append(EmptyBlockIssue(
                            line_number=node.start_point[0] + 1,
                            issue_type=issue_type,
                            description=_DESCRIPTIONS.get(issue_type, ""),
                            severity=_SEVERITY_MAP.get(issue_type, SEVERITY_LOW),
                            context=content[
                                node.start_byte:node.end_byte
                            ].decode("utf-8", errors="replace")[:80],
                        ))
                for child in node.children:
                    visit(child)
                return

            body = node.child_by_field_name("body")
            if body is not None:
                visit(body)

            consequence = node.child_by_field_name("consequence")
            if consequence is not None:
                visit(consequence)

            alternative = node.child_by_field_name("alternative")
            if alternative is not None:
                visit(alternative)

            for child in node.children:
                if child != body and child != consequence and child != alternative:
                    visit(child)

        visit(tree.root_node)

        return EmptyBlockResult(
            total_blocks=total,
            issues=tuple(issues),
            file_path=str(path),
        )
