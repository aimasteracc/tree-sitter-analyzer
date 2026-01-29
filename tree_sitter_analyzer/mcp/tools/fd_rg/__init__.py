#!/usr/bin/env python3
"""
fd and ripgrep utilities - Modular architecture.

This package provides a clean, modular interface for working with fd and ripgrep
commands. It replaces the monolithic fd_rg_utils.py module with a well-structured
set of focused classes following SOLID principles.

Architecture:
    - config.py: Configuration dataclasses (FdCommandConfig, RgCommandConfig)
    - command_builder.py: Command builders (FdCommandBuilder, RgCommandBuilder)
    - result_parser.py: Result parsers (FdResultParser, RgResultParser, RgResultTransformer)
    - utils.py: Shared utilities (command execution, file I/O)

Usage Example:
    >>> from tree_sitter_analyzer.mcp.tools.fd_rg import (
    ...     FdCommandConfig,
    ...     FdCommandBuilder,
    ...     FdResultParser,
    ...     run_command_capture,
    ... )
    >>>
    >>> # Create configuration
    >>> config = FdCommandConfig(
    ...     roots=("src/",),
    ...     pattern="*.py",
    ...     glob=True,
    ...     hidden=False,
    ... )
    >>>
    >>> # Build command
    >>> builder = FdCommandBuilder()
    >>> cmd = builder.build(config)
    >>>
    >>> # Execute and parse
    >>> rc, stdout, stderr = await run_command_capture(cmd)
    >>> parser = FdResultParser()
    >>> files = parser.parse(stdout)

Migration from fd_rg_utils:
    The old fd_rg_utils.py module is deprecated. Use this package instead:

    Old:
        from tree_sitter_analyzer.mcp.tools.fd_rg_utils import build_fd_command
        cmd = build_fd_command(
            pattern="*.py", glob=True, types=None, extensions=None,
            exclude=None, depth=None, follow_symlinks=False, hidden=False,
            no_ignore=False, size=None, changed_within=None, changed_before=None,
            full_path_match=False, absolute=True, limit=None, roots=["src/"]
        )  # 18 parameters!

    New:
        from tree_sitter_analyzer.mcp.tools.fd_rg import FdCommandConfig, FdCommandBuilder
        config = FdCommandConfig(roots=("src/",), pattern="*.py", glob=True)
        cmd = FdCommandBuilder().build(config)  # Clean and simple!
"""

from __future__ import annotations

# Command builders
from .command_builder import FdCommandBuilder, RgCommandBuilder

# Configuration classes
from .config import FdCommandConfig, RgCommandConfig, SortType

# Result parsers and transformers
# Constants (re-exported for compatibility)
from .result_parser import (
    DEFAULT_RESULTS_LIMIT,
    MAX_RESULTS_HARD_CAP,
    FdResultParser,
    RgResultParser,
    RgResultTransformer,
    group_matches_by_file,
    optimize_match_paths,
    summarize_search_results,
)

# Utilities
from .utils import (
    TempFileList,
    check_external_command,
    clamp_int,
    get_missing_commands,
    merge_command_results,
    run_command_capture,
    run_parallel_commands,
    sanitize_error_message,
    split_roots_for_parallel_processing,
    write_files_to_temp,
)

# Version info
__version__ = "2.0.0"
__all__ = [
    # Configuration
    "FdCommandConfig",
    "RgCommandConfig",
    "SortType",
    # Builders
    "FdCommandBuilder",
    "RgCommandBuilder",
    # Parsers
    "FdResultParser",
    "RgResultParser",
    "RgResultTransformer",
    "group_matches_by_file",
    "summarize_search_results",
    "optimize_match_paths",
    # Utilities
    "check_external_command",
    "clamp_int",
    "get_missing_commands",
    "merge_command_results",
    "run_command_capture",
    "run_parallel_commands",
    "sanitize_error_message",
    "split_roots_for_parallel_processing",
    "TempFileList",
    "write_files_to_temp",
    # Constants
    "MAX_RESULTS_HARD_CAP",
    "DEFAULT_RESULTS_LIMIT",
]
