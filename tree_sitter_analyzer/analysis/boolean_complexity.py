"""Boolean Complexity Analyzer.

Detects overly complex boolean expressions that are hard to reason about.
Counts conditions in boolean chains (&&/||/and/or) and flags expressions
with too many conditions, suggesting extraction into named variables.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

RATING_GOOD = "good"
RATING_WARNING = "warning"
RATING_CRITICAL = "critical"

def _rating(condition_count: int) -> str:
    if condition_count <= 3:
        return RATING_GOOD
    if condition_count == 4:
        return RATING_WARNING
    return RATING_CRITICAL

# C-style boolean operators (used inside binary_expression nodes)
_CSTYLE_BOOL_OPS: frozenset[str] = frozenset({
    "&&",
    "||",
})

# Supplements for extensions where knowledge is not yet available
_BOOL_SUPPLEMENT: dict[str, frozenset[str]] = {
    ".ts": frozenset({"binary_expression"}),
    ".tsx": frozenset({"binary_expression"}),
}

def _is_cstyle_bool(node: tree_sitter.Node) -> bool:
    """Check if a binary_expression uses a boolean operator."""
    if node.type != "binary_expression":
        return False
    return any(c.type in _CSTYLE_BOOL_OPS for c in node.children)

@dataclass(frozen=True)
class BooleanHotspot:
    """A complex boolean expression."""

    line_number: int
    condition_count: int
    expression: str

@dataclass(frozen=True)
class BooleanComplexityResult:
    """Aggregated boolean complexity result for a file."""

    max_conditions: int
    total_expressions: int
    hotspots: tuple[BooleanHotspot, ...]
    file_path: str

class BooleanComplexityAnalyzer(BaseAnalyzer):
    """Analyzes boolean expression complexity in source code."""

    def analyze_file(self, file_path: Path | str) -> BooleanComplexityResult:
        path = Path(file_path)
        if not path.exists():
            return BooleanComplexityResult(
                max_conditions=0,
                total_expressions=0,
                hotspots=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return BooleanComplexityResult(
                max_conditions=0,
                total_expressions=0,
                hotspots=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> BooleanComplexityResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return BooleanComplexityResult(
                max_conditions=0,
                total_expressions=0,
                hotspots=(),
                file_path=str(path),
            )

        knowledge = self._get_knowledge(ext)
        bool_ops = knowledge.boolean_operator_nodes
        if not bool_ops:
            bool_ops = _BOOL_SUPPLEMENT.get(ext, frozenset())

        content = path.read_bytes()
        tree = parser.parse(content)

        total = 0
        max_cond = 0
        hotspots: list[BooleanHotspot] = []

        def _is_bool_node(node: tree_sitter.Node) -> bool:
            if node.type == "boolean_operator":
                return True
            if node.type in bool_ops and node.type == "binary_expression":
                return _is_cstyle_bool(node)
            return False

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total, max_cond

            if _is_bool_node(node):
                count = self._count_conditions(node, ext)
                total += 1
                if count > max_cond:
                    max_cond = count
                if count >= 4:
                    text = content[
                        node.start_byte:node.end_byte
                    ].decode("utf-8", errors="replace")
                    if len(text) > 80:
                        text = text[:77] + "..."
                    hotspots.append(
                        BooleanHotspot(
                            line_number=node.start_point[0] + 1,
                            condition_count=count,
                            expression=text,
                        )
                    )

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return BooleanComplexityResult(
            max_conditions=max_cond,
            total_expressions=total,
            hotspots=tuple(hotspots),
            file_path=str(path),
        )

    def _count_conditions(
        self, node: tree_sitter.Node, ext: str
    ) -> int:
        """Count leaf conditions in a boolean expression tree."""
        is_bool = (
            node.type == "boolean_operator"
            if ext == ".py"
            else _is_cstyle_bool(node)
        )
        if not is_bool:
            return 1
        count = 0
        for child in node.children:
            if child.type in ("&&", "||", "and", "or"):
                continue
            count += self._count_conditions(child, ext)
        return count
