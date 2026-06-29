#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.__main__ module

Provides tests for the main entry point.
"""

import pytest


class TestMainEntry:
    """Test class for __main__.py"""

    def test_main_module_import(self):
        """Test that __main__ module imports without errors."""
        try:
            import tree_sitter_analyzer.__main__  # noqa: F401
        except ImportError as e:
            pytest.fail(f"Failed to import __main__ module: {e}")

    def test_main_module_exposes_cli_main(self):
        """Test that __main__ module exposes the cli_main.main callable."""
        import tree_sitter_analyzer.__main__ as main_mod

        assert hasattr(main_mod, "main")
        assert callable(main_mod.main)

    def test_cli_integration_availability(self):
        """Test CLI integration availability"""
        try:
            from tree_sitter_analyzer import cli

            assert hasattr(cli, "main")
        except ImportError:
            pytest.fail("CLI module not available")
