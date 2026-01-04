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


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Analyze code using Tree-sitter and extract structured information.",
        epilog="Example: uv run tree-sitter-analyzer examples/Sample.java --table=full",
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
        "--describe-query",
        help="Display description of specified query key (requires --language or target file)",
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
        choices=["json", "text", "toon"],
        default="json",
        help="Specify output format: 'json' (default), 'text', or 'toon' (50-70%% token reduction)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "toon"],
        help="Alias for --output-format (json or toon)",
    )
    parser.add_argument(
        "--toon-use-tabs",
        action="store_true",
        help="Use tab delimiters instead of commas in TOON format (further compression)",
    )
    parser.add_argument(
        "--table",
        choices=["full", "compact", "csv", "json", "toon"],
        help="Output in table format (toon format provides 50-70%% token reduction)",
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
        help="Display summary of specified element types (default: classes,methods)",
    )
    parser.add_argument(
        "--structure",
        action="store_true",
        help="Output detailed structure information in JSON format",
    )
    parser.add_argument(
        "--statistics",
        action="store_true",
        help="Display only statistical information (requires --query-key or --advanced)",
    )

    # Language options
    parser.add_argument(
        "--language",
        help="Explicitly specify language (auto-detected from extension if omitted)",
    )

    # SQL Platform Compatibility options
    parser.add_argument(
        "--sql-platform-info",
        action="store_true",
        help="Show current SQL platform detection details",
    )
    parser.add_argument(
        "--record-sql-profile",
        action="store_true",
        help="Record a new SQL behavior profile for the current platform",
    )
    parser.add_argument(
        "--compare-sql-profiles",
        nargs=2,
        metavar=("PROFILE1", "PROFILE2"),
        help="Compare two SQL behavior profiles",
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
        "--partial-read-requests-json",
        help="Batch partial read: JSON string containing either {'requests': [...]} or a list of requests[]",
    )
    parser.add_argument(
        "--partial-read-requests-file",
        help="Batch partial read: path to a JSON file containing either {'requests': [...]} or a list of requests[]",
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
    parser.add_argument(
        "--allow-truncate",
        action="store_true",
        help="Batch mode: allow truncation of results to fit limits (default: fail on limit exceed)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Batch mode: stop on first error (default: partial success)",
    )

    # Batch metrics options (spec unification with MCP tool arguments)
    parser.add_argument(
        "--metrics-only",
        action="store_true",
        help="Batch metrics: compute file metrics only (no structural analysis). Requires --file-paths or --files-from.",
    )
    parser.add_argument(
        "--file-paths",
        nargs="+",
        help="Batch metrics: list of file paths (space-separated). Example: --file-paths a.py b.py",
    )
    parser.add_argument(
        "--files-from",
        help="Batch metrics: read file paths from a text file (one path per line)",
    )

    return parser


def handle_special_commands(args: argparse.Namespace) -> int | None:
    """Handle special commands that don't fit the normal pattern."""

    def _effective_output_format() -> str:
        # --format is an alias for json/toon; --output-format supports json/text/toon
        fmt = getattr(args, "format", None) or getattr(args, "output_format", "json")
        return str(fmt)

    def _tool_output_format() -> str:
        # Tools only accept json/toon; map text -> toon for batch modes.
        fmt = _effective_output_format()
        return "toon" if fmt in {"toon", "text"} else "json"

    def _load_requests_payload() -> list[dict[str, Any]]:
        # Local import avoids rare closure/scoping issues in some execution contexts.
        import json as _json

        if getattr(args, "partial_read_requests_json", None):
            raw = args.partial_read_requests_json
        elif getattr(args, "partial_read_requests_file", None):
            with open(args.partial_read_requests_file, encoding="utf-8") as f:
                raw = f.read()
        else:
            raise ValueError("No batch requests source provided")

        payload = _json.loads(raw)
        if isinstance(payload, dict) and "requests" in payload:
            reqs = payload["requests"]
        else:
            reqs = payload
        if not isinstance(reqs, list):
            raise ValueError(
                "Batch requests must be a list or {'requests': [...]} JSON"
            )
        return reqs

    def _load_file_paths() -> list[str]:
        paths: list[str] = []
        if getattr(args, "file_paths", None):
            paths.extend([str(p) for p in args.file_paths])
        if getattr(args, "files_from", None):
            with open(args.files_from, encoding="utf-8") as f:
                for line in f.read().splitlines():
                    s = line.strip()
                    if s:
                        paths.append(s)
        # De-dup while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for p in paths:
            if p not in seen:
                unique.append(p)
                seen.add(p)
        return unique

    # Batch partial read (unified with MCP tool arguments)
    if (
        hasattr(args, "partial_read")
        and args.partial_read
        and (
            getattr(args, "partial_read_requests_json", None)
            or getattr(args, "partial_read_requests_file", None)
        )
    ):
        try:
            from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool

            requests_list = _load_requests_payload()
            project_root = getattr(args, "project_root", None) or os.getcwd()
            read_tool = ReadPartialTool(project_root=project_root)
            tool_args: dict[str, Any] = {
                "requests": requests_list,
                "output_format": _tool_output_format(),
                "format": "text",
                "allow_truncate": bool(getattr(args, "allow_truncate", False)),
                "fail_fast": bool(getattr(args, "fail_fast", False)),
            }
            result = asyncio.run(read_tool.execute(tool_args))

            fmt = _effective_output_format()
            if fmt == "toon":
                print(result.get("toon_content", ""))
            else:
                # json or text: print the returned dict as JSON (text is mapped for batch modes)
                from tree_sitter_analyzer.output_manager import output_json

                output_json(result)
            return 0 if result.get("success", False) else 1
        except Exception as e:
            output_error(f"Batch partial read failed: {e}")
            return 1

    # Batch metrics (unified with MCP tool arguments)
    if getattr(args, "metrics_only", False):
        file_paths = _load_file_paths()
        if not file_paths:
            output_error("--metrics-only requires --file-paths or --files-from")
            return 1
        try:
            from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import (
                AnalyzeScaleTool,
            )

            project_root = getattr(args, "project_root", None) or os.getcwd()
            scale_tool = AnalyzeScaleTool(project_root=project_root)
            tool_args = {
                "file_paths": file_paths,
                "metrics_only": True,
                "output_format": _tool_output_format(),
            }
            result = asyncio.run(scale_tool.execute(tool_args))

            fmt = _effective_output_format()
            if fmt == "toon":
                print(result.get("toon_content", ""))
            else:
                from tree_sitter_analyzer.output_manager import output_json

                output_json(result)
            return 0 if result.get("success", False) else 1
        except Exception as e:
            output_error(f"Batch metrics failed: {e}")
            return 1

    # Validate partial read options (single-range mode)
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

    # SQL Platform Compatibility Commands
    if args.sql_platform_info:
        from tree_sitter_analyzer.platform_compat.detector import PlatformDetector
        from tree_sitter_analyzer.platform_compat.profiles import BehaviorProfile

        info = PlatformDetector.detect()
        output_list(
            [
                "SQL Platform Information:",
                f"  OS Name: {info.os_name}",
                f"  OS Version: {info.os_version}",
                f"  Python Version: {info.python_version}",
                f"  Platform Key: {info.platform_key}",
                "",
            ]
        )

        profile = BehaviorProfile.load(info.platform_key)
        if profile:
            output_list(
                [
                    f"Loaded Profile: {info.platform_key}",
                    f"  Schema Version: {profile.schema_version}",
                    f"  Behaviors Recorded: {len(profile.behaviors)}",
                    f"  Adaptation Rules: {', '.join(profile.adaptation_rules) if profile.adaptation_rules else 'None'}",
                ]
            )
        else:
            output_list(
                [
                    f"No profile found for {info.platform_key}",
                    "  Using default adaptation rules.",
                ]
            )
        return 0

    if args.record_sql_profile:
        from pathlib import Path

        from tree_sitter_analyzer.platform_compat.recorder import BehaviorRecorder

        output_info("Starting SQL behavior recording...")
        try:
            recorder = BehaviorRecorder()
            profile = recorder.record_all()

            # Default output directory
            output_dir = Path("tests/platform_profiles")
            output_dir.mkdir(parents=True, exist_ok=True)

            profile.save(output_dir)
            output_info(f"Recorded profile for {profile.platform_key}")
            output_info(f"Saved to {output_dir}")
        except Exception as e:
            output_error(f"Failed to record profile: {e}")
            return 1
        return 0

    if args.compare_sql_profiles:
        import json
        from pathlib import Path

        from tree_sitter_analyzer.platform_compat.compare import (
            compare_profiles,
            generate_diff_report,
        )
        from tree_sitter_analyzer.platform_compat.profiles import BehaviorProfile

        p1_path = Path(args.compare_sql_profiles[0])
        p2_path = Path(args.compare_sql_profiles[1])

        if not p1_path.exists():
            output_error(f"Profile not found: {p1_path}")
            return 1
        if not p2_path.exists():
            output_error(f"Profile not found: {p2_path}")
            return 1

        try:
            from tree_sitter_analyzer.platform_compat.profiles import (
                BehaviorProfile,
                ParsingBehavior,
            )

            def load_profile(path: Path) -> BehaviorProfile:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    # Manual deserialization of nested objects
                    behaviors: dict[str, ParsingBehavior] = {}
                    for key, b_data in data.get("behaviors", {}).items():
                        if isinstance(b_data, dict):
                            behaviors[key] = ParsingBehavior(**b_data)
                        # If b_data is not a dict, it's not a valid ParsingBehavior
                        # and should be skipped or an error raised.
                        # For now, we'll skip to avoid type errors.

                    return BehaviorProfile(
                        schema_version=data.get("schema_version", "1.0.0"),
                        platform_key=data["platform_key"],
                        behaviors=behaviors,
                        adaptation_rules=data.get("adaptation_rules", []),
                    )

            p1 = load_profile(p1_path)
            p2 = load_profile(p2_path)

            comparison = compare_profiles(p1, p2)
            report = generate_diff_report(comparison)
            print(report)
        except Exception as e:
            output_error(f"Error comparing profiles: {e}")
            return 1
        return 0

    return None


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
