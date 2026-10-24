"""Per-stage completeness for the unified query language (RFC-0041 §3).

Completeness is *derived from what was examined*, never from the absence of a
failure flag:

* a stage starts ``unknown`` and becomes ``complete`` only when every input it
  examined produced positive coverage (for relations: the producer's own
  ``completeness == "complete"`` — ``nav action=callers`` is consumed as-is);
* a producer that reports no coverage at all is ``unknown``
  (:data:`PRODUCER_COVERAGE_MISSING`), not complete;
* a stage's *effective* coverage folds in every stage before it, so the query
  total is ``complete`` only when every stage is.

Status order: ``complete`` < ``incomplete`` (a known lower bound) <
``unknown`` (not even a bound). Combining takes the worst status and the
ordered union of reasons.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

COMPLETE = "complete"
INCOMPLETE = "incomplete"
UNKNOWN = "unknown"
STATUSES = (COMPLETE, INCOMPLETE, UNKNOWN)
_RANK = {COMPLETE: 0, INCOMPLETE: 1, UNKNOWN: 2}

# -- UQL-owned reason codes (closed set; callers' own codes pass through) -----
#: The producer returned no completeness field.
PRODUCER_COVERAGE_MISSING = "PRODUCER_COVERAGE_MISSING"
#: The producer call failed; partial rows (if any) are kept.
RELATION_ERROR = "RELATION_ERROR"
#: The producer listed fewer rows than it counted.
RELATION_LIMIT = "RELATION_LIMIT"
#: Traversal stopped at the per-query node budget.
RELATION_NODE_BUDGET = "RELATION_NODE_BUDGET"
#: ``impact()`` stopped at its depth cap with an unexpanded frontier.
RELATION_DEPTH_LIMIT = "RELATION_DEPTH_LIMIT"
#: ``callees()`` has no producer coverage claim.
CALLEES_COVERAGE_UNREPORTED = "CALLEES_COVERAGE_UNREPORTED"
#: Some callees did not resolve to a project definition.
CALLEE_UNRESOLVED = "CALLEE_UNRESOLVED"
#: A test-file helper is itself called by another helper (> 1 hop).
TEST_HELPER_DEPTH = "TEST_HELPER_DEPTH"
#: ``tested()`` / ``untested()`` could not decide some rows.
MEMBERSHIP_UNKNOWN = "MEMBERSHIP_UNKNOWN"
#: The selector uses edge / history / rule predicates without coverage proof.
SELECTOR_PREDICATE_UNPROVEN = "SELECTOR_PREDICATE_UNPROVEN"
#: The selector matched more symbols than the evaluator cap.
SELECT_CAP_REACHED = "SELECT_CAP_REACHED"
#: A stage before this one was not complete.
UPSTREAM_INCOMPLETE = "UPSTREAM_INCOMPLETE"
UPSTREAM_UNKNOWN = "UPSTREAM_UNKNOWN"
#: Paging across calls could not be pinned to one source generation.
CURSOR_GENERATION_UNVERIFIED = "CURSOR_GENERATION_UNVERIFIED"

UQL_REASONS = frozenset(
    {
        PRODUCER_COVERAGE_MISSING,
        RELATION_ERROR,
        RELATION_LIMIT,
        RELATION_NODE_BUDGET,
        RELATION_DEPTH_LIMIT,
        CALLEES_COVERAGE_UNREPORTED,
        CALLEE_UNRESOLVED,
        TEST_HELPER_DEPTH,
        MEMBERSHIP_UNKNOWN,
        SELECTOR_PREDICATE_UNPROVEN,
        SELECT_CAP_REACHED,
        UPSTREAM_INCOMPLETE,
        UPSTREAM_UNKNOWN,
        CURSOR_GENERATION_UNVERIFIED,
    }
)


@dataclass(frozen=True)
class Coverage:
    """A completeness status with the reasons that justify anything less."""

    status: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in _RANK:
            raise ValueError(f"invalid completeness status: {self.status!r}")
        if self.status == COMPLETE and self.reasons:
            raise ValueError("complete coverage cannot carry reasons")
        if self.status != COMPLETE and not self.reasons:
            raise ValueError("non-complete coverage must name a reason")

    @property
    def complete(self) -> bool:
        return self.status == COMPLETE


COMPLETE_COVERAGE = Coverage(COMPLETE)


def gap(status: str, *reasons: str) -> Coverage:
    return Coverage(status, tuple(dict.fromkeys(reasons)))


def combine(coverages: Iterable[Coverage]) -> Coverage:
    """Worst status, ordered union of reasons. No inputs examined = unknown."""
    items = list(coverages)
    if not items:
        return gap(UNKNOWN, PRODUCER_COVERAGE_MISSING)
    worst = max(items, key=lambda c: _RANK[c.status]).status
    if worst == COMPLETE:
        return COMPLETE_COVERAGE
    reasons: dict[str, None] = {}
    for item in items:
        for reason in item.reasons:
            reasons[reason] = None
    return Coverage(worst, tuple(reasons))


def combine_or_complete(coverages: Iterable[Coverage]) -> Coverage:
    """Like :func:`combine`, but an empty input set is vacuously complete.

    Only for stages whose input set was itself established (e.g. a relation
    over zero upstream rows examines nothing and claims nothing extra).
    """
    items = list(coverages)
    return combine(items) if items else COMPLETE_COVERAGE


def with_upstream(own: Coverage, upstream: Coverage) -> Coverage:
    """A stage's effective coverage: its own gaps plus an upstream marker."""
    if upstream.complete:
        return own
    marker = UPSTREAM_UNKNOWN if upstream.status == UNKNOWN else UPSTREAM_INCOMPLETE
    status = max((own.status, upstream.status), key=lambda s: _RANK[s])
    return gap(status, *own.reasons, marker)


def from_producer(response: Mapping[str, Any] | Any) -> Coverage:
    """Consume a ``nav action=callers`` payload's coverage contract as-is."""
    if not isinstance(response, Mapping) or response.get("success") is False:
        return gap(UNKNOWN, RELATION_ERROR)
    status = response.get("completeness")
    if status not in _RANK:
        return gap(UNKNOWN, PRODUCER_COVERAGE_MISSING)
    reasons = tuple(str(r) for r in response.get("completeness_reasons") or ())
    if status == COMPLETE:
        listed = response.get("callers_listed")
        counted = response.get("caller_count")
        if isinstance(listed, int) and isinstance(counted, int) and counted > listed:
            return gap(INCOMPLETE, RELATION_LIMIT)
        return COMPLETE_COVERAGE
    if not reasons:
        reasons = (PRODUCER_COVERAGE_MISSING,)
    return Coverage(str(status), reasons)
