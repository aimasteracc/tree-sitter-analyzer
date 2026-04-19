"""Unclosed File Analyzer.

Detects open() calls not wrapped in a with statement, which can cause
file handle leaks. Files opened without `with` should be explicitly
closed, but this is error-prone and should use context managers instead.
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


@dataclass(frozen=True)
class UnclosedFileHotspot:
    """An open() call not in a with statement."""

    line_number: int
    variable: str
    severity: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "variable": self.variable,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class UnclosedFileResult:
    """Aggregated unclosed file analysis result."""

    total_hotspots: int
    hotspots: tuple[UnclosedFileHotspot, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_hotspots": self.total_hotspots,
            "hotspots": [h.to_dict() for h in self.hotspots],
            "file_path": self.file_path,
        }


class UnclosedFileAnalyzer(BaseAnalyzer):
    """Detects open() calls not wrapped in a with statement."""

    SUPPORTED_EXTENSIONS: set[str] = {".py"}

    def analyze_file(self, file_path: Path | str) -> UnclosedFileResult:
        path = Path(file_path)
        if not path.exists():
            return UnclosedFileResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return UnclosedFileResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> UnclosedFileResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return UnclosedFileResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        hotspots: list[UnclosedFileHotspot] = []

        self._walk(tree.root_node, content, hotspots)

        return UnclosedFileResult(
            total_hotspots=len(hotspots),
            hotspots=tuple(hotspots),
            file_path=str(path),
        )

    def _walk(
        self,
        node: tree_sitter.Node,
        content: bytes,
        hotspots: list[UnclosedFileHotspot],
    ) -> None:
        if node.type == "with_statement":
            return

        if node.type == "assignment":
            self._check_assignment(node, content, hotspots)

        for child in node.children:
            self._walk(child, content, hotspots)

    def _check_assignment(
        self,
        node: tree_sitter.Node,
        content: bytes,
        hotspots: list[UnclosedFileHotspot],
    ) -> None:
        right = node.child_by_field_name("right")
        if right is None or right.type != "call":
            return

        func = right.child_by_field_name("function")
        if func is None or func.type != "identifier":
            return

        func_name = content[
            func.start_byte:func.end_byte
        ].decode("utf-8", errors="replace")
        if func_name != "open":
            return

        left = node.child_by_field_name("left")
        if left is None:
            return

        var_name = content[
            left.start_byte:left.end_byte
        ].decode("utf-8", errors="replace")

        hotspots.append(
            UnclosedFileHotspot(
                line_number=node.start_point[0] + 1,
                variable=var_name,
                severity=SEVERITY_MEDIUM,
            )
        )
