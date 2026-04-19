"""Nested Class Analyzer.

Detects classes defined inside other classes (nested/inner classes).
While sometimes intentional (builders, helpers), deeply nested or
frequent nested classes often indicate a design smell that could
be improved with composition or module-level classes.
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
class NestedClassIssue:
    """A class defined inside another class."""

    line_number: int
    inner_class: str
    outer_class: str
    nesting_depth: int
    severity: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "inner_class": self.inner_class,
            "outer_class": self.outer_class,
            "nesting_depth": self.nesting_depth,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class NestedClassResult:
    """Aggregated nested class analysis result."""

    total_issues: int
    issues: tuple[NestedClassIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_issues": self.total_issues,
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


class NestedClassAnalyzer(BaseAnalyzer):
    """Detects classes defined inside other classes."""

    SUPPORTED_EXTENSIONS: set[str] = {".py", ".java", ".cs", ".cpp", ".hpp"}

    def analyze_file(self, file_path: Path | str) -> NestedClassResult:
        path = Path(file_path)
        if not path.exists():
            return NestedClassResult(
                total_issues=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return NestedClassResult(
                total_issues=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> NestedClassResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return NestedClassResult(
                total_issues=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        issues: list[NestedClassIssue] = []
        self._walk(tree.root_node, content, issues, depth=0)

        return NestedClassResult(
            total_issues=len(issues),
            issues=tuple(issues),
            file_path=str(path),
        )

    def _walk(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[NestedClassIssue],
        depth: int,
    ) -> None:
        if node.type in ("class_definition", "class_declaration"):
            class_name = self._get_name(node, content)
            if class_name and depth > 0:
                outer = self._find_enclosing_class(node, content)
                issues.append(
                    NestedClassIssue(
                        line_number=node.start_point[0] + 1,
                        inner_class=class_name,
                        outer_class=outer,
                        nesting_depth=depth,
                        severity=(
                            SEVERITY_MEDIUM if depth >= 2 else SEVERITY_LOW
                        ),
                    )
                )

            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    self._walk(child, content, issues, depth + 1)
            return

        for child in node.children:
            self._walk(child, content, issues, depth)

    def _get_name(
        self, node: tree_sitter.Node, content: bytes
    ) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return ""
        return content[
            name_node.start_byte:name_node.end_byte
        ].decode("utf-8", errors="replace")

    def _find_enclosing_class(
        self, node: tree_sitter.Node, content: bytes
    ) -> str:
        parent = node.parent
        while parent is not None:
            if parent.type in (
                "class_definition",
                "class_declaration",
            ):
                name = self._get_name(parent, content)
                if name:
                    return name
            parent = parent.parent
        return "<unknown>"
