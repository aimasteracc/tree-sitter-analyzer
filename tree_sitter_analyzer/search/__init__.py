"""
Semantic Code Search Module

Provides query classification, fast path execution, and result formatting
for the semantic code search feature.
"""
from __future__ import annotations

from tree_sitter_analyzer.search.classifier import (
    ClassificationResult,
    FastPathHandler,
    QueryClassifier,
    QueryType,
)
from tree_sitter_analyzer.search.executor import ExecutionResult, FastPathExecutor
from tree_sitter_analyzer.search.formatter import (
    SearchResultFormatter,
    format_search_error,
)

__all__ = [
    "QueryClassifier",
    "QueryType",
    "ClassificationResult",
    "FastPathHandler",
    "FastPathExecutor",
    "ExecutionResult",
    "SearchResultFormatter",
    "format_search_error",
]
