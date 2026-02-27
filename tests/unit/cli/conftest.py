"""Shared fixtures for CLI tests."""

import argparse

import pytest


@pytest.fixture
def make_namespace():
    """Factory fixture for creating argparse Namespace objects."""

    def _make_namespace(**kwargs):
        defaults = {
            "command": None,
            "path": ".",
            "format": "table",
            "output": None,
            "verbose": False,
            "quiet": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    return _make_namespace
