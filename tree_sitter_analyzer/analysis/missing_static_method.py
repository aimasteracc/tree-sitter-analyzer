"""Missing Static Method Analyzer.

Detects instance methods that never reference 'self' in their body,
indicating they should be @staticmethod instead. This is a common
code smell that misleads callers about the method's dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"


@dataclass(frozen=True)
class MissingStaticMethodIssue:
    """An instance method that doesn't use self."""

    line_number: int
    method_name: str
    class_name: str
    severity: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "method_name": self.method_name,
            "class_name": self.class_name,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class MissingStaticMethodResult:
    """Aggregated missing static method analysis result."""

    total_issues: int
    issues: tuple[MissingStaticMethodIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_issues": self.total_issues,
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


class MissingStaticMethodAnalyzer(BaseAnalyzer):
    """Detects instance methods that never use self."""

    SUPPORTED_EXTENSIONS: set[str] = {".py"}

    def analyze_file(self, file_path: Path | str) -> MissingStaticMethodResult:
        path = Path(file_path)
        if not path.exists():
            return MissingStaticMethodResult(
                total_issues=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return MissingStaticMethodResult(
                total_issues=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> MissingStaticMethodResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return MissingStaticMethodResult(
                total_issues=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        issues: list[MissingStaticMethodIssue] = []
        self._walk(tree.root_node, content, issues)

        return MissingStaticMethodResult(
            total_issues=len(issues),
            issues=tuple(issues),
            file_path=str(path),
        )

    def _walk(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MissingStaticMethodIssue],
    ) -> None:
        if node.type == "class_definition":
            self._check_class(node, content, issues)

        for child in node.children:
            self._walk(child, content, issues)

    def _check_class(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MissingStaticMethodIssue],
    ) -> None:
        class_name = self._get_class_name(node, content)
        if not class_name:
            return

        body = node.child_by_field_name("body")
        if body is None:
            return

        for child in body.children:
            if child.type == "function_definition":
                self._check_method(
                    child, content, class_name, issues
                )
            elif child.type == "decorated_definition":
                inner = child.child_by_field_name("definition")
                if inner is None:
                    for sub in child.children:
                        if sub.type == "function_definition":
                            inner = sub
                            break

                if inner is not None and inner.type == "function_definition":
                    if self._is_staticmethod(child):
                        continue
                    if self._is_classmethod(child):
                        continue
                    self._check_method(
                        inner, content, class_name, issues
                    )

    def _check_method(
        self,
        node: tree_sitter.Node,
        content: bytes,
        class_name: str,
        issues: list[MissingStaticMethodIssue],
    ) -> None:
        params = node.child_by_field_name("parameters")
        if params is None:
            return

        first_param = None
        for child in params.children:
            if child.type in ("identifier", "typed_parameter"):
                first_param = child
                break

        if first_param is None:
            return

        param_text = content[
            first_param.start_byte:first_param.end_byte
        ].decode("utf-8", errors="replace")

        if param_text != "self" and param_text != "cls":
            return

        body = node.child_by_field_name("body")
        if body is None:
            return

        method_name = self._get_function_name(node, content)
        if not method_name:
            return

        if method_name.startswith("__") and method_name.endswith("__"):
            return

        if self._body_references_self(body, content):
            return

        issues.append(
            MissingStaticMethodIssue(
                line_number=node.start_point[0] + 1,
                method_name=method_name,
                class_name=class_name,
                severity=SEVERITY_MEDIUM,
            )
        )

    def _body_references_self(
        self, body: tree_sitter.Node, content: bytes
    ) -> bool:
        cursor = body.walk()
        reached_root = False
        while not reached_root:
            current = cursor.node
            if current is not None:
                if current.type == "attribute":
                    obj = current.child_by_field_name("object")
                    if obj is not None and obj.type == "identifier":
                        text = content[
                            obj.start_byte:obj.end_byte
                        ].decode("utf-8", errors="replace")
                        if text == "self":
                            return True
                elif current.type == "identifier":
                    text = content[
                        current.start_byte:current.end_byte
                    ].decode("utf-8", errors="replace")
                    if text == "self":
                        return True
            if cursor.goto_first_child():
                continue
            if cursor.goto_next_sibling():
                continue
            retracing = True
            while retracing:
                if not cursor.goto_parent():
                    retracing = False
                    reached_root = True
                elif cursor.node == body:
                    retracing = False
                    reached_root = True
                elif cursor.goto_next_sibling():
                    retracing = False
        return False

    def _get_class_name(
        self, node: tree_sitter.Node, content: bytes
    ) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return ""
        return content[
            name_node.start_byte:name_node.end_byte
        ].decode("utf-8", errors="replace")

    def _get_function_name(
        self, node: tree_sitter.Node, content: bytes
    ) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return ""
        return content[
            name_node.start_byte:name_node.end_byte
        ].decode("utf-8", errors="replace")

    def _is_staticmethod(self, decorated: tree_sitter.Node) -> bool:
        for child in decorated.children:
            if child.type == "decorator":
                raw = child.text
                if raw is not None:
                    text = raw.decode("utf-8", errors="replace")
                    if text == "@staticmethod":
                        return True
        return False

    def _is_classmethod(self, decorated: tree_sitter.Node) -> bool:
        for child in decorated.children:
            if child.type == "decorator":
                raw = child.text
                if raw is not None:
                    text = raw.decode("utf-8", errors="replace")
                    if text == "@classmethod":
                        return True
        return False
