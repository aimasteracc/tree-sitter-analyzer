#!/usr/bin/env python3
"""
CLI Argument Validator

Validates CLI argument combinations and provides clear error messages.
"""

from typing import Any


class CLIArgumentValidator:
    """Validator for CLI argument combinations."""

    def __init__(self):
        """Initialize the validator."""
        pass

    def validate_arguments(self, args: Any) -> str | None:
        """
        Validate CLI argument combinations.

        Args:
            args: Parsed command line arguments

        Returns:
            None if valid, error message string if invalid
        """
        # Check for --table and --query-key combination
        table_specified = (
            hasattr(args, "table") and args.table is not None and args.table != ""
        )
        query_key_specified = (
            hasattr(args, "query_key")
            and args.query_key is not None
            and args.query_key != ""
        )

        if table_specified and query_key_specified:
            return "--table and --query-key cannot be used together. Use --query-key with --filter instead."

        # All validations passed
        return None

    def validate_table_query_exclusivity(self, args: Any) -> str | None:
        """
        Validate that --table and --query-key are mutually exclusive.

        Args:
            args: Parsed command line arguments

        Returns:
            None if valid, error message string if invalid
        """
        table_specified = (
            hasattr(args, "table") and args.table is not None and args.table != ""
        )
        query_key_specified = (
            hasattr(args, "query_key")
            and args.query_key is not None
            and args.query_key != ""
        )

        if table_specified and query_key_specified:
            return "--table and --query-key cannot be used together. Use --query-key with --filter instead."

        return None

    def get_usage_examples(self) -> str:
        """
        Get usage examples for correct argument combinations.

        Returns:
            String containing usage examples
        """
        return """
Correct usage examples:

# Use table format only:
uv run python -m tree_sitter_analyzer examples/BigService.java --table full

# Use query-key only:
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods

# Use query-key with filter:
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# Invalid combination (will cause error):
uv run python -m tree_sitter_analyzer examples/BigService.java --table full --query-key methods
"""
