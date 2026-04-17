"""
Query Classifier Module

Classifies user queries into simple (fast path) or complex (LLM path) based on
regex pattern matching. Simple queries use deterministic tools (grep, ast-grep)
while complex queries require semantic understanding via LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class QueryType(Enum):
    """Query classification types."""
    SIMPLE = "simple"  # Fast path: grep/ast-grep
    COMPLEX = "complex"  # LLM path: semantic understanding


@dataclass
class ClassificationResult:
    """Result of query classification."""
    query_type: QueryType
    params: dict[str, Any]
    confidence: float  # 0.0 to 1.0
    matched_pattern: str | None = None


class FastPathHandler:
    """Handler type for fast path queries."""

    def __init__(
        self,
        name: str,
        pattern: str,
        handler_func: str,
        description: str,
    ) -> None:
        """
        Initialize a fast path handler.

        Args:
            name: Handler name (e.g., "grep_by_name")
            pattern: Regex pattern to match queries
            handler_func: Name of executor method to call
            description: Human-readable description
        """
        self.name = name
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.handler_func = handler_func
        self.description = description


class QueryClassifier:
    """
    Classifies queries and extracts parameters for fast path execution.

    Uses regex pattern matching to identify simple queries that can be handled
    by deterministic tools (grep, ast-grep, existing MCP tools) vs complex queries
    that require LLM semantic understanding.
    """

    # Predefined fast path patterns (simple → complex precedence)
    FAST_PATH_PATTERNS = [
        FastPathHandler(
            name="grep_by_name",
            pattern=r"functions?\s+(?P<action>named|containing)\s+(?P<name>\w+)",
            handler_func="grep_by_name",
            description="Find functions by name",
        ),
        FastPathHandler(
            name="grep_in_files",
            pattern=r"all\s+(?P<term>\w+(?:\s+\w+)*)\s+in\s+(?P<filetype>\w+)\s+files?",
            handler_func="grep_in_files",
            description="Find code in specific file types",
        ),
        FastPathHandler(
            name="dependency_of",
            pattern=r"dependen(cies|cy)\s+of|calls?\s+from\s+(?P<symbol>\w+)",
            handler_func="dependency_of",
            description="Find dependencies of a symbol",
        ),
        FastPathHandler(
            name="what_calls",
            pattern=r"what\s+calls?\s+(?P<symbol>\w+)",
            handler_func="what_calls",
            description="Find what calls a symbol",
        ),
    ]

    # Complex query patterns (require LLM)
    # These patterns detect semantic query structures
    COMPLEX_PATTERNS = [
        r"\w+\s+that\s+.*\s+but\s+",  # Conditional logic: X that Y but Z
        r"\w+\s+that\s+.*\s+without\s+",  # Negative constraints: X that Y without Z
        r"all\s+\w+\s+that\s+.*\s+without\s+",  # Negative with "all"
        r"find\s+.*\s+that\s+.*\s+but\s+",  # Find queries with conditions
        r"find\s+.*\s+that\s+.*\s+without\s+",  # Find queries with negative constraints
    ]

    def __init__(self) -> None:
        """Initialize the query classifier."""
        self._custom_patterns: list[FastPathHandler] = []

    def classify(self, query: str) -> ClassificationResult:
        """
        Classify query and extract parameters.

        Checks fast path patterns first (precedence rule). If no match,
        checks complex patterns. If still no match, defaults to COMPLEX
        (LLM path) with low confidence.

        Args:
            query: User query string

        Returns:
            ClassificationResult with query type and extracted parameters
        """
        # Check fast path patterns first (precedence rule)
        for handler in self.FAST_PATH_PATTERNS + self._custom_patterns:
            match = handler.pattern.search(query)
            if match:
                params = match.groupdict() if match.groupdict() else {}
                return ClassificationResult(
                    query_type=QueryType.SIMPLE,
                    params={
                        "handler": handler.handler_func,
                        "params": params,
                        "pattern_name": handler.name,
                    },
                    confidence=0.9,
                    matched_pattern=handler.pattern.pattern,
                )

        # Check complex patterns
        for pattern in self.COMPLEX_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return ClassificationResult(
                    query_type=QueryType.COMPLEX,
                    params={},
                    confidence=0.8,
                    matched_pattern=pattern,
                )

        # Default: complex (LLM path) with low confidence
        return ClassificationResult(
            query_type=QueryType.COMPLEX,
            params={},
            confidence=0.3,
            matched_pattern=None,
        )

    def add_pattern(
        self,
        pattern: str,
        handler: str,
        name: str,
        description: str = "",
    ) -> None:
        """
        Add a new fast path pattern.

        Args:
            pattern: Regex pattern to match queries
            handler: Name of executor method to call
            name: Handler name
            description: Human-readable description
        """
        new_handler = FastPathHandler(
            name=name,
            pattern=pattern,
            handler_func=handler,
            description=description,
        )
        self._custom_patterns.append(new_handler)

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about pattern usage.

        Returns:
            Dictionary with pattern counts (for adaptive learning)
        """
        # This will be populated during query execution
        return {
            "total_queries": 0,
            "fast_path_count": 0,
            "llm_path_count": 0,
            "pattern_matches": {},
        }
