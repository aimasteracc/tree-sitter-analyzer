"""Core, output, project/logging, partial-read, and batch argument groups."""

from __future__ import annotations

import argparse

from ... import __version__


def _add_core_options(parser: argparse.ArgumentParser) -> None:
    """Add version and target-file options."""
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument("file_path", nargs="?", help="Path to the file to analyze")


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    """Add output formatting options."""
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
        choices=["full", "compact", "csv", "json", "toon", "signatures"],
        help=(
            "Output in table format. "
            "'signatures' = lightweight method-directory (~25%% of full tokens); "
            "toon = 50-70%% token reduction"
        ),
    )
    parser.add_argument(
        "--include-javadoc",
        action="store_true",
        help="Include JavaDoc/documentation comments in output",
    )


def _add_project_and_logging_options(parser: argparse.ArgumentParser) -> None:
    """Add project and logging options."""
    parser.add_argument(
        "--project-root",
        help="Project root directory for security validation (auto-detected if not specified)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress INFO level logs (show errors only)",
    )


def _add_partial_read_options(parser: argparse.ArgumentParser) -> None:
    """Add single and batch partial-read options."""
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


def _add_batch_options(parser: argparse.ArgumentParser) -> None:
    """Add batch project-health and metrics options."""
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Project health: score all source files and report grade distribution, worst files, and refactoring targets",
    )
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
