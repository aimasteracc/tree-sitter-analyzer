#!/usr/bin/env python3
"""
Configuration dataclasses for fd and ripgrep commands.

This module defines immutable configuration objects that replace
the previous parameter explosion (16-18 parameters per function).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SortType(str, Enum):
    """Sort types for file listing and search results."""

    NAME = "name"
    PATH = "path"
    SIZE = "size"
    MODIFIED = "modified"
    MTIME = "mtime"  # Alias for MODIFIED
    EXT = "ext"
    EXTENSION = "extension"  # Alias for EXT


@dataclass(frozen=True)
class FdCommandConfig:
    """Configuration for fd file search command.

    Replaces 18 individual parameters with a single, immutable config object.
    All fields have sensible defaults to minimize required parameters.
    """

    # Required
    roots: tuple[str, ...]

    # Search pattern
    pattern: str | None = None
    glob: bool = False
    full_path_match: bool = False

    # File type filters
    types: tuple[str, ...] | None = None
    extensions: tuple[str, ...] | None = None
    exclude: tuple[str, ...] | None = None

    # Search depth and following
    depth: int | None = None
    follow_symlinks: bool = False

    # Hidden and ignored files
    hidden: bool = False
    no_ignore: bool = False

    # File attributes
    size: tuple[str, ...] | None = None
    changed_within: str | None = None
    changed_before: str | None = None

    # Output options
    absolute: bool = True
    limit: int | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.roots:
            raise ValueError("At least one root directory is required")

        if self.depth is not None and self.depth < 0:
            raise ValueError("Depth must be non-negative")

        if self.limit is not None and self.limit < 0:
            raise ValueError("Limit must be non-negative")


@dataclass(frozen=True)
class RgCommandConfig:
    """Configuration for ripgrep content search command.

    Replaces 17 individual parameters with a single, immutable config object.
    All fields have sensible defaults to minimize required parameters.
    """

    # Required
    query: str

    # Search targets
    roots: tuple[str, ...] | None = None
    files_from: str | None = None

    # Search behavior
    case: str = "smart"  # "smart", "insensitive", "sensitive"
    fixed_strings: bool = False
    word: bool = False
    multiline: bool = False

    # File filters
    include_globs: tuple[str, ...] | None = None
    exclude_globs: tuple[str, ...] | None = None
    follow_symlinks: bool = False
    hidden: bool = False
    no_ignore: bool = False
    max_filesize: str | None = None

    # Context and output
    context_before: int | None = None
    context_after: int | None = None
    encoding: str | None = None
    max_count: int | None = None

    # Performance
    timeout_ms: int | None = None

    # Output mode
    count_only_matches: bool = False

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.query:
            raise ValueError("Query string is required")

        if self.case not in ("smart", "insensitive", "sensitive"):
            raise ValueError(f"Invalid case mode: {self.case}")

        if self.context_before is not None and self.context_before < 0:
            raise ValueError("context_before must be non-negative")

        if self.context_after is not None and self.context_after < 0:
            raise ValueError("context_after must be non-negative")

        if self.max_count is not None and self.max_count < 0:
            raise ValueError("max_count must be non-negative")

        if self.timeout_ms is not None and self.timeout_ms < 0:
            raise ValueError("timeout_ms must be non-negative")
