"""Unit tests for the agent-envelope rules in ``envelope_violations``."""

from __future__ import annotations

from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.tool_response import (
    COMPLETENESS_STATUSES,
    FAILURE_VERDICTS,
    envelope_violations,
    known_completeness_reasons,
)

REASON = "MISSING_INDEX"


def rules(payload: Any) -> list[str]:
    return [rule for rule, _ in envelope_violations(payload, "t")]


def ok(**extra: Any) -> dict[str, Any]:
    return {"success": True, **extra}


def fail(**extra: Any) -> dict[str, Any]:
    return {"success": False, "error": "boom", "error_code": "E", **extra}


class TestBase:
    def test_conforming_success_has_no_violations(self) -> None:
        assert envelope_violations(ok(verdict="SAFE")) == []

    def test_conforming_failure_has_no_violations(self) -> None:
        assert envelope_violations(fail(verdict="ERROR")) == []

    @pytest.mark.parametrize(
        "payload",
        [
            [],
            {},
            {"success": "yes"},
            {"success": False, "error_code": "E"},
            {"success": True, "verdict": "NO_PATH"},
        ],
    )
    def test_base_contract_reported_as_single_base_rule(self, payload: Any) -> None:
        assert rules(payload) == ["base"]

    def test_never_raises_and_names_tool(self) -> None:
        found = envelope_violations({"x": 1}, "nav")
        assert found[0][0] == "base"
        assert "nav" in found[0][1]


class TestVerdict:
    def test_agent_summary_must_be_dict(self) -> None:
        assert rules(ok(agent_summary="SAFE")) == ["agent-summary-shape"]

    def test_non_canonical_summary_verdict(self) -> None:
        assert rules(ok(agent_summary={"verdict": "NO_PATH"})) == ["verdict-canonical"]

    def test_mirror_mismatch(self) -> None:
        assert rules(ok(verdict="SAFE", agent_summary={"verdict": "REVIEW"})) == [
            "verdict-mirror"
        ]

    def test_mirror_match_ok(self) -> None:
        assert rules(ok(verdict="INFO", agent_summary={"verdict": "INFO"})) == []

    def test_na_placeholder_is_unset(self) -> None:
        assert rules(ok(agent_summary={"verdict": "n/a"})) == []
        assert rules(fail(agent_summary={"verdict": "n/a"})) == []

    @pytest.mark.parametrize("verdict", ["SAFE", "INFO", "REVIEW", "WARN"])
    def test_failure_with_go_ahead_verdict(self, verdict: str) -> None:
        assert rules(fail(verdict=verdict)) == ["failure-verdict"]

    def test_failure_verdict_via_summary(self) -> None:
        assert rules(fail(agent_summary={"verdict": "SAFE"})) == ["failure-verdict"]

    @pytest.mark.parametrize("verdict", sorted(FAILURE_VERDICTS))
    def test_failure_verdicts_accepted(self, verdict: str) -> None:
        assert rules(fail(verdict=verdict)) == []

    def test_success_with_error_verdict(self) -> None:
        assert rules(ok(verdict="ERROR")) == ["success-verdict"]


class TestErrorCode:
    def test_failure_needs_machine_code(self) -> None:
        assert rules({"success": False, "error": "x"}) == ["error-code"]

    def test_error_type_suffices(self) -> None:
        assert rules({"success": False, "error": "x", "error_type": "T"}) == []

    def test_empty_code_does_not_count(self) -> None:
        assert rules({"success": False, "error": "x", "error_code": ""}) == [
            "error-code"
        ]

    def test_success_needs_no_code(self) -> None:
        assert rules(ok()) == []


class TestCompleteness:
    def test_statuses(self) -> None:
        assert COMPLETENESS_STATUSES == {"complete", "incomplete", "unknown"}

    def test_unknown_status(self) -> None:
        assert rules(ok(completeness="partial")) == ["completeness-status"]

    def test_complete_without_reasons_ok(self) -> None:
        assert rules(ok(completeness="complete", completeness_reasons=[])) == []

    def test_complete_with_reasons(self) -> None:
        assert rules(ok(completeness="complete", completeness_reasons=[REASON])) == [
            "completeness-reasons"
        ]

    @pytest.mark.parametrize("status", ["incomplete", "unknown"])
    def test_non_complete_needs_reason(self, status: str) -> None:
        assert rules(ok(completeness=status)) == ["completeness-reasons"]

    def test_primary_reason_alone_suffices(self) -> None:
        assert rules(ok(completeness="incomplete", completeness_reason=REASON)) == []

    def test_reasons_must_be_list(self) -> None:
        assert rules(ok(completeness="incomplete", completeness_reasons=REASON)) == [
            "completeness-reasons"
        ]

    def test_primary_must_lead_list(self) -> None:
        payload = ok(
            completeness="incomplete",
            completeness_reason="RELATION_LIMIT",
            completeness_reasons=[REASON, "RELATION_LIMIT"],
        )
        assert rules(payload) == ["completeness-reasons"]

    def test_unknown_reason_code(self) -> None:
        found = envelope_violations(
            ok(completeness="incomplete", completeness_reasons=["MADE_UP"])
        )
        assert [r for r, _ in found] == ["completeness-reason-code"]
        assert "MADE_UP" in found[0][1]

    def test_uql_stage_prefixed_reason_accepted(self) -> None:
        payload = ok(
            completeness="incomplete",
            completeness_reasons=[f"symbol:{REASON}"],
        )
        assert rules(payload) == []

    def test_stage_prefix_does_not_launder_unknown_code(self) -> None:
        payload = ok(completeness="incomplete", completeness_reasons=["symbol:MADE_UP"])
        assert rules(payload) == ["completeness-reason-code"]

    def test_known_reasons_include_callers_and_uql(self) -> None:
        known = known_completeness_reasons()
        assert REASON in known
        assert "SELECT_CAP_REACHED" in known


class TestTruncation:
    def test_flag_must_be_bool(self) -> None:
        assert rules(ok(truncated="no")) == ["truncation"]
        assert rules(ok(skipped_files_truncated=1)) == ["truncation"]

    @pytest.mark.parametrize(
        ("total", "listed"),
        [
            ("total_count", "returned_count"),
            ("total_matches", "returned_matches"),
            ("caller_count", "callers_listed"),
        ],
    )
    def test_short_listing_cannot_claim_untruncated(
        self, total: str, listed: str
    ) -> None:
        assert rules(ok(truncated=False, **{total: 5, listed: 3})) == ["truncation"]
        assert rules(ok(truncated=True, **{total: 5, listed: 3})) == []
        assert rules(ok(**{total: 5, listed: 3})) == []

    def test_listed_exceeds_total(self) -> None:
        assert rules(ok(total_count=2, returned_count=3)) == ["truncation"]

    def test_bool_counts_ignored(self) -> None:
        assert rules(ok(truncated=False, total_count=True, returned_count=0)) == []

    def test_equal_counts_ok(self) -> None:
        assert rules(ok(truncated=False, total_count=4, returned_count=4)) == []


def test_multiple_rules_reported_together() -> None:
    payload = {
        "success": False,
        "error": "x",
        "verdict": "SAFE",
        "completeness": "unknown",
        "truncated": "maybe",
    }
    assert rules(payload) == [
        "failure-verdict",
        "error-code",
        "completeness-reasons",
        "truncation",
    ]
