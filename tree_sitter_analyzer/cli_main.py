#!/usr/bin/env python3
"""CLI Main Module - Entry point for command-line interface."""

import argparse
import logging
import os
import sys
from typing import Any

from .cli.argument_parser import create_argument_parser
from .cli.argument_validator import CLIArgumentValidator

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
from .cli.special_commands import SpecialCommandHandler
from .output_manager import output_error, output_info


class CLICommandFactory:
    """Factory for creating CLI commands based on arguments."""

    @staticmethod
    def create_command(args: argparse.Namespace) -> Any:
        """Create appropriate command based on arguments."""

        # Validate argument combinations first
        validator = CLIArgumentValidator()
        validation_error = validator.validate_arguments(args)
        if validation_error:
            output_error(validation_error)
            output_info(validator.get_usage_examples())
            return None

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

        # Handle table command with or without query-key
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


def main() -> None:
    """Main entry point for the CLI."""
    # Early check for quiet mode to set environment variable before any imports
    if "--quiet" in sys.argv:
        os.environ["LOG_LEVEL"] = "ERROR"
    else:
        # Set default log level to ERROR to prevent log output in CLI
        os.environ["LOG_LEVEL"] = "ERROR"

    parser = create_argument_parser()
    args = parser.parse_args()

    # Handle --format alias for --output-format
    if hasattr(args, "format") and args.format:
        args.output_format = args.format

    # Configure all logging to ERROR level to prevent output contamination
    logging.getLogger().setLevel(logging.ERROR)
    logging.getLogger("tree_sitter_analyzer").setLevel(logging.ERROR)
    logging.getLogger("tree_sitter_analyzer.performance").setLevel(logging.ERROR)
    logging.getLogger("tree_sitter_analyzer.plugins").setLevel(logging.ERROR)
    logging.getLogger("tree_sitter_analyzer.plugins.manager").setLevel(logging.ERROR)

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
    special_result = SpecialCommandHandler.handle(args)
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
