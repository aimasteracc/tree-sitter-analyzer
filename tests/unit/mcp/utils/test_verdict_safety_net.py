"""Tests for the verdict-injection safety net in apply_output_format_to_response.

Background — pain pass 4 audit: 6 utility tools shipped without verdict
and the universal helper ``apply_output_format_to_response`` is the single
bottleneck every tool calls before returning. Injecting a default ``INFO``
here catches every future tool that forgets to set verdict, without forcing
36 separate patches.
"""

from __future__ import annotations

from tree_sitter_analyzer.mcp.utils.format_helper import (
    apply_output_format_to_response,
)


class TestVerdictSafetyNetJSON:
    """JSON callers must also see the default verdict."""

    def test_success_without_verdict_gets_info(self):
        out = apply_output_format_to_response({"success": True}, "json")
        assert out["verdict"] == "INFO"

    def test_explicit_verdict_is_preserved(self):
        out = apply_output_format_to_response(
            {"success": True, "verdict": "CAUTION"}, "json"
        )
        assert out["verdict"] == "CAUTION"

    def test_failure_responses_are_not_touched(self):
        # Failures use the explicit error envelope; we don't auto-assign
        # a verdict because the agent shouldn't branch on it. The tool
        # (or the validator) handles failures separately.
        out = apply_output_format_to_response(
            {"success": False, "error": "boom"}, "json"
        )
        assert "verdict" not in out


class TestVerdictSafetyNetIdempotence:
    """Repeated calls must converge — important when wrapper helpers
    re-format an already-formatted response."""

    def test_double_application_stays_info(self):
        first = apply_output_format_to_response({"success": True}, "json")
        second = apply_output_format_to_response(first, "json")
        assert second["verdict"] == "INFO"

    def test_does_not_overwrite_existing_value(self):
        first = apply_output_format_to_response(
            {"success": True, "verdict": "CAUTION"}, "json"
        )
        second = apply_output_format_to_response(first, "json")
        assert second["verdict"] == "CAUTION"
