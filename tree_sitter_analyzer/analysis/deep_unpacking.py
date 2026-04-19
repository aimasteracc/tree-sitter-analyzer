"""Deep Unpacking Analyzer.

Detects excessive tuple unpacking where too many variables are assigned
from a single iterable. This reduces readability and risks silent failures
if the number of elements doesn't match (Python raises ValueError).

Common threshold: 4+ variables in a single unpacking.
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
DEFAULT_THRESHOLD = 4


@dataclass(frozen=True)
class DeepUnpackingHotspot:
    """An excessive tuple unpacking."""

    line_number: int
    variable_count: int
    severity: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "variable_count": self.variable_count,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class DeepUnpackingResult:
    """Aggregated deep unpacking analysis result."""

    total_hotspots: int
    hotspots: tuple[DeepUnpackingHotspot, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_hotspots": self.total_hotspots,
            "hotspots": [h.to_dict() for h in self.hotspots],
            "file_path": self.file_path,
        }


class DeepUnpackingAnalyzer(BaseAnalyzer):
    """Detects excessive tuple unpacking (too many variables from one iterable)."""

    SUPPORTED_EXTENSIONS: set[str] = {".py"}

    def analyze_file(self, file_path: Path | str) -> DeepUnpackingResult:
        path = Path(file_path)
        if not path.exists():
            return DeepUnpackingResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return DeepUnpackingResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> DeepUnpackingResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return DeepUnpackingResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        hotspots: list[DeepUnpackingHotspot] = []
        self._walk(tree.root_node, content, hotspots)

        return DeepUnpackingResult(
            total_hotspots=len(hotspots),
            hotspots=tuple(hotspots),
            file_path=str(path),
        )

    def _walk(
        self,
        node: tree_sitter.Node,
        content: bytes,
        hotspots: list[DeepUnpackingHotspot],
    ) -> None:
        if node.type == "assignment":
            self._check_assignment(node, content, hotspots)
        elif node.type == "for_statement":
            self._check_for_unpacking(node, content, hotspots)

        for child in node.children:
            self._walk(child, content, hotspots)

    def _check_assignment(
        self,
        node: tree_sitter.Node,
        content: bytes,
        hotspots: list[DeepUnpackingHotspot],
    ) -> None:
        left = node.child_by_field_name("left")
        if left is None:
            return

        count = self._count_unpack_targets(left)
        if count >= DEFAULT_THRESHOLD:
            hotspots.append(
                DeepUnpackingHotspot(
                    line_number=node.start_point[0] + 1,
                    variable_count=count,
                    severity=SEVERITY_HIGH if count >= 6 else SEVERITY_MEDIUM,
                )
            )

    def _check_for_unpacking(
        self,
        node: tree_sitter.Node,
        content: bytes,
        hotspots: list[DeepUnpackingHotspot],
    ) -> None:
        left = node.child_by_field_name("left")
        if left is None:
            for child in node.children:
                if child.type in ("pattern", "tuple_pattern", "identifier"):
                    left = child
                    break

        if left is None:
            return

        count = self._count_unpack_targets(left)
        if count >= DEFAULT_THRESHOLD:
            hotspots.append(
                DeepUnpackingHotspot(
                    line_number=node.start_point[0] + 1,
                    variable_count=count,
                    severity=SEVERITY_HIGH if count >= 6 else SEVERITY_MEDIUM,
                )
            )

    def _count_unpack_targets(self, node: tree_sitter.Node) -> int:
        if node.type == "tuple_pattern":
            count = 0
            for child in node.children:
                if child.type not in (",", "(", ")"):
                    count += 1
            return count

        if node.type == "pattern_list":
            count = 0
            for child in node.children:
                if child.type not in (",",):
                    count += 1
            return count

        return 0
