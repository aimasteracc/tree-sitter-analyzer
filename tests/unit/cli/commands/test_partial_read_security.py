#!/usr/bin/env python3
"""Tests for PartialReadCommand security validation."""
import argparse
from pathlib import Path

import pytest


class TestPartialReadCommandSecurity:
    """Test security validation in PartialReadCommand."""

    @pytest.fixture
    def command_class(self):
        """Get PartialReadCommand class."""
        from tree_sitter_analyzer.cli.commands.partial_read_command import (
            PartialReadCommand,
        )

        return PartialReadCommand

    def test_rejects_path_traversal_attack(self, command_class, tmp_path):
        """Should reject paths with .. traversal."""
        # Create a file in tmp_path
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        args = argparse.Namespace(
            file_path="../../../etc/passwd",
            start_line=1,
            end_line=10,
            output_format="text",
        )

        command = command_class(args)
        result = command.validate_file()

        assert result is False

    def test_rejects_symlink_outside_project(self, command_class, tmp_path):
        """Should reject symlinks pointing outside project."""
        # Create symlink pointing outside
        symlink = tmp_path / "symlink"
        try:
            symlink.symlink_to("/etc/passwd")
        except OSError:
            pytest.skip("Cannot create symlink on this system")

        args = argparse.Namespace(
            file_path=str(symlink),
            start_line=1,
            end_line=10,
            output_format="text",
        )

        command = command_class(args)
        result = command.validate_file()

        assert result is False

    def test_accepts_valid_file(self, command_class, tmp_path):
        """Should accept valid files within project."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n" * 10)

        args = argparse.Namespace(
            file_path=str(test_file),
            start_line=1,
            end_line=5,
            output_format="text",
        )

        command = command_class(args)
        result = command.validate_file()

        assert result is True

    def test_rejects_absolute_path_outside_project(self, command_class):
        """Should reject absolute paths outside project."""
        args = argparse.Namespace(
            file_path="/etc/passwd",
            start_line=1,
            end_line=10,
            output_format="text",
        )

        command = command_class(args)
        result = command.validate_file()

        assert result is False
