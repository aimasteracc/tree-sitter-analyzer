"""Tests for the shared _validate_positive_int utility (RFC-0015 P1-B)."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools._validators import _validate_positive_int

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
