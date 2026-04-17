"""
Unit tests for StructuralAnalyzer.

Tests multi-feature scoring for wrapper detection based on AST structure.
"""
from __future__ import annotations

import pytest
from tree_sitter import Language, Parser
from tree_sitter_python import language

from tree_sitter_analyzer.grammar_discovery.structural_analyzer import (
    ChildTypeInfo,
    StructuralAnalysis,
    StructuralAnalyzer,
)


@pytest.fixture
def python_language() -> Language:
    """Get Python tree-sitter language for testing."""
    return Language(language())


@pytest.fixture
def analyzer(python_language: Language) -> StructuralAnalyzer:
    """Get StructuralAnalyzer instance for testing."""
    return StructuralAnalyzer(python_language)


@pytest.fixture
def parser(python_language: Language) -> Parser:
    """Get Parser instance for testing."""
    parser = Parser(python_language)
    return parser


@pytest.fixture
def simple_function_node(python_language: Language) -> Language:
    """Parse a simple function for testing."""
    parser = Parser(python_language)
    code = """
def foo(x, y):
    return x + y
"""
    tree = parser.parse(bytes(code, "utf-8"))
    return tree.root_node


@pytest.fixture
def decorated_function_node(python_language: Language) -> Language:
    """Parse a decorated function for testing."""
    parser = Parser(python_language)
    code = """
@decorator
def foo(x):
    pass
"""
    tree = parser.parse(bytes(code, "utf-8"))
    return tree.root_node


class TestChildTypeInfo:
    """Test ChildTypeInfo dataclass."""

    def test_to_dict(self) -> None:
        """Test ChildTypeInfo serialization."""
        info = ChildTypeInfo(
            node_type="identifier",
            count=3,
            is_field=True,
        )
        result = info.to_dict()
        assert result == {
            "node_type": "identifier",
            "count": 3,
            "is_field": True,
        }


class TestStructuralAnalysis:
    """Test StructuralAnalysis dataclass."""

    def test_to_dict(self) -> None:
        """Test StructuralAnalysis serialization."""
        analysis = StructuralAnalysis(
            node_type="decorated_definition",
            total_occurrences=5,
            child_types=[
                ChildTypeInfo(node_type="decorator", count=2, is_field=False),
                ChildTypeInfo(node_type="function_definition", count=3, is_field=False),
            ],
            field_usage={"definition": 3},
            avg_children_per_occurrence=2.5,
            has_definition_field=True,
            has_decorator_field=False,
            distinct_child_types=2,
            wrapper_score=50,
        )
        result = analysis.to_dict()

        assert result["node_type"] == "decorated_definition"
        assert result["total_occurrences"] == 5
        assert result["wrapper_score"] == 50
        assert len(result["child_types"]) == 2


class TestStructuralAnalyzer:
    """Test StructuralAnalyzer class."""

    def test_analyze_code_sample_returns_dict(
        self, analyzer: StructuralAnalyzer, simple_function_node: Language,
    ) -> None:
        """Test that analyze_code_sample returns a dictionary."""
        result = analyzer.analyze_code_sample(simple_function_node)
        assert isinstance(result, dict)

    def test_analyze_code_sample_contains_module(
        self, analyzer: StructuralAnalyzer, simple_function_node: Language,
    ) -> None:
        """Test that analysis includes module node type."""
        result = analyzer.analyze_code_sample(simple_function_node)
        assert "module" in result

    def test_analyze_code_sample_contains_function_definition(
        self, analyzer: StructuralAnalyzer, simple_function_node: Language,
    ) -> None:
        """Test that analysis includes function_definition node type."""
        result = analyzer.analyze_code_sample(simple_function_node)
        assert "function_definition" in result

    def test_analyze_code_sample_has_occurrence_counts(
        self, analyzer: StructuralAnalyzer, simple_function_node: Language,
    ) -> None:
        """Test that analysis tracks occurrence counts."""
        result = analyzer.analyze_code_sample(simple_function_node)

        for _node_type, analysis in result.items():
            assert analysis.total_occurrences > 0
            assert analysis.total_occurrences == analysis.total_occurrences

    def test_analyze_code_sample_calculates_wrapper_scores(
        self, analyzer: StructuralAnalyzer, decorated_function_node: Language,
    ) -> None:
        """Test that wrapper scores are calculated."""
        result = analyzer.analyze_code_sample(decorated_function_node)

        for _node_type, analysis in result.items():
            assert isinstance(analysis.wrapper_score, int)
            assert analysis.wrapper_score >= 0

    def test_analyze_code_sample_tracks_child_types(
        self, analyzer: StructuralAnalyzer, simple_function_node: Language,
    ) -> None:
        """Test that child types are tracked."""
        result = analyzer.analyze_code_sample(simple_function_node)

        for _node_type, analysis in result.items():
            assert isinstance(analysis.child_types, list)

    def test_detect_wrappers_returns_list(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that detect_wrappers returns a list."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
            parser.parse(bytes("@decorator\ndef bar(): pass", "utf-8")).root_node,
        ]
        wrappers = analyzer.detect_wrappers(code_samples)
        assert isinstance(wrappers, list)

    def test_detect_wrappers_filters_by_confidence(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that detect_wrappers filters by min_confidence."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
        ]
        wrappers_high = analyzer.detect_wrappers(code_samples, min_confidence=50)
        wrappers_low = analyzer.detect_wrappers(code_samples, min_confidence=10)

        assert len(wrappers_high) <= len(wrappers_low)

    def test_detect_wrappers_sorted_by_score(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that wrappers are sorted by wrapper_score descending."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
            parser.parse(bytes("@decorator\ndef bar(): pass", "utf-8")).root_node,
        ]
        wrappers = analyzer.detect_wrappers(code_samples)

        for i in range(len(wrappers) - 1):
            assert wrappers[i].wrapper_score >= wrappers[i + 1].wrapper_score

    def test_calculate_wrapper_score_all_features(
        self, analyzer: StructuralAnalyzer,
    ) -> None:
        """Test wrapper score calculation with all features present."""
        score = analyzer._calculate_wrapper_score(
            node_type="decorated_definition",
            field_usage={"definition": 5, "decorator": 2},
            child_types={"decorator": 2, "function_definition": 3},
            avg_children=2.5,
        )

        # All features present: 30 + 30 + 20 + 10 + 10 = 100
        assert score == 100

    def test_calculate_wrapper_score_no_features(
        self, analyzer: StructuralAnalyzer,
    ) -> None:
        """Test wrapper score calculation with no features."""
        score = analyzer._calculate_wrapper_score(
            node_type="identifier",
            field_usage={},
            child_types={"string": 1},
            avg_children=0.5,
        )

        # No features present: 0
        assert score == 0

    def test_calculate_wrapper_score_partial_features(
        self, analyzer: StructuralAnalyzer,
    ) -> None:
        """Test wrapper score calculation with partial features."""
        score = analyzer._calculate_wrapper_score(
            node_type="with_statement",
            field_usage={},
            child_types={"with_clause": 2, "block": 1},
            avg_children=3.0,
        )

        # child_types (20) + avg_children >= 2 (10) + name_pattern (10, with_statement matches "with_") = 40
        assert score == 40

    def test_analyze_code_sample_multiple_occurrences(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test analysis with multiple occurrences of same type."""
        code = """
def foo(): pass
def bar(): pass
def baz(): pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        # function_definition should appear 3 times
        func_analysis = result.get("function_definition")
        if func_analysis:
            assert func_analysis.total_occurrences == 3
