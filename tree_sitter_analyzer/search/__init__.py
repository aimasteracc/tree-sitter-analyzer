"""
Semantic Code Search Module

Provides query classification, fast path execution, LLM integration, and result formatting
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
from tree_sitter_analyzer.search.llm_integration import (
    AnthropicClient,
    LLMClient,
    LLMIntegration,
    LLMProvider,
    LLMResult,
    OpenAIClient,
    ToolCall,
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
    "LLMIntegration",
    "LLMProvider",
    "LLMResult",
    "ToolCall",
    "OpenAIClient",
    "AnthropicClient",
    "LLMClient",
]
