"""Query Method Mutation Detector.

Detects methods whose names suggest read-only queries (get*, is*, has*,
check*, find*, can*, should*, validate*) but that modify object state
(self/this fields), violating the Command-Query Separation principle.

Issues detected:
  - query_method_mutation: query-named method writes to self/this fields

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"

ISSUE_QUERY_MUTATION = "query_method_mutation"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_QUERY_MUTATION: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_QUERY_MUTATION: (
        "Query-named method modifies object state (CQS violation)"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_QUERY_MUTATION: (
        "Rename the method to indicate a command, or separate the "
        "state mutation into a distinct command method"
    ),
}

_QUERY_PREFIXES_PY: frozenset[str] = frozenset({
    "get_", "is_", "has_", "check_", "find_",
    "can_", "should_", "validate_",
})

_QUERY_PREFIXES_CAMEL: frozenset[str] = frozenset({
    "get", "is", "has", "check", "find",
    "can", "should", "validate",
    "Get", "Is", "Has", "Check", "Find",
    "Can", "Should", "Validate",
})


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _is_query_name_py(name: str) -> bool:
    lower = name.lower()
    return any(lower.startswith(p) for p in _QUERY_PREFIXES_PY)


def _is_query_name_camel(name: str) -> bool:
    for prefix in _QUERY_PREFIXES_CAMEL:
        if name.startswith(prefix) and len(name) > len(prefix):
            next_char = name[len(prefix)]
            if next_char.isupper() or next_char == "_":
                return True
    return False


@dataclass(frozen=True)
class QueryMutationIssue:
    line: int
    issue_type: str
    severity: str
    method_name: str
    field_name: str
    description: str
    suggestion: str


@dataclass(frozen=True)
class QueryMutationResult:
    issues: tuple[QueryMutationIssue, ...]
    total_issues: int
    medium_severity: int
    file_path: str
    language: str

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "total_issues": self.total_issues,
            "medium_severity": self.medium_severity,
            "issues": [
                {
                    "line": i.line,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "method_name": i.method_name,
                    "field_name": i.field_name,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
        }


def _empty_result(file_path: str, language: str) -> QueryMutationResult:
    return QueryMutationResult(
        issues=(),
        total_issues=0,
        medium_severity=0,
        file_path=file_path,
        language=language,
    )


def _is_pointer_receiver(func_text: str) -> bool:
    return bool(re.search(r"\(\w+\s+\*\w+\)", func_text))


class QueryMutationAnalyzer(BaseAnalyzer):
    """Detects query-named methods that mutate object state."""

    def analyze_file(self, file_path: Path | str) -> QueryMutationResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path), "unknown")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return _empty_result(str(path), "unknown")

        language_map: dict[str, str] = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
            ".go": "go",
        }
        lang = language_map.get(ext, "unknown")

        content = path.read_bytes()
        text = content.decode("utf-8", errors="replace")

        if ext == ".py":
            issues = self._analyze_python(content, text)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            issues = self._analyze_javascript(content, text)
        elif ext == ".java":
            issues = self._analyze_java(content, text)
        elif ext == ".go":
            issues = self._analyze_go(content, text)
        else:
            issues = []

        issue_tuple = tuple(issues)
        medium = sum(1 for i in issue_tuple if i.severity == SEVERITY_MEDIUM)
        return QueryMutationResult(
            issues=issue_tuple,
            total_issues=len(issue_tuple),
            medium_severity=medium,
            file_path=str(path),
            language=lang,
        )

    # -- Python -----------------------------------------------------------

    def _analyze_python(
        self, content: bytes, text: str
    ) -> list[QueryMutationIssue]:
        language, parser = self._get_parser(".py")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[QueryMutationIssue] = []
        for func_node, func_name in self._collect_py_functions(tree.root_node):
            if not _is_query_name_py(func_name):
                continue
            if not self._py_method_has_self(func_node):
                continue
            self._check_py_self_mutation(func_node, func_name, issues)

        return issues

    def _collect_py_functions(
        self, node: tree_sitter.Node
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        if node.type == "function_definition":
            name = ""
            for child in node.children:
                if child.type == "identifier":
                    name = _txt(child)
                    break
            results.append((node, name))
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    results.extend(self._collect_py_functions(child))
        else:
            for child in node.children:
                results.extend(self._collect_py_functions(child))
        return results

    def _py_method_has_self(self, func_node: tree_sitter.Node) -> bool:
        params_node = func_node.child_by_field_name("parameters")
        if not params_node:
            return False
        for child in params_node.children:
            if child.type == "identifier" and _txt(child) == "self":
                return True
        return False

    def _check_py_self_mutation(
        self,
        func_node: tree_sitter.Node,
        func_name: str,
        issues: list[QueryMutationIssue],
    ) -> None:
        body = func_node.child_by_field_name("body")
        if not body:
            return
        self._walk_py_assignments(body, func_name, issues)

    def _walk_py_assignments(
        self,
        node: tree_sitter.Node,
        func_name: str,
        issues: list[QueryMutationIssue],
    ) -> None:
        if node.type in ("assignment", "augmented_assignment"):
            left = node.child_by_field_name("left")
            if left:
                left_text = _txt(left)
                match = re.match(r"^self\.(\w+)", left_text)
                if match:
                    field = match.group(1)
                    issues.append(QueryMutationIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_QUERY_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        method_name=func_name,
                        field_name=field,
                        description=(
                            f"Query method '{func_name}' modifies "
                            f"self.{field}"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_QUERY_MUTATION],
                    ))

        for child in node.children:
            self._walk_py_assignments(child, func_name, issues)

    # -- JavaScript/TypeScript --------------------------------------------

    def _analyze_javascript(
        self, content: bytes, text: str
    ) -> list[QueryMutationIssue]:
        language, parser = self._get_parser(".js")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[QueryMutationIssue] = []
        for func_node, func_name in self._collect_js_methods(tree.root_node):
            if not _is_query_name_camel(func_name):
                continue
            self._check_js_this_mutation(func_node, func_name, issues)

        return issues

    def _collect_js_methods(
        self, node: tree_sitter.Node
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []

        if node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            name = _txt(name_node) if name_node else ""
            if name:
                results.append((node, name))

        if node.type != "method_definition":
            for child in node.children:
                results.extend(self._collect_js_methods(child))

        return results

    def _check_js_this_mutation(
        self,
        func_node: tree_sitter.Node,
        func_name: str,
        issues: list[QueryMutationIssue],
    ) -> None:
        body = func_node.child_by_field_name("body")
        if not body:
            return
        self._walk_js_assignments(body, func_name, issues)

    def _walk_js_assignments(
        self,
        node: tree_sitter.Node,
        func_name: str,
        issues: list[QueryMutationIssue],
    ) -> None:
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left:
                left_text = _txt(left)
                match = re.match(r"^this\.(\w+)", left_text)
                if match:
                    field = match.group(1)
                    issues.append(QueryMutationIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_QUERY_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        method_name=func_name,
                        field_name=field,
                        description=(
                            f"Query method '{func_name}' modifies "
                            f"this.{field}"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_QUERY_MUTATION],
                    ))

        for child in node.children:
            self._walk_js_assignments(child, func_name, issues)

    # -- Java -------------------------------------------------------------

    def _analyze_java(
        self, content: bytes, text: str
    ) -> list[QueryMutationIssue]:
        language, parser = self._get_parser(".java")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[QueryMutationIssue] = []
        for method_node, method_name in self._collect_java_methods(
            tree.root_node,
        ):
            if not _is_query_name_camel(method_name):
                continue
            self._check_java_this_mutation(method_node, method_name, issues)

        return issues

    def _collect_java_methods(
        self, node: tree_sitter.Node
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []

        if node.type == "method_declaration":
            name = ""
            for child in node.children:
                if child.type == "identifier" and not name:
                    name = _txt(child)
            if name:
                results.append((node, name))

        if node.type != "method_declaration":
            for child in node.children:
                results.extend(self._collect_java_methods(child))

        return results

    def _check_java_this_mutation(
        self,
        method_node: tree_sitter.Node,
        method_name: str,
        issues: list[QueryMutationIssue],
    ) -> None:
        body = method_node.child_by_field_name("body")
        if not body:
            return
        self._walk_java_assignments(body, method_name, issues)

    def _walk_java_assignments(
        self,
        node: tree_sitter.Node,
        method_name: str,
        issues: list[QueryMutationIssue],
    ) -> None:
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left:
                left_text = _txt(left)
                match = re.match(r"^this\.(\w+)", left_text)
                if match:
                    field = match.group(1)
                    issues.append(QueryMutationIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_QUERY_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        method_name=method_name,
                        field_name=field,
                        description=(
                            f"Query method '{method_name}' modifies "
                            f"this.{field}"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_QUERY_MUTATION],
                    ))

        for child in node.children:
            self._walk_java_assignments(child, method_name, issues)

    # -- Go ---------------------------------------------------------------

    def _analyze_go(
        self, content: bytes, text: str
    ) -> list[QueryMutationIssue]:
        language, parser = self._get_parser(".go")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[QueryMutationIssue] = []
        for func_node, func_name, receiver in (
            self._collect_go_methods(tree.root_node)
        ):
            if not receiver:
                continue
            if not _is_query_name_camel(func_name):
                continue
            func_text = _txt(func_node)
            if not _is_pointer_receiver(func_text):
                continue
            self._check_go_receiver_mutation(
                func_node, func_name, receiver, issues,
            )

        return issues

    def _collect_go_methods(
        self, node: tree_sitter.Node
    ) -> list[tuple[tree_sitter.Node, str, str]]:
        results: list[tuple[tree_sitter.Node, str, str]] = []

        if node.type == "method_declaration":
            name = ""
            receiver = ""
            first_param_list = True
            for child in node.children:
                if child.type in ("identifier", "field_identifier") and not name:
                    name = _txt(child)
                elif child.type == "parameter_list" and first_param_list:
                    first_param_list = False
                    for param in child.children:
                        if param.type == "parameter_declaration":
                            for sc in param.children:
                                if sc.type == "identifier":
                                    receiver = _txt(sc)
                                    break
                            break
            if name:
                results.append((node, name, receiver))

        if node.type != "method_declaration":
            for child in node.children:
                results.extend(self._collect_go_methods(child))

        return results

    def _check_go_receiver_mutation(
        self,
        func_node: tree_sitter.Node,
        func_name: str,
        receiver: str,
        issues: list[QueryMutationIssue],
    ) -> None:
        body = func_node.child_by_field_name("body")
        if not body:
            return
        self._walk_go_assignments(body, func_name, receiver, issues)

    def _walk_go_assignments(
        self,
        node: tree_sitter.Node,
        func_name: str,
        receiver: str,
        issues: list[QueryMutationIssue],
    ) -> None:
        if node.type == "assignment_statement":
            left = node.child_by_field_name("left")
            if left:
                left_text = _txt(left)
                pattern = rf"^{re.escape(receiver)}\.(\w+)"
                match = re.match(pattern, left_text)
                if match:
                    field = match.group(1)
                    issues.append(QueryMutationIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_QUERY_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        method_name=func_name,
                        field_name=field,
                        description=(
                            f"Query method '{func_name}' modifies "
                            f"{receiver}.{field}"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_QUERY_MUTATION],
                    ))

        for child in node.children:
            self._walk_go_assignments(child, func_name, receiver, issues)
