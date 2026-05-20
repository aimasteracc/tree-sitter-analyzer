"""Argument validation helpers for search_content."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .output_format_validator import get_default_validator

PathListValidator = Callable[[list[str]], list[str]]

_STRING_OPTIONS = ["case", "encoding", "max_filesize"]
_BOOLEAN_OPTIONS = [
    "fixed_strings",
    "word",
    "multiline",
    "follow_symlinks",
    "hidden",
    "no_ignore",
    "count_only_matches",
    "summary_only",
    "enable_parallel",
]
_INTEGER_OPTIONS = ["context_before", "context_after", "max_count", "timeout_ms"]
_STRING_LIST_OPTIONS = ["include_globs", "exclude_globs"]


def validate_search_arguments(
    arguments: dict[str, Any],
    validate_roots: PathListValidator,
    validate_files: PathListValidator,
) -> bool:
    """Validate query, roots/files, and search option types."""
    validator = get_default_validator()
    validator.validate_output_format_exclusion(arguments)

    _validate_query_and_inputs(arguments)
    _validate_option_types(arguments)

    if "roots" in arguments:
        validate_roots(arguments["roots"])
    if "files" in arguments:
        validate_files(arguments["files"])

    return True


def _validate_query_and_inputs(arguments: dict[str, Any]) -> None:
    """Require a non-empty query and at least one search target."""
    if (
        "query" not in arguments
        or not isinstance(arguments["query"], str)
        or not arguments["query"].strip()
    ):
        raise ValueError("query is required and must be a non-empty string")
    if "roots" not in arguments and "files" not in arguments:
        raise ValueError("Either roots or files must be provided")


def _validate_option_types(arguments: dict[str, Any]) -> None:
    """Validate optional ripgrep argument types."""
    _validate_options(arguments, _STRING_OPTIONS, str, "a string")
    _validate_options(arguments, _BOOLEAN_OPTIONS, bool, "a boolean")
    _validate_options(arguments, _INTEGER_OPTIONS, int, "an integer")
    for key in _STRING_LIST_OPTIONS:
        if key in arguments:
            value = arguments[key]
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise ValueError(f"{key} must be an array of strings")


def _validate_options(
    arguments: dict[str, Any],
    keys: list[str],
    expected_type: type,
    type_phrase: str,
) -> None:
    """Validate homogeneous optional argument types."""
    for key in keys:
        if key in arguments and not isinstance(arguments[key], expected_type):
            raise ValueError(f"{key} must be {type_phrase}")
