"""Tests for the shared _validate_positive_int utility (RFC-0015 P1-B).

Also tests invalid_enum_error() for consistent enum validation errors (#449).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools._validators import (
    _validate_positive_int,
    invalid_enum_error,
)

# --- Happy path ---


def test_valid_int_passes() -> None:
    args: dict = {"max_edges": 30}
    _validate_positive_int(args, "max_edges")
    assert args["max_edges"] == 30


def test_none_is_noop() -> None:
    args: dict = {"max_edges": None}
    _validate_positive_int(args, "max_edges")
    assert args["max_edges"] is None


def test_missing_key_is_noop() -> None:
    args: dict = {}
    _validate_positive_int(args, "max_edges")
    assert args == {}


def test_whole_number_float_coerced() -> None:
    args: dict = {"max_edges": 30.0}
    _validate_positive_int(args, "max_edges")
    assert args["max_edges"] == 30
    assert type(args["max_edges"]) is int


def test_whole_number_float_1_coerced() -> None:
    args: dict = {"max_edges": 1.0}
    _validate_positive_int(args, "max_edges")
    assert args["max_edges"] == 1
    assert type(args["max_edges"]) is int


# --- Error path ---


def test_fractional_float_rejected() -> None:
    with pytest.raises(ValueError, match="max_edges"):
        _validate_positive_int({"max_edges": 30.5}, "max_edges")


def test_float_zero_rejected() -> None:
    with pytest.raises(ValueError, match="max_edges"):
        _validate_positive_int({"max_edges": 0.0}, "max_edges")


def test_float_negative_rejected() -> None:
    with pytest.raises(ValueError, match="max_edges"):
        _validate_positive_int({"max_edges": -1.0}, "max_edges")


def test_bool_true_rejected() -> None:
    with pytest.raises(ValueError, match="max_edges"):
        _validate_positive_int({"max_edges": True}, "max_edges")


def test_bool_false_rejected() -> None:
    with pytest.raises(ValueError, match="max_edges"):
        _validate_positive_int({"max_edges": False}, "max_edges")


def test_zero_int_rejected() -> None:
    with pytest.raises(ValueError, match="max_edges"):
        _validate_positive_int({"max_edges": 0}, "max_edges")


def test_negative_int_rejected() -> None:
    with pytest.raises(ValueError, match="max_edges"):
        _validate_positive_int({"max_edges": -5}, "max_edges")


def test_string_rejected() -> None:
    with pytest.raises(ValueError, match="max_edges"):
        _validate_positive_int({"max_edges": "30"}, "max_edges")


# --- invalid_enum_error tests (issue #449) ---


def test_invalid_enum_error_basic() -> None:
    """Error message enumerates valid values in sorted order."""
    exc = invalid_enum_error("mode", "invalid", ["file", "all", "project"])
    # Valid values should be sorted: all, file, project
    assert str(exc) == "Invalid mode: 'invalid'. Valid values: all, file, project"


def test_invalid_enum_error_single_valid() -> None:
    """Works with a single valid value."""
    exc = invalid_enum_error("action", "bad", ["only_one"])
    assert str(exc) == "Invalid action: 'bad'. Valid values: only_one"


def test_invalid_enum_error_with_context() -> None:
    """Context string is appended to the message."""
    exc = invalid_enum_error(
        "mode", "summary", ["all", "dead_functions"], context="for action=dead"
    )
    assert (
        str(exc)
        == "Invalid mode: 'summary'. Valid values: all, dead_functions (for action=dead)"
    )


def test_invalid_enum_error_preserves_value_type() -> None:
    """The received value is quoted with repr()."""
    exc = invalid_enum_error("format_type", "json", ["csv", "toon"])
    assert str(exc) == "Invalid format_type: 'json'. Valid values: csv, toon"


def test_invalid_enum_error_empty_list() -> None:
    """Edge case: empty valid list (should not happen in practice)."""
    exc = invalid_enum_error("mode", "anything", [])
    # Note: trailing space comes from ', '.join([])
    assert str(exc) == "Invalid mode: 'anything'. Valid values: "


def test_invalid_enum_error_routes_to_validation_recovery_hint() -> None:
    """opencode P2 (#490): the enumerated message must classify as a
    validation error with an actionable (non-generic) recovery hint."""
    from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
        build_agent_friendly_error,
    )
    from tree_sitter_analyzer.mcp.tools._validators import invalid_enum_error

    err = invalid_enum_error("mode", "bogus", ["all", "summary"])
    payload = build_agent_friendly_error("health", err)
    assert payload["error_type"] == "validation"
    assert "valid values" in payload["recovery_hint"].lower()
