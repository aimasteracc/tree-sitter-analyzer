"""Tricky module to test AST vs regex call detection.

This module contains function names in comments, strings, and variables
that would fool a regex-based detector but NOT an AST-based one.
"""


def real_caller():
    """This function ACTUALLY calls helper()."""
    return helper("data")


def fake_caller_comment():
    """This function does NOT call helper.

    # helper() is mentioned in a comment, not a real call
    """
    return 42


def fake_caller_string():
    """This function does NOT call helper."""
    msg = "please call helper() for help"
    return msg


def fake_caller_variable():
    """This function assigns helper to a variable but doesn't call it as function."""
    helper_ref = "helper"
    return helper_ref


def helper(data):
    """A helper function (duplicated name to test scope)."""
    return data
