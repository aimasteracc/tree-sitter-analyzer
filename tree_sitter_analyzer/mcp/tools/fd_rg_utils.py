#!/usr/bin/env python3
"""
Backward compatibility shim for fd/ripgrep utilities.

⚠️ DEPRECATED: This module will be removed in v3.0.0 (planned for 2026-Q3).
Please migrate to the new modular fd_rg package:

    from tree_sitter_analyzer.mcp.tools.fd_rg import (
        FdCommandConfig, FdCommandBuilder,
        RgCommandConfig, RgCommandBuilder,
        run_command_capture, check_external_command,
    )

Migration Guide:
    Old (18 parameters):
        cmd = build_fd_command(
            pattern="*.py", glob=True, types=None, extensions=None,
            exclude=None, depth=None, follow_symlinks=False, hidden=False,
            no_ignore=False, size=None, changed_within=None, changed_before=None,
            full_path_match=False, absolute=True, limit=None, roots=["src/"]
        )

    New (clean config object):
        config = FdCommandConfig(roots=("src/",), pattern="*.py", glob=True)
        cmd = FdCommandBuilder().build(config)

This module provides ONLY the actively used functions for backward compatibility.
All other deprecated functions have been removed. See git history for full legacy API.
"""

from __future__ import annotations

import warnings
from typing import Any

# Re-export from new modular package
from .fd_rg import (
    FdCommandBuilder,
    FdCommandConfig,
    RgCommandBuilder,
    RgCommandConfig,
    RgResultTransformer,
    merge_command_results,
    run_parallel_commands,
)

# Constants for backward compatibility
DEFAULT_RESULTS_LIMIT = 2000
DEFAULT_RG_MAX_FILESIZE = "1G"
RG_MAX_FILESIZE_HARD_CAP_BYTES = 10 * 1024 * 1024 * 1024  # 10GB
DEFAULT_RG_TIMEOUT_MS = 4000
RG_TIMEOUT_HARD_CAP_MS = 30000


def _emit_deprecation_warning(func_name: str) -> None:
    """Emit FutureWarning for deprecated function usage."""
    warnings.warn(
        f"{func_name} is deprecated and will be removed in v3.0.0. "
        f"Migrate to tree_sitter_analyzer.mcp.tools.fd_rg package. "
        f"See module docstring for migration guide.",
        FutureWarning,
        stacklevel=3,
    )


# ============================================================================
# ACTIVELY USED FUNCTIONS - Keep for backward compatibility
# ============================================================================


def build_fd_command(
    *,
    pattern: str | None,
    glob: bool,
    types: list[str] | None,
    extensions: list[str] | None,
    exclude: list[str] | None,
    depth: int | None,
    follow_symlinks: bool,
    hidden: bool,
    no_ignore: bool,
    size: list[str] | None,
    changed_within: str | None,
    changed_before: str | None,
    full_path_match: bool,
    absolute: bool,
    limit: int | None,
    roots: list[str],
) -> list[str]:
    """Build fd command (DEPRECATED - use FdCommandConfig + FdCommandBuilder)."""
    _emit_deprecation_warning("build_fd_command()")

    config = FdCommandConfig(
        roots=tuple(roots),
        pattern=pattern,
        glob=glob,
        types=tuple(types) if types else None,
        extensions=tuple(extensions) if extensions else None,
        exclude=tuple(exclude) if exclude else None,
        depth=depth,
        follow_symlinks=follow_symlinks,
        hidden=hidden,
        no_ignore=no_ignore,
        size=tuple(size) if size else None,
        changed_within=changed_within,
        changed_before=changed_before,
        full_path_match=full_path_match,
        absolute=absolute,
        limit=limit,
    )
    return FdCommandBuilder().build(config)


def build_rg_command(
    *,
    query: str,
    case: str | None,
    fixed_strings: bool,
    word: bool,
    multiline: bool,
    include_globs: list[str] | None,
    exclude_globs: list[str] | None,
    follow_symlinks: bool,
    hidden: bool,
    no_ignore: bool,
    max_filesize: str | None,
    context_before: int | None,
    context_after: int | None,
    encoding: str | None,
    max_count: int | None,
    timeout_ms: int | None,
    roots: list[str] | None,
    files_from: str | None,
    count_only_matches: bool = False,
) -> list[str]:
    """Build ripgrep command (DEPRECATED - use RgCommandConfig + RgCommandBuilder)."""
    _emit_deprecation_warning("build_rg_command()")

    config = RgCommandConfig(
        query=query,
        case=case or "smart",
        fixed_strings=fixed_strings,
        word=word,
        multiline=multiline,
        include_globs=tuple(include_globs) if include_globs else None,
        exclude_globs=tuple(exclude_globs) if exclude_globs else None,
        follow_symlinks=follow_symlinks,
        hidden=hidden,
        no_ignore=no_ignore,
        max_filesize=max_filesize,
        context_before=context_before,
        context_after=context_after,
        encoding=encoding,
        max_count=max_count,
        timeout_ms=timeout_ms,
        roots=tuple(roots) if roots else None,
        files_from=files_from,
        count_only_matches=count_only_matches,
    )
    return RgCommandBuilder().build(config)


def parse_size_to_bytes(size_str: str) -> int | None:
    """Parse size strings like '10M', '200K' to bytes (DEPRECATED)."""
    _emit_deprecation_warning("parse_size_to_bytes()")
    return RgCommandBuilder()._parse_size_to_bytes(size_str)


def create_file_summary_from_count_data(count_data: dict[str, int]) -> dict[str, Any]:
    """Create file summary from count data (DEPRECATED)."""
    _emit_deprecation_warning("create_file_summary_from_count_data()")
    return RgResultTransformer().create_file_summary_from_count(count_data)


def extract_file_list_from_count_data(count_data: dict[str, int]) -> list[str]:
    """Extract file list from count data (DEPRECATED)."""
    _emit_deprecation_warning("extract_file_list_from_count_data()")
    return [file_path for file_path in count_data.keys() if file_path != "__total__"]


# Aliases for backward compatibility
run_parallel_rg_searches = run_parallel_commands
merge_rg_results = merge_command_results


# ============================================================================
# REMOVED FUNCTIONS - No longer available
# ============================================================================
# The following functions were removed as they had zero usage in the codebase:
# - normalize_max_filesize() -> Use RgCommandBuilder()._normalize_max_filesize()
# - parse_rg_json_lines_to_matches() -> Use RgResultParser().parse_json_matches()
# - group_matches_by_file() -> Use RgResultTransformer().group_by_file()
# - optimize_match_paths() -> Use RgResultTransformer().optimize_paths()
# - _optimize_file_path() -> Use RgResultTransformer()._optimize_file_path()
# - summarize_search_results() -> Use RgResultTransformer().summarize()
# - parse_rg_count_output() -> Use RgResultParser().parse_count_output()
#
# If you need these functions, import directly from fd_rg package:
#   from tree_sitter_analyzer.mcp.tools.fd_rg import RgResultParser, RgResultTransformer
