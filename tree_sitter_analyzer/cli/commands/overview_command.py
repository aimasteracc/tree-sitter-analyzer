#!/usr/bin/env python3
"""
CLI command for unified project overview.

Provides a single command to generate comprehensive project health reports
by aggregating results from multiple analysis tools.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ...output_manager import output_data, output_error, output_info, set_output_mode
from ...overview.aggregator import OverviewAggregator
from ...overview.reporter import OverviewReporter


def _build_parser() -> argparse.ArgumentParser:
    """Build argument parser for overview CLI."""
    parser = argparse.ArgumentParser(
        description="Unified project overview: aggregate all analysis tools into one report.",
        epilog="""
Examples:
  # Generate full overview with all analyses
  %(prog)s

  # Generate overview with specific analyses only
  %(prog)s --include health_score dependency_graph

  # Choose output format
  %(prog)s --format markdown
  %(prog)s --format json
  %(prog)s --format toon

  # Run analyses sequentially (disable parallel execution)
  %(prog)s --no-parallel

  # Analyze a specific project
  %(prog)s --project-root /path/to/project
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--format",
        choices=["markdown", "json", "toon"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    parser.add_argument(
        "--include",
        nargs="+",
        choices=[
            "dependency_graph",
            "health_score",
            "design_patterns",
            "security_scan",
            "dead_code",
            "ownership",
            "blast_radius",
        ],
        help="Include only specific analyses (default: all)",
    )

    parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="Run analyses sequentially (default: parallel)",
    )

    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root directory (default: current directory)",
    )

    return parser


def main(args: list[str] | None = None) -> int:
    """Main entry point for overview CLI.

    Args:
        args: Command line arguments (uses sys.argv if None).

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    parser = _build_parser()
    parsed_args = parser.parse_args(args)

    # Set output mode
    set_output_mode()

    # Resolve project path
    project_root = Path(parsed_args.project_root).resolve()
    if not project_root.exists():
        output_error(f"Project root does not exist: {project_root}")
        return 1

    output_info(f"Analyzing project: {project_root}")

    try:
        # Create aggregator
        aggregator = OverviewAggregator(
            str(project_root),
            parallel=not parsed_args.no_parallel,
        )

        # Map CLI argument names to internal names
        include_mapping = {
            "dependency_graph": "dependency_graph",
            "health_score": "health_score",
            "design_patterns": "design_patterns",
            "security_scan": "security_scan",
            "dead_code": "dead_code",
            "ownership": "ownership",
            "blast_radius": "blast_radius",
        }

        # Convert include list
        include_list = None
        if parsed_args.include:
            include_list = [include_mapping[name] for name in parsed_args.include]

        # Generate overview
        report = aggregator.generate_overview(include=include_list)

        # Create reporter and format output
        reporter = OverviewReporter(report)

        if parsed_args.format == "markdown":
            output = reporter.generate_markdown()
        elif parsed_args.format == "json":
            output = reporter.generate_json()
        else:  # toon
            output = reporter.generate_toon()

        output_data(output)
        return 0

    except KeyboardInterrupt:
        output_info("\nInterrupted by user")
        return 130
    except Exception as e:
        output_error(f"Error generating overview: {e}")
        return 1
