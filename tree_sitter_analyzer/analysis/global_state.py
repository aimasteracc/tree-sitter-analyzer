"""Global State Analyzer.

Detects module-level mutable state, `global` keyword usage, and `nonlocal`
keyword usage that create hidden coupling and testability issues.

Supports Python, JavaScript/TypeScript, Java, Go.
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
SEVERITY_LOW = "low"

ISSUE_GLOBAL_STATE = "global_state"
ISSUE_GLOBAL_KEYWORD = "global_keyword"
ISSUE_NONLOCAL_KEYWORD = "nonlocal_keyword"
ISSUE_STATIC_MUTABLE = "static_mutable"
ISSUE_PACKAGE_VAR = "package_var"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_GLOBAL_STATE: SEVERITY_MEDIUM,
    ISSUE_GLOBAL_KEYWORD: SEVERITY_HIGH,
    ISSUE_NONLOCAL_KEYWORD: SEVERITY_HIGH,
    ISSUE_STATIC_MUTABLE: SEVERITY_MEDIUM,
    ISSUE_PACKAGE_VAR: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_GLOBAL_STATE: "Module-level mutable variable creates hidden coupling",
    ISSUE_GLOBAL_KEYWORD: "`global` statement modifies module-level state from function scope",
    ISSUE_NONLOCAL_KEYWORD: "`nonlocal` statement modifies enclosing scope state",
    ISSUE_STATIC_MUTABLE: "Static non-final field is shared mutable state",
    ISSUE_PACKAGE_VAR: "Package-level variable (not const) is shared mutable state",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_GLOBAL_STATE: "Wrap state in a class or pass explicitly as parameters.",
    ISSUE_GLOBAL_KEYWORD: "Return values instead of mutating global state.",
    ISSUE_NONLOCAL_KEYWORD: "Refactor to use return values or a class instance.",
    ISSUE_STATIC_MUTABLE: "Make field final or use instance fields instead.",
    ISSUE_PACKAGE_VAR: "Use const or move into a struct with controlled access.",
}

# Supplements for extensions where knowledge is not yet available
_SCOPE_SUPPLEMENT: dict[str, frozenset[str]] = {
    ".ts": frozenset({
        "function_declaration", "function_expression", "arrow_function",
        "method_definition", "class_declaration",
    }),
    ".tsx": frozenset({
        "function_declaration", "function_expression", "arrow_function",
        "method_definition", "class_declaration",
    }),
}

# Python mutable collection literals at module scope
_PY_MUTABLE_COLLECTIONS = frozenset({"list", "dictionary", "set"})

# Java collection types that are mutable
_JAVA_MUTABLE_TYPES = frozenset({
    "ArrayList", "HashMap", "HashSet", "LinkedList",
    "TreeMap", "TreeSet", "LinkedHashMap", "LinkedHashSet",
    "Vector", "Hashtable", "StringBuilder", "StringBuffer",
    "ArrayDeque", "PriorityQueue", "Properties",
})


@dataclass(frozen=True)
class GlobalStateFinding:
    issue_type: str
    name: str
    line: int
    severity: str
    description: str
    suggestion: str


@dataclass
class GlobalStateResult:
    file_path: str
    findings: list[GlobalStateFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_findings": len(self.findings),
            "high_severity": sum(
                1 for f in self.findings if f.severity == SEVERITY_HIGH
            ),
            "findings": [
                {
                    "issue_type": f.issue_type,
                    "name": f.name,
                    "line": f.line,
                    "severity": f.severity,
                    "description": f.description,
                    "suggestion": f.suggestion,
                }
                for f in self.findings
            ],
        }


class GlobalStateAnalyzer(BaseAnalyzer):
    """Detects global/module-level mutable state across multiple languages."""

    SUPPORTED_EXTENSIONS: set[str] = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"}

    def analyze_file(self, file_path: str) -> GlobalStateResult:
        path = Path(file_path)
        if not path.exists():
            return GlobalStateResult(file_path=file_path)

        extension = path.suffix
        if extension not in self.SUPPORTED_EXTENSIONS:
            return GlobalStateResult(file_path=file_path)

        language, parser = self._get_parser(extension)
        if language is None or parser is None:
            return GlobalStateResult(file_path=file_path)

        source = path.read_bytes()
        tree = parser.parse(source)
        return self._analyze(tree, file_path, extension, language, source)

    def _analyze(
        self,
        tree: tree_sitter.Tree,
        file_path: str,
        extension: str,
        language: Any,
        source: bytes,
    ) -> GlobalStateResult:
        result = GlobalStateResult(file_path=file_path)

        if extension == ".py":
            self._analyze_python(tree, source, result, extension)
        elif extension in (".js", ".jsx", ".ts", ".tsx"):
            self._analyze_js_ts(tree, source, result, extension)
        elif extension == ".java":
            self._analyze_java(tree, source, result)
        elif extension == ".go":
            self._analyze_go(tree, source, result, extension)

        return result

    def _is_module_level(self, node: tree_sitter.Node, extension: str) -> bool:
        boundaries = self._get_scope_boundaries(extension)
        parent = node.parent
        while parent is not None:
            if parent.type in boundaries:
                return False
            parent = parent.parent
        return True

    def _get_scope_boundaries(self, extension: str) -> frozenset[str]:
        knowledge = self._get_knowledge(extension)
        boundaries = knowledge.scope_boundary_nodes
        if not boundaries:
            boundaries = _SCOPE_SUPPLEMENT.get(extension, frozenset())
        return boundaries

    def _get_text(self, node: tree_sitter.Node, source: bytes) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _add_finding(
        self,
        result: GlobalStateResult,
        issue_type: str,
        name: str,
        line: int,
    ) -> None:
        result.findings.append(
            GlobalStateFinding(
                issue_type=issue_type,
                name=name,
                line=line,
                severity=_SEVERITY_MAP.get(issue_type, SEVERITY_LOW),
                description=_DESCRIPTIONS.get(issue_type, ""),
                suggestion=_SUGGESTIONS.get(issue_type, ""),
            )
        )

    def _analyze_python(
        self, tree: tree_sitter.Tree, source: bytes, result: GlobalStateResult,
        extension: str,
    ) -> None:
        boundaries = self._get_scope_boundaries(extension)
        self._walk_python(tree.root_node, source, result, boundaries)

    def _walk_python(
        self,
        node: tree_sitter.Node,
        source: bytes,
        result: GlobalStateResult,
        boundaries: frozenset[str],
        in_scope: bool = False,
    ) -> None:

        if node.type == "global_statement":
            for child in node.children:
                if child.type == "identifier":
                    name = self._get_text(child, source)
                    self._add_finding(
                        result, ISSUE_GLOBAL_KEYWORD, name, node.start_point[0] + 1
                    )
            return

        if node.type == "nonlocal_statement":
            for child in node.children:
                if child.type == "identifier":
                    name = self._get_text(child, source)
                    self._add_finding(
                        result, ISSUE_NONLOCAL_KEYWORD, name, node.start_point[0] + 1
                    )
            return

        is_in_scope = in_scope or node.type in boundaries

        if not is_in_scope and node.type == "assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None:
                name = self._get_text(left, source)
                is_lambda = right is not None and right.type == "lambda"
                if not self._is_upper_snake(name) and not is_lambda:
                    self._add_finding(
                        result, ISSUE_GLOBAL_STATE, name, node.start_point[0] + 1
                    )

        for child in node.children:
            self._walk_python(child, source, result, boundaries, is_in_scope)

    def _is_upper_snake(self, name: str) -> bool:
        return name.isupper() or (
            "_" in name and all(c == "_" or c.isupper() or c.isdigit() for c in name)
        )

    def _analyze_js_ts(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        result: GlobalStateResult,
        extension: str,
    ) -> None:
        boundaries = self._get_scope_boundaries(extension)

        def walk(node: tree_sitter.Node, in_scope: bool = False) -> None:
            is_in_scope = in_scope or node.type in boundaries

            if not is_in_scope:
                if node.type == "variable_declarator":
                    name_node = node.child_by_field_name("name")
                    if name_node is not None:
                        name = self._get_text(name_node, source)
                        parent = node.parent
                        is_const = False
                        if parent is not None:
                            parent_text = self._get_text(parent, source)
                            first_word = parent_text.split()[0] if parent_text else ""
                            is_const = first_word == "const"
                        if not is_const:
                            self._add_finding(
                                result, ISSUE_GLOBAL_STATE, name, node.start_point[0] + 1
                            )

                elif node.type == "assignment_expression":
                    left = node.child_by_field_name("left")
                    if left is not None and left.type == "identifier":
                        name = self._get_text(left, source)
                        self._add_finding(
                            result, ISSUE_GLOBAL_STATE, name, node.start_point[0] + 1
                        )

            for child in node.children:
                walk(child, is_in_scope)

        walk(tree.root_node)

    def _analyze_java(
        self, tree: tree_sitter.Tree, source: bytes, result: GlobalStateResult
    ) -> None:

        def walk(node: tree_sitter.Node) -> None:
            if node.type == "field_declaration":
                is_static = False
                is_final = False
                for child in node.children:
                    if child.type == "modifiers":
                        mod_text = self._get_text(child, source)
                        is_static = "static" in mod_text
                        is_final = "final" in mod_text

                if is_static and not is_final:
                    for child in node.children:
                        if child.type == "variable_declarator":
                            name_node = child.child_by_field_name("name")
                            if name_node is not None:
                                name = self._get_text(name_node, source)
                                self._add_finding(
                                    result, ISSUE_STATIC_MUTABLE, name, node.start_point[0] + 1
                                )

            for child in node.children:
                walk(child)

        walk(tree.root_node)

    def _extract_go_var_spec(
        self, spec: tree_sitter.Node, source: bytes, result: GlobalStateResult
    ) -> None:
        for child in spec.children:
            if child.type == "identifier":
                name = self._get_text(child, source)
                self._add_finding(
                    result, ISSUE_PACKAGE_VAR, name, spec.start_point[0] + 1
                )

    def _analyze_go(
        self, tree: tree_sitter.Tree, source: bytes, result: GlobalStateResult,
        extension: str,
    ) -> None:
        boundaries = self._get_scope_boundaries(extension)

        def walk(node: tree_sitter.Node, in_func: bool = False) -> None:
            is_in_func = in_func or node.type in boundaries

            if not is_in_func and node.type == "var_declaration":
                for child in node.children:
                    if child.type == "var_spec":
                        self._extract_go_var_spec(child, source, result)
                    elif child.type == "var_spec_list":
                        for spec in child.children:
                            if spec.type == "var_spec":
                                self._extract_go_var_spec(spec, source, result)

            elif not is_in_func and node.type == "short_var_declaration":
                left = node.child_by_field_name("left")
                if left is not None:
                    name = self._get_text(left, source)
                    self._add_finding(
                        result, ISSUE_PACKAGE_VAR, name, node.start_point[0] + 1
                    )

            for child in node.children:
                walk(child, is_in_func)

        walk(tree.root_node)
