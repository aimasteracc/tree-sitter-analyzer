"""Late-Binding Closure Detector.

Detects closures created inside loops that capture loop variables by
reference rather than by value. This is a classic bug pattern where
the closure sees the final value of the loop variable instead of the
value at each iteration.

Issue types:
  - late_binding_lambda: lambda in loop body captures loop variable (Python)
  - late_binding_func: function expression in loop captures loop variable (JS/TS)
  - late_binding_arrow: arrow function in loop captures loop variable (JS/TS)

Supports Python, JavaScript, TypeScript, Java.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import (
    _EXTENSION_TO_LANGUAGE,
    BaseAnalyzer,
)
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

ISSUE_LATE_BINDING_LAMBDA = "late_binding_lambda"
ISSUE_LATE_BINDING_FUNC = "late_binding_func"
ISSUE_LATE_BINDING_ARROW = "late_binding_arrow"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_LATE_BINDING_LAMBDA: (
        "Lambda inside loop captures loop variable by reference"
    ),
    ISSUE_LATE_BINDING_FUNC: (
        "Function expression inside loop captures loop variable by reference"
    ),
    ISSUE_LATE_BINDING_ARROW: (
        "Arrow function inside loop captures loop variable by reference"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_LATE_BINDING_LAMBDA: (
        "Use a default argument to capture the current value: "
        "lambda x=i: x instead of lambda: i"
    ),
    ISSUE_LATE_BINDING_FUNC: (
        "Use let/const instead of var, or wrap in an IIFE to capture current value"
    ),
    ISSUE_LATE_BINDING_ARROW: (
        "Use let/const instead of var, or wrap in an IIFE to capture current value"
    ),
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


_LOOP_TYPES: set[str] = {
    "for_statement",
    "while_statement",
    "for_in_statement",
    "list_comprehension",
    "set_comprehension",
    "dict_comprehension",
    "generator_expression",
    "enhanced_for_statement",
}

_CLOSURE_TYPES_PYTHON: set[str] = {"lambda"}
_CLOSURE_TYPES_JS: set[str] = {"function_expression", "arrow_function"}
_CLOSURE_TYPES_JAVA: set[str] = {"lambda_expression"}


def _get_loop_variables(node: tree_sitter.Node, language: str) -> set[str]:
    """Extract variable names bound by a loop node."""
    names: set[str] = set()

    if language == "python":
        if node.type in ("for_statement", "for_in_statement"):
            left = node.child_by_field_name("left")
            if left:
                _extract_names(left, names)
        elif node.type in (
            "list_comprehension",
            "set_comprehension",
            "dict_comprehension",
            "generator_expression",
        ):
            for child in node.children:
                if child.type == "for_in_clause":
                    for sub in child.children:
                        if sub.type == "for":
                            continue
                        if sub.type == "in":
                            continue
                        if sub.type == "identifier":
                            names.add(_node_text(sub))
                        elif sub.type in ("tuple", "list", "pattern_list"):
                            _extract_names(sub, names)
    elif language in ("javascript", "typescript", "tsx"):
        if node.type == "for_statement":
            init = node.child_by_field_name("initializer")
            if init:
                _extract_js_var_names(init, names, include_var_only=True)
        elif node.type == "for_in_statement":
            left = node.child_by_field_name("left")
            if left:
                _extract_names(left, names)
    elif language == "java":
        if node.type == "enhanced_for_statement":
            for child in node.children:
                if child.type in (
                    "integral_type",
                    "local_variable_type",
                    "identifier",
                ):
                    pass
                if child.type == "identifier":
                    prev = child.prev_named_sibling
                    if prev and prev.type not in (
                        "integral_type",
                        "local_variable_type",
                    ):
                        names.add(_node_text(child))
            name_node = node.child_by_field_name("name")
            if name_node:
                names.add(_node_text(name_node))
    return names


def _extract_names(node: tree_sitter.Node, names: set[str]) -> None:
    if node.type == "identifier":
        names.add(_node_text(node))
    elif node.type in ("tuple", "list", "pattern_list"):
        for child in node.children:
            _extract_names(child, names)


def _extract_js_var_names(
    node: tree_sitter.Node,
    names: set[str],
    include_var_only: bool = False,
) -> None:
    if node.type == "variable_declarator":
        name_node = node.child_by_field_name("name")
        if name_node:
            names.add(_node_text(name_node))
    elif node.type == "variable_declaration":
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    names.add(_node_text(name_node))
    elif node.type == "assignment_expression":
        left = node.child_by_field_name("left")
        if left and left.type == "identifier":
            names.add(_node_text(left))
    elif node.type == "var_identifier":
        names.add(_node_text(node))
    elif node.type == "lexical_declaration":
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    names.add(_node_text(name_node))


def _references_name(
    node: tree_sitter.Node,
    target_names: set[str],
) -> bool:
    """Check if node or any descendant references a target name."""
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "identifier":
            if _node_text(current) in target_names:
                return True
        for child in current.children:
            stack.append(child)
    return False


@dataclass(frozen=True)
class LateBindingIssue:
    line: int
    issue_type: str
    severity: str
    description: str
    suggestion: str
    context: str
    loop_variable: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
            "loop_variable": self.loop_variable,
        }


@dataclass
class LateBindingClosureResult:
    file_path: str
    total_closures: int
    issues: list[LateBindingIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_closures": self.total_closures,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class LateBindingClosureAnalyzer(BaseAnalyzer):
    """Detects closures in loops that capture loop variables by reference."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> LateBindingClosureResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return LateBindingClosureResult(
                file_path=str(path),
                total_closures=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return LateBindingClosureResult(
                file_path=str(path),
                total_closures=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        lang_name = _EXTENSION_TO_LANGUAGE.get(ext, "")
        issues: list[LateBindingIssue] = []
        total_closures = 0

        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()

            if node.type in _LOOP_TYPES:
                loop_vars = _get_loop_variables(node, lang_name)
                if loop_vars:
                    found = self._scan_for_closures(
                        node, loop_vars, lang_name,
                    )
                    total_closures += found[0]
                    issues.extend(found[1])
            else:
                for child in node.children:
                    stack.append(child)

        return LateBindingClosureResult(
            file_path=str(path),
            total_closures=total_closures,
            issues=issues,
        )

    def _scan_for_closures(
        self,
        loop_node: tree_sitter.Node,
        loop_vars: set[str],
        language: str,
    ) -> tuple[int, list[LateBindingIssue]]:
        """Find closures inside a loop that reference loop variables."""
        closure_types = self._closure_types_for(language)
        total = 0
        issues: list[LateBindingIssue] = []

        stack: list[tree_sitter.Node] = list(loop_node.children)
        while stack:
            node = stack.pop()

            if node.type in closure_types:
                total += 1
                body = node.child_by_field_name("body")
                if body is None:
                    for child in node.children:
                        if child.type not in ("identifier", "(", ")", ":"):
                            body = child
                            break
                if body is None:
                    body = node

                for var_name in loop_vars:
                    if _references_name(body, {var_name}):
                        issue_type = self._issue_type_for(
                            node.type, language,
                        )
                        if issue_type:
                            issues.append(LateBindingIssue(
                                line=node.start_point[0] + 1,
                                issue_type=issue_type,
                                severity=SEVERITY_HIGH,
                                description=_DESCRIPTIONS[issue_type],
                                suggestion=_SUGGESTIONS[issue_type],
                                context=(
                                    f"{_txt(node)[:60]} captures "
                                    f"loop variable '{var_name}'"
                                ),
                                loop_variable=var_name,
                            ))
            else:
                for child in node.children:
                    stack.append(child)

        return total, issues

    def _closure_types_for(self, language: str) -> set[str]:
        if language == "python":
            return _CLOSURE_TYPES_PYTHON
        if language in ("javascript", "typescript", "tsx"):
            return _CLOSURE_TYPES_JS
        if language == "java":
            return _CLOSURE_TYPES_JAVA
        return set()

    def _issue_type_for(self, closure_type: str, language: str) -> str | None:
        if language == "python":
            return ISSUE_LATE_BINDING_LAMBDA
        if language in ("javascript", "typescript", "tsx"):
            if closure_type == "arrow_function":
                return ISSUE_LATE_BINDING_ARROW
            return ISSUE_LATE_BINDING_FUNC
        if language == "java":
            return ISSUE_LATE_BINDING_LAMBDA
        return None
