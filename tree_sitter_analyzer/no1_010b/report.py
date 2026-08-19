"""NO1-010B B2 report builder (RFC-0026 §3/§4, B2 exit artifact).

Emits the exact B2 report shape — VCSR with per-class, per-repo AND per-arm
breakdown (arms are never pooled, C31); the reliability metric
``successful_indexed_trials / all_trials`` with exact numerator, denominator and
infrastructure-vs-product failure classes (C38); the 99% reliability gate status
(C39); and the paired evidence-effect endpoint (C56).

The builder is pure: it reports what the run actually produced and never
synthesises a value. When preflight rejects the corpus run, zero attempts are
retained, so VCSR is ``NOT_PRODUCED`` — a null, not a zero-percent measurement.
"""

from __future__ import annotations

from typing import Any

from .preflight import PreflightResult
from .record import BenchmarkRecord

#: ROADMAP §3 reliability gate; B2 cannot complete below it (C39).
RELIABILITY_THRESHOLD = 0.99

#: Frozen paired-endpoint parameters (RFC-0026 §2, C56).
PAIRED_MINIMUM_EFFECT = 0.05
PAIRED_ALPHA = 0.05

_REPORT_SCHEMA = "no1-010b/report/1"


def _counter(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _corpus_summary(records: list[BenchmarkRecord]) -> dict[str, Any]:
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


def _vcsr_block() -> dict[str, Any]:
    """VCSR for a run that retained zero attempts.

    ``0/0`` is not ``0%``: no attempt reached a verdict, so the endpoint has no
    value. Reporting ``0.0`` here would be a fabricated measurement.
    """
    return {
        "state": "NOT_PRODUCED",
        "value": None,
        "numerator": 0,
        "denominator": 0,
        "per_class": {},
        "per_repo": {},
        "per_arm": {},
    }


def _reliability_block() -> dict[str, Any]:
    return {
        "metric": "successful_indexed_trials / all_trials",
        "successful_indexed_trials": 0,
        "all_trials": 0,
        "ratio": None,
        "threshold": RELIABILITY_THRESHOLD,
        "gate_status": "NOT_EVALUATED",
        "failure_classes": {"product": 0, "infrastructure": 0},
        "failure_class_breakdown": {"product": {}, "infrastructure": {}},
        "per_arm": {},
    }


def _paired_endpoint_block() -> dict[str, Any]:
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


def build_report(
    *,
    records: list[BenchmarkRecord],
    preflight: PreflightResult,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Build the B2 report for a model-free, preflight-rejected corpus run."""
    blocking = [gate.gate for gate in preflight.gates]
    failed_checks = [
        check.check for check in preflight.checks if check.status != "PASS"
    ]
    run_status = (
        "REJECTED_AT_PREFLIGHT" if preflight.status != "ACCEPTED" else "COMPLETED"
    )
    return {
        "schema": _REPORT_SCHEMA,
        "rfc": "RFC-0026",
        "phase": "B2",
        "run_status": run_status,
        "arm_mode": "model_free",
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
            "attempts_consumed": 0,
            "static_checks": [
                {"check": item.check, "status": item.status, "detail": item.detail}
                for item in preflight.checks
            ],
            "failed_checks": failed_checks,
            "unsatisfied_gates": [
                {
                    "gate": item.gate,
                    "constraint": item.constraint,
                    "status": item.status,
                    "detail": item.detail,
                }
                for item in preflight.gates
            ],
        },
        "arms": [],
        "attempts_retained": 0,
        "vcsr": _vcsr_block(),
        "reliability": _reliability_block(),
        "paired_evidence_endpoint": _paired_endpoint_block(),
        "b2_complete": False,
        "b2_block_reasons": failed_checks + blocking,
    }
