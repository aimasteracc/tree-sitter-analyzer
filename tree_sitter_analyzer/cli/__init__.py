#!/usr/bin/env python3
"""
CLI Package

Command-line interface components using the Command Pattern.
"""

from .info_commands import (
    DescribeQueryCommand,
    InfoCommand,
    ListQueriesCommand,
    ShowExtensionsCommand,
    ShowLanguagesCommand,
)

# Modern framework imports
try:
    from ..cli_main import main
    from ..core.analysis_engine import get_analysis_engine
    from ..query_loader import QueryLoader

    query_loader = QueryLoader()
except ImportError:
    # Minimal fallback for import safety
    get_analysis_engine = None  # type: ignore
    main = None  # type: ignore
    query_loader = None  # type: ignore

__all__ = [
    "InfoCommand",
    "ListQueriesCommand",
    "DescribeQueryCommand",
    "ShowLanguagesCommand",
    "ShowExtensionsCommand",
    # Core framework exports
    "query_loader",
    "get_analysis_engine",
    "main",
]
