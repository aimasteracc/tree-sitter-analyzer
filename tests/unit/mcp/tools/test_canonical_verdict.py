"""Tests for the canonical verdict vocabulary enforcement.

The :data:`CANONICAL_VERDICTS` set is the single source of truth for
what verdict strings agents are allowed to branch on. If a tool emits a
string outside this set, the agent's switch statement falls through to
default-INFO behavior — that is a real, multiple-times-observed bug
(see AGENT_UX_PAIN.md pains #9, #93). These tests pin both the contents
of the canonical set and the rejection behavior in
:func:`validate_tool_response`.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.tool_response import (
    CANONICAL_VERDICTS,
    validate_tool_response,
)


class TestCanonicalVerdictSet:
    """The vocabulary itself is part of the public contract."""

    def test_set_is_frozen(self):
        # frozenset prevents accidental mutation by importers.
        assert isinstance(CANONICAL_VERDICTS, frozenset)

    def test_set_contents_match_documented_contract(self):
        # Pinning the exact membership stops drift. If you add a new
        # verdict, update this test deliberately.
        assert CANONICAL_VERDICTS == {
            "SAFE",
            "CAUTION",
            "REVIEW",
            "UNSAFE",
            "INFO",
            "WARN",
            "ERROR",
            "NOT_FOUND",
        }

    def test_no_lowercase_or_mixed_case_aliases(self):
        # All canonical verdicts are UPPER_SNAKE. Catches a regression
        # where someone might add e.g. "Safe" or "review".
        for v in CANONICAL_VERDICTS:
            assert v == v.upper(), f"{v} must be UPPER_SNAKE"


class TestValidateToolResponseVerdict:
    """The verdict check is the gate that prevents pains #9/#93 recurring."""

    def test_accepts_payload_with_no_verdict_key(self):
        # The check is opt-in: legacy tools that haven't been migrated
        # yet should not start failing the contract.
        assert validate_tool_response({"success": True}, "noop") is None

    @pytest.mark.parametrize("verdict", sorted(CANONICAL_VERDICTS))
    def test_accepts_every_canonical_verdict(self, verdict: str):
        assert (
            validate_tool_response({"success": True, "verdict": verdict}, "ok") is None
        )

    @pytest.mark.parametrize(
        "bad",
        [
            "CLEAN",
            "NEEDS_REVIEW",
            "LOOKS_GOOD",
            "READY",
            "ok",
            "safe",
            "Safe",
        ],
    )
    def test_rejects_non_canonical_strings(self, bad: str):
        with pytest.raises(AssertionError, match="not in the canonical set"):
            validate_tool_response({"success": True, "verdict": bad}, "bad")

    def test_rejects_non_string_verdict(self):
        with pytest.raises(AssertionError, match="must be str"):
            validate_tool_response({"success": True, "verdict": 1}, "bad")
        with pytest.raises(AssertionError, match="must be str"):
            validate_tool_response({"success": True, "verdict": None}, "bad")

    def test_error_message_names_the_tool(self):
        with pytest.raises(AssertionError, match=r"my_tool:"):
            validate_tool_response({"success": True, "verdict": "CLEAN"}, "my_tool")
