"""Unit tests for context optimizer module."""
from __future__ import annotations

import pytest

from tree_sitter_analyzer.analysis.context_optimizer import (
    CodeElement,
    calculate_compression_ratio,
    filter_by_importance,
    optimize_for_llm,
    parse_toon_elements,
    score_importance,
)


class TestCodeElement:
    """Test CodeElement dataclass."""

    def test_create_code_element(self) -> None:
        """Test creating a CodeElement."""
        element = CodeElement(
            name="my_function",
            element_type="function",
            complexity=5,
            dependency_count=3,
            call_frequency=10,
            indent_level=0,
        )
        assert element.name == "my_function"
        assert element.element_type == "function"
        assert element.complexity == 5
        assert element.dependency_count == 3
        assert element.call_frequency == 10

    def test_code_element_hash(self) -> None:
        """Test CodeElement is hashable."""
        element = CodeElement(
            name="my_function",
            element_type="function",
            complexity=5,
            dependency_count=3,
            call_frequency=10,
            indent_level=0,
        )
        element_set = {element}
        assert len(element_set) == 1


class TestScoreImportance:
    """Test importance scoring algorithm."""

    def test_high_complexity_scores_higher(self) -> None:
        """Test that higher complexity increases score."""
        low_complexity = CodeElement(
            name="simple_func",
            element_type="function",
            complexity=1,
            dependency_count=0,
            call_frequency=0,
        )
        high_complexity = CodeElement(
            name="complex_func",
            element_type="function",
            complexity=20,
            dependency_count=0,
            call_frequency=0,
        )

        assert score_importance(high_complexity) > score_importance(low_complexity)

    def test_many_dependencies_scores_higher(self) -> None:
        """Test that more dependencies increase score."""
        few_deps = CodeElement(
            name="isolated_func",
            element_type="function",
            complexity=5,
            dependency_count=1,
            call_frequency=0,
        )
        many_deps = CodeElement(
            name="integrated_func",
            element_type="function",
            complexity=5,
            dependency_count=20,
            call_frequency=0,
        )

        assert score_importance(many_deps) > score_importance(few_deps)

    def test_high_call_frequency_scores_higher(self) -> None:
        """Test that higher call frequency increases score."""
        rarely_called = CodeElement(
            name="rare_func",
            element_type="function",
            complexity=5,
            dependency_count=5,
            call_frequency=1,
        )
        often_called = CodeElement(
            name="common_func",
            element_type="function",
            complexity=5,
            dependency_count=5,
            call_frequency=50,
        )

        assert score_importance(often_called) > score_importance(rarely_called)

    def test_score_normalization(self) -> None:
        """Test that scores are normalized to 0-1 range."""
        extreme = CodeElement(
            name="extreme_func",
            element_type="function",
            complexity=100,
            dependency_count=100,
            call_frequency=100,
        )

        score = score_importance(extreme)
        assert 0.0 <= score <= 1.0

    def test_weighted_scoring_formula(self) -> None:
        """Test the weighted scoring formula."""
        element = CodeElement(
            name="test_func",
            element_type="function",
            complexity=10,
            dependency_count=5,
            call_frequency=20,
        )

        score = score_importance(element)
        # Expected: (10 * 0.4) + (5 * 0.3) + (20 * 0.3) = 4 + 1.5 + 6 = 11.5
        # Normalized: 11.5 / 100 = 0.115
        expected = (10 * 0.4 + 5 * 0.3 + 20 * 0.3) / 100.0
        assert abs(score - expected) < 0.001


class TestFilterByImportance:
    """Test importance-based filtering."""

    def test_filter_empty_list(self) -> None:
        """Test filtering empty list."""
        result = filter_by_importance([])
        assert result == []

    def test_filter_keeps_top_percentile(self) -> None:
        """Test that filtering keeps top N% by score."""
        elements = [
            CodeElement(f"func_{i}", "function", i, 0, 0, indent_level=0) for i in range(10)
        ]

        # Keep top 50%
        result = filter_by_importance(elements, threshold=0.5, min_elements=1)
        assert len(result) == 5

        # Should keep highest complexity elements
        names = {el.name for el in result}
        assert "func_9" in names  # Highest complexity
        assert "func_8" in names
        assert "func_7" in names
        assert "func_6" in names
        assert "func_5" in names
        assert "func_0" not in names  # Lowest complexity

    def test_filter_respects_min_elements(self) -> None:
        """Test that min_elements is always preserved."""
        elements = [
            CodeElement(f"func_{i}", "function", i, 0, 0, indent_level=0) for i in range(3)
        ]

        # Even with 0.1 threshold, should keep at least 2 elements
        result = filter_by_importance(elements, threshold=0.1, min_elements=2)
        assert len(result) == 2

    def test_filter_sorts_by_importance(self) -> None:
        """Test that results are sorted by importance descending."""
        elements = [
            CodeElement("low", "function", 1, 0, 0, indent_level=0),
            CodeElement("high", "function", 10, 0, 0, indent_level=0),
            CodeElement("mid", "function", 5, 0, 0, indent_level=0),
        ]

        result = filter_by_importance(elements, threshold=1.0, min_elements=1)
        assert result[0].name == "high"
        assert result[1].name == "mid"
        assert result[2].name == "low"


class TestParseToonElements:
    """Test TOON format parsing."""

    def test_parse_function(self) -> None:
        """Test parsing a function definition."""
        toon = "my_function() [complexity: 5]"
        elements = parse_toon_elements(toon)

        assert len(elements) == 1
        assert elements[0].name == "my_function"
        assert elements[0].element_type == "function"
        assert elements[0].complexity == 5

    def test_parse_class(self) -> None:
        """Test parsing a class definition."""
        toon = "MyClass [complexity: 12]"
        elements = parse_toon_elements(toon)

        assert len(elements) == 1
        assert elements[0].name == "MyClass"
        assert elements[0].element_type == "class"
        assert elements[0].complexity == 12

    def test_parse_indented_method(self) -> None:
        """Test parsing indented method."""
        # Use 4 spaces for indentation (standard in TOON)
        toon = "    method_one() [complexity: 3]"
        elements = parse_toon_elements(toon)

        assert len(elements) == 1
        assert elements[0].name == "method_one"
        # Methods are detected by indent_level > 0
        assert elements[0].indent_level > 0

    def test_parse_multiple_elements(self) -> None:
        """Test parsing multiple elements."""
        toon = """
        MyClass [complexity: 12]
            method_one() [complexity: 3]
            method_two() [complexity: 7]
        my_function() [complexity: 5]
        """
        elements = parse_toon_elements(toon)

        assert len(elements) == 4
        assert elements[0].name == "MyClass"
        assert elements[1].name == "method_one"
        assert elements[2].name == "method_two"
        assert elements[3].name == "my_function"

    def test_ignores_comments_and_empty_lines(self) -> None:
        """Test that comments and empty lines are ignored."""
        toon = """
        # This is a comment

        my_function() [complexity: 5]

        ```
        ```
        """
        elements = parse_toon_elements(toon)

        assert len(elements) == 1
        assert elements[0].name == "my_function"


class TestOptimizeForLlm:
    """Test LLM optimization."""

    def test_optimize_empty_input(self) -> None:
        """Test optimizing empty input."""
        result = optimize_for_llm("")
        assert result == ""

    def test_optimize_preserves_structure(self) -> None:
        """Test that optimization preserves TOON structure."""
        toon = """
        high_complex_func() [complexity: 20]
        low_complex_func() [complexity: 1]
        """
        result = optimize_for_llm(toon, threshold=0.5)

        # Should keep high complexity function
        assert "high_complex_func()" in result
        # Format should be preserved
        assert "[complexity:" in result

    def test_optimize_with_dependency_data(self) -> None:
        """Test optimization with dependency counts."""
        toon = """
        isolated() [complexity: 5]
        integrated() [complexity: 5]
        """
        dep_counts = {"isolated": 0, "integrated": 20}

        result = optimize_for_llm(toon, threshold=0.5, dependency_counts=dep_counts)

        # Should keep integrated (more dependencies)
        assert "integrated()" in result

    def test_optimize_with_call_frequency(self) -> None:
        """Test optimization with call frequency data."""
        toon = """
        rarely_called() [complexity: 5]
        often_called() [complexity: 5]
        """
        call_freqs = {"rarely_called": 1, "often_called": 100}

        result = optimize_for_llm(toon, threshold=0.5, call_frequencies=call_freqs)

        # Should keep often_called
        assert "often_called()" in result


class TestCalculateCompressionRatio:
    """Test compression ratio calculation."""

    def test_no_compression(self) -> None:
        """Test when no compression occurs."""
        ratio = calculate_compression_ratio("hello world", "hello world")
        assert ratio == 0.0

    def test_half_compression(self) -> None:
        """Test 50% compression."""
        # "hello world test" is 17 chars, "hello world" is 11 chars
        # Compression = 1 - 11/17 = 6/17 ≈ 0.35
        ratio = calculate_compression_ratio("hello world test", "hello world")
        assert 0.3 < ratio < 0.4

    def test_full_compression(self) -> None:
        """Test near-full compression."""
        ratio = calculate_compression_ratio("hello world test", "")
        assert ratio == 1.0

    def test_empty_input(self) -> None:
        """Test with empty input."""
        ratio = calculate_compression_ratio("", "output")
        assert ratio == 0.0


class TestIntegration:
    """Integration tests."""

    def test_full_optimization_pipeline(self) -> None:
        """Test complete optimization pipeline."""
        original = """
        complex_dep_func() [complexity: 20]
        simple_isolated_func() [complexity: 1]
        mid_func() [complexity: 10]
        rarely_called_func() [complexity: 5]
        often_called_func() [complexity: 5]
        """

        dep_counts = {
            "complex_dep_func": 30,
            "simple_isolated_func": 0,
            "mid_func": 10,
            "rarely_called_func": 5,
            "often_called_func": 5,
        }

        call_freqs = {
            "complex_dep_func": 100,
            "simple_isolated_func": 1,
            "mid_func": 20,
            "rarely_called_func": 1,
            "often_called_func": 50,
        }

        optimized = optimize_for_llm(
            original, threshold=0.5, dependency_counts=dep_counts, call_frequencies=call_freqs
        )

        # Should keep top 50% (2-3 elements)
        optimized_lines = [line for line in optimized.split("\n") if line.strip()]
        assert 2 <= len(optimized_lines) <= 3

        # Highest scored element should be preserved
        assert "complex_dep_func()" in optimized

        # Calculate compression
        ratio = calculate_compression_ratio(original, optimized)
        assert ratio > 0.3  # At least 30% compression
