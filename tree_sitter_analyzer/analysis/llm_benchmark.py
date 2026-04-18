"""LLM Benchmark — Measure fidelity of context optimization.

This module provides tools to validate that context optimization preserves
semantic information by testing question-answering capability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


@dataclass(frozen=True)
class Question:
    """A test question for benchmarking."""

    question: str
    # Keywords that must appear in the content to answer the question
    required_keywords: set[str]
    # Optional keywords that strengthen confidence
    optional_keywords: set[str] = field(default_factory=set)
    # Category of question (complexity, dependencies, structure, etc.)
    category: str = "general"


@dataclass
class BenchmarkResult:
    """Result of running a benchmark."""

    total_questions: int
    answerable_from_original: int
    answerable_from_optimized: int
    fidelity: float  # % of questions answerable from optimized
    compression_ratio: float  # % size reduction
    original_size: int
    optimized_size: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_questions": self.total_questions,
            "answerable_from_original": self.answerable_from_original,
            "answerable_from_optimized": self.answerable_from_optimized,
            "fidelity": f"{self.fidelity:.1%}",
            "compression_ratio": f"{self.compression_ratio:.1%}",
            "original_size": self.original_size,
            "optimized_size": self.optimized_size,
        }


def generate_questions_from_code(content: str) -> list[Question]:
    """Generate test questions based on code content.

    Analyzes code content and generates questions that test understanding
    of important aspects: complexity, dependencies, structure.

    Args:
        content: Code content or TOON output

    Returns:
        List of Question objects
    """
    questions: list[Question] = []

    # Extract function/class names and their properties
    elements = _extract_code_elements(content)

    if not elements:
        return questions

    # Question 1: Which function has highest complexity?
    if elements:
        max_complexity_el = max(elements, key=lambda e: e.get("complexity", 0))
        questions.append(Question(
            question="Which function has the highest cyclomatic complexity?",
            required_keywords={max_complexity_el["name"]},
            optional_keywords={"complexity", "highest", "maximum"},
            category="complexity"
        ))

    # Question 2: List all functions with complexity > threshold
    high_complexity = [e for e in elements if e.get("complexity", 0) > 10]
    if high_complexity:
        keywords = {e["name"] for e in high_complexity}
        questions.append(Question(
            question="Which functions have complexity greater than 10?",
            required_keywords=keywords,
            optional_keywords={"complexity", "greater"},
            category="complexity"
        ))

    # Question 3: What classes are defined?
    classes = [e for e in elements if e.get("type") == "class"]
    if classes:
        class_names = {e["name"] for e in classes}
        questions.append(Question(
            question="What classes are defined in this code?",
            required_keywords=class_names,
            optional_keywords={"class", "defined"},
            category="structure"
        ))

    # Question 4: What methods belong to a specific class?
    if classes:
        # Pick first class
        target_class = classes[0]["name"]
        methods = [e for e in elements if e.get("type") == "method"]
        if methods:
            method_names = {e["name"] for e in methods}
            questions.append(Question(
                question=f"What methods are defined in {target_class}?",
                required_keywords=method_names | {target_class},
                optional_keywords={"method", "defined"},
                category="structure"
            ))

    # Question 5: Function count
    questions.append(Question(
        question="How many functions are defined?",
        required_keywords={str(len([e for e in elements if e.get("type") in ("function", "method")]))},
        optional_keywords={"function", "count", "many"},
        category="structure"
    ))

    return questions


def _extract_code_elements(content: str) -> list[dict[str, Any]]:
    """Extract code elements from content.

    Args:
        content: TOON formatted output or code

    Returns:
        List of element dictionaries
    """
    elements: list[dict[str, Any]] = []

    # Try TOON format first
    for raw_line in content.split("\n"):
        # Skip empty and comments
        if not raw_line.strip() or raw_line.strip().startswith("#") or raw_line.strip().startswith("```"):
            continue

        # Track indentation before stripping
        indent_match = re.match(r"^(\s*)", raw_line)
        indent_level = len(indent_match.group(1)) if indent_match else 0

        line = raw_line.strip()

        # Match TOON format: name() [complexity: N] or name [complexity: N]
        match = re.search(r"(\w+)\s*(\(\))?\s*\[complexity:\s*(\d+)\]", line)
        if match:
            name = match.group(1)
            has_parens = match.group(2) is not None
            complexity = int(match.group(3))

            # Determine type (indented functions are methods)
            if has_parens:
                element_type = "method" if indent_level > 0 else "function"
            else:
                element_type = "class"

            elements.append({
                "name": name,
                "type": element_type,
                "complexity": complexity,
                "indent_level": indent_level,
            })

    return elements


@lru_cache(maxsize=64)
def can_answer_question(question: str, content: str, required_keywords: frozenset[str], optional_keywords: frozenset[str] = frozenset()) -> bool:
    """Check if content contains enough information to answer a question.

    Args:
        question: The question text
        content: The content to search in
        required_keywords: Keywords that MUST be present
        optional_keywords: Keywords that strengthen confidence

    Returns:
        True if question can be answered from content
    """
    content_lower = content.lower()

    # Check required keywords
    required_present = all(
        kw.lower() in content_lower for kw in required_keywords
    )

    if not required_present:
        return False

    # Check optional keywords (at least 50% for confidence)
    if optional_keywords:
        optional_present = sum(
            1 for kw in optional_keywords if kw.lower() in content_lower
        )
        return optional_present >= len(optional_keywords) * 0.5

    return True


def run_benchmark(
    original_content: str,
    optimized_content: str,
    questions: list[Question] | None = None,
) -> BenchmarkResult:
    """Run benchmark on original vs optimized content.

    Args:
        original_content: Original TOON/code content
        optimized_content: Optimized content
        questions: Optional list of questions (auto-generated if None)

    Returns:
        BenchmarkResult with fidelity and compression metrics
    """
    # Auto-generate questions if not provided
    if questions is None:
        questions = generate_questions_from_code(original_content)

    if not questions:
        # Default generic questions if extraction failed
        questions = [
            Question(
                question="What functions are defined?",
                required_keywords={"function", "defined"},
                category="structure"
            ),
            Question(
                question="What is the structure of this code?",
                required_keywords={"complexity"},
                category="structure"
            ),
        ]

    original_size = len(original_content)
    optimized_size = len(optimized_content)

    # Test questions against original
    answerable_original = sum(
        1 for q in questions
        if can_answer_question(
            q.question,
            original_content,
            frozenset(q.required_keywords),
            frozenset(q.optional_keywords)
        )
    )

    # Test questions against optimized
    answerable_optimized = sum(
        1 for q in questions
        if can_answer_question(
            q.question,
            optimized_content,
            frozenset(q.required_keywords),
            frozenset(q.optional_keywords)
        )
    )

    # Calculate fidelity
    fidelity = answerable_optimized / answerable_original if answerable_original > 0 else 0.0

    # Calculate compression ratio
    compression_ratio = 1.0 - (optimized_size / original_size) if original_size > 0 else 0.0

    return BenchmarkResult(
        total_questions=len(questions),
        answerable_from_original=answerable_original,
        answerable_from_optimized=answerable_optimized,
        fidelity=fidelity,
        compression_ratio=compression_ratio,
        original_size=original_size,
        optimized_size=optimized_size,
    )


def format_benchmark_report(result: BenchmarkResult) -> str:
    """Format benchmark result as readable report.

    Args:
        result: Benchmark result

    Returns:
        Formatted report string
    """
    return f"""
# LLM Fidelity Benchmark Report

## Summary
- Total Questions: {result.total_questions}
- Answerable from Original: {result.answerable_from_original}
- Answerable from Optimized: {result.answerable_from_optimized}
- **Fidelity: {result.fidelity:.1%}** (higher is better)
- **Compression: {result.compression_ratio:.1%}** (size reduction)

## Quality Assessment
{'✅ Excellent: 90%+ fidelity' if result.fidelity >= 0.9 else
 '✅ Good: 70-90% fidelity' if result.fidelity >= 0.7 else
 '⚠️  Fair: 50-70% fidelity' if result.fidelity >= 0.5 else
 '❌ Poor: <50% fidelity'}

## Size Metrics
- Original: {result.original_size} chars
- Optimized: {result.optimized_size} chars
- Reduction: {result.original_size - result.optimized_size} chars
"""


def analyze_fidelity_vs_compression(
    original_content: str,
    thresholds: list[float] | None = None,
) -> dict[str, BenchmarkResult]:
    """Analyze fidelity across different compression thresholds.

    Args:
        original_content: Original content
        thresholds: List of thresholds to test (default: [0.3, 0.5, 0.7])

    Returns:
        Dictionary mapping threshold -> BenchmarkResult
    """
    from .context_optimizer import optimize_for_llm

    if thresholds is None:
        thresholds = [0.3, 0.5, 0.7]

    results = {}

    for threshold in thresholds:
        optimized = optimize_for_llm(original_content, threshold=threshold)
        result = run_benchmark(original_content, optimized)
        results[f"threshold_{threshold:.1f}"] = result

    return results
