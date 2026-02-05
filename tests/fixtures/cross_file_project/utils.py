"""Utility module with helper functions."""


def helper(data):
    """Helper function that processes data."""
    return process_data(data)


def validate(value):
    """Validate the processed value."""
    return value is not None


def process_data(data):
    """Internal function that processes data."""
    return data.upper() if data else None
