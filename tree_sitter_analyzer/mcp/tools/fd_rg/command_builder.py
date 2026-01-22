#!/usr/bin/env python3
"""
Command builders for fd and ripgrep.

This module implements the Builder Pattern to construct fd and rg commands
from configuration objects, replacing the previous monolithic functions
with 16-18 parameters.
"""

from __future__ import annotations

from .config import FdCommandConfig, RgCommandConfig


class FdCommandBuilder:
    """Builds fd commands from configuration objects.

    Responsibilities:
    - Convert FdCommandConfig to command-line arguments
    - Apply flags in correct order
    - Handle edge cases (e.g., pattern vs roots)

    Single Responsibility: Command construction only.
    """

    def build(self, config: FdCommandConfig) -> list[str]:
        """Build fd command from configuration.

        Args:
            config: Immutable configuration object

        Returns:
            Complete fd command as list of strings
        """
        cmd: list[str] = ["fd", "--color", "never"]

        # Search mode flags
        if config.glob:
            cmd.append("--glob")
        if config.full_path_match:
            cmd.append("-p")

        # Output format
        if config.absolute:
            cmd.append("-a")

        # Traversal behavior
        if config.follow_symlinks:
            cmd.append("-L")
        if config.hidden:
            cmd.append("-H")
        if config.no_ignore:
            cmd.append("-I")

        # Depth limit
        if config.depth is not None:
            cmd.extend(["-d", str(config.depth)])

        # File type filters
        if config.types:
            for file_type in config.types:
                cmd.extend(["-t", str(file_type)])

        if config.extensions:
            for ext in config.extensions:
                # Remove leading dot if present
                clean_ext = ext[1:] if ext.startswith(".") else ext
                cmd.extend(["-e", clean_ext])

        if config.exclude:
            for pattern in config.exclude:
                cmd.extend(["-E", pattern])

        # File attribute filters
        if config.size:
            for size_spec in config.size:
                cmd.extend(["-S", size_spec])

        if config.changed_within:
            cmd.extend(["--changed-within", str(config.changed_within)])

        if config.changed_before:
            cmd.extend(["--changed-before", str(config.changed_before)])

        # Result limit
        if config.limit is not None:
            cmd.extend(["--max-results", str(config.limit)])

        # Pattern (required to prevent roots being interpreted as pattern)
        if config.pattern:
            cmd.append(config.pattern)
        else:
            cmd.append(".")  # Match all files

        # Search roots (directories to search)
        cmd.extend(config.roots)

        return cmd


class RgCommandBuilder:
    """Builds ripgrep commands from configuration objects.

    Responsibilities:
    - Convert RgCommandConfig to command-line arguments
    - Handle JSON vs count-only output modes
    - Apply search flags in correct order

    Single Responsibility: Command construction only.
    """

    # Default and hard cap values
    DEFAULT_MAX_FILESIZE = "1G"
    MAX_FILESIZE_HARD_CAP_BYTES = 10 * 1024 * 1024 * 1024  # 10GB

    def build(self, config: RgCommandConfig) -> list[str]:
        """Build ripgrep command from configuration.

        Args:
            config: Immutable configuration object

        Returns:
            Complete rg command as list of strings
        """
        # Base command with output mode
        if config.count_only_matches:
            cmd = ["rg", "--count-matches", "--no-heading", "--color", "never"]
        else:
            cmd = ["rg", "--json", "--no-heading", "--color", "never"]

        # Case sensitivity
        cmd.extend(self._build_case_flags(config.case))

        # Search mode flags
        if config.fixed_strings:
            cmd.append("-F")
        if config.word:
            cmd.append("-w")
        if config.multiline:
            cmd.append("--multiline")

        # Traversal behavior
        if config.follow_symlinks:
            cmd.append("-L")
        if config.hidden:
            cmd.append("-H")
        if config.no_ignore:
            cmd.append("-u")  # Respect ignore but include hidden

        # File filters (globs)
        if config.include_globs:
            for glob in config.include_globs:
                cmd.extend(["-g", glob])

        if config.exclude_globs:
            for glob in config.exclude_globs:
                # Add ! prefix if not present
                pattern = glob if glob.startswith("!") else f"!{glob}"
                cmd.extend(["-g", pattern])

        # Context lines
        if config.context_before is not None:
            cmd.extend(["-B", str(config.context_before)])
        if config.context_after is not None:
            cmd.extend(["-A", str(config.context_after)])

        # Encoding
        if config.encoding:
            cmd.extend(["--encoding", config.encoding])

        # Match limit per file
        if config.max_count is not None:
            cmd.extend(["-m", str(config.max_count)])

        # File size limit
        max_filesize = self._normalize_max_filesize(config.max_filesize)
        cmd.extend(["--max-filesize", max_filesize])

        # Query (must come before roots/files)
        cmd.append(config.query)

        # Search targets
        if config.roots:
            cmd.extend(config.roots)
        # Note: files_from is not supported in current implementation

        return cmd

    def _build_case_flags(self, case_mode: str) -> list[str]:
        """Build case sensitivity flags.

        Args:
            case_mode: "smart", "insensitive", or "sensitive"

        Returns:
            List of flags for case sensitivity
        """
        if case_mode == "smart":
            return ["-S"]
        elif case_mode == "insensitive":
            return ["-i"]
        elif case_mode == "sensitive":
            return ["-s"]
        return []

    def _normalize_max_filesize(self, user_value: str | None) -> str:
        """Normalize and validate max filesize parameter.

        Args:
            user_value: User-provided filesize string (e.g., "10M")

        Returns:
            Validated filesize string
        """
        if not user_value:
            return self.DEFAULT_MAX_FILESIZE

        # Parse to bytes for validation
        bytes_val = self._parse_size_to_bytes(user_value)
        if bytes_val is None:
            return self.DEFAULT_MAX_FILESIZE

        # Enforce hard cap
        if bytes_val > self.MAX_FILESIZE_HARD_CAP_BYTES:
            return "10G"

        return user_value

    def _parse_size_to_bytes(self, size_str: str) -> int | None:
        """Parse size string to bytes.

        Args:
            size_str: Size string like "10M", "200K"

        Returns:
            Size in bytes, or None if invalid
        """
        if not size_str:
            return None

        s = size_str.strip().upper()
        try:
            if s.endswith("K"):
                return int(float(s[:-1]) * 1024)
            if s.endswith("M"):
                return int(float(s[:-1]) * 1024 * 1024)
            if s.endswith("G"):
                return int(float(s[:-1]) * 1024 * 1024 * 1024)
            return int(s)
        except ValueError:
            return None
