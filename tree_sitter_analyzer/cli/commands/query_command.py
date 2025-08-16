#!/usr/bin/env python3
"""
Query Command

Handles query execution functionality.
"""

from ...core.query_service import QueryService
from ...output_manager import output_data, output_error, output_info, output_json
from .base_command import BaseCommand


class QueryCommand(BaseCommand):
    """Command for executing queries."""

    def __init__(self, args):
        """Initialize the query command with QueryService."""
        super().__init__(args)
        self.query_service = QueryService()

    async def execute_query(
        self, language: str, query: str, query_name: str = "custom"
    ) -> list[dict] | None:
        """Execute a specific tree-sitter query using QueryService."""
        try:
            # Get filter expression if provided
            filter_expression = getattr(self.args, "filter", None)

            if query_name != "custom":
                # Use predefined query key
                results = await self.query_service.execute_query(
                    self.args.file_path,
                    language,
                    query_key=query_name,
                    filter_expression=filter_expression,
                )
            else:
                # Use custom query string
                results = await self.query_service.execute_query(
                    self.args.file_path,
                    language,
                    query_string=query,
                    filter_expression=filter_expression,
                )

            return results

        except Exception as e:
            output_error(f"Query execution failed: {e}")
            return None

    async def execute_async(self, language: str) -> int:
        # Get the query to execute
        query_to_execute = None

        if hasattr(self.args, "query_key") and self.args.query_key:
            # Sanitize query key input
            sanitized_query_key = self.security_validator.sanitize_input(
                self.args.query_key, max_length=100
            )
            # Check if query exists
            available_queries = self.query_service.get_available_queries(language)
            if sanitized_query_key not in available_queries:
                output_error(
                    f"Query '{sanitized_query_key}' not found for language '{language}'"
                )
                return 1
            # Store query name - QueryService will resolve the query string
            query_to_execute = sanitized_query_key  # This is actually the query key now
            query_name = sanitized_query_key
        elif hasattr(self.args, "query_string") and self.args.query_string:
            # Security check for query string (potential regex patterns)
            is_safe, error_msg = self.security_validator.regex_checker.validate_pattern(
                self.args.query_string
            )
            if not is_safe:
                output_error(f"Unsafe query pattern: {error_msg}")
                return 1
            query_to_execute = self.args.query_string
            query_name = "custom"

        if not query_to_execute:
            output_error("No query specified.")
            return 1

        # Execute specific query
        results = await self.execute_query(language, query_to_execute, query_name)
        if results is None:
            return 1

        # Output results
        if results:
            if self.args.output_format == "json":
                output_json(results)
            else:
                for i, query_result in enumerate(results, 1):
                    output_data(
                        f"\n{i}. {query_result['capture_name']} ({query_result['node_type']})"
                    )
                    output_data(
                        f"   Position: Line {query_result['start_line']}-{query_result['end_line']}"
                    )
                    output_data(f"   Content:\n{query_result['content']}")
        else:
            output_info("\nINFO: No results found matching the query.")

        return 0
