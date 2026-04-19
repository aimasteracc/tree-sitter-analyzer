"""Duplicate Condition Analyzer.

Detects identical if conditions that appear multiple times in the same
file, indicating DRY violations that should be extracted into shared
variables or helper functions.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

_CONDITION_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"if_statement", "elif_clause"}),
    ".js": frozenset({"if_statement"}),
    ".jsx": frozenset({"if_statement"}),
    ".ts": frozenset({"if_statement"}),
    ".tsx": frozenset({"if_statement"}),
    ".java": frozenset({"if_statement"}),
    ".go": frozenset({"if_statement"}),
}

_WHITESPACE_RE = re.compile(r"\s+")

def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip())

@dataclass(frozen=True)
class DuplicateCondition:
    """A condition that appears multiple times."""

    condition: str
    occurrences: tuple[int, ...]
    count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "condition": self.condition,
            "occurrences": self.occurrences,
            "count": self.count,
        }

@dataclass(frozen=True)
class DuplicateConditionResult:
    """Aggregated duplicate condition analysis result."""

    total_conditions: int
    unique_conditions: int
    duplicates: tuple[DuplicateCondition, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_conditions": self.total_conditions,
            "unique_conditions": self.unique_conditions,
            "duplicate_count": len(self.duplicates),
            "duplicates": [d.to_dict() for d in self.duplicates],
            "file_path": self.file_path,
        }

class DuplicateConditionAnalyzer(BaseAnalyzer):
    """Analyzes duplicate if conditions in source code."""

    def analyze_file(self, file_path: Path | str) -> DuplicateConditionResult:
        path = Path(file_path)
        if not path.exists():
            return DuplicateConditionResult(
                total_conditions=0,
                unique_conditions=0,
                duplicates=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return DuplicateConditionResult(
                total_conditions=0,
                unique_conditions=0,
                duplicates=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> DuplicateConditionResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return DuplicateConditionResult(
                total_conditions=0,
                unique_conditions=0,
                duplicates=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        cond_types = _CONDITION_NODE_TYPES.get(ext, frozenset())

        condition_map: dict[str, list[int]] = defaultdict(list)

        def visit(node: tree_sitter.Node) -> None:
            if node.type in cond_types:
                cond_node = node.child_by_field_name("condition")
                if cond_node is None:
                    cond_node = self._extract_condition_node(node, ext)
                if cond_node is not None:
                    cond_text = content[
                        cond_node.start_byte:cond_node.end_byte
                    ].decode("utf-8", errors="replace")
                    normalized = _normalize(cond_text)
                    line = cond_node.start_point[0] + 1
                    condition_map[normalized].append(line)

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        total = sum(len(v) for v in condition_map.values())
        unique = len(condition_map)

        duplicates: list[DuplicateCondition] = []
        for cond, lines in condition_map.items():
            if len(lines) >= 2:
                duplicates.append(
                    DuplicateCondition(
                        condition=cond,
                        occurrences=tuple(lines),
                        count=len(lines),
                    )
                )

        duplicates.sort(key=lambda d: d.count, reverse=True)

        return DuplicateConditionResult(
            total_conditions=total,
            unique_conditions=unique,
            duplicates=tuple(duplicates),
            file_path=str(path),
        )

    @staticmethod
    def _extract_condition_node(
        node: tree_sitter.Node, ext: str
    ) -> tree_sitter.Node | None:
        if ext == ".go":
            for child in node.children:
                if child.type not in ("if", "for"):
                    return child
        if ext == ".java":
            paren = node.child_by_field_name("parenthesized_condition")
            if paren is not None:
                for child in paren.children:
                    if child.type != "(":
                        return child
        return None
