"""
Grammar Introspection Module

Provides runtime introspection of tree-sitter grammars using the Language API.
This allows automatic discovery of node types, fields, and wrapper patterns
without manually maintaining configuration files.

Based on phase3-feasibility-report.md analysis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter import Language


@dataclass(frozen=True)
class NodeTypeInfo:
    """Information about a tree-sitter node type."""

    kind_id: int
    kind_name: str
    is_named: bool = True
    is_visible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind_id": self.kind_id,
            "kind_name": self.kind_name,
            "is_named": self.is_named,
            "is_visible": self.is_visible,
        }


@dataclass(frozen=True)
class FieldInfo:
    """Information about a tree-sitter field."""

    field_id: int
    field_name: str
    is_multiple: bool = False
    is_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "field_name": self.field_name,
            "is_multiple": self.is_multiple,
            "is_required": self.is_required,
        }


@dataclass(frozen=True)
class WrapperCandidate:
    """A potential wrapper node type with confidence score."""

    node_type: str
    confidence: int
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_type": self.node_type,
            "confidence": self.confidence,
            "reasons": self.reasons,
        }


class GrammarIntrospector:
    """
    Runtime introspection of tree-sitter grammars.

    Uses tree-sitter's Language API to enumerate node types, fields, and
    detect wrapper patterns through heuristic analysis.

    Example:
        >>> lang = Language(tree_sitter_python.language())
        >>> intro = GrammarIntrospector(lang)
        >>> node_types = intro.enumerate_node_types()
        >>> wrappers = intro.heuristic_wrapper_detection()
    """

    # Common wrapper name patterns (suffixes/prefixes indicating wrapper nodes)
    WRAPPER_PATTERNS = [
        "decorated_",
        "with_",
        "annotated_",
        "wrapped_",
        "scoped_",
        "aliased_",
    ]

    # Node types that are definitively NOT wrappers
    NON_WRAPPER_TYPES = {
        "identifier",
        "string",
        "number",
        "comment",
        "terminal",
        "lexical",
    }

    def __init__(self, language: Language) -> None:
        """Initialize the introspector with a tree-sitter Language."""
        self._language = language

    def enumerate_node_types(self) -> list[NodeTypeInfo]:
        """
        Enumerate all node types in the grammar.

        Returns:
            List of NodeTypeInfo objects for all node types in the grammar.
        """
        node_count = self._language.node_kind_count
        node_types = []

        for i in range(node_count):
            kind_name = self._language.node_kind_for_id(i)
            if kind_name is None:
                continue
            is_named = self._language.node_kind_is_named(i)

            # Assume visible by default (node_kind_is_visible_not_supported in most)
            is_visible = True

            node_types.append(
                NodeTypeInfo(
                    kind_id=i,
                    kind_name=kind_name,
                    is_named=is_named,
                    is_visible=is_visible,
                )
            )

        return node_types

    def enumerate_fields(self) -> list[FieldInfo]:
        """
        Enumerate all fields in the grammar.

        Returns:
            List of FieldInfo objects for all fields in the grammar.
        """
        field_count = self._language.field_count
        fields = []

        for i in range(field_count):
            field_name = self._language.field_name_for_id(i)
            if field_name is None:
                continue

            fields.append(
                FieldInfo(
                    field_id=i,
                    field_name=field_name,
                    is_multiple=False,  # Tree-sitter doesn't expose this via API
                    is_required=True,  # Default to True (no API to check)
                )
            )

        return fields

    def heuristic_wrapper_detection(
        self,
        node_types: list[NodeTypeInfo] | None = None,
    ) -> list[WrapperCandidate]:
        """
        Detect potential wrapper node types using heuristic patterns.

        This uses name-based heuristics to identify nodes that are likely
        wrappers (nodes that contain other nodes as children).

        Args:
            node_types: Optional list of node types (will enumerate if not provided)

        Returns:
            List of WrapperCandidate objects with confidence scores.
        """
        if node_types is None:
            node_types = self.enumerate_node_types()

        candidates = []

        for node_type in node_types:
            kind_name = node_type.kind_name

            # Skip obvious non-wrappers
            if kind_name in self.NON_WRAPPER_TYPES:
                continue

            # Score based on name patterns
            score = 0
            reasons = []

            for pattern in self.WRAPPER_PATTERNS:
                if kind_name.startswith(pattern) or kind_name.endswith(pattern):
                    score += 50
                    reasons.append(f"Matches wrapper pattern: {pattern}")
                    break

            # Additional heuristics based on node type naming
            if "_" in kind_name:
                parts = kind_name.split("_")
                if any(p in parts for p in ["definition", "declaration", "statement"]):
                    score += 10
                    reasons.append("Contains definition/declaration keyword")

            # Add as candidate if score > 0
            if score > 0:
                candidates.append(
                    WrapperCandidate(
                        node_type=kind_name,
                        confidence=score,
                        reasons=reasons,
                    )
                )

        # Sort by confidence descending
        return sorted(candidates, key=lambda c: c.confidence, reverse=True)

    def get_node_type_id(self, kind_name: str) -> int | None:
        """
        Get the node type ID for a given kind name.

        Args:
            kind_name: The name of the node type (e.g., "function_definition")

        Returns:
            The node type ID, or None if not found.
        """
        # Tree-sitter doesn't provide a direct name->id lookup
        # We need to iterate through all types
        node_count = self._language.node_kind_count
        for i in range(node_count):
            if self._language.node_kind_for_id(i) == kind_name:
                return i
        return None

    def get_field_id(self, field_name: str) -> int | None:
        """
        Get the field ID for a given field name.

        Args:
            field_name: The name of the field (e.g., "name", "body")

        Returns:
            The field ID, or None if not found.
        """
        field_count = self._language.field_count
        for i in range(field_count):
            if self._language.field_name_for_id(i) == field_name:
                return i
        return None

    def get_summary(self) -> dict[str, Any]:
        """
        Get a summary of the grammar.

        Returns:
            Dictionary with grammar statistics.
        """
        node_types = self.enumerate_node_types()
        fields = self.enumerate_fields()
        wrappers = self.heuristic_wrapper_detection(node_types)

        named_count = sum(1 for nt in node_types if nt.is_named)
        anonymous_count = len(node_types) - named_count

        return {
            "total_node_types": len(node_types),
            "named_node_types": named_count,
            "anonymous_node_types": anonymous_count,
            "total_fields": len(fields),
            "wrapper_candidates": len(wrappers),
            "high_confidence_wrappers": sum(1 for w in wrappers if w.confidence >= 50),
        }
