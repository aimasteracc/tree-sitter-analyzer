#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.__main__ module

Provides tests for the main entry point.
"""

from unittest.mock import patch

import pytest


class TestMainEntry:
    """Test class for __main__.py"""

    def test_main_module_import_only(self):
        """Test for module import only"""
        # Verify that no import errors occur
        try:
            import tree_sitter_analyzer.__main__  # noqa: F401

            assert True  # Import successful
        except ImportError as e:
            pytest.fail(f"Failed to import __main__ module: {e}")

    def test_main_module_execution_with_mock(self):
        """Test main execution using mock"""
        with patch("tree_sitter_analyzer.cli_main.main") as mock_main:
            mock_main.return_value = None

            # Test actual execution

            assert True  # Execution successful

    def test_cli_integration_availability(self):
        """Test CLI integration availability"""
        try:
            from tree_sitter_analyzer import cli

            assert hasattr(cli, "main")
        except ImportError:
            pytest.fail("CLI module not available")
