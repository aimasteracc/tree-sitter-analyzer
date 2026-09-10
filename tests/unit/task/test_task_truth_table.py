"""RFC-0022 static verification truth table contract (Phase A).

Exact pins for every row of the fixed truth table (RFC-0022 §Static
verification truth table): ordered first-match-wins semantics, truncation
overriding fresh success, malformed finding overriding freshness,
degrade(), canonical severity aggregation, zero-contribution WARN, and the
final fail-closed SAFE/NOT_FOUND -> WARN rule.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.task.truth_table import (
    FRESH,
    MISSING,
    NOT_APPLICABLE,
    STALE,
    UNKNOWN,
    aggregate_status,
    aggregate_status_and_verdict,
    aggregate_verdict,
    contribute,
    degrade,
)


def _c(**kwargs) -> dict:
    base = {
        "row": "r",
        "state": "succeeded",
        "kind": "generic",
        "finding": "none",
        "freshness": FRESH,
        "truncated": False,
    }
    base.update(kwargs)
    return base


# --- Row semantics --------------------------------------------------------


def test_row_not_required_is_ignored_without_verdict() -> None:
    c = contribute(**_c(state="not_required", freshness=NOT_APPLICABLE))
    assert (c.status_contribution, c.verdict_contribution) == ("ignored", None)


def test_row_not_called_is_unknown_without_verdict() -> None:
    c = contribute(**_c(state="not_called"))
    assert (c.status_contribution, c.verdict_contribution) == ("unknown", None)
    assert c.finding == UNKNOWN and c.freshness == UNKNOWN and c.truncated is None


def test_row_failed_is_unknown_without_verdict_and_truncated_false() -> None:
    c = contribute(**_c(state="failed"))
    assert (c.status_contribution, c.verdict_contribution) == ("unknown", None)
    assert c.finding == UNKNOWN and c.freshness == UNKNOWN and c.truncated is False


def test_row_malformed_overrides_freshness_and_truncation() -> None:
    # Row 4: succeeded + malformed beats any freshness/truncation combo.
    for kwargs in (
        {"finding": "malformed", "freshness": FRESH, "truncated": False},
        {"finding": "malformed", "freshness": STALE, "truncated": False},
        {"finding": "malformed", "freshness": FRESH, "truncated": True},
    ):
        c = contribute(**_c(**kwargs))
        assert (c.status_contribution, c.verdict_contribution) == ("unknown", None)
        assert c.finding == "malformed"


def test_row_fresh_none_contributes_primitive_non_risk_verdict() -> None:
    for verdict in ("SAFE", "INFO", "NOT_FOUND"):
        c = contribute(**_c(finding="none", primitive_verdict=verdict))
        assert (c.status_contribution, c.verdict_contribution) == ("complete", verdict)


def test_row_fresh_none_without_non_risk_verdict_canonicalizes_unknown() -> None:
    c = contribute(**_c(finding="none", primitive_verdict="WARN"))
    assert (c.status_contribution, c.verdict_contribution) == ("unknown", None)
    assert c.finding == "malformed"
    c2 = contribute(**_c(finding="none", primitive_verdict=None))
    assert (c2.status_contribution, c2.verdict_contribution) == ("unknown", None)


def test_row_fresh_risk_contributes_primitive_risk_verdict() -> None:
    for verdict in ("UNSAFE", "WARN", "REVIEW", "CAUTION"):
        c = contribute(**_c(finding="risk", primitive_verdict=verdict))
        assert (c.status_contribution, c.verdict_contribution) == ("complete", verdict)


def test_row_fresh_structural_invalid_contributes_review_or_unsafe() -> None:
    c = contribute(
        **_c(kind="structural", finding="invalid", primitive_verdict="REVIEW")
    )
    assert (c.status_contribution, c.verdict_contribution) == ("complete", "REVIEW")
    c2 = contribute(
        **_c(kind="structural", finding="invalid", primitive_verdict="UNSAFE")
    )
    assert (c2.status_contribution, c2.verdict_contribution) == ("complete", "UNSAFE")


def test_row_fresh_structural_invalid_missing_verdict_defaults_review() -> None:
    c = contribute(
        row="r",
        state="succeeded",
        kind="structural",
        finding="invalid",
        freshness=FRESH,
        truncated=False,
        primitive_verdict=None,
    )
    assert (c.status_contribution, c.verdict_contribution) == ("complete", "REVIEW")


def test_row_fresh_constraint_violation_preserves_primitive_severity() -> None:
    # error/critical -> UNSAFE (RFC row 8: validated primitive verdict).
    blocking = contribute(
        **_c(
            kind="constraints",
            finding="violation",
            violations=[{"severity": "error", "path": "a.py"}],
        )
    )
    assert (blocking.status_contribution, blocking.verdict_contribution) == (
        "complete",
        "UNSAFE",
    )
    warning = contribute(
        **_c(
            kind="constraints",
            finding="violation",
            violations=[{"severity": "warning", "path": "a.py"}],
        )
    )
    assert (warning.status_contribution, warning.verdict_contribution) == (
        "complete",
        "CAUTION",
    )
    informational = contribute(
        **_c(
            kind="constraints",
            finding="violation",
            violations=[{"severity": "info", "path": "a.py"}],
        )
    )
    assert (informational.status_contribution, informational.verdict_contribution) == (
        "complete",
        "SAFE",
    )


def test_row_no_config_is_complete_without_verdict() -> None:
    c = contribute(
        **_c(
            kind="constraints",
            finding="no_config",
            freshness=NOT_APPLICABLE,
            truncated=False,
        )
    )
    assert (c.status_contribution, c.verdict_contribution) == ("complete", None)


def test_row_stale_or_missing_or_unknown_freshness_degrades() -> None:
    for freshness in (STALE, MISSING, UNKNOWN):
        c = contribute(
            **_c(finding="none", freshness=freshness, primitive_verdict="SAFE")
        )
        assert (c.status_contribution, c.verdict_contribution) == ("partial", "WARN")


def test_row_truncated_degrades_even_when_fresh() -> None:
    c = contribute(
        **_c(finding="none", freshness=FRESH, truncated=True, primitive_verdict="INFO")
    )
    assert (c.status_contribution, c.verdict_contribution) == ("partial", "WARN")
    c2 = contribute(
        **_c(finding="risk", freshness=FRESH, truncated=None, primitive_verdict="WARN")
    )
    assert (c2.status_contribution, c2.verdict_contribution) == ("partial", "WARN")


def test_row_truncation_overrides_fresh_success() -> None:
    c = contribute(
        **_c(finding="none", freshness=FRESH, truncated=True, primitive_verdict="SAFE")
    )
    assert c.status_contribution == "partial"
    assert c.verdict_contribution == "WARN"


def test_unknown_state_canonicalizes_to_malformed() -> None:
    c = contribute(**_c(state="exploded"))  # type: ignore[arg-type]
    assert (c.status_contribution, c.verdict_contribution) == ("unknown", None)
    assert c.finding == "malformed" and c.freshness == UNKNOWN


def test_degrade_preserves_risk_and_maps_non_risk_to_warn() -> None:
    for verdict in ("UNSAFE", "WARN", "REVIEW", "CAUTION"):
        assert degrade(verdict) == verdict
    for verdict in ("SAFE", "INFO", "NOT_FOUND"):
        assert degrade(verdict) == "WARN"
    with pytest.raises(ValueError, match="non-primitive"):
        degrade("ERROR")


# --- Aggregation ----------------------------------------------------------


def test_aggregate_status_requires_all_complete() -> None:
    complete = contribute(**_c(finding="none", primitive_verdict="SAFE"))
    assert aggregate_status([complete]) == "complete"


def test_aggregate_status_partial_with_mixed_contributions() -> None:
    complete = contribute(**_c(row="a", finding="none", primitive_verdict="SAFE"))
    failed = contribute(**_c(row="b", state="failed"))
    assert aggregate_status([complete, failed]) == "partial"


def test_aggregate_status_unknown_when_all_unknown() -> None:
    failed = contribute(**_c(state="failed"))
    assert aggregate_status([failed, failed]) == "unknown"


def test_aggregate_status_ignores_not_required_rows() -> None:
    ignored = contribute(**_c(state="not_required", freshness=NOT_APPLICABLE))
    complete = contribute(**_c(row="a", finding="none", primitive_verdict="INFO"))
    assert aggregate_status([ignored, complete]) == "complete"


def test_aggregate_verdict_uses_canonical_severity_order() -> None:
    safe = contribute(**_c(row="a", finding="none", primitive_verdict="SAFE"))
    unsafe = contribute(
        **_c(
            row="b",
            kind="constraints",
            finding="violation",
            violations=[{"severity": "error", "path": "a.py"}],
        )
    )
    status, verdict = aggregate_status_and_verdict([safe, unsafe])
    assert verdict == "UNSAFE"
    assert status == "complete"


def test_zero_verdict_contributions_resolve_to_warn() -> None:
    failed = contribute(**_c(state="failed"))
    assert aggregate_verdict([failed], "unknown") == "WARN"


def test_partial_status_turns_safe_into_warn() -> None:
    partial = contribute(
        **_c(finding="none", freshness=STALE, primitive_verdict="SAFE")
    )
    status, verdict = aggregate_status_and_verdict([partial])
    assert (status, verdict) == ("partial", "WARN")


def test_partial_status_turns_not_found_into_warn() -> None:
    partial = contribute(
        **_c(finding="none", freshness=MISSING, primitive_verdict="NOT_FOUND")
    )
    status, verdict = aggregate_status_and_verdict([partial])
    assert (status, verdict) == ("partial", "WARN")


def test_incomplete_status_never_downgrades_existing_risk() -> None:
    risk = contribute(
        **_c(row="a", finding="risk", freshness=FRESH, primitive_verdict="WARN")
    )
    failed = contribute(**_c(row="b", state="failed"))
    status, verdict = aggregate_status_and_verdict([risk, failed])
    assert status == "partial"
    assert verdict == "WARN"


def test_no_config_with_stale_freshness_canonicalizes_unknown() -> None:
    c = contribute(
        **_c(kind="constraints", finding="no_config", freshness=STALE, truncated=False)
    )
    assert (c.status_contribution, c.verdict_contribution) == ("unknown", None)
    assert c.finding == "malformed"


def test_no_config_truncated_canonicalizes_unknown() -> None:
    c = contribute(
        **_c(
            kind="constraints",
            finding="no_config",
            freshness=NOT_APPLICABLE,
            truncated=True,
        )
    )
    assert (c.status_contribution, c.verdict_contribution) == ("unknown", None)


def test_finding_risk_with_non_risk_verdict_canonicalizes() -> None:
    c = contribute(**_c(finding="risk", primitive_verdict="SAFE"))
    assert (c.status_contribution, c.verdict_contribution) == ("unknown", None)


def test_degraded_row_without_primitive_verdict_has_no_verdict() -> None:
    c = contribute(**_c(finding="none", freshness=STALE, primitive_verdict=None))
    assert c.status_contribution == "partial"
    assert c.verdict_contribution is None


def test_row_twelve_fallthrough_canonicalizes() -> None:
    # A fresh, untruncated succeeded row whose finding/kind matches no row
    # (e.g. generic + violation) canonicalizes to malformed/unknown.
    c = contribute(**_c(finding="violation", freshness=FRESH, truncated=False))
    assert (c.status_contribution, c.verdict_contribution) == ("unknown", None)
    assert c.finding == "malformed"


def test_aggregate_status_empty_is_unknown() -> None:
    assert aggregate_status([]) == "unknown"
    assert aggregate_verdict([], "unknown") == "WARN"


def test_aggregate_verdict_severity_max_with_partial_status() -> None:
    # Risk verdicts are never downgraded by partial status.
    unsafe = contribute(
        **_c(
            row="a",
            kind="constraints",
            finding="violation",
            violations=[{"severity": "error", "path": "a.py"}],
        )
    )
    failed = contribute(**_c(row="b", state="failed"))
    status, verdict = aggregate_status_and_verdict([unsafe, failed])
    assert (status, verdict) == ("partial", "UNSAFE")
