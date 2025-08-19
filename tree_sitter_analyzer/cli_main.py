#!/usr/bin/env python3
"""CLI Main Module - Entry point for command-line interface."""

import argparse
import logging
import os
import sys
from typing import Any

# Import command classes
from .cli.commands import (
    AdvancedCommand,
    DefaultCommand,
    PartialReadCommand,
    QueryCommand,
    StructureCommand,
    SummaryCommand,
    TableCommand,
)
from .cli.info_commands import (
    DescribeQueryCommand,
    ListQueriesCommand,
    ShowExtensionsCommand,
    ShowLanguagesCommand,
)
from .output_manager import output_error, output_info, output_list
from .query_loader import query_loader


class CLICommandFactory:
    """Factory for creating CLI commands based on arguments."""

    @staticmethod
    def create_command(args: argparse.Namespace) -> Any:
        """Create appropriate command based on arguments."""

        # Information commands (no file analysis required)
        if args.list_queries:
            return ListQueriesCommand(args)

        if args.describe_query:
            return DescribeQueryCommand(args)

        if args.show_supported_languages:
            return ShowLanguagesCommand(args)

        if args.show_supported_extensions:
            return ShowExtensionsCommand(args)

        if args.filter_help:
            from tree_sitter_analyzer.core.query_filter import QueryFilter

            filter_service = QueryFilter()
            output_info(filter_service.get_filter_help())
            return None  # This will exit with code 0

        # File analysis commands (require file path)
        if not args.file_path:
            return None

        # Partial read command - highest priority for file operations
        if hasattr(args, "partial_read") and args.partial_read:
            return PartialReadCommand(args)

        if hasattr(args, "table") and args.table:
            return TableCommand(args)

        if hasattr(args, "structure") and args.structure:
            return StructureCommand(args)

        if hasattr(args, "summary") and args.summary is not None:
            return SummaryCommand(args)

        if hasattr(args, "advanced") and args.advanced:
            return AdvancedCommand(args)

        if hasattr(args, "query_key") and args.query_key:
            return QueryCommand(args)

        if hasattr(args, "query_string") and args.query_string:
            return QueryCommand(args)

        # Default command - if file_path is provided but no specific command, use default analysis
        return DefaultCommand(args)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Analyze code using Tree-sitter and extract structured information.",
        epilog="Example: tree-sitter-analyzer example.java --table=full",
    )

    # File path
    parser.add_argument("file_path", nargs="?", help="Path to the file to analyze")

    # Query options
    query_group = parser.add_mutually_exclusive_group(required=False)
    query_group.add_argument(
        "--query-key", help="Available query key (e.g., class, method)"
    )
    query_group.add_argument(
        "--query-string", help="Directly specify Tree-sitter query to execute"
    )

    # Query filter options
    parser.add_argument(
        "--filter",
        help="Filter query results (e.g., 'name=main', 'name=~get*,public=true')",
    )

    # Information options
    parser.add_argument(
        "--list-queries",
        action="store_true",
        help="Display list of available query keys",
    )
    parser.add_argument(
        "--filter-help",
        action="store_true",
        help="Display help for query filter syntax",
    )
    parser.add_argument(
        "--describe-query", help="Display description of specified query key"
    )
    parser.add_argument(
        "--show-supported-languages",
        action="store_true",
        help="Display list of supported languages",
    )
    parser.add_argument(
        "--show-supported-extensions",
        action="store_true",
        help="Display list of supported file extensions",
    )
    parser.add_argument(
        "--show-common-queries",
        action="store_true",
        help="Display list of common queries across multiple languages",
    )
    parser.add_argument(
        "--show-query-languages",
        action="store_true",
        help="Display list of languages with query support",
    )

    # Output format options
    parser.add_argument(
        "--output-format",
        choices=["json", "text"],
        default="json",
        help="Specify output format",
    )
    parser.add_argument(
        "--table", choices=["full", "compact", "csv"], help="Output in table format"
    )
    parser.add_argument(
        "--include-javadoc",
        action="store_true",
        help="Include JavaDoc/documentation comments in output",
    )

    # Analysis options
    parser.add_argument(
        "--advanced", action="store_true", help="Use advanced analysis features"
    )
    parser.add_argument(
        "--summary",
        nargs="?",
        const="classes,methods",
        help="Display summary of specified element types",
    )
    parser.add_argument(
        "--structure",
        action="store_true",
        help="Output detailed structure information in JSON format",
    )
    parser.add_argument(
        "--statistics", action="store_true", help="Display only statistical information"
    )

    # Language options
    parser.add_argument(
        "--language",
        help="Explicitly specify language (auto-detected from extension if omitted)",
    )

    # Project options
    parser.add_argument(
        "--project-root",
        help="Project root directory for security validation (auto-detected if not specified)",
    )

    # Logging options
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress INFO level logs (show errors only)",
    )

    # Partial reading options
    parser.add_argument(
        "--partial-read",
        action="store_true",
        help="Enable partial file reading mode",
    )
    parser.add_argument(
        "--start-line", type=int, help="Starting line number for reading (1-based)"
    )
    parser.add_argument(
        "--end-line", type=int, help="Ending line number for reading (1-based)"
    )
    parser.add_argument(
        "--start-column", type=int, help="Starting column number for reading (0-based)"
    )
    parser.add_argument(
        "--end-column", type=int, help="Ending column number for reading (0-based)"
    )

    return parser


def handle_special_commands(args: argparse.Namespace) -> int | None:
    """Handle special commands that don't fit the normal pattern."""

    # Validate partial read options
    if hasattr(args, "partial_read") and args.partial_read:
        if args.start_line is None:
            output_error("--start-line is required")
            return 1

        if args.start_line < 1:
            output_error("--start-line must be 1 or greater")
            return 1

        if args.end_line and args.end_line < args.start_line:
            output_error("--end-line must be greater than or equal to --start-line")
            return 1

        if args.start_column is not None and args.start_column < 0:
            output_error("--start-column must be 0 or greater")
            return 1

        if args.end_column is not None and args.end_column < 0:
            output_error("--end-column must be 0 or greater")
            return 1

    # Query language commands
    if args.show_query_languages:
        output_list(["Languages with query support:"])
        for lang in query_loader.list_supported_languages():
            query_count = len(query_loader.list_queries_for_language(lang))
            output_list([f"  {lang:<15} ({query_count} queries)"])
        return 0

    if args.show_common_queries:
        common_queries = query_loader.get_common_queries()
        if common_queries:
            output_list("Common queries across multiple languages:")
            for query in common_queries:
                output_list(f"  {query}")
        else:
            output_info("No common queries found.")
        return 0

    return None


def main() -> None:
    """Main entry point for the CLI."""
    # Early check for quiet mode to set environment variable before any imports
    if "--quiet" in sys.argv:
        os.environ["LOG_LEVEL"] = "ERROR"
    else:
        # Set default log level to WARNING to reduce output
        os.environ.setdefault("LOG_LEVEL", "WARNING")

    parser = create_argument_parser()
    args = parser.parse_args()

    # Configure default logging levels to reduce output
    logging.getLogger("tree_sitter_analyzer.performance").setLevel(logging.ERROR)

    # Configure logging for table output
    if hasattr(args, "table") and args.table:
        logging.getLogger().setLevel(logging.ERROR)
        logging.getLogger("tree_sitter_analyzer").setLevel(logging.ERROR)
        logging.getLogger("tree_sitter_analyzer.performance").setLevel(logging.ERROR)

    # Configure logging for quiet mode
    if hasattr(args, "quiet") and args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
        logging.getLogger("tree_sitter_analyzer").setLevel(logging.ERROR)
        logging.getLogger("tree_sitter_analyzer.performance").setLevel(logging.ERROR)

    # Handle special commands first
    special_result = handle_special_commands(args)
    if special_result is not None:
        sys.exit(special_result)

    # Create and execute command
    command = CLICommandFactory.create_command(args)

    if command:
        exit_code = command.execute()
        sys.exit(exit_code)
    elif command is None and hasattr(args, "filter_help") and args.filter_help:
        # filter_help was processed successfully
        sys.exit(0)
    else:
        if not args.file_path:
            output_error("File path not specified.")
        else:
            output_error("No executable command specified.")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        output_info("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        output_error(f"Unexpected error: {e}")
        sys.exit(1)
