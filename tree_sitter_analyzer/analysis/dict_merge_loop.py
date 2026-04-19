"""Dict Merge in Loop Analyzer.

Detects dict key assignment inside loops that should use dict.update()
or dict comprehension for better performance. Each d[key] = value
inside a loop is a Python-level operation, while dict.update() is
a single C-level bulk operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"


def _severity(loop_depth: int) -> str:
    if loop_depth >= 2:
        return SEVERITY_HIGH
    if loop_depth == 1:
        return SEVERITY_MEDIUM
    return SEVERITY_LOW


@dataclass(frozen=True)
class DictMergeHotspot:
    """A dict key assignment inside a loop."""

    line_number: int
    loop_type: str
    dict_variable: str
    severity: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "loop_type": self.loop_type,
            "dict_variable": self.dict_variable,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class DictMergeLoopResult:
    """Aggregated dict merge in loop analysis result."""

    total_hotspots: int
    hotspots: tuple[DictMergeHotspot, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_hotspots": self.total_hotspots,
            "hotspots": [h.to_dict() for h in self.hotspots],
            "file_path": self.file_path,
        }


_LOOP_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"for_statement", "while_statement"}),
}


class DictMergeLoopAnalyzer(BaseAnalyzer):
    """Detects dict key assignment in loops that should use update()."""

    SUPPORTED_EXTENSIONS: set[str] = {".py"}

    def analyze_file(self, file_path: Path | str) -> DictMergeLoopResult:
        path = Path(file_path)
        if not path.exists():
            return DictMergeLoopResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return DictMergeLoopResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> DictMergeLoopResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return DictMergeLoopResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        hotspots: list[DictMergeHotspot] = []
        loop_types = _LOOP_TYPES.get(ext, frozenset())

        def find_loops(
            node: tree_sitter.Node, depth: int
        ) -> list[tuple[tree_sitter.Node, int]]:
            result: list[tuple[tree_sitter.Node, int]] = []
            if node.type in loop_types:
                result.append((node, depth))
                for child in node.children:
                    result.extend(find_loops(child, depth + 1))
            else:
                for child in node.children:
                    result.extend(find_loops(child, depth))
            return result

        loops = find_loops(tree.root_node, 0)

        for loop_node, loop_depth in loops:
            self._find_dict_assigns(
                loop_node, content, loop_depth, hotspots
            )

        return DictMergeLoopResult(
            total_hotspots=len(hotspots),
            hotspots=tuple(hotspots),
            file_path=str(path),
        )

    def _find_dict_assigns(
        self,
        loop_node: tree_sitter.Node,
        content: bytes,
        loop_depth: int,
        hotspots: list[DictMergeHotspot],
    ) -> None:
        loop_type_name = loop_node.type.replace("_statement", "")

        def visit(node: tree_sitter.Node) -> None:
            if node.type in _LOOP_TYPES.get(".py", frozenset()):
                return

            if node.type == "assignment":
                left = node.child_by_field_name("left")
                if left is not None and left.type == "subscript":
                    value_node = left.child_by_field_name("value")
                    if value_node is not None:
                        dict_var = content[
                            value_node.start_byte:value_node.end_byte
                        ].decode("utf-8", errors="replace")
                        hotspots.append(
                            DictMergeHotspot(
                                line_number=node.start_point[0] + 1,
                                loop_type=loop_type_name,
                                dict_variable=dict_var,
                                severity=_severity(loop_depth + 1),
                            )
                        )

            for child in node.children:
                visit(child)

        for child in loop_node.children:
            visit(child)
