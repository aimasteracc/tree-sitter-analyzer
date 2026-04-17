"""
Unit tests for GrammarIntrospector.

Tests runtime introspection of tree-sitter grammars using the Language API.
"""
from __future__ import annotations

import pytest
from tree_sitter import Language
from tree_sitter_python import language

from tree_sitter_analyzer.grammar_discovery.introspector import (
    FieldInfo,
    GrammarIntrospector,
    NodeTypeInfo,
    WrapperCandidate,
)


@pytest.fixture
def python_language() -> Language:
    """Get Python tree-sitter language for testing."""
    return Language(language())


@pytest.fixture
def introspector(python_language: Language) -> GrammarIntrospector:
    """Get GrammarIntrospector instance for testing."""
    return GrammarIntrospector(python_language)


class TestNodeTypeInfo:
    """Test NodeTypeInfo dataclass."""

    def test_to_dict(self) -> None:
        """Test NodeTypeInfo serialization."""
        info = NodeTypeInfo(
            kind_id=1,
            kind_name="function_definition",
            is_named=True,
            is_visible=True,
        )
        result = info.to_dict()
        assert result == {
            "kind_id": 1,
            "kind_name": "function_definition",
            "is_named": True,
            "is_visible": True,
        }


class TestFieldInfo:
    """Test FieldInfo dataclass."""

    def test_to_dict(self) -> None:
        """Test FieldInfo serialization."""
        info = FieldInfo(
            field_id=0,
            field_name="name",
            is_multiple=False,
            is_required=True,
        )
        result = info.to_dict()
        assert result == {
            "field_id": 0,
            "field_name": "name",
            "is_multiple": False,
            "is_required": True,
        }


class TestWrapperCandidate:
    """Test WrapperCandidate dataclass."""

    def test_to_dict(self) -> None:
        """Test WrapperCandidate serialization."""
        candidate = WrapperCandidate(
            node_type="decorated_definition",
            confidence=50,
            reasons=["Matches wrapper pattern: decorated_"],
        )
        result = candidate.to_dict()
        assert result == {
            "node_type": "decorated_definition",
            "confidence": 50,
            "reasons": ["Matches wrapper pattern: decorated_"],
        }


class TestGrammarIntrospector:
    """Test GrammarIntrospector class."""

    def test_enumerate_node_types_returns_list(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that enumerate_node_types returns a list."""
        node_types = introspector.enumerate_node_types()
        assert isinstance(node_types, list)

    def test_enumerate_node_types_contains_named_types(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that enumerated node types include common Python types."""
        node_types = introspector.enumerate_node_types()
        kind_names = [nt.kind_name for nt in node_types]

        # Check for common Python node types
        assert "function_definition" in kind_names
        assert "class_definition" in kind_names
        assert "identifier" in kind_names

    def test_enumerate_node_types_count_reasonable(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that Python grammar has reasonable number of node types."""
        node_types = introspector.enumerate_node_types()
        # Python grammar typically has 200-300 node types
        assert 200 <= len(node_types) <= 300

    def test_enumerate_node_types_all_have_ids(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that all node types have valid kind_id values."""
        node_types = introspector.enumerate_node_types()
        for nt in node_types:
            assert nt.kind_id >= 0
            assert isinstance(nt.kind_name, str)
            assert len(nt.kind_name) > 0

    def test_enumerate_fields_returns_list(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that enumerate_fields returns a list."""
        fields = introspector.enumerate_fields()
        assert isinstance(fields, list)

    def test_enumerate_fields_contains_common_fields(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that enumerated fields include common field names."""
        fields = introspector.enumerate_fields()
        field_names = [f.field_name for f in fields]

        # Check for common fields
        assert "name" in field_names
        assert "body" in field_names
        assert "parameters" in field_names

    def test_enumerate_fields_count_reasonable(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that Python grammar has reasonable number of fields."""
        fields = introspector.enumerate_fields()
        # Python grammar typically has 20-40 fields
        assert 20 <= len(fields) <= 40

    def test_heuristic_wrapper_detection_returns_list(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that heuristic_wrapper_detection returns a list."""
        wrappers = introspector.heuristic_wrapper_detection()
        assert isinstance(wrappers, list)

    def test_heuristic_wrapper_detection_finds_decorated_definition(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that decorated_definition is detected as wrapper."""
        wrappers = introspector.heuristic_wrapper_detection()
        wrapper_names = [w.node_type for w in wrappers]

        assert "decorated_definition" in wrapper_names

    def test_heuristic_wrapper_detection_sorted_by_confidence(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that wrappers are sorted by confidence descending."""
        wrappers = introspector.heuristic_wrapper_detection()

        for i in range(len(wrappers) - 1):
            assert wrappers[i].confidence >= wrappers[i + 1].confidence

    def test_heuristic_wrapper_detection_skips_non_wrappers(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that obvious non-wrappers are skipped."""
        wrappers = introspector.heuristic_wrapper_detection()
        wrapper_names = [w.node_type for w in wrappers]

        # These should not be detected as wrappers
        assert "identifier" not in wrapper_names
        assert "string" not in wrapper_names
        assert "comment" not in wrapper_names

    def test_heuristic_wrapper_detection_provides_reasons(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that wrapper candidates include detection reasons."""
        wrappers = introspector.heuristic_wrapper_detection()

        for wrapper in wrappers:
            if wrapper.confidence > 0:
                assert len(wrapper.reasons) > 0
                assert all(isinstance(r, str) for r in wrapper.reasons)

    def test_get_node_type_id_valid_type(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test get_node_type_id with a valid type name."""
        type_id = introspector.get_node_type_id("function_definition")
        assert type_id is not None
        assert type_id >= 0

    def test_get_node_type_id_invalid_type(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test get_node_type_id with an invalid type name."""
        type_id = introspector.get_node_type_id("nonexistent_type")
        assert type_id is None

    def test_get_field_id_valid_field(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test get_field_id with a valid field name."""
        field_id = introspector.get_field_id("name")
        assert field_id is not None
        assert field_id >= 0

    def test_get_field_id_invalid_field(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test get_field_id with an invalid field name."""
        field_id = introspector.get_field_id("nonexistent_field")
        assert field_id is None

    def test_get_summary_returns_dict(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that get_summary returns a dictionary."""
        summary = introspector.get_summary()
        assert isinstance(summary, dict)

    def test_get_summary_contains_expected_keys(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that get_summary contains all expected keys."""
        summary = introspector.get_summary()
        expected_keys = [
            "total_node_types",
            "named_node_types",
            "anonymous_node_types",
            "total_fields",
            "wrapper_candidates",
            "high_confidence_wrappers",
        ]
        for key in expected_keys:
            assert key in summary

    def test_get_summary_values_reasonable(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that get_summary values are reasonable."""
        summary = introspector.get_summary()

        assert summary["total_node_types"] > 0
        assert summary["total_fields"] > 0
        assert summary["named_node_types"] > 0
        assert summary["wrapper_candidates"] >= 0
        assert summary["high_confidence_wrappers"] >= 0
        assert summary["named_node_types"] <= summary["total_node_types"]
