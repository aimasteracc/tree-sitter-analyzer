"""Lazy Class Detector.

Detects classes with too few methods or members that may not justify
their existence. Classes with 0-1 methods are candidates for
simplification into plain functions or data structures.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_OK = "ok"
SEVERITY_LAZY = "lazy"
SEVERITY_CANDIDATE = "removal_candidate"

DEFAULT_MAX_METHODS = 1
DEFAULT_MAX_FIELDS = 2

def _severity(method_count: int, field_count: int) -> str:
    if method_count == 0:
        return SEVERITY_CANDIDATE
    return SEVERITY_LAZY

@dataclass(frozen=True)
class LazyClassInfo:
    """A class that may be too simple to justify its existence."""

    class_name: str
    line_number: int
    method_count: int
    field_count: int
    severity: str

    def to_dict(self) -> dict[str, object]:
        return {
            "class_name": self.class_name,
            "line_number": self.line_number,
            "method_count": self.method_count,
            "field_count": self.field_count,
            "severity": self.severity,
        }

@dataclass(frozen=True)
class LazyClassResult:
    """Aggregated lazy class analysis result."""

    total_classes: int
    lazy_classes: tuple[LazyClassInfo, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_classes": self.total_classes,
            "lazy_count": len(self.lazy_classes),
            "lazy_classes": [c.to_dict() for c in self.lazy_classes],
            "file_path": self.file_path,
        }

_CLASS_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"class_definition"}),
    ".js": frozenset({"class_declaration"}),
    ".jsx": frozenset({"class_declaration"}),
    ".ts": frozenset({"class_declaration"}),
    ".tsx": frozenset({"class_declaration"}),
    ".java": frozenset({"class_declaration"}),
    ".go": frozenset({"type_declaration"}),
}

_METHOD_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({"method_definition"}),
    ".jsx": frozenset({"method_definition"}),
    ".ts": frozenset({"method_definition"}),
    ".tsx": frozenset({"method_definition"}),
    ".java": frozenset({"method_declaration", "constructor_declaration"}),
    ".go": frozenset({"method_declaration", "func_literal"}),
}

_FIELD_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"expression_statement"}),
    ".js": frozenset({"public_field_definition", "field_definition"}),
    ".jsx": frozenset({"public_field_definition", "field_definition"}),
    ".ts": frozenset({"public_field_definition", "field_definition"}),
    ".tsx": frozenset({"public_field_definition", "field_definition"}),
    ".java": frozenset({"field_declaration"}),
    ".go": frozenset({"field_declaration"}),
}

class LazyClassAnalyzer(BaseAnalyzer):
    """Analyzes classes for insufficient complexity."""

    def analyze_file(self, file_path: Path | str) -> LazyClassResult:
        path = Path(file_path)
        if not path.exists():
            return LazyClassResult(
                total_classes=0,
                lazy_classes=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return LazyClassResult(
                total_classes=0,
                lazy_classes=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> LazyClassResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return LazyClassResult(
                total_classes=0,
                lazy_classes=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        class_types = _CLASS_TYPES.get(ext, frozenset())
        method_types = _METHOD_TYPES.get(ext, frozenset())
        field_types = _FIELD_TYPES.get(ext, frozenset())

        lazy: list[LazyClassInfo] = []
        total = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total

            if node.type in class_types:
                total += 1
                name = self._get_class_name(node, content)
                body = self._get_class_body(node)
                if body is not None:
                    method_count = self._count_direct(
                        body, method_types
                    )
                    field_count = self._count_direct(
                        body, field_types
                    )
                else:
                    method_count = self._count_direct(
                        node, method_types
                    )
                    field_count = self._count_direct(
                        node, field_types
                    )

                if (
                    method_count <= DEFAULT_MAX_METHODS
                    and field_count <= DEFAULT_MAX_FIELDS
                ):
                    lazy.append(
                        LazyClassInfo(
                            class_name=name,
                            line_number=node.start_point[0] + 1,
                            method_count=method_count,
                            field_count=field_count,
                            severity=_severity(
                                method_count, field_count
                            ),
                        )
                    )
                return

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return LazyClassResult(
            total_classes=total,
            lazy_classes=tuple(lazy),
            file_path=str(path),
        )

    @staticmethod
    def _get_class_body(
        node: tree_sitter.Node,
    ) -> tree_sitter.Node | None:
        body = node.child_by_field_name("body")
        if body is not None:
            return body
        for child in node.children:
            if child.type in ("block", "class_body", "declaration_list"):
                return child
        return None

    @staticmethod
    def _get_class_name(
        node: tree_sitter.Node, content: bytes
    ) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return content[
                name_node.start_byte:name_node.end_byte
            ].decode("utf-8", errors="replace")
        return "<anonymous>"

    @staticmethod
    def _count_direct(
        node: tree_sitter.Node, types: frozenset[str]
    ) -> int:
        count = 0
        for child in node.children:
            if child.type in types:
                count += 1
        return count
