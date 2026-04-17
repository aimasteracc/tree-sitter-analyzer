"""
Structural Analysis Module

Provides multi-feature scoring for wrapper detection based on AST structure.
This analyzes how node types are actually used in real code samples.

Based on phase3-feasibility-report.md analysis.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from tree_sitter import Language, Node


@dataclass
class ChildTypeInfo:
    """Information about a child node type."""

    node_type: str
    count: int
    is_field: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_type": self.node_type,
            "count": self.count,
            "is_field": self.is_field,
        }


@dataclass
class StructuralAnalysis:
    """Result of structural analysis for a node type."""

    node_type: str
    total_occurrences: int
    child_types: list[ChildTypeInfo]
    field_usage: dict[str, int]
    avg_children_per_occurrence: float
    has_definition_field: bool
    has_decorator_field: bool
    distinct_child_types: int
    wrapper_score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_type": self.node_type,
            "total_occurrences": self.total_occurrences,
            "child_types": [ct.to_dict() for ct in self.child_types],
            "field_usage": self.field_usage,
            "avg_children_per_occurrence": self.avg_children_per_occurrence,
            "has_definition_field": self.has_definition_field,
            "has_decorator_field": self.has_decorator_field,
            "distinct_child_types": self.distinct_child_types,
            "wrapper_score": self.wrapper_score,
        }


class StructuralAnalyzer:
    """
    Analyzes AST structure to identify wrapper node types.

    Uses multi-feature scoring based on:
    - Field usage (definition, decorator)
    - Child type diversity
    - Average children count
    - Name pattern matching
    """

    def __init__(self, language: Language) -> None:
        """Initialize the analyzer with a tree-sitter Language."""
        self._language = language

    def analyze_code_sample(
        self,
        root_node: Node,
    ) -> dict[str, StructuralAnalysis]:
        """
        Analyze a code sample's AST structure.

        Args:
            root_node: The root node of the parsed code

        Returns:
            Dictionary mapping node type names to StructuralAnalysis objects.
        """
        # Collect statistics for each node type
        stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "occurrences": 0,
            "child_types": Counter[str](),
            "field_usage": Counter[str](),
            "children_counts": [],
        })

        def traverse(node: Node, depth: int = 0) -> None:
            if depth > 100:  # Prevent infinite recursion
                return

            node_type = node.type
            stats[node_type]["occurrences"] += 1
            stats[node_type]["children_counts"].append(
                sum(1 for _ in node.children)
            )

            # Analyze children
            for child in node.children:
                child_type = child.type
                stats[node_type]["child_types"][child_type] += 1

                # Check if child is a named field
                if child.is_named:
                    for field_name in self._get_field_names(node):
                        stats[node_type]["field_usage"][field_name] += 1
                        break

                traverse(child, depth + 1)

        traverse(root_node)

        # Convert stats to StructuralAnalysis objects with scoring
        results = {}
        for node_type, data in stats.items():
            child_types_list = [
                ChildTypeInfo(
                    node_type=ct,
                    count=count,
                    is_field=False,
                )
                for ct, count in data["child_types"].most_common(10)
            ]

            avg_children = (
                sum(data["children_counts"]) / len(data["children_counts"])
                if data["children_counts"]
                else 0
            )

            # Calculate wrapper score (multi-feature)
            wrapper_score = self._calculate_wrapper_score(
                node_type=node_type,
                field_usage=dict(data["field_usage"]),
                child_types=data["child_types"],
                avg_children=avg_children,
            )

            results[node_type] = StructuralAnalysis(
                node_type=node_type,
                total_occurrences=data["occurrences"],
                child_types=child_types_list,
                field_usage=dict(data["field_usage"]),
                avg_children_per_occurrence=avg_children,
                has_definition_field="definition" in data["field_usage"],
                has_decorator_field="decorator" in data["field_usage"],
                distinct_child_types=len(data["child_types"]),
                wrapper_score=wrapper_score,
            )

        return results

    def _get_field_names(self, node: Node) -> list[str]:
        """Get field names for a node's children."""
        field_names: list[str] = []
        # Tree-sitter doesn't expose field names per child via Python API
        # This is a simplified version
        return field_names

    def _calculate_wrapper_score(
        self,
        node_type: str,
        field_usage: dict[str, int],
        child_types: Counter[str],
        avg_children: float,
    ) -> int:
        """
        Calculate wrapper score using multi-feature scoring.

        Scoring formula from phase3-feasibility-report.md:
        score = 30*has_definition_field
              + 30*has_decorator_field
              + 20*len(child_types) >= 2
              + 10*avg_children >= 2
              + 10*matches_name_pattern
        """
        score = 0

        # Feature 1: Has 'definition' field (30 points)
        if "definition" in field_usage:
            score += 30

        # Feature 2: Has 'decorator' field (30 points)
        if "decorator" in field_usage:
            score += 30

        # Feature 3: Multiple child types (20 points if >= 2)
        if len(child_types) >= 2:
            score += 20

        # Feature 4: Average children >= 2 (10 points)
        if avg_children >= 2:
            score += 10

        # Feature 5: Name pattern matching (10 points)
        if any(
            node_type.startswith(p) or node_type.endswith(p)
            for p in ["decorated_", "with_", "annotated_"]
        ):
            score += 10

        return score

    def detect_wrappers(
        self,
        code_samples: list[Node],
        min_confidence: int = 50,
    ) -> list[StructuralAnalysis]:
        """
        Detect wrapper node types across multiple code samples.

        Args:
            code_samples: List of root nodes from parsed code samples
            min_confidence: Minimum wrapper score to consider as wrapper

        Returns:
            List of StructuralAnalysis objects for detected wrappers.
        """
        # Combine analysis from all samples
        combined_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "occurrences": 0,
            "child_types": Counter[str](),
            "field_usage": Counter[str](),
            "children_counts": [],
            "samples": 0,
        })

        for root_node in code_samples:
            analysis = self.analyze_code_sample(root_node)

            for node_type, struct in analysis.items():
                stats = combined_stats[node_type]
                stats["occurrences"] += struct.total_occurrences
                stats["child_types"].update(
                    ct.node_type for ct in struct.child_types
                )
                stats["field_usage"].update(struct.field_usage)
                stats["children_counts"].extend(
                    [struct.avg_children_per_occurrence] * struct.total_occurrences
                )
                stats["samples"] += 1

        # Calculate final wrapper scores and filter by confidence
        wrappers = []
        for node_type, data in combined_stats.items():
            avg_children = (
                sum(data["children_counts"]) / len(data["children_counts"])
                if data["children_counts"]
                else 0
            )

            wrapper_score = self._calculate_wrapper_score(
                node_type=node_type,
                field_usage=dict(data["field_usage"]),
                child_types=data["child_types"],
                avg_children=avg_children,
            )

            if wrapper_score >= min_confidence:
                child_types_list = [
                    ChildTypeInfo(
                        node_type=ct,
                        count=count,
                        is_field=False,
                    )
                    for ct, count in data["child_types"].most_common(10)
                ]

                wrappers.append(
                    StructuralAnalysis(
                        node_type=node_type,
                        total_occurrences=data["occurrences"],
                        child_types=child_types_list,
                        field_usage=dict(data["field_usage"]),
                        avg_children_per_occurrence=avg_children,
                        has_definition_field="definition" in data["field_usage"],
                        has_decorator_field="decorator" in data["field_usage"],
                        distinct_child_types=len(data["child_types"]),
                        wrapper_score=wrapper_score,
                    )
                )

        # Sort by wrapper score descending
        return sorted(wrappers, key=lambda w: w.wrapper_score, reverse=True)
