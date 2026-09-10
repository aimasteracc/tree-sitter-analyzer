#!/usr/bin/env python3
"""Types for the mutation probe subsystem (RFC-0029).

ConstrainsResult carries the verdict and timing for a single probe call.
FailureKind classifies what happened during a pytest run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# FailureKind: what happened when pytest ran a single test.
# NONE          — test passed (no failure)
# ASSERTION     — test failed with an assertion-derived error
#                 (AssertionError, pytest.fail, raises() mismatch)
# NON_ASSERTION — test failed with a non-assertion exception
#                 (ImportError, AttributeError, NameError, …)
# NOT_RUN       — test was not collected / deselected / timed out
FailureKind = Literal["NONE", "ASSERTION", "NON_ASSERTION", "NOT_RUN"]

Verdict = Literal["constrains", "does_not_constrain", "unknown"]


@dataclass(frozen=True)
class ConstrainsResult:
    """Whether a test detects a single applied mutation.

    ``constrains`` is emitted only when the baseline passed AND the mutated
    run failed with an assertion-derived failure.  Every other case is
    ``does_not_constrain`` or ``unknown`` — never optimistically
    ``constrains``.

    Fields
    ------
    verdict:
        "constrains" | "does_not_constrain" | "unknown"
    reason:
        Closed subcode for non-constrains verdicts; None only when constrains.
        Subcodes: BASELINE_NOT_GREEN | NO_INVERTIBLE_BRANCH | NOT_ISOLABLE |
                  MUTATED_RUN_CRASHED | TIMEOUT | INVALID_LOCATION |
                  FILE_NOT_FOUND | MUTATED_RUN_PASSED
    mutation:
        Human-readable description of the applied mutation.
    baseline_failure, mutated_failure:
        FailureKind for each run.
    baseline_ms, mutated_ms:
        Wall time for each subprocess run.
    overhead_ms:
        Total wall time minus the two run durations (harness startup cost).
    """

    verdict: Verdict
    reason: str | None
    mutation: str
    baseline_failure: FailureKind
    mutated_failure: FailureKind
    baseline_ms: float
    mutated_ms: float
    overhead_ms: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe dict representation."""
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "mutation": self.mutation,
            "baseline_failure": self.baseline_failure,
            "mutated_failure": self.mutated_failure,
            "baseline_ms": round(self.baseline_ms, 1),
            "mutated_ms": round(self.mutated_ms, 1),
            "overhead_ms": round(self.overhead_ms, 1),
        }
