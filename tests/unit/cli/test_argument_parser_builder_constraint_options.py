"""Focused parser coverage for constraint-check CLI options."""

import argparse

import pytest

from tree_sitter_analyzer.cli.argument_parser_builder import (
    _add_mcp_equivalent_options,
)


def test_constraints_read_only_option_sets_exact_destination() -> None:
    parser = argparse.ArgumentParser()
    _add_mcp_equivalent_options(parser)

    args = parser.parse_args(["--constraints-read-only"])

    assert args.constraints_read_only is True


class TestFullIndexMCPEquivalentOptions:
    """Regression: CLI --full-index-mode choices must match MCP tool valid modes.

    Dogfood-found bug: argparse exposed {rebuild,stats,clear} but CodeGraphFullIndexTool
    only accepts {full,incremental}. Using TSA on TSA to discover and verify the fix.
    """

    def _make_parser(self):
        p = argparse.ArgumentParser()
        _add_mcp_equivalent_options(p)
        return p

    def test_full_index_mode_default_is_incremental(self):
        """Default mode must match MCP tool default ('incremental')."""
        parser = self._make_parser()
        args = parser.parse_args(["--full-index"])
        assert args.full_index_mode == "incremental"

    def test_full_index_mode_accepts_full(self):
        parser = self._make_parser()
        args = parser.parse_args(["--full-index", "--full-index-mode", "full"])
        assert args.full_index_mode == "full"

    def test_full_index_mode_accepts_incremental(self):
        parser = self._make_parser()
        args = parser.parse_args(["--full-index", "--full-index-mode", "incremental"])
        assert args.full_index_mode == "incremental"

    def test_full_index_mode_rejects_rebuild(self):
        """'rebuild' was the old invalid choice — must now be rejected."""
        parser = self._make_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--full-index", "--full-index-mode", "rebuild"])

    def test_full_index_mode_rejects_stats(self):
        """'stats' was an old invalid choice — must now be rejected."""
        parser = self._make_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--full-index", "--full-index-mode", "stats"])
