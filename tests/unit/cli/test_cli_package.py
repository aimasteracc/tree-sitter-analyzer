#!/usr/bin/env python3
"""
Tests for CLI package __init__.py
"""


def test_cli_imports() -> None:
    """Test that CLI package can be imported."""
    import tree_sitter_analyzer.cli

    assert tree_sitter_analyzer.cli is not None


def test_cli_exports() -> None:
    """Test that CLI package exports expected names."""
    from tree_sitter_analyzer.cli import (
        DescribeQueryCommand,
        InfoCommand,
        ListQueriesCommand,
        ShowExtensionsCommand,
        ShowLanguagesCommand,
        get_analysis_engine,
        main,
        query_loader,
    )

    assert DescribeQueryCommand is not None
    assert InfoCommand is not None
    assert ListQueriesCommand is not None
    assert ShowExtensionsCommand is not None
    assert ShowLanguagesCommand is not None
    assert main is not None
    assert query_loader is not None
    assert get_analysis_engine is not None


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


def test_cli_import_error_fallback() -> None:
    """Test CLI package sets None fallbacks when core imports fail."""
    import importlib
    import sys
    from unittest.mock import patch

    cli_mods_snapshot = {m: sys.modules[m] for m in list(sys.modules) if m.startswith("tree_sitter_analyzer.cli")}

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
        for mod in list(sys.modules):
            if mod.startswith("tree_sitter_analyzer.cli"):
                del sys.modules[mod]
        sys.modules.update(cli_mods_snapshot)
