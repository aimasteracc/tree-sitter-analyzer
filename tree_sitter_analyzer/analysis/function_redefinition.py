"""Function Redefinition Detector.

Detects functions defined multiple times in the same scope. The later
definition silently replaces the earlier one, which is almost always
a bug rather than intentional.

Issue types:
  - function_redefinition: def f(): ... def f(): ... (same scope)
  - method_redefinition: same method defined twice in a class

Supports Python, JavaScript, TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

ISSUE_FUNC_REDEF = "function_redefinition"
ISSUE_METHOD_REDEF = "method_redefinition"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_FUNC_REDEF: (
        "Function is defined again in the same scope, "
        "silently replacing the earlier definition"
    ),
    ISSUE_METHOD_REDEF: (
        "Method is defined again in the same class, "
        "silently replacing the earlier definition"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_FUNC_REDEF: (
        "Rename one of the functions or remove the duplicate."
    ),
    ISSUE_METHOD_REDEF: (
        "Rename one of the methods or remove the duplicate."
    ),
}

_FUNC_DEF_TYPES: set[str] = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
    "generator_function_declaration",
}

_CLASS_TYPES: set[str] = {
    "class_definition",
    "class_declaration",
    "interface_declaration",
    "struct_declaration",
    "type_declaration",
}

_SCOPE_NODE_TYPES: set[str] = {
    "module",
    "program",
    "block",
    "statement_block",
    "function_definition",
    "function_declaration",
    "method_definition",
    "if_statement",
    "for_statement",
    "while_statement",
    "try_statement",
    "with_statement",
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _get_function_name(node: tree_sitter.Node) -> str | None:
    """Extract the name from a function definition node."""
    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(name_node)
    return None


@dataclass(frozen=True)
class RedefinitionIssue:
    line: int
    issue_type: str
    severity: str
    description: str
    suggestion: str
    context: str
    original_line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
            "original_line": self.original_line,
        }


@dataclass
class FunctionRedefinitionResult:
    file_path: str
    total_functions: int
    issues: list[RedefinitionIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_functions": self.total_functions,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class FunctionRedefinitionAnalyzer(BaseAnalyzer):
    """Detects functions defined multiple times in the same scope."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
        }

    def analyze_file(
        self, file_path: str | Path,
    ) -> FunctionRedefinitionResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return FunctionRedefinitionResult(
                file_path=str(path),
                total_functions=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return FunctionRedefinitionResult(
                file_path=str(path),
                total_functions=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        total = 0
        issues: list[RedefinitionIssue] = []

        total += self._scan_scope(
            tree.root_node, issues, is_class=False,
        )

        return FunctionRedefinitionResult(
            file_path=str(path),
            total_functions=total,
            issues=issues,
        )

    def _scan_scope(
        self,
        node: tree_sitter.Node,
        issues: list[RedefinitionIssue],
        is_class: bool,
    ) -> int:
        """Scan a scope for duplicate function definitions."""
        total = 0
        seen: dict[str, int] = {}

        children = list(node.children)

        if is_class:
            body_nodes: list[tree_sitter.Node] = []
            for child in children:
                if child.type in ("block", "body", "declaration_list",
                                  "class_body", "interface_body"):
                    body_nodes = list(child.children)
                    break
            if body_nodes:
                children = body_nodes

        for child in children:
            if child.type in _FUNC_DEF_TYPES:
                name = _get_function_name(child)
                if name:
                    total += 1
                    if name in seen:
                        issue_type = (
                            ISSUE_METHOD_REDEF
                            if is_class
                            else ISSUE_FUNC_REDEF
                        )
                        issues.append(RedefinitionIssue(
                            line=child.start_point[0] + 1,
                            issue_type=issue_type,
                            severity=SEVERITY_HIGH,
                            description=_DESCRIPTIONS[issue_type],
                            suggestion=_SUGGESTIONS[issue_type],
                            context=f"{name} (first defined at L{seen[name]})",
                            original_line=seen[name],
                        ))
                    else:
                        seen[name] = child.start_point[0] + 1

            if child.type in _CLASS_TYPES:
                total += self._scan_scope(
                    child, issues, is_class=True,
                )
            elif child.type in _SCOPE_NODE_TYPES:
                total += self._scan_scope(
                    child, issues, is_class=False,
                )

        return total
