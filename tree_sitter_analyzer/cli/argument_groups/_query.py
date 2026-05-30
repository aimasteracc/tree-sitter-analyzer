"""Query selection and SQL platform argument groups."""

from __future__ import annotations

import argparse


def _add_query_options(parser: argparse.ArgumentParser) -> None:
    """Add query selection and informational options."""
    query_group = parser.add_mutually_exclusive_group(required=False)
    query_group.add_argument(
        "--query-key", help="Available query key (e.g., class, method)"
    )
    query_group.add_argument(
        "--query-string", help="Directly specify Tree-sitter query to execute"
    )
    parser.add_argument(
        "--filter",
        help="Filter query results (e.g., 'name=main', 'name=~get*,public=true')",
    )
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


def _add_sql_platform_options(parser: argparse.ArgumentParser) -> None:
    """Add SQL platform compatibility options."""
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
