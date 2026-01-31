#!/usr/bin/env python3
"""
fd and ripgrep Utilities.

Modular interface for fd and ripgrep commands.

Architecture:
    - config.py: Configuration dataclasses (FdCommandConfig, RgCommandConfig)
    - command_builder.py: Command builders (FdCommandBuilder, RgCommandBuilder)
    - result_parser.py: Result parsers (FdResultParser, RgResultParser, RgResultTransformer)
    - utils.py: Shared utilities (command execution, file I/O)

Version: 1.10.5
Date: 2026-01-28
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
