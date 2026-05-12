#!/usr/bin/env python3
"""
Tests for CLI __main__ module entry point.
"""

from unittest.mock import patch


def test_cli_main_module_importable() -> None:
    """Test that cli.__main__ module can be imported."""
    from tree_sitter_analyzer.cli import __main__ as cli_main

    assert cli_main is not None
    assert hasattr(cli_main, "__doc__")


def test_cli_main_has_main_function() -> None:
    """Test that cli.__main__ references the main function."""
    from tree_sitter_analyzer.cli.__main__ import main

    assert main is not None
    assert callable(main)


def test_cli_main_runs_main_when_executed() -> None:
    """Test that __main__ executes main() when run as script."""
    import runpy

    with patch("tree_sitter_analyzer.cli_main.main") as mock_main:
        runpy.run_module("tree_sitter_analyzer.cli.__main__", run_name="__main__")
        mock_main.assert_called_once()
