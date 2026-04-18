"""Unit tests for LLM benchmark module."""
from __future__ import annotations

from tree_sitter_analyzer.analysis.llm_benchmark import (
    BenchmarkResult,
    Question,
    _extract_code_elements,
    analyze_fidelity_vs_compression,
    can_answer_question,
    format_benchmark_report,
    generate_questions_from_code,
    run_benchmark,
)


class TestQuestion:
    """Test Question dataclass."""

    def test_create_question(self) -> None:
        """Test creating a question."""
        q = Question(
            question="What is the main function?",
            required_keywords={"main", "function"},
            optional_keywords={"entry", "point"},
            category="structure"
        )
        assert q.question == "What is the main function?"
        assert "main" in q.required_keywords
        assert q.category == "structure"


class TestExtractCodeElements:
    """Test code element extraction."""

    def test_extract_function(self) -> None:
        """Test extracting a function."""
        content = "my_function() [complexity: 5]"
        elements = _extract_code_elements(content)

        assert len(elements) == 1
        assert elements[0]["name"] == "my_function"
        assert elements[0]["type"] == "function"
        assert elements[0]["complexity"] == 5

    def test_extract_class(self) -> None:
        """Test extracting a class."""
        content = "MyClass [complexity: 12]"
        elements = _extract_code_elements(content)

        assert len(elements) == 1
        assert elements[0]["name"] == "MyClass"
        assert elements[0]["type"] == "class"

    def test_extract_indented_method(self) -> None:
        """Test extracting indented method."""
        content = "  my_method() [complexity: 3]"
        elements = _extract_code_elements(content)

        assert len(elements) == 1
        assert elements[0]["name"] == "my_method"
        assert elements[0]["type"] == "method"

    def test_extract_multiple_elements(self) -> None:
        """Test extracting multiple elements."""
        content = """
        MyClass [complexity: 12]
            method_one() [complexity: 3]
        function_one() [complexity: 5]
        """
        elements = _extract_code_elements(content)

        assert len(elements) == 3
        names = {e["name"] for e in elements}
        assert "MyClass" in names
        assert "method_one" in names
        assert "function_one" in names


class TestGenerateQuestionsFromCode:
    """Test question generation from code."""

    def test_generates_questions_for_valid_content(self) -> None:
        """Test generating questions from valid TOON content."""
        content = """
        complex_func() [complexity: 20]
        simple_func() [complexity: 1]
        MyClass [complexity: 10]
        """
        questions = generate_questions_from_code(content)

        assert len(questions) > 0
        assert any(q.category == "complexity" for q in questions)

    def test_includes_high_complexity_question(self) -> None:
        """Test that high complexity question is generated."""
        content = """
        high_complexity_func() [complexity: 25]
        low_complexity_func() [complexity: 2]
        """
        questions = generate_questions_from_code(content)

        complexity_questions = [q for q in questions if q.category == "complexity"]
        assert len(complexity_questions) > 0
        assert "high_complexity_func" in complexity_questions[0].required_keywords

    def test_includes_structure_questions(self) -> None:
        """Test that structure questions are generated."""
        content = """
        MyClass [complexity: 5]
            my_method() [complexity: 3]
        """
        questions = generate_questions_from_code(content)

        structure_questions = [q for q in questions if q.category == "structure"]
        assert len(structure_questions) > 0

    def test_returns_empty_for_invalid_content(self) -> None:
        """Test that invalid content returns empty list."""
        questions = generate_questions_from_code("")
        assert len(questions) == 0


class TestCanAnswerQuestion:
    """Test question answerability checking."""

    def test_can_answer_with_all_required_keywords(self) -> None:
        """Test that all required keywords allow answering."""
        content = "The main function is the entry point of the program."

        result = can_answer_question(
            "What is the main function?",
            content,
            frozenset({"main", "function"}),
        )

        assert result is True

    def test_cannot_answer_missing_required_keyword(self) -> None:
        """Test that missing required keyword prevents answering."""
        content = "The function is important."

        result = can_answer_question(
            "What is the main function?",
            content,
            frozenset({"main", "function"}),
        )

        assert result is False

    def test_can_answer_with_optional_keywords(self) -> None:
        """Test optional keywords strengthen confidence."""
        content = "The main function is the entry point of execution."

        result = can_answer_question(
            "What is the main function?",
            content,
            frozenset({"main", "function"}),
            frozenset({"entry", "point", "execution"}),
        )

        assert result is True

    def test_case_insensitive_matching(self) -> None:
        """Test that matching is case-insensitive."""
        content = "THE MAIN FUNCTION IS HERE"

        result = can_answer_question(
            "Where is the function?",
            content,
            frozenset({"main", "function"}),
        )

        assert result is True


class TestRunBenchmark:
    """Test benchmark execution."""

    def test_run_benchmark_basic(self) -> None:
        """Test running a basic benchmark."""
        original = """
        important_func() [complexity: 15]
        trivial_func() [complexity: 1]
        """

        optimized = "important_func() [complexity: 15]"

        questions = [
            Question(
                question="Which function has complexity 15?",
                required_keywords={"important_func", "15"},
                category="complexity"
            ),
        ]

        result = run_benchmark(original, optimized, questions)

        assert result.total_questions == 1
        assert result.answerable_from_original == 1
        assert result.answerable_from_optimized == 1
        assert result.fidelity == 1.0

    def test_calculates_compression_ratio(self) -> None:
        """Test compression ratio calculation."""
        original = "a" * 1000
        optimized = "a" * 500

        result = run_benchmark(original, optimized, [])

        assert result.original_size == 1000
        assert result.optimized_size == 500
        assert result.compression_ratio == 0.5

    def test_fidelity_zero_when_no_questions_answerable(self) -> None:
        """Test fidelity when optimized content cannot answer any questions."""
        original = "critical_func() [complexity: 20]"
        optimized = ""

        questions = [
            Question(
                question="What functions exist?",
                required_keywords={"critical_func"},
                category="structure"
            ),
        ]

        result = run_benchmark(original, optimized, questions)

        assert result.fidelity == 0.0

    def test_fidelity_calculates_correctly(self) -> None:
        """Test fidelity calculation with partial answerability."""
        original = "func_a() func_b() func_c()"
        optimized = "func_a() func_c()"  # Missing func_b

        questions = [
            Question("A?", frozenset({"func_a"})),
            Question("B?", frozenset({"func_b"})),
            Question("C?", frozenset({"func_c"})),
        ]

        result = run_benchmark(original, optimized, questions)

        # 2/3 answerable from optimized
        assert result.fidelity == 2.0 / 3.0

    def test_auto_generates_questions_if_none(self) -> None:
        """Test that questions are auto-generated if not provided."""
        original = "my_func() [complexity: 10]"
        optimized = "my_func() [complexity: 10]"

        result = run_benchmark(original, optimized)

        assert result.total_questions > 0


class TestBenchmarkResult:
    """Test BenchmarkResult dataclass."""

    def test_to_dict(self) -> None:
        """Test converting result to dictionary."""
        result = BenchmarkResult(
            total_questions=10,
            answerable_from_original=10,
            answerable_from_optimized=9,
            fidelity=0.9,
            compression_ratio=0.5,
            original_size=1000,
            optimized_size=500,
        )

        d = result.to_dict()

        assert d["total_questions"] == 10
        assert d["fidelity"] == "90.0%"
        assert d["compression_ratio"] == "50.0%"


class TestFormatBenchmarkReport:
    """Test benchmark report formatting."""

    def test_format_report(self) -> None:
        """Test formatting benchmark report."""
        result = BenchmarkResult(
            total_questions=10,
            answerable_from_original=10,
            answerable_from_optimized=9,
            fidelity=0.9,
            compression_ratio=0.5,
            original_size=1000,
            optimized_size=500,
        )

        report = format_benchmark_report(result)

        assert "90.0%" in report
        assert "50.0%" in report
        assert "Excellent" in report
        assert "10" in report


class TestAnalyzeFidelityVsCompression:
    """Test fidelity vs compression analysis."""

    def test_analyze_multiple_thresholds(self) -> None:
        """Test analyzing across multiple thresholds."""
        content = """
        high() [complexity: 20]
        mid() [complexity: 10]
        low() [complexity: 1]
        """

        results = analyze_fidelity_vs_compression(content, thresholds=[0.3, 0.5, 0.7])

        assert "threshold_0.3" in results
        assert "threshold_0.5" in results
        assert "threshold_0.7" in results

        # Lower threshold should keep more content
        assert results["threshold_0.3"].optimized_size >= results["threshold_0.5"].optimized_size


class TestIntegration:
    """Integration tests."""

    def test_full_benchmark_workflow(self) -> None:
        """Test complete benchmark workflow."""
        original = """
        complex_api_handler() [complexity: 25]
        simple_getter() [complexity: 2]
        business_logic() [complexity: 18]
        utility_helper() [complexity: 1]
        """

        # Simulate optimization (keep top 50%)
        optimized = """
        complex_api_handler() [complexity: 25]
        business_logic() [complexity: 18]
        """

        # Run benchmark
        result = run_benchmark(original, optimized)

        # Verify metrics
        assert 0.0 <= result.fidelity <= 1.0
        assert 0.0 <= result.compression_ratio <= 1.0
        assert result.optimized_size < result.original_size

        # Format and verify report
        report = format_benchmark_report(result)
        assert "Fidelity:" in report
        assert "Compression:" in report
