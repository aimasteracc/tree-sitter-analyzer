#!/usr/bin/env python3
"""
Standalone CLI for semantic code search.

Provides natural language and pattern-based code search using query classification,
fast path execution (grep/ripgrep), and LLM fallback for complex queries.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from ...output_manager import output_data, output_error, output_info, set_output_mode
from ...project_detector import detect_project_root
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


def _build_parser() -> argparse.ArgumentParser:
    """Build argument parser for semantic search CLI."""
    parser = argparse.ArgumentParser(
        description="Semantic code search using query classification and LLM understanding.",
        epilog="""
Examples:
  # Simple pattern matching (fast path)
  %(prog)s --query "functions named authenticate"
  %(prog)s --query "all database in python files"

  # Complex semantic queries (LLM path)
  %(prog)s --query "functions that call database but don't handle errors"
  %(prog)s --query "all endpoints that use input without validation"

  # Output formats
  %(prog)s --query "test functions" --format text
  %(prog)s --query "API endpoints" --format json
  %(prog)s --query "controllers" --format toon
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--query",
        required=True,
        help="Search query (natural language or pattern)",
    )

    parser.add_argument(
        "--format",
        choices=["text", "json", "toon"],
        default="text",
        help="Output format: 'text' (default), 'json', or 'toon'",
    )

    parser.add_argument(
        "--project-root",
        help="Project root directory (auto-detected if omitted)",
    )

    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=60,
        help="Cache TTL in minutes (default: 60)",
    )

    parser.add_argument(
        "--llm-provider",
        choices=["anthropic", "openai"],
        default="anthropic",
        help="LLM provider for complex queries (default: anthropic)",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable query caching",
    )

    parser.add_argument(
        "--show-cache-stats",
        action="store_true",
        help="Show cache statistics and exit",
    )

    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the query cache and exit",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )

    return parser


async def _run(args: argparse.Namespace) -> int:
    """Run the semantic search."""
    set_output_mode(quiet=bool(args.quiet), json_output=(args.format == "json"))

    project_root = detect_project_root(None, args.project_root)

    # Initialize components
    classifier = QueryClassifier()
    executor = FastPathExecutor(project_root=str(project_root))

    llm_provider = (
        LLMProvider.ANTHROPIC
        if args.llm_provider == "anthropic"
        else LLMProvider.OPENAI
    )
    llm = LLMIntegration(preferred_provider=llm_provider)

    cache = QueryCache(
        project_root=str(project_root),
        ttl_minutes=args.cache_ttl,
    )
    formatter = SearchResultFormatter()

    # Handle cache management commands
    if args.show_cache_stats:
        stats = cache.get_stats()
        output_data(
            {
                "total_queries": stats.total_queries,
                "cache_hits": stats.cache_hits,
                "cache_misses": stats.cache_misses,
                "hit_rate": f"{stats.hit_rate():.1%}",
                "invalidations": stats.invalidations,
            }
        )
        return 0

    if args.clear_cache:
        cache.clear()
        output_info("Cache cleared")
        return 0

    # Sanitize query
    sanitized_query = args.query.strip()[:500]

    try:
        # Step 1: Classify the query
        classification = classifier.classify(sanitized_query)

        if not args.quiet:
            output_info(
                f"Query type: {classification.query_type.value} "
                f"(confidence: {classification.confidence:.2f})"
            )

        # Step 2: Check cache (unless disabled)
        handler_name = classification.params.get("handler", "unknown")

        if not args.no_cache:
            cached_results = cache.get(sanitized_query, handler_name)
            if cached_results is not None:
                if not args.quiet:
                    output_info("Cache hit - returning cached results")

                output = formatter.format(
                    cached_results,
                    format_type=args.format,
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
            result = executor.execute(
                handler=handler_name,
                params=classification.params.get("params", {}),
            )

            if not result.success:
                error_output = format_search_error(
                    result.error or "Unknown error",
                    args.format,
                )
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
            if not args.quiet:
                output_info("Using LLM for semantic understanding...")

            available_tools = [
                "grep_by_name",
                "grep_in_files",
                "dependency_of",
                "what_calls",
            ]

            llm_result = llm.parse_query(sanitized_query, available_tools)

            if not llm_result.tool_calls:
                error_output = format_search_error(
                    "LLM could not parse the query",
                    args.format,
                )
                output_error(error_output)
                return 1

            # Execute the first suggested tool call
            tool_call = llm_result.tool_calls[0]
            result = executor.execute(
                handler=tool_call.tool_name,
                params=tool_call.parameters,
            )

            if not result.success:
                error_output = format_search_error(
                    result.error or "Unknown error",
                    args.format,
                )
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
        if not args.no_cache:
            cache.set(sanitized_query, handler_name, results)

        # Step 5: Format and output results
        output = formatter.format(results, format_type=args.format, metadata=metadata)
        output_data(output)

        return 0

    except Exception as e:
        output_error(f"Search failed: {e}")
        return 1


def main() -> int:
    """Entry point for semantic search CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
