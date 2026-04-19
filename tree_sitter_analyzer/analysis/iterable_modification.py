"""Iterable Modification in Loop Analyzer.

Detects modification of a collection (list/dict/set) while iterating
over it, which causes RuntimeError in Python or silently skips elements.
Common patterns: list.remove(), list.append(), list.insert(),
dict.pop(), set.add(), set.discard() on the iterated collection.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"


_MODIFYING_METHODS: frozenset[bytes] = frozenset({
    b"append", b"extend", b"insert", b"remove",
    b"pop", b"clear", b"add", b"discard",
    b"update", b"setdefault", b"del",
})

_MODIFYING_OPS: frozenset[str] = frozenset({
    "augmented_assignment",
})


@dataclass(frozen=True)
class IterModHotspot:
    """A collection modification while iterating over it."""

    line_number: int
    loop_variable: str
    method_name: str
    severity: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "loop_variable": self.loop_variable,
            "method_name": self.method_name,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class IterableModificationResult:
    """Aggregated iterable modification analysis result."""

    total_hotspots: int
    hotspots: tuple[IterModHotspot, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_hotspots": self.total_hotspots,
            "hotspots": [h.to_dict() for h in self.hotspots],
            "file_path": self.file_path,
        }


class IterableModificationAnalyzer(BaseAnalyzer):
    """Detects collection modification while iterating over it."""

    SUPPORTED_EXTENSIONS: set[str] = {".py"}

    def analyze_file(self, file_path: Path | str) -> IterableModificationResult:
        path = Path(file_path)
        if not path.exists():
            return IterableModificationResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return IterableModificationResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> IterableModificationResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return IterableModificationResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        hotspots: list[IterModHotspot] = []

        self._walk(tree.root_node, content, hotspots)

        return IterableModificationResult(
            total_hotspots=len(hotspots),
            hotspots=tuple(hotspots),
            file_path=str(path),
        )

    def _walk(
        self,
        node: tree_sitter.Node,
        content: bytes,
        hotspots: list[IterModHotspot],
    ) -> None:
        if node.type == "for_statement":
            self._check_for_loop(node, content, hotspots)

        for child in node.children:
            self._walk(child, content, hotspots)

    def _check_for_loop(
        self,
        for_node: tree_sitter.Node,
        content: bytes,
        hotspots: list[IterModHotspot],
    ) -> None:
        iter_var = self._get_iter_target(for_node, content)
        if iter_var is None:
            return

        body = for_node.child_by_field_name("body")
        if body is None:
            return

        self._scan_body(body, iter_var, content, hotspots)

    def _get_iter_target(
        self, for_node: tree_sitter.Node, content: bytes
    ) -> str | None:
        """Extract the collection being iterated from `for x in items`."""
        right = for_node.child_by_field_name("right")
        if right is None:
            return None

        if right.type == "identifier":
            return content[
                right.start_byte:right.end_byte
            ].decode("utf-8", errors="replace")

        if right.type == "call":
            func = right.child_by_field_name("function")
            if func is not None and func.type == "attribute":
                obj = func.child_by_field_name("object")
                if obj is not None and obj.type == "identifier":
                    return content[
                        obj.start_byte:obj.end_byte
                    ].decode("utf-8", errors="replace")

        return None

    def _scan_body(
        self,
        body: tree_sitter.Node,
        iter_var: str,
        content: bytes,
        hotspots: list[IterModHotspot],
    ) -> None:
        def visit(node: tree_sitter.Node) -> None:
            if node.type == "for_statement":
                return

            if node.type == "call":
                func = node.child_by_field_name("function")
                if func is not None and func.type == "attribute":
                    obj = func.child_by_field_name("object")
                    attr = func.child_by_field_name("attribute")
                    if (
                        obj is not None
                        and obj.type == "identifier"
                        and attr is not None
                    ):
                        obj_name = content[
                            obj.start_byte:obj.end_byte
                        ].decode("utf-8", errors="replace")
                        method_name = content[
                            attr.start_byte:attr.end_byte
                        ].decode("utf-8", errors="replace")
                        if (
                            obj_name == iter_var
                            and method_name.encode() in _MODIFYING_METHODS
                        ):
                            hotspots.append(
                                IterModHotspot(
                                    line_number=node.start_point[0] + 1,
                                    loop_variable=iter_var,
                                    method_name=method_name,
                                    severity=SEVERITY_MEDIUM,
                                )
                            )

            if node.type == "delete_statement":
                for child in node.children:
                    if child.type == "subscript":
                        value = child.child_by_field_name("value")
                        if value is not None and value.type == "identifier":
                            obj_name = content[
                                value.start_byte:value.end_byte
                            ].decode("utf-8", errors="replace")
                            if obj_name == iter_var:
                                hotspots.append(
                                    IterModHotspot(
                                        line_number=node.start_point[0] + 1,
                                        loop_variable=iter_var,
                                        method_name="del",
                                        severity=SEVERITY_HIGH,
                                    )
                                )

            for child in node.children:
                visit(child)

        for child in body.children:
            visit(child)
