#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer/__main__.py module.

Tests that the package entry point is importable and that the CLI
can be invoked via `python -m tree_sitter_analyzer`.
"""

import subprocess
import sys


class TestMainModuleImport:
    """Tests for importing the __main__ module."""

    def test_module_importable(self):
        """Test that tree_sitter_analyzer.__main__ can be imported."""
        import tree_sitter_analyzer.__main__  # noqa: F401

    def test_main_function_importable(self):
        """Test that the main function is importable from __main__."""
        from tree_sitter_analyzer.__main__ import main

        assert callable(main)


class TestMainCLIEntryPoints:
    """Tests for running the package as a CLI via subprocess."""

    def test_help_flag_succeeds(self):
        """Test that `python -m tree_sitter_analyzer --help` exits with code 0."""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"--help exited with code {result.returncode}; stderr: {result.stderr}"
        )

    def test_no_args_runs_without_crash(self):
        """Test that `python -m tree_sitter_analyzer` with no args doesn't crash with an unhandled exception."""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # May exit with non-zero (e.g., missing required args), but should not crash
        assert result.returncode in (0, 1, 2), (
            f"Unexpected exit code {result.returncode}; stderr: {result.stderr}"
        )
