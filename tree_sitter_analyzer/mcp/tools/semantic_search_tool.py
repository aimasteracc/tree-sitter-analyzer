#!/usr/bin/env python3
"""
Semantic Search MCP Tool

Provides natural language and pattern-based code search as an MCP tool.
Integrates query classification, fast path execution, LLM fallback, and caching.
"""

from __future__ import annotations

from typing import Any

from ...formatters.toon_encoder import ToonEncoder
from ...search import (
    ExecutionResult,
    FastPathExecutor,
    LLMIntegration,
    LLMProvider,
    QueryCache,
    QueryClassifier,
    QueryType,
    SearchResultFormatter,
)


class SemanticSearchTool:
    """
    Semantic code search tool with query classification and LLM understanding.

    Features:
    - Query classification (simple vs complex)
    - Fast path execution for simple queries (grep/ripgrep)
    - LLM fallback for complex semantic queries
    - Git SHA-based cache invalidation
    - Multiple output formats (text, JSON, TOON)
    """

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize the semantic search tool.

        Args:
            project_root: Root directory of the project to search
        """
        self.project_root = project_root

        # Initialize search components
        self.classifier = QueryClassifier()
        self.executor = FastPathExecutor(project_root=project_root)
        self.llm = LLMIntegration(preferred_provider=LLMProvider.ANTHROPIC)
        self.cache = QueryCache(project_root=project_root)
        self.formatter = SearchResultFormatter()

    def get_name(self) -> str:
        """Get the tool name."""
        return "semantic_search"

    def get_description(self) -> str:
        """Get the tool description."""
        return """Semantic code search using natural language and pattern-based queries.

Features:
- Query classification for fast/slow path routing
- Fast path: grep/ripgrep for simple patterns (<1s)
- LLM path: semantic understanding for complex queries (<5s)
- Git SHA-based cache invalidation
- Multiple output formats (text, JSON, TOON)

Example queries:
- "functions named authenticate"
- "all database in python files"
- "functions that call database but don't handle errors"
- "API endpoints without authentication"

Parameters:
- query (required): Natural language or pattern query
- format (optional): Output format - "text", "json", or "toon" (default: "text")
- use_cache (optional): Enable/disable caching (default: true)
- llm_provider (optional): "anthropic" or "openai" (default: "anthropic")
"""

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get MCP tool definition.

        Returns:
            Tool definition dictionary
        """
        return {
            "name": "semantic_search",
            "description": self.get_description(),
            "inputSchema": {
                "type": "object",
                "properties": self.get_parameters()["properties"],
                "required": self.get_parameters()["required"],
            },
        }

    def get_parameters(self) -> dict[str, Any]:
        """Get the tool parameters schema."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language or pattern-based search query",
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "json", "toon"],
                    "description": "Output format (default: text)",
                },
                "use_cache": {
                    "type": "boolean",
                    "description": "Enable query caching (default: true)",
                },
                "llm_provider": {
                    "type": "string",
                    "enum": ["anthropic", "openai"],
                    "description": "LLM provider for complex queries (default: anthropic)",
                },
            },
            "required": ["query"],
        }

    def _format_results(
        self,
        results: list[dict[str, Any]],
        format_type: str,
        metadata: dict[str, Any],
    ) -> str:
        """
        Format results for output.

        Args:
            results: Search results to format
            format_type: Output format type
            metadata: Additional metadata to include

        Returns:
            Formatted output string
        """
        if format_type == "toon":
            # Use TOON encoder for compressed output
            encoder = ToonEncoder()

            formatted_data = {
                "results": results,
                "metadata": metadata,
                "count": len(results),
            }

            return encoder.encode(formatted_data)
        else:
            # Use standard formatter
            return self.formatter.format(results, format_type=format_type, metadata=metadata)

    def execute(self, arguments: dict[str, Any]) -> str:
        """
        Execute the semantic search.

        Args:
            arguments: Tool arguments from the MCP request

        Returns:
            Formatted search results
        """
        query = arguments.get("query", "")
        if not query:
            return self.formatter.format([], format_type="text", metadata={"error": "No query provided"})

        format_type = arguments.get("format", "text")
        use_cache = arguments.get("use_cache", True)
        llm_provider_name = arguments.get("llm_provider", "anthropic")

        # Set LLM provider
        if llm_provider_name == "openai":
            self.llm = LLMIntegration(preferred_provider=LLMProvider.OPENAI)
        else:
            self.llm = LLMIntegration(preferred_provider=LLMProvider.ANTHROPIC)

        try:
            # Step 1: Classify the query
            classification = self.classifier.classify(query)

            # Step 2: Check cache (if enabled)
            handler_name = classification.params.get("handler", "unknown")

            if use_cache:
                cached_results = self.cache.get(query, handler_name)
                if cached_results is not None:
                    return self._format_results(
                        cached_results,
                        format_type,
                        metadata={
                            "query": query,
                            "cached": True,
                            "execution_time": 0.0,
                        },
                    )

            # Step 3: Execute based on classification
            if classification.query_type == QueryType.SIMPLE:
                # Fast path execution
                result: ExecutionResult = self.executor.execute(
                    handler=handler_name,
                    params=classification.params.get("params", {}),
                )

                if not result.success:
                    error_msg = result.error or "Unknown error"
                    return self.formatter.format([], format_type=format_type, metadata={"error": error_msg})

                results = result.results
                metadata = {
                    "query": query,
                    "cached": False,
                    "execution_time": result.execution_time,
                    "tool_used": result.tool_used,
                    "confidence": classification.confidence,
                }

            else:
                # LLM path for complex queries
                available_tools = [
                    "grep_by_name",
                    "grep_in_files",
                    "dependency_of",
                    "what_calls",
                ]

                llm_result = self.llm.parse_query(query, available_tools)

                if not llm_result.tool_calls:
                    return self.formatter.format(
                        [],
                        format_type=format_type,
                        metadata={"error": "LLM could not parse the query"},
                    )

                # Execute the first suggested tool call
                tool_call = llm_result.tool_calls[0]
                result = self.executor.execute(
                    handler=tool_call.tool_name,
                    params=tool_call.parameters,
                )

                if not result.success:
                    error_msg = result.error or "Unknown error"
                    return self.formatter.format([], format_type=format_type, metadata={"error": error_msg})

                results = result.results
                metadata = {
                    "query": query,
                    "cached": False,
                    "execution_time": result.execution_time + llm_result.execution_time,
                    "tool_used": f"LLM + {result.tool_used}",
                    "llm_provider": llm_result.provider_used.value,
                    "reasoning": tool_call.reasoning or "",
                    "confidence": classification.confidence,
                }

            # Step 4: Cache the results (if enabled)
            if use_cache:
                self.cache.set(query, handler_name, results)

            # Step 5: Format and return results
            return self._format_results(results, format_type, metadata)

        except Exception as e:
            error_msg = f"Search failed: {e}"
            return self.formatter.format([], format_type=format_type, metadata={"error": error_msg})
