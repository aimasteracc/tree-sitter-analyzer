"""Context Optimizer — LLM Context Window Optimization.

Reduces token consumption of code analysis output while preserving
semantically important information for LLM understanding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

# Scoring weights (tunable based on validation results)
WEIGHT_COMPLEXITY = 0.4
WEIGHT_DEPENDENCY = 0.3
WEIGHT_CALL_FREQUENCY = 0.3


@dataclass(frozen=True)
class CodeElement:
    """A code element that can be scored and filtered."""

    name: str
    element_type: str  # function, class, method, variable, etc.
    complexity: int  # cyclomatic complexity
    dependency_count: int  # number of dependencies
    call_frequency: int  # approximate call frequency
    line_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    indent_level: int = 0  # track indentation for method detection

    def __hash__(self) -> int:
        return hash((self.name, self.element_type, self.line_number))


def score_importance(element: CodeElement) -> float:
    """Calculate importance score for a code element.

    Higher score = more important for LLM understanding.

    Formula:
        score = complexity * 0.4 + dependency_count * 0.3 + call_frequency * 0.3

    Args:
        element: The code element to score.

    Returns:
        Importance score (0.0 to 1.0 normalized).
    """
    # Weighted sum
    raw_score = (
        element.complexity * WEIGHT_COMPLEXITY
        + element.dependency_count * WEIGHT_DEPENDENCY
        + element.call_frequency * WEIGHT_CALL_FREQUENCY
    )

    # Normalize to 0-1 range (heuristic: max expected score ~100)
    return min(raw_score / 100.0, 1.0)


def filter_by_importance(
    elements: list[CodeElement],
    threshold: float = 0.5,
    min_elements: int = 1,
) -> list[CodeElement]:
    """Filter code elements by importance score.

    Keeps elements above the threshold percentile, ensuring at least
    min_elements are retained.

    Args:
        elements: List of code elements to filter.
        threshold: Percentile threshold (0.0-1.0). Keep top N%.
        min_elements: Minimum number of elements to always retain.

    Returns:
        Filtered list of code elements, sorted by importance descending.
    """
    if not elements:
        return []

    # Score all elements
    scored_elements = [(el, score_importance(el)) for el in elements]
    scored_elements.sort(key=lambda x: x[1], reverse=True)

    # Determine cutoff score
    n = len(scored_elements)
    cutoff_idx = max(int(n * threshold), min_elements)
    cutoff_idx = min(cutoff_idx, n)

    # Keep elements above cutoff
    result = [scored_elements[i][0] for i in range(cutoff_idx)]

    logger.debug(
        f"Filtered {n} elements to {len(result)} (threshold={threshold}, kept top {cutoff_idx})"
    )

    return result


@lru_cache(maxsize=128)
def parse_toon_elements(toon_output: str) -> list[CodeElement]:
    """Parse TOON format output into CodeElement objects.

    TOON format example:
        ```
        my_function() [complexity: 5]
        MyClass [complexity: 12]
            method_one() [complexity: 3]
        ```

    Args:
        toon_output: TOON formatted string.

    Returns:
        List of parsed CodeElement objects.
    """
    elements = []
    lines = toon_output.split("\n")

    for line in lines:
        # Skip empty lines and comments
        if not line or line.strip().startswith("#") or line.strip() == "":
            continue

        # Skip markdown code block markers
        if line.strip().startswith("```"):
            continue

        # Extract complexity from TOON format
        complexity_match = re.search(r"\[complexity:\s*(\d+)\]", line)
        complexity = int(complexity_match.group(1)) if complexity_match else 1

        # Extract element name and type
        # Function: my_function()
        # Class: MyClass
        # Method:   method_one() (indented)
        indent_match = re.match(r"^(\s*)", line)
        indent_level = len(indent_match.group(1)) if indent_match else 0

        # Remove complexity annotation for name extraction
        clean_line = re.sub(r"\s*\[complexity:\s*\d+\]", "", line)
        clean_line = clean_line.strip()

        # Skip if no valid name (e.g., just "code block" text)
        if not clean_line or " " in clean_line and "()" not in clean_line:
            continue

        # Determine element type
        if "()" in clean_line:
            element_type = "method" if indent_level > 0 else "function"
            name = clean_line.replace("()", "")
        else:
            element_type = "class"
            name = clean_line

        if name and name not in ("code", "block"):
            elements.append(
                CodeElement(
                    name=name,
                    element_type=element_type,
                    complexity=complexity,
                    dependency_count=0,  # Will be populated by caller
                    call_frequency=0,  # Will be populated by caller
                    line_number=0,  # Not available from TOON
                    indent_level=indent_level,
                )
            )

    return elements


def optimize_for_llm(
    toon_output: str,
    threshold: float = 0.5,
    dependency_counts: dict[str, int] | None = None,
    call_frequencies: dict[str, int] | None = None,
) -> str:
    """Optimize TOON output for LLM context windows.

    1. Parse TOON → extract code elements
    2. Score each element (complexity + dependencies + call frequency)
    3. Filter by threshold (keep top N%)
    4. Reconstruct TOON format

    Args:
        toon_output: TOON formatted string to optimize.
        threshold: Importance threshold (0.0-1.0).
        dependency_counts: Optional mapping of element name → dependency count.
        call_frequencies: Optional mapping of element name → call frequency.

    Returns:
        Optimized TOON formatted string.
    """
    if not toon_output or not toon_output.strip():
        return toon_output

    # Parse elements
    elements = parse_toon_elements(toon_output)

    # Enrich with dependency and call frequency data
    dep_counts = dependency_counts or {}
    call_freqs = call_frequencies or {}

    enriched_elements = []
    for el in elements:
        enriched_elements.append(
            CodeElement(
                name=el.name,
                element_type=el.element_type,
                complexity=el.complexity,
                dependency_count=dep_counts.get(el.name, 0),
                call_frequency=call_freqs.get(el.name, 0),
                line_number=el.line_number,
                metadata=el.metadata,
            )
        )

    # Filter by importance
    filtered = filter_by_importance(enriched_elements, threshold)

    # Reconstruct TOON format
    result_lines = []
    for el in filtered:
        indent = "  " if el.element_type == "method" else ""
        complexity_note = f" [complexity: {el.complexity}]"
        func_parens = "()" if el.element_type in ("function", "method") else ""
        result_lines.append(f"{indent}{el.name}{func_parens}{complexity_note}")

    return "\n".join(result_lines)


def calculate_compression_ratio(original: str, optimized: str) -> float:
    """Calculate compression ratio.

    Args:
        original: Original TOON output.
        optimized: Optimized TOON output.

    Returns:
        Compression ratio (0.0-1.0, where 0.5 = 50% reduction).
    """
    if not original:
        return 0.0

    original_len = len(original)
    optimized_len = len(optimized)

    if original_len == 0:
        return 0.0

    return 1.0 - (optimized_len / original_len)
