"""Contracts for the NO1-010B B2 report builder (RFC-0026 §3/§4, C31/C38/C39).

The report is the B2 exit artifact, so its honesty properties are pinned here:
zero retained attempts must render VCSR as ``NOT_PRODUCED`` with a ``null``
value (never a fabricated ``0.0``), arms are never pooled, and the reliability
gate is reported as not evaluated rather than as met.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.no1_010b.preflight import run_preflight
from tree_sitter_analyzer.no1_010b.record_loader import load_corpus_records
from tree_sitter_analyzer.no1_010b.report import (
    PAIRED_ALPHA,
    PAIRED_MINIMUM_EFFECT,
    RELIABILITY_THRESHOLD,
    build_report,
)

CORPUS_ROOT = Path(__file__).resolve().parents[3] / "benchmarks" / "no1_010b"


def _report() -> dict:
    records = load_corpus_records(str(CORPUS_ROOT / "corpus.jsonl"))
    return build_report(
        records=records,
        preflight=run_preflight(records, CORPUS_ROOT),
        provenance={"analyzer_commit": "deadbeef"},
    )


def test_reliability_threshold_is_the_roadmap_gate() -> None:
    assert RELIABILITY_THRESHOLD == 0.99


def test_paired_endpoint_parameters_are_the_frozen_values() -> None:
    assert (PAIRED_MINIMUM_EFFECT, PAIRED_ALPHA) == (0.05, 0.05)


def test_preflight_rejection_is_reported_as_the_run_status() -> None:
    assert _report()["run_status"] == "REJECTED_AT_PREFLIGHT"


def test_zero_retained_attempts_render_vcsr_as_not_produced() -> None:
    assert _report()["vcsr"]["state"] == "NOT_PRODUCED"


def test_unproduced_vcsr_value_is_null_not_zero() -> None:
    """A 0/0 endpoint has no value; emitting 0.0 would fabricate a measurement."""
    assert _report()["vcsr"]["value"] is None


def test_vcsr_denominator_is_zero_when_no_attempt_was_retained() -> None:
    assert _report()["vcsr"]["denominator"] == 0


def test_report_carries_per_arm_vcsr_breakdown_and_never_pools_arms() -> None:
    assert _report()["vcsr"]["per_arm"] == {}


def test_reliability_gate_is_not_evaluated_without_attempts() -> None:
    assert _report()["reliability"]["gate_status"] == "NOT_EVALUATED"


def test_reliability_numerator_and_denominator_are_both_zero() -> None:
    reliability = _report()["reliability"]
    assert (
        reliability["successful_indexed_trials"],
        reliability["all_trials"],
    ) == (0, 0)


def test_reliability_failure_classes_split_product_from_infrastructure() -> None:
    assert _report()["reliability"]["failure_classes"] == {
        "product": 0,
        "infrastructure": 0,
    }


def test_paired_evidence_endpoint_is_not_admitted() -> None:
    assert _report()["paired_evidence_endpoint"]["admission"] == "NOT_ADMITTED"


def test_b2_is_not_complete_while_the_reliability_gate_is_unmet() -> None:
    assert _report()["b2_complete"] is False


def test_b2_block_reasons_list_every_unsatisfied_gate() -> None:
    report = _report()
    gate_names = [gate["gate"] for gate in report["preflight"]["unsatisfied_gates"]]
    assert report["b2_block_reasons"] == gate_names


def test_report_emits_no_public_claim_at_e0() -> None:
    report = _report()
    assert (report["evidence_level"], report["public_claim"]) == ("E0", None)


def test_report_records_the_run_as_model_free() -> None:
    assert _report()["arm_mode"] == "model_free"


def test_report_lists_no_arms() -> None:
    assert _report()["arms"] == []


def test_report_echoes_the_supplied_provenance() -> None:
    assert _report()["provenance"] == {"analyzer_commit": "deadbeef"}


def test_report_corpus_block_pins_the_registered_task_count() -> None:
    assert _report()["corpus"]["task_count"] == 10


def test_report_corpus_block_pins_the_expected_terminal_distribution() -> None:
    assert _report()["corpus"]["expected_terminals"] == {
        "PASS/null": 9,
        "FAIL/VERIFICATION_FAILED": 1,
    }
