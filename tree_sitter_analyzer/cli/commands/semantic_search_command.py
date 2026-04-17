#!/usr/bin/env python3
"""
Semantic Search Command

Handles semantic code search functionality using query classification,
fast path execution, and LLM integration.
"""

from typing import Any

from ...output_manager import output_data, output_error, output_info
from ...search import (
    FastPathExecutor,
    LLMIntegration,
    LLMProvider,
    QueryCache,
    QueryClassifier,
    QueryType,
    SearchResultFormatter,
    format_search_error,
)
from .base_command import BaseCommand


class SemanticSearchCommand(BaseCommand):
    """Command for semantic code search."""

    def __init__(self, args: Any) -> None:
        """Initialize the semantic search command."""
        super().__init__(args)

        # Initialize components
        self.classifier = QueryClassifier()
        self.executor = FastPathExecutor(project_root=getattr(args, "project_root", None))
        self.llm = LLMIntegration(
            preferred_provider=LLMProvider.ANTHROPIC,
        )
        self.cache = QueryCache(project_root=getattr(args, "project_root", None))
        self.formatter = SearchResultFormatter()

    async def execute_async(self, language: str = "unknown") -> int:
        """
        Execute the semantic search command.

        Args:
            language: Detected/specified target language (ignored for semantic search)

        Returns:
            Exit code (0 for success, 1 for error)
        """
        # Semantic search doesn't need language detection, but we keep the parameter
        # for compatibility with BaseCommand interface
        _ = language  # Mark as intentionally unused
        # Get query from arguments
        query = getattr(self.args, "query", None)
        if not query:
            output_error("No query provided. Use --query to specify a search query.")
            return 1

        # Get format type
        format_type = getattr(self.args, "format", "text")

        # Sanitize query input
        sanitized_query = self.security_validator.sanitize_input(query, max_length=500)

        try:
            # Step 1: Classify the query
            classification = self.classifier.classify(sanitized_query)

            output_info(
                f"Query type: {classification.query_type.value} "
                f"(confidence: {classification.confidence:.2f})"
            )

            # Step 2: Check cache first
            handler_name = classification.params.get("handler", "unknown")
            cached_results = self.cache.get(sanitized_query, handler_name)

            if cached_results is not None:
                output_info("Cache hit - returning cached results")
                output = self.formatter.format(
                    cached_results,
                    format_type=format_type,
                    metadata={
                        "query": sanitized_query,
                        "cached": True,
                        "execution_time": 0.0,
                    },
                )
                output_data(output)
                return 0

            # Step 3: Execute based on classification
            if classification.query_type == QueryType.SIMPLE:
                # Fast path execution
                result = self.executor.execute(
                    handler=handler_name,
                    params=classification.params.get("params", {}),
                )

                if not result.success:
                    error_output = format_search_error(result.error or "Unknown error", format_type)
                    output_error(error_output)
                    return 1

                results = result.results
                metadata = {
                    "query": sanitized_query,
                    "cached": False,
                    "execution_time": result.execution_time,
                    "tool_used": result.tool_used,
                }

            else:
                # LLM path for complex queries
                output_info("Using LLM for semantic understanding...")

                available_tools = [
                    "grep_by_name",
                    "grep_in_files",
                    "dependency_of",
                    "what_calls",
                ]

                llm_result = self.llm.parse_query(sanitized_query, available_tools)

                if not llm_result.tool_calls:
                    error_output = format_search_error(
                        "LLM could not parse the query",
                        format_type,
                    )
                    output_error(error_output)
                    return 1

                # Execute the first suggested tool call
                tool_call = llm_result.tool_calls[0]
                result = self.executor.execute(
                    handler=tool_call.tool_name,
                    params=tool_call.parameters,
                )

                if not result.success:
                    error_output = format_search_error(result.error or "Unknown error", format_type)
                    output_error(error_output)
                    return 1

                results = result.results
                metadata = {
                    "query": sanitized_query,
                    "cached": False,
                    "execution_time": result.execution_time + llm_result.execution_time,
                    "tool_used": f"LLM + {result.tool_used}",
                    "llm_provider": llm_result.provider_used.value,
                    "reasoning": tool_call.reasoning or "",
                }

            # Step 4: Cache the results
            self.cache.set(sanitized_query, handler_name, results)

            # Step 5: Format and output results
            output = self.formatter.format(results, format_type=format_type, metadata=metadata)
            output_data(output)

            return 0

        except Exception as e:
            output_error(f"Search failed: {e}")
            return 1
