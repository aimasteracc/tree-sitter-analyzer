"""Shared fixtures for utility tests."""

import logging

import pytest


@pytest.fixture
def clean_logger():
    """Create a clean logger instance that doesn't pollute other tests."""

    def _make_logger(name="test_logger"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(logging.DEBUG)
        return logger

    return _make_logger
