"""
CLI main entry point for tree-sitter-analyzer v2.

Provides command-line interface for:
- analyze: Analyze code structure
- search-files: Find files using fd
- search-content: Search content using ripgrep
"""

import argparse
import sys
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.detector import LanguageDetector
from tree_sitter_analyzer_v2.core.parser_registry import get_all_parsers
from tree_sitter_analyzer_v2.formatters import get_default_registry
from tree_sitter_analyzer_v2.search import SearchEngine
from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI."""
    parser = argparse.ArgumentParser(
        prog="tree-sitter-analyzer-v2",
        description="Tree-sitter based code analysis tool with MCP support",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze code structure of a file")
    analyze_parser.add_argument("file_path", help="Path to file to analyze")
    analyze_parser.add_argument(
        "--format",
        choices=["toon", "markdown", "summary"],
        default="markdown",
        help="Output format (default: markdown for CLI readability)",
    )
    analyze_parser.add_argument(
        "--summary",
        action="store_true",
        help="Show concise summary (overrides --format, faster than full analysis)",
    )

    # Search files command
    search_files_parser = subparsers.add_parser("search-files", help="Find files using fd")
    search_files_parser.add_argument("root_dir", help="Root directory to search in")
    search_files_parser.add_argument(
        "pattern", nargs="?", default="*", help="Glob pattern (default: *)"
    )
    search_files_parser.add_argument("--type", help="File type filter (e.g., py, ts, java)")

    # Search content command
    search_content_parser = subparsers.add_parser(
        "search-content", help="Search content using ripgrep"
    )
    search_content_parser.add_argument("root_dir", help="Root directory to search in")
    search_content_parser.add_argument("pattern", help="Search pattern")
    search_content_parser.add_argument("--type", help="File type filter (e.g., py, ts, java)")
    search_content_parser.add_argument(
        "--ignore-case", "-i", action="store_true", help="Case-insensitive search"
    )

    return parser


def cmd_analyze(args: argparse.Namespace) -> int:
    """Execute analyze command."""
    file_path = Path(args.file_path)

    # Check file exists
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    # Read file with encoding detection
    encoding_detector = EncodingDetector()
    content = encoding_detector.read_file_safe(file_path)

    # Detect language
    detector = LanguageDetector()
    detection = detector.detect_from_content(content, filename=file_path.name)

    if not detection or detection["language"] is None:
        print(f"Error: Unsupported or undetected language: {file_path}", file=sys.stderr)
        return 1

    language = detection["language"].lower()

    # Get appropriate parser (DIP: resolve via registry)
    parsers: dict[str, Any] = get_all_parsers()

    if language not in parsers:
        print(f"Error: Language '{language}' not supported yet", file=sys.stderr)
        return 1

    parser = parsers[language]

    try:
        # Parse file (content already read with encoding detection)
        result = parser.parse(content, str(file_path))

        # Add language and file info to result for summary formatter
        result["language"] = language
        result["file_path"] = str(file_path)

        # Add line count statistics for summary mode
        if args.summary:
            lines = content.splitlines()
            total_lines = len(lines)
            code_lines = sum(
                1 for line in lines if line.strip() and not line.strip().startswith("#")
            )
            comment_lines = sum(1 for line in lines if line.strip().startswith("#"))
            blank_lines = sum(1 for line in lines if not line.strip())

            if "metadata" not in result:
                result["metadata"] = {}
            result["metadata"]["total_lines"] = total_lines
            result["metadata"]["code_lines"] = code_lines
            result["metadata"]["comment_lines"] = comment_lines
            result["metadata"]["blank_lines"] = blank_lines

        # Format output
        formatter_registry = get_default_registry()

        # --summary takes precedence over --format
        if args.summary:
            formatter = formatter_registry.get("summary")
        else:
            formatter = formatter_registry.get(args.format)

        formatted_output = formatter.format(result)

        # Print to stdout
        print(formatted_output)
        return 0

    except Exception as e:
        print(f"Error analyzing file: {e}", file=sys.stderr)
        return 1


def cmd_search_files(args: argparse.Namespace) -> int:
    """Execute search-files command."""
    root_dir = Path(args.root_dir)

    # Check directory exists
    if not root_dir.exists():
        print(f"Error: Directory not found: {root_dir}", file=sys.stderr)
        return 1

    try:
        engine = SearchEngine()
        files = engine.find_files(root_dir=str(root_dir), pattern=args.pattern, file_type=args.type)

        # Print results
        for file_path in files:
            print(file_path)

        return 0

    except Exception as e:
        print(f"Error searching files: {e}", file=sys.stderr)
        return 1


def cmd_search_content(args: argparse.Namespace) -> int:
    """Execute search-content command."""
    root_dir = Path(args.root_dir)

    # Check directory exists
    if not root_dir.exists():
        print(f"Error: Directory not found: {root_dir}", file=sys.stderr)
        return 1

    try:
        engine = SearchEngine()
        matches = engine.search_content(
            root_dir=str(root_dir),
            pattern=args.pattern,
            file_type=args.type,
            case_sensitive=not args.ignore_case,
            is_regex=False,  # Default to fixed-string search
        )

        # Print results
        for match in matches:
            print(f"{match['file']}:{match['line_number']}:{match['line_content']}")

        return 0

    except Exception as e:
        print(f"Error searching content: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Show help if no command specified
    if not args.command:
        parser.print_help()
        return 0

    # Dispatch to command handler
    commands = {
        "analyze": cmd_analyze,
        "search-files": cmd_search_files,
        "search-content": cmd_search_content,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"Error: Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
