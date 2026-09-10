"""RFC-0022 static verification truth table (Phase A).

Implements the fixed truth table from RFC-0022 §Static verification truth
table, verbatim. Each required invocation produces exactly one contribution;
``finding`` is the normalized primitive result, never task inference. The
table is ordered: the first matching row wins, so truncation overrides a
fresh success and malformed finding overrides freshness. Any input tuple
matching no row canonicalizes to ``(succeeded, malformed, unknown, unknown)``
before a second, final lookup.

Status aggregation and verdict aggregation follow the RFC exactly:
- ``complete`` requires all remaining contributions to be complete;
- ``partial`` requires at least one useful complete/partial contribution and
  at least one non-complete contribution; otherwise status is ``unknown``;
- verdicts use the canonical severity order
  ``UNSAFE > WARN > REVIEW > CAUTION > SAFE > INFO > NOT_FOUND``; zero verdict
  contributions resolve to ``WARN``; incompleteness never downgrades an
  existing risk verdict; as a final fail-closed rule, a ``partial|unknown``
  status turns candidate ``SAFE|NOT_FOUND`` into ``WARN``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import VERDICT_SEVERITY, Status, Verdict

InvocationState = Literal["not_required", "not_called", "failed", "succeeded"]
Finding = Literal[
    "none", "risk", "invalid", "violation", "no_config", "malformed", "unknown"
]
RowKind = Literal["generic", "structural", "constraints"]
StatusContribution = Literal["complete", "partial", "unknown", "ignored"]

#: Frozen freshness states (RFC-0022 §Freshness and snapshot truth).
FRESH: Literal["fresh"] = "fresh"
STALE: Literal["stale"] = "stale"
MISSING: Literal["missing"] = "missing"
NOT_APPLICABLE: Literal["not_applicable"] = "not_applicable"
UNKNOWN: Literal["unknown"] = "unknown"

#: Risk verdicts preserved by degrade(); non-risk verdicts map to WARN.
_RISK_VERDICTS = frozenset({"UNSAFE", "WARN", "REVIEW", "CAUTION"})
#: Non-risk primitive verdicts a fresh, untruncated success may contribute.
_NON_RISK_VERDICTS = frozenset({"SAFE", "INFO", "NOT_FOUND"})
#: Structural invalidity verdicts (RFC row 7: primitive REVIEW or UNSAFE).
_STRUCTURAL_INVALID_VERDICTS = frozenset({"REVIEW", "UNSAFE"})
#: Constraint severity -> validated primitive verdict (RFC row 8).
_BLOCKING_SEVERITIES = frozenset({"error", "critical"})
_WARNING_SEVERITIES = frozenset({"warn", "warning"})


@dataclass(frozen=True)
class Contribution:
    """One truth-table row result for a single required invocation.

    ``row`` identifies the route row (``facade.action`` plus condition tag);
    ``kind`` selects the row class (generic/structural/constraints);
    ``state`` is the invocation state; ``finding`` is the normalized
    primitive finding (``malformed`` when the wire fragment was unusable);
    ``truncated`` is ``True``, ``False``, or ``None`` (unknown); the
    ``status_contribution`` is one of complete/partial/unknown/ignored and
    ``verdict_contribution`` is the canonical verdict or ``None``.
    """

    row: str
    kind: RowKind
    state: InvocationState
    finding: Finding
    freshness: str
    truncated: bool | None
    status_contribution: StatusContribution
    verdict_contribution: Verdict | None
    locator: str | None = None
    evidence_id: str | None = None
    primitive_verdict: Verdict | None = None

    @property
    def ignored(self) -> bool:
        return self.status_contribution == "ignored"


def degrade(verdict: Verdict) -> Verdict:
    """RFC degrade(): preserve risk verdicts; map SAFE|INFO|NOT_FOUND to WARN."""
    if verdict in _RISK_VERDICTS:
        return verdict
    if verdict in _NON_RISK_VERDICTS:
        return "WARN"
    raise ValueError(f"degrade() got non-primitive verdict {verdict!r}")


def _constraint_verdict(violations: list[dict[str, object]]) -> Verdict:
    """RFC row 8: preserve the primitive's authoritative constraint verdict.

    error/critical -> UNSAFE, warning-only -> CAUTION, informational-only
    -> SAFE. The task never turns every violation into UNSAFE on its own.
    """
    has_blocking = any(
        str(item.get("severity", "")).lower() in _BLOCKING_SEVERITIES
        for item in violations
    )
    has_warning = any(
        str(item.get("severity", "")).lower() in _WARNING_SEVERITIES
        for item in violations
    )
    if has_blocking:
        return "UNSAFE"
    if has_warning:
        return "CAUTION"
    return "SAFE"


def contribute(
    *,
    row: str,
    state: InvocationState,
    kind: RowKind,
    finding: Finding,
    freshness: str,
    truncated: bool | None,
    primitive_verdict: Verdict | None = None,
    violations: list[dict[str, object]] | None = None,
) -> Contribution:
    """Evaluate one input tuple against the fixed truth table.

    The first matching row wins; any tuple matching no row canonicalizes to
    ``(succeeded, malformed, unknown, unknown)`` and is looked up a second
    time (RFC-0022 §Static verification truth table).
    """
    if state == "not_required":
        return Contribution(
            row, kind, state, finding, freshness, truncated, "ignored", None
        )
    if state == "not_called":
        return Contribution(row, kind, state, UNKNOWN, UNKNOWN, None, "unknown", None)
    if state == "failed":
        return Contribution(row, kind, state, UNKNOWN, UNKNOWN, False, "unknown", None)
    if finding == "malformed":
        # Row 4: malformed finding overrides freshness and truncation.
        return Contribution(
            row, kind, state, "malformed", UNKNOWN, None, "unknown", None
        )
    if kind == "constraints" and finding == "no_config":
        if freshness == NOT_APPLICABLE and truncated is False:
            # Row 9: NO_CONFIG is a completed constraints row, no verdict.
            return Contribution(
                row,
                kind,
                state,
                "no_config",
                NOT_APPLICABLE,
                False,
                "complete",
                None,
                primitive_verdict=primitive_verdict,
            )
        # NO_CONFIG with stale freshness or truncation matches no row.
        return _canonical_lookup(row, kind, primitive_verdict)
    if freshness == FRESH and truncated is False:
        if kind == "structural" and finding == "invalid":
            # Row 7: structural invalidity permits complete + REVIEW/UNSAFE.
            verdict = (
                primitive_verdict
                if primitive_verdict in _STRUCTURAL_INVALID_VERDICTS
                else "REVIEW"
            )
            return Contribution(
                row,
                kind,
                state,
                "invalid",
                FRESH,
                False,
                "complete",
                verdict,
                primitive_verdict=primitive_verdict,
            )
        if kind == "constraints" and finding == "violation":
            # Row 8: validated primitive verdict, never task-inferred UNSAFE.
            return Contribution(
                row,
                kind,
                state,
                "violation",
                FRESH,
                False,
                "complete",
                _constraint_verdict(violations or []),
                primitive_verdict=primitive_verdict,
            )
        if finding == "none":
            if primitive_verdict in _NON_RISK_VERDICTS:
                # Row 5: complete + primitive non-risk verdict.
                return Contribution(
                    row,
                    kind,
                    state,
                    "none",
                    FRESH,
                    False,
                    "complete",
                    primitive_verdict,
                    primitive_verdict=primitive_verdict,
                )
            return _canonical_lookup(row, kind, primitive_verdict)
        if finding == "risk":
            if primitive_verdict in _RISK_VERDICTS:
                # Row 6: complete + primitive risk verdict.
                return Contribution(
                    row,
                    kind,
                    state,
                    "risk",
                    FRESH,
                    False,
                    "complete",
                    primitive_verdict,
                    primitive_verdict=primitive_verdict,
                )
            return _canonical_lookup(row, kind, primitive_verdict)
    # Rows 10-11: stale/missing/unknown freshness or any truncation degrade.
    if truncated is True or truncated is None or freshness != FRESH:
        degraded = degrade(primitive_verdict) if primitive_verdict is not None else None
        return Contribution(
            row,
            kind,
            state,
            finding,
            freshness,
            truncated,
            "partial",
            degraded,
            primitive_verdict=primitive_verdict,
        )
    # Row 12: no row matched — canonicalize and re-lookup.
    return _canonical_lookup(row, kind, primitive_verdict)


def _canonical_lookup(
    row: str, kind: RowKind, primitive_verdict: Verdict | None
) -> Contribution:
    """Row 12: canonicalize to (succeeded, malformed, unknown, unknown)."""
    return Contribution(
        row,
        kind,
        "succeeded",
        "malformed",
        UNKNOWN,
        None,
        "unknown",
        None,
        primitive_verdict=primitive_verdict,
    )


def aggregate_status(contributions: list[Contribution]) -> Status:
    """RFC aggregate status over non-ignored contributions."""
    remaining = [c for c in contributions if not c.ignored]
    if not remaining:
        return "unknown"
    if all(c.status_contribution == "complete" for c in remaining):
        return "complete"
    if any(c.status_contribution in {"complete", "partial"} for c in remaining):
        return "partial"
    return "unknown"


def aggregate_verdict(contributions: list[Contribution], status: Status) -> Verdict:
    """RFC aggregate verdict with the fail-closed final rule."""
    verdicts = [
        c.verdict_contribution
        for c in contributions
        if c.verdict_contribution is not None
    ]
    if not verdicts:
        return "WARN"
    candidate = max(verdicts, key=lambda v: VERDICT_SEVERITY[v])
    if status in {"partial", "unknown"} and candidate in {"SAFE", "NOT_FOUND"}:
        return "WARN"
    return candidate


def aggregate_status_and_verdict(
    contributions: list[Contribution],
) -> tuple[Status, Verdict]:
    """Freeze (status, verdict) from all contributions (RFC-0022)."""
    status = aggregate_status(contributions)
    return status, aggregate_verdict(contributions, status)
