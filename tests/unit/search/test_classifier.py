"""
Unit tests for QueryClassifier.
"""
from __future__ import annotations

import pytest

from tree_sitter_analyzer.search.classifier import (
    FastPathHandler,
    QueryClassifier,
    QueryType,
)


class TestQueryType:
    """Test QueryType enum."""

    def test_values(self) -> None:
        """Test enum values."""
        assert QueryType.SIMPLE.value == "simple"
        assert QueryType.COMPLEX.value == "complex"


class TestFastPathHandler:
    """Test FastPathHandler dataclass."""

    def test_init(self) -> None:
        """Test FastPathHandler initialization."""
        handler = FastPathHandler(
            name="test_handler",
            pattern=r"test\s+(\w+)",
            handler_func="test_func",
            description="Test handler",
        )

        assert handler.name == "test_handler"
        assert handler.description == "Test handler"
        assert handler.handler_func == "test_func"

    def test_pattern_compilation(self) -> None:
        """Test that pattern is compiled as regex."""
        handler = FastPathHandler(
            name="test",
            pattern=r"functions?\s+(\w+)",
            handler_func="test",
            description="",
        )

        # Should be able to use the pattern for matching
        match = handler.pattern.search("functions test_name")
        assert match is not None
        assert match.group(1) == "test_name"


class TestQueryClassifier:
    """Test QueryClassifier class."""

    @pytest.fixture
    def classifier(self) -> QueryClassifier:
        """Get QueryClassifier instance."""
        return QueryClassifier()

    def test_init(self, classifier: QueryClassifier) -> None:
        """Test QueryClassifier initialization."""
        assert classifier is not None
        assert len(classifier.FAST_PATH_PATTERNS) == 4
        assert len(classifier.COMPLEX_PATTERNS) == 5

    def test_classify_simple_grep_by_name(self, classifier: QueryClassifier) -> None:
        """Test classification of simple 'functions named' query."""
        result = classifier.classify("functions named authenticate")

        assert result.query_type == QueryType.SIMPLE
        assert result.confidence == 0.9
        assert result.params["handler"] == "grep_by_name"
        assert result.params["params"]["name"] == "authenticate"

    def test_classify_simple_grep_containing(self, classifier: QueryClassifier) -> None:
        """Test classification of 'functions containing' query."""
        result = classifier.classify("functions containing user")

        assert result.query_type == QueryType.SIMPLE
        assert result.params["handler"] == "grep_by_name"
        assert result.params["params"]["name"] == "user"

    def test_classify_simple_in_files(self, classifier: QueryClassifier) -> None:
        """Test classification of 'all X in Y files' query."""
        result = classifier.classify("all database in python files")

        assert result.query_type == QueryType.SIMPLE
        assert result.params["handler"] == "grep_in_files"

    def test_classify_simple_dependency_of(self, classifier: QueryClassifier) -> None:
        """Test classification of 'dependencies of' query."""
        result = classifier.classify("dependencies of UserService")

        assert result.query_type == QueryType.SIMPLE
        assert result.params["handler"] == "dependency_of"

    def test_classify_simple_what_calls(self, classifier: QueryClassifier) -> None:
        """Test classification of 'what calls' query."""
        result = classifier.classify("what calls authenticate")

        assert result.query_type == QueryType.SIMPLE
        assert result.params["handler"] == "what_calls"

    def test_classify_complex_conditional(self, classifier: QueryClassifier) -> None:
        """Test classification of complex conditional query."""
        result = classifier.classify("functions that call database but don't handle errors")

        assert result.query_type == QueryType.COMPLEX
        assert result.confidence == 0.8
        assert "handler" not in result.params

    def test_classify_complex_negative_constraint(self, classifier: QueryClassifier) -> None:
        """Test classification of complex negative constraint query."""
        result = classifier.classify("all endpoints that use input without validation")

        assert result.query_type == QueryType.COMPLEX
        assert result.confidence == 0.8

    def test_classify_unknown_defaults_to_complex(self, classifier: QueryClassifier) -> None:
        """Test that unknown queries default to complex with low confidence."""
        result = classifier.classify("some random query that doesn't match patterns")

        assert result.query_type == QueryType.COMPLEX
        assert result.confidence == 0.3
        assert result.matched_pattern is None

    def test_add_pattern(self, classifier: QueryClassifier) -> None:
        """Test adding a custom fast path pattern."""
        initial_custom_count = len(classifier._custom_patterns)

        classifier.add_pattern(
            pattern=r"custom\s+pattern\s+(\w+)",
            handler="custom_handler",
            name="custom_pattern",
            description="Custom pattern for testing",
        )

        assert len(classifier._custom_patterns) == initial_custom_count + 1

        # Test that the new pattern works
        result = classifier.classify("custom pattern test_value")
        assert result.query_type == QueryType.SIMPLE
        assert result.params["handler"] == "custom_handler"

    def test_fast_path_precedence_over_complex(self, classifier: QueryClassifier) -> None:
        """Test that fast path patterns take precedence over complex patterns."""
        # This query should match the simple pattern (functions named/containing)
        # because "functions" alone doesn't match the full pattern
        result = classifier.classify("functions named database")

        assert result.query_type == QueryType.SIMPLE
        assert result.params["handler"] == "grep_by_name"

    def test_get_stats(self, classifier: QueryClassifier) -> None:
        """Test getting statistics."""
        stats = classifier.get_stats()

        assert "total_queries" in stats
        assert "fast_path_count" in stats
        assert "llm_path_count" in stats
        assert "pattern_matches" in stats
        assert stats["total_queries"] == 0
