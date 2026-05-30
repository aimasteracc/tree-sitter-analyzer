"""Shared fixtures for grammar_coverage unit tests."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def make_parser_mock():
    """Factory: return a mock parser that returns *tree* from parse()."""

    def _factory(tree: MagicMock) -> MagicMock:
        parser = MagicMock()
        parser.parse.return_value = tree
        return parser

    return _factory


def _make_parser_mock(tree: MagicMock) -> MagicMock:
    """Module-level helper for non-fixture call sites."""
    parser = MagicMock()
    parser.parse.return_value = tree
    return parser
