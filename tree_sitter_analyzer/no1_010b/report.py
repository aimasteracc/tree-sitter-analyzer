"""NO1-010B B2 report builder (RFC-0026 §3/§4, B2 exit artifact).

Emits the exact B2 report shape — VCSR with per-class, per-repo AND per-arm
breakdown (arms are never pooled, C31); the reliability metric
``successful_indexed_trials / all_trials`` with exact numerator, denominator and
infrastructure-vs-product failure classes (C38); the 99% reliability gate status
(C39); and the paired evidence-effect endpoint (C56).

Every block is **computed from the attempt records it describes**. An earlier
draft returned fixed literals from zero-argument helpers, which meant its own
tests asserted ``None is None`` and would have stayed green while a run with 8
of 10 tasks passing reported ``NOT_PRODUCED`` — the 2026-06-08 TOON shape, a
test protecting a bug. The invariant that replaces it: a run with retained
attempts can never render as ``NOT_PRODUCED``.

Zero retained attempts still render VCSR as ``NOT_PRODUCED`` with a ``null``
value rather than ``0.0``: no attempt reached a verdict, so the endpoint has no
value and a zero would be a fabricated measurement.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import comb
from typing import Any

from .preflight import CATEGORY_MEANING, PreflightResult
from .record import BenchmarkRecord

#: ROADMAP §3 reliability gate; B2 cannot complete below it (C39).
RELIABILITY_THRESHOLD = 0.99

#: Frozen paired-endpoint parameters (RFC-0026 §2, C56).
PAIRED_MINIMUM_EFFECT = 0.05
PAIRED_ALPHA = 0.05

_REPORT_SCHEMA = "no1-010b/report/2"

#: RFC-0026 §3 terminal-state -> failure-class mapping. A FAIL with any named
#: product reason code is a product failure; UNKNOWN splits by subcode.
PRODUCT_UNKNOWN_REASONS = frozenset(
    {
        "PATCH_NOT_APPLICABLE",
        "PATCH_OVER_BOUND",
        "PROVENANCE_MISSING",
        "AGENT_OUTPUT_ERROR",
    }
)
INFRASTRUCTURE_UNKNOWN_REASONS = frozenset(
    {
        "ORACLE_LOAD_ERROR",
        "ORACLE_EXECUTION_ERROR",
        "ORACLE_PROTOCOL_ERROR",
        "ORACLE_TIMEOUT",
        "VERIFICATION_EXECUTION_ERROR",
        "VERIFICATION_TIMEOUT",
        "INDEX_REFRESH_ERROR",
        "INDEX_QUERY_ERROR",
        "EVIDENCE_CHECK_ERROR",
        "SANDBOX_FAILURE",
        "REGISTRY_FAILURE",
    }
)


@dataclass(frozen=True)
class Attempt:
    """One retained execution attempt (RFC-0026 §4: all attempts are retained)."""

    task_id: str
    task_class: str
    repo: str
    arm_id: str
    verdict: str  # PASS | FAIL | UNKNOWN
    reason_code: str | None = None

    @property
    def reached_verdict(self) -> bool:
        """Whether the attempt produced a product outcome (§3 numerator rule)."""
        return self.verdict in {"PASS", "FAIL"}

    @property
    def failure_class(self) -> str | None:
        if self.verdict == "PASS":
            return None
        if self.verdict == "FAIL":
            return "product"
        if self.reason_code in PRODUCT_UNKNOWN_REASONS:
            return "product"
        if self.reason_code in INFRASTRUCTURE_UNKNOWN_REASONS:
            return "infrastructure"
        return "infrastructure"


@dataclass(frozen=True)
class PairedCell:
    """One registered treatment/control cell of the paired endpoint (C56)."""

    pair_id: str
    task_id: str
    repeat_index: int
    treatment_pass: bool
    control_pass: bool


def _counter(values: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _grouped_vcsr(attempts: Sequence[Attempt], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Attempt]] = {}
    for attempt in attempts:
        groups.setdefault(getattr(attempt, key), []).append(attempt)
    return {
        name: {
            "numerator": sum(1 for item in group if item.verdict == "PASS"),
            "denominator": len(group),
            "value": _rate(
                sum(1 for item in group if item.verdict == "PASS"), len(group)
            ),
        }
        for name, group in sorted(groups.items())
    }


def _corpus_summary(records: Sequence[BenchmarkRecord]) -> dict[str, Any]:
    return {
        "task_count": len(records),
        "per_class_counts": _counter([item.task_class for item in records]),
        "per_repo_counts": _counter([item.repo for item in records]),
        "expected_terminals": _counter(
            [
                f"{item.expected_terminal.verdict}/"
                f"{item.expected_terminal.reason_code or 'null'}"
                for item in records
            ]
        ),
        "task_ids": [item.id for item in records],
    }


def vcsr_block(attempts: Sequence[Attempt]) -> dict[str, Any]:
    """Compute VCSR over the retained attempts.

    Denominator is every retained attempt: ``unknown`` is a first-class outcome
    and never a pass (RFC-0026 Summary), so dropping UNKNOWN attempts would
    flatter the numerator.
    """
    denominator = len(attempts)
    numerator = sum(1 for attempt in attempts if attempt.verdict == "PASS")
    return {
        "state": "PRODUCED" if denominator else "NOT_PRODUCED",
        "value": _rate(numerator, denominator),
        "numerator": numerator,
        "denominator": denominator,
        "per_class": _grouped_vcsr(attempts, "task_class"),
        "per_repo": _grouped_vcsr(attempts, "repo"),
        "per_arm": _grouped_vcsr(attempts, "arm_id"),
    }


def _gate_status(numerator: int, denominator: int) -> str:
    if not denominator:
        return "NOT_EVALUATED"
    return "MET" if numerator / denominator >= RELIABILITY_THRESHOLD else "NOT_MET"


def reliability_block(attempts: Sequence[Attempt]) -> dict[str, Any]:
    """Compute ``successful_indexed_trials / all_trials`` per §3's fixed mapping."""
    denominator = len(attempts)
    numerator = sum(1 for attempt in attempts if attempt.reached_verdict)
    classes = {"product": 0, "infrastructure": 0}
    breakdown: dict[str, dict[str, int]] = {"product": {}, "infrastructure": {}}
    for attempt in attempts:
        failure_class = attempt.failure_class
        if failure_class is None:
            continue
        classes[failure_class] += 1
        key = attempt.reason_code or attempt.verdict
        breakdown[failure_class][key] = breakdown[failure_class].get(key, 0) + 1

    per_arm: dict[str, dict[str, Any]] = {}
    arms: dict[str, list[Attempt]] = {}
    for attempt in attempts:
        arms.setdefault(attempt.arm_id, []).append(attempt)
    for arm_id, group in sorted(arms.items()):
        arm_numerator = sum(1 for item in group if item.reached_verdict)
        per_arm[arm_id] = {
            "successful_indexed_trials": arm_numerator,
            "all_trials": len(group),
            "ratio": _rate(arm_numerator, len(group)),
            "gate_status": _gate_status(arm_numerator, len(group)),
        }

    return {
        "metric": "successful_indexed_trials / all_trials",
        "successful_indexed_trials": numerator,
        "all_trials": denominator,
        "ratio": _rate(numerator, denominator),
        "threshold": RELIABILITY_THRESHOLD,
        "gate_status": _gate_status(numerator, denominator),
        "failure_classes": classes,
        "failure_class_breakdown": breakdown,
        "per_arm": per_arm,
    }


def _exact_one_sided_p(n10: int, n01: int) -> float:
    """RFC-0026 §2: ``sum(comb(D, k) * 0.5**D for k in n10..D)``, 1.0 when D=0."""
    discordant = n10 + n01
    if discordant == 0:
        return 1.0
    return sum(
        comb(discordant, k) * 0.5**discordant for k in range(n10, discordant + 1)
    )


def paired_endpoint_block(
    cells: Sequence[PairedCell],
    *,
    reliability_gate: str,
    unknown_attempts: int,
    matrix_complete: bool,
) -> dict[str, Any]:
    """Compute the paired evidence-effect endpoint exactly as §2 freezes it."""
    if not cells:
        return {
            "state": "NOT_EVALUATED",
            "matrix_complete": False,
            "n11": 0,
            "n10": 0,
            "n01": 0,
            "n00": 0,
            "paired_effect": None,
            "p_value": None,
            "minimum_effect": PAIRED_MINIMUM_EFFECT,
            "alpha": PAIRED_ALPHA,
            "admission": "NOT_ADMITTED",
        }
    n11 = sum(1 for c in cells if c.treatment_pass and c.control_pass)
    n10 = sum(1 for c in cells if c.treatment_pass and not c.control_pass)
    n01 = sum(1 for c in cells if not c.treatment_pass and c.control_pass)
    n00 = sum(1 for c in cells if not c.treatment_pass and not c.control_pass)
    total = len(cells)
    effect = (n10 - n01) / total
    p_value = _exact_one_sided_p(n10, n01)
    admitted = (
        matrix_complete
        and unknown_attempts == 0
        and reliability_gate == "MET"
        and effect >= PAIRED_MINIMUM_EFFECT
        and p_value <= PAIRED_ALPHA
        and n10 > n01
    )
    return {
        "state": "EVALUATED",
        "matrix_complete": matrix_complete,
        "n11": n11,
        "n10": n10,
        "n01": n01,
        "n00": n00,
        "paired_effect": effect,
        "p_value": p_value,
        "minimum_effect": PAIRED_MINIMUM_EFFECT,
        "alpha": PAIRED_ALPHA,
        "admission": "ADMITTED" if admitted else "NOT_ADMITTED",
    }


def build_report(
    *,
    records: Sequence[BenchmarkRecord],
    preflight: PreflightResult,
    provenance: dict[str, Any],
    attempts: Sequence[Attempt] = (),
    paired_cells: Sequence[PairedCell] = (),
    matrix_complete: bool = False,
) -> dict[str, Any]:
    """Build the B2 report from the run's actual preflight result and attempts."""
    failed_checks = [
        check.check for check in preflight.checks if check.status != "PASS"
    ]
    blocking = [gate.gate for gate in preflight.gates]
    run_status = (
        "REJECTED_AT_PREFLIGHT" if preflight.status != "ACCEPTED" else "COMPLETED"
    )
    vcsr = vcsr_block(attempts)
    reliability = reliability_block(attempts)
    unknown_attempts = sum(1 for attempt in attempts if attempt.verdict == "UNKNOWN")
    paired = paired_endpoint_block(
        paired_cells,
        reliability_gate=str(reliability["gate_status"]),
        unknown_attempts=unknown_attempts,
        matrix_complete=matrix_complete,
    )
    arm_ids = sorted({attempt.arm_id for attempt in attempts})
    b2_complete = (
        run_status == "COMPLETED"
        and not failed_checks
        and not blocking
        and vcsr["state"] == "PRODUCED"
        and reliability["gate_status"] == "MET"
        and unknown_attempts == 0
    )
    return {
        "schema": _REPORT_SCHEMA,
        "rfc": "RFC-0026",
        "phase": "B2",
        "run_status": run_status,
        "arm_mode": "agent_arms" if arm_ids else "model_free",
        "evidence_level": "E0",
        "public_claim": None,
        "public_claim_policy": (
            "E0-E3 emit no public or competitive wording (RFC-0026 §4). This "
            "report is internal evidence only and is not admitted to the claim "
            "registry."
        ),
        "provenance": provenance,
        "corpus": _corpus_summary(records),
        "preflight": {
            "status": preflight.status,
            "attempts_consumed": len(attempts),
            "static_checks": [
                {"check": item.check, "status": item.status, "detail": item.detail}
                for item in preflight.checks
            ],
            "failed_checks": failed_checks,
            "gate_categories": CATEGORY_MEANING,
            "unsatisfied_gates": [
                {
                    "gate": item.gate,
                    "constraint": item.constraint,
                    "category": item.category,
                    "status": item.status,
                    "detail": item.detail,
                }
                for item in preflight.gates
            ],
        },
        "arms": arm_ids,
        "attempts_retained": len(attempts),
        "vcsr": vcsr,
        "reliability": reliability,
        "paired_evidence_endpoint": paired,
        "b2_complete": b2_complete,
        "b2_block_reasons": failed_checks + blocking,
    }
