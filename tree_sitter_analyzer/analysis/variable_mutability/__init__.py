"""Variable mutability analysis — detects shadow, unused, const-reassign, loop-mutation."""
from __future__ import annotations

from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.analysis.variable_mutability._go import (
    GoMutabilityMixin,
)
from tree_sitter_analyzer.analysis.variable_mutability._java import (
    JavaMutabilityMixin,
)
from tree_sitter_analyzer.analysis.variable_mutability._javascript import (
    JavaScriptMutabilityMixin,
)
from tree_sitter_analyzer.analysis.variable_mutability._python import (
    PythonMutabilityMixin,
)
from tree_sitter_analyzer.analysis.variable_mutability._types import (
    MUTABILITY_LOOP_MUTATION,
    MUTABILITY_REASSIGNED_CONST,
    MUTABILITY_SHADOW,
    MUTABILITY_UNUSED,
    MutabilityIssue,
    MutabilityResult,
    _compute_score,
    _empty_result,
)
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

__all__ = [
    "MUTABILITY_SHADOW",
    "MUTABILITY_UNUSED",
    "MUTABILITY_REASSIGNED_CONST",
    "MUTABILITY_LOOP_MUTATION",
    "MutabilityIssue",
    "MutabilityResult",
    "VariableMutabilityAnalyzer",
]


class VariableMutabilityAnalyzer(
    PythonMutabilityMixin,
    JavaScriptMutabilityMixin,
    JavaMutabilityMixin,
    GoMutabilityMixin,
    BaseAnalyzer,
):
    """Analyzes variable mutability issues across Python, JS/TS, Java, Go."""

    def analyze_file(self, file_path: Path | str) -> MutabilityResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path))
        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return _empty_result(str(path))

        content = path.read_bytes()
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return _empty_result(str(path))

        tree = parser.parse(content)

        if ext == ".py":
            issues = self._analyze_python(tree.root_node, content)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            issues = self._analyze_javascript(tree.root_node, content)
        elif ext == ".java":
            issues = self._analyze_java(tree.root_node, content)
        elif ext == ".go":
            issues = self._analyze_go(tree.root_node, content)
        else:
            issues = []

        issue_counts: dict[str, int] = {}
        for iss in issues:
            issue_counts[iss.issue_type] = issue_counts.get(iss.issue_type, 0) + 1

        score = _compute_score(len(issues), issues)

        return MutabilityResult(
            file_path=str(path),
            issues=tuple(issues),
            total_issues=len(issues),
            quality_score=round(score, 1),
            issue_counts=issue_counts,
        )

    def _extract_identifiers(self, node: tree_sitter.Node) -> list[tree_sitter.Node]:
        results: list[tree_sitter.Node] = []
        if node.type == "identifier":
            results.append(node)
        elif node.type == "tuple":
            for child in node.children:
                results.extend(self._extract_identifiers(child))
        elif node.type == "pattern_list":
            for child in node.children:
                results.extend(self._extract_identifiers(child))
        elif node.type == "name":
            results.append(node)
        for child in node.children:
            if child.type == "identifier" and child not in results:
                results.append(child)
        return results
