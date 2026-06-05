#!/usr/bin/env python3
"""CLI Main Module - Entry point for command-line interface."""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

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
from .output_manager import output_error, output_info, output_list
from .query_loader import query_loader

_NO_COMMAND_MATCH = object()
_FILE_SCOPED_AGENT_COMMANDS = {
    "file-health": "--file-health",
    "safe-to-edit": "--safe-to-edit",
    "refactor": "--refactor",
    "smart-context": "--smart-context",
}
_PROJECT_SCOPED_AGENT_COMMANDS = {
    "agent-skills": "--agent-skills",
    "agent-workflow": "--agent-workflow",
    "change-impact": "--change-impact",
    "detect-routes": "--detect-routes",
    "overview": "--overview",
    "parser-readiness": "--parser-readiness",
    "project-health": "--project-health",
    "test-gap": "--test-gap",
}


class CLICommandFactory:
    """Factory for creating CLI commands based on arguments."""

    @staticmethod
    def create_command(args: argparse.Namespace) -> Any:
        """Create appropriate command based on arguments."""
        if not _validate_command_arguments(args):
            return None

        info_command = _create_info_command(args)
        if info_command is not _NO_COMMAND_MATCH:
            return info_command

        if not getattr(args, "file_path", None):
            return None

        return _create_file_command(args)


def _validate_command_arguments(args: argparse.Namespace) -> bool:
    """Validate CLI argument combinations before selecting a command."""
    validator = CLIArgumentValidator()
    validation_error = validator.validate_arguments(args)
    if not validation_error:
        return True
    output_error(validation_error)
    output_info(validator.get_usage_examples())
    return False


def _create_info_command(args: argparse.Namespace) -> Any:
    """Create commands that do not require a file path."""
    if getattr(args, "list_queries", False):
        return ListQueriesCommand(args)
    if getattr(args, "describe_query", None):
        return DescribeQueryCommand(args)
    if getattr(args, "show_supported_languages", False):
        return ShowLanguagesCommand(args)
    if getattr(args, "show_supported_extensions", False):
        return ShowExtensionsCommand(args)
    if getattr(args, "filter_help", False):
        _print_filter_help(args)
        return None
    return _NO_COMMAND_MATCH


def _print_filter_help(args: argparse.Namespace | None = None) -> None:
    """Print query filter help (text) or emit a JSON envelope.

    r37ai (dogfood): ``--filter-help`` previously ignored
    ``--format json`` and always called ``output_info`` (plain text).
    Agents piping through ``json.loads`` failed. Now mirrors the
    pattern of the other info commands (r37ad/ae): JSON path emits
    canonical envelope keys, text path preserves backward compat.
    """
    from tree_sitter_analyzer.core.query_filter import QueryFilter

    help_text = QueryFilter().get_filter_help()
    from tree_sitter_analyzer.cli.output_format import wants_json_output

    if args is not None and wants_json_output(args):
        from tree_sitter_analyzer.output_manager import output_json

        line_count = help_text.count("\n") + 1
        summary_line = f"filter_help: {line_count} lines of query filter syntax docs"
        output_json(
            {
                "success": True,
                "filter_help": help_text,
                "summary_line": summary_line,
                "verdict": "INFO",
                "agent_summary": {
                    "summary_line": summary_line,
                    "next_step": (
                        "Apply the filter syntax via `--filter='<expression>'` "
                        "when running `--query-key` or `--query-string`."
                    ),
                    "verdict": "INFO",
                },
            }
        )
        return
    output_info(help_text)


def _create_file_command(args: argparse.Namespace) -> Any:
    """Create the highest-priority file-analysis command for parsed arguments."""
    command_specs = (
        ("partial_read", PartialReadCommand),
        ("table", TableCommand),
        ("structure", StructureCommand),
        ("summary", SummaryCommand),
        ("advanced", AdvancedCommand),
        ("query_key", QueryCommand),
        ("query_string", QueryCommand),
    )
    for attr_name, command_cls in command_specs:
        if _argument_is_selected(args, attr_name):
            return command_cls(args)
    return DefaultCommand(args)


def _argument_is_selected(args: argparse.Namespace, attr_name: str) -> bool:
    """Return True when an argparse field selects a command."""
    value = getattr(args, attr_name, None)
    return value is not None if attr_name == "summary" else bool(value)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    from .cli.argument_parser_builder import create_argument_parser as build_parser

    return build_parser()


def handle_special_commands(args: argparse.Namespace) -> int | None:
    """Handle special commands that don't fit the normal pattern."""
    from .cli.special_commands import (
        SpecialCommandContext,
    )
    from .cli.special_commands import (
        handle_special_commands as handle_special,
    )
    from .output_manager import output_json

    return handle_special(
        args,
        SpecialCommandContext(
            asyncio_run=asyncio.run,
            output_json=output_json,
            output_error=output_error,
            output_info=output_info,
            output_list=output_list,
            query_loader=query_loader,
        ),
    )


def main() -> None:
    """Main entry point for the CLI."""
    _set_cli_log_environment()
    parser = create_argument_parser()
    args = parser.parse_args(_normalize_agent_command_aliases(sys.argv[1:]))
    _apply_format_alias(args)
    _configure_logging(args)

    special_result = handle_special_commands(args)
    if special_result is not None:
        sys.exit(special_result)

    _execute_selected_command(args, parser)


def _set_cli_log_environment() -> None:
    """Force CLI logging to stderr-only error noise regardless of quiet mode."""
    os.environ["LOG_LEVEL"] = "ERROR"


def _normalize_agent_command_aliases(argv: list[str]) -> list[str]:
    """Rewrite agent-friendly subcommands to the existing flag-based CLI."""
    if not argv:
        return argv

    command, rest = argv[0], argv[1:]
    if command in _PROJECT_SCOPED_AGENT_COMMANDS:
        return [_PROJECT_SCOPED_AGENT_COMMANDS[command], *rest]
    if command in _FILE_SCOPED_AGENT_COMMANDS:
        return _normalize_file_scoped_alias(command, rest)
    return argv


def _normalize_file_scoped_alias(command: str, rest: list[str]) -> list[str]:
    flag = _FILE_SCOPED_AGENT_COMMANDS[command]
    if not rest or rest[0].startswith("-"):
        return [flag, *rest]
    return [rest[0], flag, *rest[1:]]


def _apply_format_alias(args: argparse.Namespace) -> None:
    """Mirror --format into --output-format after parsing."""
    if hasattr(args, "format") and args.format:
        args.output_format = args.format


def _configure_logging(args: argparse.Namespace) -> None:
    """Configure noisy loggers before command execution."""
    for logger_name in (
        "",
        "tree_sitter_analyzer",
        "tree_sitter_analyzer.performance",
        "tree_sitter_analyzer.plugins",
        "tree_sitter_analyzer.plugins.manager",
    ):
        logging.getLogger(logger_name).setLevel(logging.ERROR)


def _execute_selected_command(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    """Create the selected command and exit with the correct status."""
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
        msg = str(e)
        if "does not exist" in msg.lower() or "file not found" in msg.lower():
            output_error(f"File not found: {msg}")
            output_info("Check the file path and try again.")
        elif "unsupported language" in msg.lower():
            output_error(f"Unsupported language: {msg}")
            output_info(
                "Run with --show-supported-languages to see available languages."
            )
        elif "invalid file path" in msg.lower():
            output_error(f"Invalid path: {msg}")
            output_info("Use --project-root to set the project root directory.")
        else:
            output_error(f"Unexpected error: {msg}")
        sys.exit(1)
