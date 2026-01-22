#!/usr/bin/env python3
"""
Unit tests for fd_rg command builders.

Tests the FdCommandBuilder and RgCommandBuilder classes to ensure
they correctly convert configuration objects into command-line arguments.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.fd_rg import (
    FdCommandBuilder,
    FdCommandConfig,
    RgCommandBuilder,
    RgCommandConfig,
)


class TestFdCommandBuilder:
    """Tests for FdCommandBuilder."""

    def test_minimal_config(self):
        """Test building command with minimal configuration."""
        config = FdCommandConfig(roots=("src/",))
        builder = FdCommandBuilder()
        cmd = builder.build(config)

        assert cmd[0] == "fd"
        assert "--color" in cmd
        assert "never" in cmd
        assert "." in cmd  # Default pattern
        assert "src/" in cmd

    def test_pattern_and_glob(self):
        """Test pattern and glob flag."""
        config = FdCommandConfig(
            roots=("src/",),
            pattern="*.py",
            glob=True,
        )
        builder = FdCommandBuilder()
        cmd = builder.build(config)

        assert "--glob" in cmd
        assert "*.py" in cmd

    def test_file_type_filters(self):
        """Test file type filters."""
        config = FdCommandConfig(
            roots=("src/",),
            types=("f", "l"),
            extensions=("py", ".js"),
            exclude=("*.pyc", "__pycache__"),
        )
        builder = FdCommandBuilder()
        cmd = builder.build(config)

        assert "-t" in cmd
        assert "f" in cmd
        assert "l" in cmd
        assert "-e" in cmd
        assert "py" in cmd
        assert "js" in cmd  # Leading dot removed
        assert "-E" in cmd
        assert "*.pyc" in cmd
        assert "__pycache__" in cmd

    def test_depth_and_traversal(self):
        """Test depth and traversal options."""
        config = FdCommandConfig(
            roots=("src/",),
            depth=3,
            follow_symlinks=True,
            hidden=True,
            no_ignore=True,
        )
        builder = FdCommandBuilder()
        cmd = builder.build(config)

        assert "-d" in cmd
        assert "3" in cmd
        assert "-L" in cmd
        assert "-H" in cmd
        assert "-I" in cmd

    def test_file_attributes(self):
        """Test file attribute filters."""
        config = FdCommandConfig(
            roots=("src/",),
            size=("+10M", "-1G"),
            changed_within="1d",
            changed_before="1w",
        )
        builder = FdCommandBuilder()
        cmd = builder.build(config)

        assert "-S" in cmd
        assert "+10M" in cmd
        assert "-1G" in cmd
        assert "--changed-within" in cmd
        assert "1d" in cmd
        assert "--changed-before" in cmd
        assert "1w" in cmd

    def test_output_options(self):
        """Test output options."""
        config = FdCommandConfig(
            roots=("src/",),
            absolute=True,
            limit=100,
        )
        builder = FdCommandBuilder()
        cmd = builder.build(config)

        assert "-a" in cmd
        assert "--max-results" in cmd
        assert "100" in cmd

    def test_multiple_roots(self):
        """Test multiple search roots."""
        config = FdCommandConfig(
            roots=("src/", "tests/", "docs/"),
        )
        builder = FdCommandBuilder()
        cmd = builder.build(config)

        assert "src/" in cmd
        assert "tests/" in cmd
        assert "docs/" in cmd


class TestRgCommandBuilder:
    """Tests for RgCommandBuilder."""

    def test_minimal_config(self):
        """Test building command with minimal configuration."""
        config = RgCommandConfig(query="TODO")
        builder = RgCommandBuilder()
        cmd = builder.build(config)

        assert cmd[0] == "rg"
        assert "--json" in cmd
        assert "--no-heading" in cmd
        assert "--color" in cmd
        assert "never" in cmd
        assert "TODO" in cmd

    def test_count_only_mode(self):
        """Test count-only mode."""
        config = RgCommandConfig(
            query="TODO",
            count_only_matches=True,
        )
        builder = RgCommandBuilder()
        cmd = builder.build(config)

        assert "--count-matches" in cmd
        assert "--json" not in cmd

    def test_case_sensitivity(self):
        """Test case sensitivity modes."""
        # Smart case
        config = RgCommandConfig(query="TODO", case="smart")
        cmd = RgCommandBuilder().build(config)
        assert "-S" in cmd

        # Insensitive
        config = RgCommandConfig(query="TODO", case="insensitive")
        cmd = RgCommandBuilder().build(config)
        assert "-i" in cmd

        # Sensitive
        config = RgCommandConfig(query="TODO", case="sensitive")
        cmd = RgCommandBuilder().build(config)
        assert "-s" in cmd

    def test_search_mode_flags(self):
        """Test search mode flags."""
        config = RgCommandConfig(
            query="TODO",
            fixed_strings=True,
            word=True,
            multiline=True,
        )
        builder = RgCommandBuilder()
        cmd = builder.build(config)

        assert "-F" in cmd
        assert "-w" in cmd
        assert "--multiline" in cmd

    def test_traversal_options(self):
        """Test traversal options."""
        config = RgCommandConfig(
            query="TODO",
            follow_symlinks=True,
            hidden=True,
            no_ignore=True,
        )
        builder = RgCommandBuilder()
        cmd = builder.build(config)

        assert "-L" in cmd
        assert "-H" in cmd
        assert "-u" in cmd

    def test_file_filters(self):
        """Test file filters (globs)."""
        config = RgCommandConfig(
            query="TODO",
            include_globs=("*.py", "*.js"),
            exclude_globs=("*.pyc", "!*.min.js"),
        )
        builder = RgCommandBuilder()
        cmd = builder.build(config)

        assert "-g" in cmd
        assert "*.py" in cmd
        assert "*.js" in cmd
        assert "!*.pyc" in cmd
        assert "!*.min.js" in cmd

    def test_context_lines(self):
        """Test context lines."""
        config = RgCommandConfig(
            query="TODO",
            context_before=3,
            context_after=2,
        )
        builder = RgCommandBuilder()
        cmd = builder.build(config)

        assert "-B" in cmd
        assert "3" in cmd
        assert "-A" in cmd
        assert "2" in cmd

    def test_encoding_and_limits(self):
        """Test encoding and match limits."""
        config = RgCommandConfig(
            query="TODO",
            encoding="utf-8",
            max_count=10,
        )
        builder = RgCommandBuilder()
        cmd = builder.build(config)

        assert "--encoding" in cmd
        assert "utf-8" in cmd
        assert "-m" in cmd
        assert "10" in cmd

    def test_max_filesize_normalization(self):
        """Test max filesize normalization."""
        # Default
        config = RgCommandConfig(query="TODO")
        cmd = RgCommandBuilder().build(config)
        assert "--max-filesize" in cmd
        assert "1G" in cmd

        # Custom valid
        config = RgCommandConfig(query="TODO", max_filesize="10M")
        cmd = RgCommandBuilder().build(config)
        assert "10M" in cmd

        # Over hard cap (should clamp to 10G)
        config = RgCommandConfig(query="TODO", max_filesize="100G")
        cmd = RgCommandBuilder().build(config)
        assert "10G" in cmd

    def test_search_targets(self):
        """Test search targets (roots)."""
        config = RgCommandConfig(
            query="TODO",
            roots=("src/", "tests/"),
        )
        builder = RgCommandBuilder()
        cmd = builder.build(config)

        assert "src/" in cmd
        assert "tests/" in cmd


class TestFdCommandConfig:
    """Tests for FdCommandConfig validation."""

    def test_empty_roots_raises_error(self):
        """Test that empty roots raises ValueError."""
        with pytest.raises(ValueError, match="At least one root"):
            FdCommandConfig(roots=())

    def test_negative_depth_raises_error(self):
        """Test that negative depth raises ValueError."""
        with pytest.raises(ValueError, match="Depth must be non-negative"):
            FdCommandConfig(roots=("src/",), depth=-1)

    def test_negative_limit_raises_error(self):
        """Test that negative limit raises ValueError."""
        with pytest.raises(ValueError, match="Limit must be non-negative"):
            FdCommandConfig(roots=("src/",), limit=-1)


class TestRgCommandConfig:
    """Tests for RgCommandConfig validation."""

    def test_empty_query_raises_error(self):
        """Test that empty query raises ValueError."""
        with pytest.raises(ValueError, match="Query string is required"):
            RgCommandConfig(query="")

    def test_invalid_case_mode_raises_error(self):
        """Test that invalid case mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid case mode"):
            RgCommandConfig(query="TODO", case="invalid")

    def test_negative_context_raises_error(self):
        """Test that negative context raises ValueError."""
        with pytest.raises(ValueError, match="context_before must be non-negative"):
            RgCommandConfig(query="TODO", context_before=-1)

        with pytest.raises(ValueError, match="context_after must be non-negative"):
            RgCommandConfig(query="TODO", context_after=-1)

    def test_negative_max_count_raises_error(self):
        """Test that negative max_count raises ValueError."""
        with pytest.raises(ValueError, match="max_count must be non-negative"):
            RgCommandConfig(query="TODO", max_count=-1)

    def test_negative_timeout_raises_error(self):
        """Test that negative timeout raises ValueError."""
        with pytest.raises(ValueError, match="timeout_ms must be non-negative"):
            RgCommandConfig(query="TODO", timeout_ms=-1)
