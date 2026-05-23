#!/usr/bin/env python3
"""
Tests for fd_rg_utils module - build_rg_command.

This module tests the shared utilities for fd and ripgrep
command execution and result processing.
"""

from tree_sitter_analyzer.mcp.tools import fd_rg_utils


class TestBuildRgCommand:
    """Tests for build_rg_command function."""

    def test_build_basic_command(self):
        """Test building basic ripgrep command."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "rg" in cmd
        assert "--json" in cmd
        assert "--no-heading" in cmd
        assert "--color" in cmd
        assert "never" in cmd
        assert "test" in cmd
        assert "/path" in cmd

    def test_build_with_case_smart(self):
        """Test building with smart case sensitivity."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-S" in cmd

    def test_build_with_case_insensitive(self):
        """Test building with insensitive case."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case="insensitive",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-i" in cmd

    def test_build_with_case_sensitive(self):
        """Test building with sensitive case."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case="sensitive",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-s" in cmd

    def test_build_with_fixed_strings(self):
        """Test building with fixed strings."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=True,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-F" in cmd

    def test_build_with_word(self):
        """Test building with word matching."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=True,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-w" in cmd

    def test_build_with_multiline(self):
        """Test building with multiline support."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=True,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "--multiline" in cmd

    def test_build_with_include_globs(self):
        """Test building with include globs."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=["*.py", "*.js"],
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-g" in cmd
        assert "*.py" in cmd
        assert "*.js" in cmd

    def test_build_with_exclude_globs(self):
        """Test building with exclude globs."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=["*.log", "__pycache__"],
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-g" in cmd
        assert "!*.log" in cmd or "*.log" in cmd

    def test_build_with_context_before(self):
        """Test building with context before."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=3,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-B" in cmd
        assert "3" in cmd

    def test_build_with_context_after(self):
        """Test building with context after."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=3,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-A" in cmd
        assert "3" in cmd

    def test_build_with_encoding(self):
        """Test building with encoding."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding="utf-8",
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "--encoding" in cmd
        assert "utf-8" in cmd

    def test_build_with_max_count(self):
        """Test building with max count."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=100,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-m" in cmd
        assert "100" in cmd

    def test_build_with_max_filesize(self):
        """Test building with max filesize."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize="10M",
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "--max-filesize" in cmd
        assert "10M" in cmd

    def test_build_with_follow_symlinks(self):
        """Test building with follow symlinks."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=True,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-L" in cmd

    def test_build_with_hidden(self):
        """Test building with hidden files."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=True,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        # Pain #27 (2026-05-23): this test used to assert "-H" in cmd because
        # the implementation passed -H for hidden=True. rg's actual semantic
        # is -H = --with-filename (default on for multi-file). To search
        # hidden files you need the LONG form --hidden. The old assertion
        # was pinning the bug as correct behavior.
        assert "--hidden" in cmd
        assert "-H" not in cmd

    def test_build_with_no_ignore(self):
        """Test building with no ignore."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=True,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-u" in cmd

    def test_build_count_only_matches(self):
        """Test building with count only matches."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
            count_only_matches=True,
        )
        assert "--count-matches" in cmd
        assert "--json" not in cmd  # Count mode doesn't use JSON
