#!/usr/bin/env python3
"""
Command Line Interface

New CLI implementation that uses the API facade for all operations.
Provides a clean separation between CLI concerns and core analysis logic.
"""

import argparse
import importlib.metadata
import json
import logging
import sys
from pathlib import Path
from typing import Any

from .. import api

# Configure logging for CLI
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="tree-sitter-analyzer",
        description="Extensible multi-language code analyzer using Tree-sitter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a Java file
  tree-sitter-analyzer analyze example.java

  # Analyze with specific language
  tree-sitter-analyzer analyze --language python script.py

  # Execute specific queries
  tree-sitter-analyzer analyze --queries functions,classes example.java

  # Extract only code elements
  tree-sitter-analyzer extract example.py

  # List supported languages
  tree-sitter-analyzer languages

  # Get framework information
  tree-sitter-analyzer info

For more information, visit: https://github.com/aimasteracc/tree-sitter-analyzer
        """,
    )

    # Global options
    # Get version dynamically from package metadata
    try:
        version = importlib.metadata.version("tree-sitter-analyzer")
    except importlib.metadata.PackageNotFoundError:
        version = "0.9.9"  # Fallback version

    parser.add_argument(
        "--version", action="version", version=f"tree-sitter-analyzer {version}"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress non-essential output"
    )
    parser.add_argument(
        "--output",
        "-o",
        choices=["json", "text", "table"],
        default="text",
        help="Output format (default: text)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Analyze command
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze source code files",
        description="Perform comprehensive analysis of source code files",
    )
    analyze_parser.add_argument("file_path", help="Path to the source file to analyze")
    analyze_parser.add_argument(
        "--language", "-l", help="Programming language (auto-detected if not specified)"
    )
    analyze_parser.add_argument(
        "--queries", help="Comma-separated list of queries to execute"
    )
    analyze_parser.add_argument(
        "--no-elements", action="store_true", help="Skip code element extraction"
    )
    analyze_parser.add_argument(
        "--no-queries", action="store_true", help="Skip query execution"
    )

    # Extract command
    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract code elements from files",
        description="Extract specific code elements like functions, classes, etc.",
    )
    extract_parser.add_argument("file_path", help="Path to the source file")
    extract_parser.add_argument(
        "--language", "-l", help="Programming language (auto-detected if not specified)"
    )
    extract_parser.add_argument(
        "--types",
        help="Comma-separated list of element types to extract (e.g., functions,classes)",
    )

    # Query command
    query_parser = subparsers.add_parser(
        "query",
        help="Execute specific queries on files",
        description="Execute specific tree-sitter queries on source files",
    )
    query_parser.add_argument("file_path", help="Path to the source file")
    query_parser.add_argument("query_name", help="Name of the query to execute")
    query_parser.add_argument(
        "--language", "-l", help="Programming language (auto-detected if not specified)"
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate source files",
        description="Check if files can be parsed and analyzed",
    )
    validate_parser.add_argument(
        "file_path", help="Path to the source file to validate"
    )

    # Languages command
    languages_parser = subparsers.add_parser(
        "languages",
        help="List supported languages",
        description="Show all supported programming languages and their extensions",
    )
    languages_parser.add_argument(
        "--extensions",
        action="store_true",
        help="Show file extensions for each language",
    )

    # Info command
    subparsers.add_parser(
        "info",
        help="Show framework information",
        description="Display information about the analyzer framework",
    )

    # Queries command
    queries_parser = subparsers.add_parser(
        "queries",
        help="List available queries",
        description="Show available queries for a specific language",
    )
    queries_parser.add_argument("language", help="Programming language name")

    return parser


def handle_analyze_command(args: argparse.Namespace) -> int:
    """Handle the analyze command."""
    try:
        file_path = Path(args.file_path)

        if not file_path.exists():
            print(f"Error: File '{file_path}' does not exist", file=sys.stderr)
            return 1

        # Parse queries if provided
        queries = None
        if args.queries:
            queries = [q.strip() for q in args.queries.split(",")]

        # Perform analysis
        result = api.analyze_file(
            file_path=file_path,
            language=args.language,
            queries=queries,
            include_elements=not args.no_elements,
            include_queries=not args.no_queries,
        )

        # Output results
        if args.output == "json":
            print(json.dumps(result, indent=2))
        else:
            format_analysis_output(result, args.output)

        return 0 if result.get("success", False) else 1

    except Exception as e:
        print(f"Error during analysis: {e}", file=sys.stderr)
        return 1


def handle_extract_command(args: argparse.Namespace) -> int:
    """Handle the extract command."""
    try:
        file_path = Path(args.file_path)

        if not file_path.exists():
            print(f"Error: File '{file_path}' does not exist", file=sys.stderr)
            return 1

        # Parse element types if provided
        element_types = None
        if args.types:
            element_types = [t.strip() for t in args.types.split(",")]

        # Extract elements
        result = api.extract_elements(
            file_path=file_path, language=args.language, element_types=element_types
        )

        # Output results
        if args.output == "json":
            print(json.dumps(result, indent=2))
        else:
            format_extraction_output(result, args.output)

        return 0 if result.get("success", False) else 1

    except Exception as e:
        print(f"Error during extraction: {e}", file=sys.stderr)
        return 1


def handle_query_command(args: argparse.Namespace) -> int:
    """Handle the query command."""
    try:
        file_path = Path(args.file_path)

        if not file_path.exists():
            print(f"Error: File '{file_path}' does not exist", file=sys.stderr)
            return 1

        # Execute query
        result = api.execute_query(
            file_path=file_path, query_name=args.query_name, language=args.language
        )

        # Output results
        if args.output == "json":
            print(json.dumps(result, indent=2))
        else:
            format_query_output(result, args.output)

        return 0 if result.get("success", False) else 1

    except Exception as e:
        print(f"Error during query execution: {e}", file=sys.stderr)
        return 1


def handle_validate_command(args: argparse.Namespace) -> int:
    """Handle the validate command."""
    try:
        file_path = Path(args.file_path)

        # Validate file
        result = api.validate_file(file_path)

        # Output results
        if args.output == "json":
            print(json.dumps(result, indent=2))
        else:
            format_validation_output(result, args.output)

        return 0 if result.get("valid", False) else 1

    except Exception as e:
        print(f"Error during validation: {e}", file=sys.stderr)
        return 1


def handle_languages_command(args: argparse.Namespace) -> int:
    """Handle the languages command."""
    try:
        languages = api.get_supported_languages()

        if args.output == "json":
            if args.extensions:
                lang_info = {}
                for lang in languages:
                    extensions = api.get_file_extensions(lang)
                    lang_info[lang] = extensions
                print(json.dumps(lang_info, indent=2))
            else:
                print(json.dumps(languages, indent=2))
        else:
            print("Supported Languages:")
            print("=" * 20)
            for lang in sorted(languages):
                if args.extensions:
                    extensions = api.get_file_extensions(lang)
                    ext_str = ", ".join(extensions) if extensions else "No extensions"
                    print(f"  {lang:<12} - {ext_str}")
                else:
                    print(f"  {lang}")

            if not args.extensions:
                print(f"\nTotal: {len(languages)} languages")
                print("Use --extensions to see file extensions for each language")

        return 0

    except Exception as e:
        print(f"Error getting language information: {e}", file=sys.stderr)
        return 1


def handle_info_command(args: argparse.Namespace) -> int:
    """Handle the info command."""
    try:
        info = api.get_framework_info()

        if args.output == "json":
            print(json.dumps(info, indent=2))
        else:
            print("Tree-sitter Analyzer Framework Information")
            print("=" * 45)
            print(f"Name: {info.get('name', 'Unknown')}")
            print(f"Version: {info.get('version', 'Unknown')}")
            print(f"Supported Languages: {info.get('total_languages', 0)}")

            languages = info.get("supported_languages", [])
            if languages:
                print(f"Languages: {', '.join(sorted(languages))}")

            components = info.get("core_components", [])
            if components:
                print(f"Core Components: {', '.join(components)}")

        return 0

    except Exception as e:
        print(f"Error getting framework information: {e}", file=sys.stderr)
        return 1


def handle_queries_command(args: argparse.Namespace) -> int:
    """Handle the queries command."""
    try:
        if not api.is_language_supported(args.language):
            print(
                f"Error: Language '{args.language}' is not supported", file=sys.stderr
            )
            return 1

        queries = api.get_available_queries(args.language)

        if args.output == "json":
            print(json.dumps(queries, indent=2))
        else:
            print(f"Available Queries for {args.language}:")
            print("=" * (25 + len(args.language)))
            for query in sorted(queries):
                print(f"  {query}")

            print(f"\nTotal: {len(queries)} queries")

        return 0

    except Exception as e:
        print(f"Error getting query information: {e}", file=sys.stderr)
        return 1


def format_analysis_output(result: dict[str, Any], output_format: str) -> None:
    """Format and display analysis results."""
    if not result.get("success", False):
        print(
            f"Analysis failed: {result.get('error', 'Unknown error')}", file=sys.stderr
        )
        return

    print("Analysis Results")
    print("=" * 16)

    # File information
    file_info = result.get("file_info", {})
    print(f"File: {file_info.get('path', 'Unknown')}")

    # Language information
    lang_info = result.get("language_info", {})
    language = lang_info.get("language", "Unknown")
    auto_detected = lang_info.get("auto_detected", False)
    detection_str = " (auto-detected)" if auto_detected else ""
    print(f"Language: {language}{detection_str}")

    # AST information
    ast_info = result.get("ast_info", {})
    print(f"Source Lines: {ast_info.get('source_lines', 0)}")
    print(f"AST Nodes: {ast_info.get('node_count', 0)}")

    # Query results
    query_results = result.get("query_results", {})
    if query_results:
        print("\nQuery Results:")
        for query_name, matches in query_results.items():
            print(f"  {query_name}: {len(matches)} matches")

    # Elements
    elements = result.get("elements", [])
    if elements:
        print(f"\nCode Elements: {len(elements)} found")
        element_types: dict[str, int] = {}
        for element in elements:
            elem_type = element.get("type", "unknown")
            element_types[elem_type] = element_types.get(elem_type, 0) + 1

        for elem_type, count in sorted(element_types.items()):
            print(f"  {elem_type}: {count}")


def format_extraction_output(result: dict[str, Any], output_format: str) -> None:
    """Format and display extraction results."""
    if not result.get("success", False):
        print(
            f"Extraction failed: {result.get('error', 'Unknown error')}",
            file=sys.stderr,
        )
        return

    elements = result.get("elements", [])
    language = result.get("language", "Unknown")

    print("Code Element Extraction Results")
    print("=" * 31)
    print(f"File: {result.get('file_path', 'Unknown')}")
    print(f"Language: {language}")
    print(f"Elements Found: {len(elements)}")

    if elements:
        print("\nElements:")
        for element in elements:
            name = element.get("name", "Unknown")
            elem_type = element.get("type", "unknown")
            start_line = element.get("start_line", 0)
            print(f"  {elem_type}: {name} (line {start_line})")


def format_query_output(result: dict[str, Any], output_format: str) -> None:
    """Format and display query results."""
    if not result.get("success", False):
        print(f"Query failed: {result.get('error', 'Unknown error')}", file=sys.stderr)
        return

    query_name = result.get("query_name", "Unknown")
    matches = result.get("results", [])
    language = result.get("language", "Unknown")

    print("Query Execution Results")
    print("=" * 23)
    print(f"File: {result.get('file_path', 'Unknown')}")
    print(f"Language: {language}")
    print(f"Query: {query_name}")
    print(f"Matches: {len(matches)}")

    if matches:
        print("\nMatches:")
        for i, match in enumerate(matches, 1):
            start_line = match.get("start_line", 0)
            content = match.get("content", "").strip()
            if len(content) > 50:
                content = content[:47] + "..."
            print(f"  {i}. Line {start_line}: {content}")


def format_validation_output(result: dict[str, Any], output_format: str) -> None:
    """Format and display validation results."""
    valid = result.get("valid", False)
    exists = result.get("exists", False)
    readable = result.get("readable", False)
    language = result.get("language")
    supported = result.get("supported", False)
    errors = result.get("errors", [])

    print("File Validation Results")
    print("=" * 23)
    print(f"Valid: {'✓' if valid else '✗'}")
    print(f"Exists: {'✓' if exists else '✗'}")
    print(f"Readable: {'✓' if readable else '✗'}")
    print(f"Language: {language or 'Unknown'}")
    print(f"Supported: {'✓' if supported else '✗'}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")


def main() -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Configure logging based on verbosity
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle commands
    if args.command == "analyze":
        return handle_analyze_command(args)
    elif args.command == "extract":
        return handle_extract_command(args)
    elif args.command == "query":
        return handle_query_command(args)
    elif args.command == "validate":
        return handle_validate_command(args)
    elif args.command == "languages":
        return handle_languages_command(args)
    elif args.command == "info":
        return handle_info_command(args)
    elif args.command == "queries":
        return handle_queries_command(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
