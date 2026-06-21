#!/usr/bin/env python3
"""
Tests for CLI package __init__.py
"""

import pytest


def test_cli_imports() -> None:
    """Test that CLI package can be imported."""
    import tree_sitter_analyzer.cli

    assert tree_sitter_analyzer.cli.__name__ == "tree_sitter_analyzer.cli"


def test_cli_exports() -> None:
    """Test that CLI package exports expected names.

    Force a fresh import even if a sibling test (e.g. the
    sys.modules-polluting fallback test, even when skipped, in
    case xdist loadfile order ever pre-loads it) left the cli
    module cached with None-typed exports.
    """
    import importlib
    # Re-run cli/__init__.py without invalidating already-collected modules.
    # Deleting cli_main or command modules makes later patch("...") calls hit
    # freshly imported modules while tests still hold old function objects.
    cli = importlib.import_module("tree_sitter_analyzer.cli")
    cli = importlib.reload(cli)

    assert isinstance(cli.DescribeQueryCommand, type)
    assert isinstance(cli.InfoCommand, type)
    assert isinstance(cli.ListQueriesCommand, type)
    assert isinstance(cli.ShowExtensionsCommand, type)
    assert isinstance(cli.ShowLanguagesCommand, type)
    assert callable(cli.main)
    assert callable(cli.query_loader.list_supported_languages)
    assert callable(cli.get_analysis_engine)


def test_cli_all_attribute() -> None:
    """Test that CLI __all__ contains expected attributes."""
    from tree_sitter_analyzer.cli import __all__ as cli_all

    assert "InfoCommand" in cli_all
    assert "ListQueriesCommand" in cli_all
    assert "DescribeQueryCommand" in cli_all
    assert "ShowLanguagesCommand" in cli_all
    assert "ShowExtensionsCommand" in cli_all
    assert "query_loader" in cli_all
    assert "get_analysis_engine" in cli_all
    assert "main" in cli_all


def test_cli_info_commands_imported() -> None:
    """Test that CLI info commands are properly imported."""
    from tree_sitter_analyzer.cli import (
        DescribeQueryCommand,
        InfoCommand,
        ListQueriesCommand,
        ShowExtensionsCommand,
        ShowLanguagesCommand,
    )

    # Verify they are classes
    assert isinstance(DescribeQueryCommand, type)
    assert isinstance(InfoCommand, type)
    assert isinstance(ListQueriesCommand, type)
    assert isinstance(ShowExtensionsCommand, type)
    assert isinstance(ShowLanguagesCommand, type)


def test_cli_has_dir() -> None:
    """Test that CLI package has expected directory structure."""
    import tree_sitter_analyzer.cli

    assert hasattr(tree_sitter_analyzer.cli, "__all__")
    assert hasattr(tree_sitter_analyzer.cli, "__doc__")


@pytest.mark.skip(
    reason="This test pollutes sys.modules/sys.meta_path in a way that "
    "leaks into neighbouring tests on xdist loadfile workers — "
    "test_cli_exports / test_find_and_grep_cli observe a None-fallback "
    "cli module afterwards on macOS+Windows. The fallback path it "
    "guards is defensive (imports already work in real installs); "
    "skip until the test is rewritten with subprocess isolation."
)
def test_cli_import_error_fallback() -> None:
    """Test CLI package sets None fallbacks when core imports fail."""
    import importlib
    import sys

    block_list = {
        "tree_sitter_analyzer.cli_main",
        "tree_sitter_analyzer.core.analysis_engine",
        "tree_sitter_analyzer.query_loader",
    }

    class BlockFinder:
        def find_spec(self, fullname, path, target=None):
            if fullname in block_list:
                raise ImportError(f"Blocked import of {fullname}")
            return None

    finder = BlockFinder()
    sys.meta_path.insert(0, finder)

    try:
        for mod in list(sys.modules):
            if mod.startswith("tree_sitter_analyzer.cli"):
                del sys.modules[mod]

        cli = importlib.import_module("tree_sitter_analyzer.cli")
        assert cli.main is None, f"Expected main=None, got {cli.main}"
        assert cli.get_analysis_engine is None, (
            f"Expected get_analysis_engine=None, got {cli.get_analysis_engine}"
        )
        assert cli.query_loader is None, (
            f"Expected queryloader=None, got {cli.query_loader}"
        )
    finally:
        sys.meta_path.remove(finder)
        # Drop every module this test may have polluted (cli + the
        # blocked imports themselves) and force a fresh import. The
        # earlier "restore from snapshot" approach was unreliable
        # because the snapshot was often empty on xdist workers and
        # because `cli_main` could be cached in a None-resolved state.
        polluted = (
            "tree_sitter_analyzer.cli",
            "tree_sitter_analyzer.cli_main",
            "tree_sitter_analyzer.core.analysis_engine",
            "tree_sitter_analyzer.query_loader",
        )
        for mod in list(sys.modules):
            if mod.startswith("tree_sitter_analyzer.cli") or mod in polluted:
                del sys.modules[mod]
        importlib.import_module("tree_sitter_analyzer.cli")
