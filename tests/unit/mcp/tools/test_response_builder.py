"""Unit tests for :mod:`tree_sitter_analyzer.mcp.tools._response_builder`.

The factory's job is to make the ``verdict='OK'``-class of bug
impossible at construction time. These tests pin:

  * Every canonical verdict is accepted; every non-canonical string
    raises :class:`InvalidVerdictError`.
  * Warnings are included when provided, omitted when empty.
  * :func:`build_error` defaults to ``verdict="ERROR"``.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools._response_builder import (
    CANONICAL_VERDICTS,
    InvalidVerdictError,
    build_error,
    build_response,
)
from tree_sitter_analyzer.mcp.tools.tool_response import (
    CANONICAL_VERDICTS as TOOL_RESPONSE_VERDICTS,
)
from tree_sitter_analyzer.mcp.tools.tool_response import validate_tool_response


class TestCanonicalVerdictSet:
    """The factory's vocabulary must match the validator's vocabulary."""

    def test_set_is_frozen_and_matches_validator(self) -> None:
        assert isinstance(CANONICAL_VERDICTS, frozenset)
        # Drift between the factory and the validator would re-introduce
        # the original bug class. Pin equality here.
        assert CANONICAL_VERDICTS == TOOL_RESPONSE_VERDICTS
        assert CANONICAL_VERDICTS == {
            "SAFE",
            "REVIEW",
            "CAUTION",
            "UNSAFE",
            "INFO",
            "WARN",
            "ERROR",
            "NOT_FOUND",
        }


class TestBuildResponse:
    """Happy path + the rejection contract."""

    @pytest.mark.parametrize("verdict", sorted(CANONICAL_VERDICTS))
    def test_accepts_every_canonical_verdict(self, verdict: str) -> None:
        envelope = build_response(verdict=verdict)
        assert envelope == {"success": True, "verdict": verdict}
        # Output must also satisfy the runtime validator.
        validate_tool_response(envelope, f"build_response[{verdict}]")

    def test_default_success_is_true_and_merges_fields(self) -> None:
        envelope = build_response(
            verdict="INFO",
            mode="summary",
            total_routes=3,
        )
        assert envelope == {
            "success": True,
            "verdict": "INFO",
            "mode": "summary",
            "total_routes": 3,
        }

    def test_explicit_success_false_with_error_passes(self) -> None:
        # Tools sometimes go through build_response (not build_error)
        # for NOT_FOUND cases that carry extra payload.
        envelope = build_response(
            verdict="NOT_FOUND",
            success=False,
            error="not found",
            available=["a", "b"],
        )
        validate_tool_response(envelope, "explicit_failure")

    @pytest.mark.parametrize(
        "bad",
        [
            "OK",
            "safe",
            "Safe",
            "CLEAN",
            "NEEDS_REVIEW",
            "LOOKS_GOOD",
            "READY",
            "",
            "info",
        ],
    )
    def test_rejects_non_canonical_verdict(self, bad: str) -> None:
        with pytest.raises(InvalidVerdictError, match="not in canonical set"):
            build_response(verdict=bad)

    def test_invalid_verdict_error_is_a_value_error(self) -> None:
        # Subclassing ValueError lets callers reuse generic argument
        # validation handlers.
        with pytest.raises(ValueError):
            build_response(verdict="OK")

    def test_error_message_is_actionable(self) -> None:
        with pytest.raises(InvalidVerdictError) as exc_info:
            build_response(verdict="OK")
        msg = str(exc_info.value)
        # Names the bad verdict, lists canonical options, points to the
        # right helper for the failure case.
        assert "'OK'" in msg
        assert "SAFE" in msg
        assert "build_error" in msg


class TestWarnings:
    """Warnings list: included when present, omitted when empty/None."""

    def test_omits_warnings_key_when_none(self) -> None:
        envelope = build_response(verdict="INFO")
        assert "warnings" not in envelope

    def test_omits_warnings_key_when_empty_list(self) -> None:
        # Falsy list treated the same as None — consumers don't have to
        # handle ``warnings: []``.
        envelope = build_response(verdict="INFO", warnings=[])
        assert "warnings" not in envelope

    def test_includes_and_copies_warnings(self) -> None:
        warnings_in = ["stale_cache: run --mode resolve"]
        envelope = build_response(verdict="INFO", warnings=warnings_in)
        assert envelope["warnings"] == warnings_in
        # Defensive copy — mutating the input must not retroactively
        # mutate the envelope.
        warnings_in.append("two")
        assert envelope["warnings"] == ["stale_cache: run --mode resolve"]


class TestBuildError:
    """``build_error`` is a thin wrapper over ``build_response``."""

    def test_defaults_verdict_to_error(self) -> None:
        envelope = build_error(error="boom")
        assert envelope == {"success": False, "verdict": "ERROR", "error": "boom"}
        validate_tool_response(envelope, "default_error")

    def test_accepts_not_found_verdict_and_extra_fields(self) -> None:
        envelope = build_error(
            error="symbol 'xyz' not found",
            verdict="NOT_FOUND",
            available_functions=["a", "b"],
        )
        assert envelope["verdict"] == "NOT_FOUND"
        assert envelope["success"] is False
        assert envelope["available_functions"] == ["a", "b"]

    def test_rejects_non_canonical_verdict(self) -> None:
        with pytest.raises(InvalidVerdictError):
            build_error(error="boom", verdict="OOPS")
