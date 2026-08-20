"""Contracts for the NO1-010B B2 report builder (RFC-0026 §3/§4, C31/C38/C39).

The report is the B2 exit artifact, so its honesty properties are pinned here.
Critically, the blocks are computed from attempt records: the tests below feed
real attempts in and assert the derived numbers, so a builder that hardcoded
``NOT_PRODUCED`` would fail rather than stay green.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.no1_010b.preflight import (
    OracleSignature,
    PreflightResult,
    run_preflight,
)
from tree_sitter_analyzer.no1_010b.record_loader import load_corpus_records
from tree_sitter_analyzer.no1_010b.report import (
    PAIRED_ALPHA,
    PAIRED_MINIMUM_EFFECT,
    RELIABILITY_THRESHOLD,
    Attempt,
    PairedCell,
    build_report,
    paired_endpoint_block,
    reliability_block,
    vcsr_block,
)

CORPUS_ROOT = Path(__file__).resolve().parents[3] / "benchmarks" / "no1_010b"
CORPUS_PATH = CORPUS_ROOT / "corpus.jsonl"


def _records() -> list:
    return load_corpus_records(str(CORPUS_PATH))


@pytest.fixture(scope="module")
def committed_preflight() -> PreflightResult:
    """One real preflight over the committed corpus, shared by the module.

    Preflight executes ten oracles as subprocesses; running it in module setup
    keeps that real cost out of the unit-suite per-test call budget.
    """
    records = _records()
    return run_preflight(records, CORPUS_ROOT, corpus_path=CORPUS_PATH)


@pytest.fixture(scope="module")
def report(committed_preflight: PreflightResult) -> dict:
    return build_report(
        records=_records(),
        preflight=committed_preflight,
        provenance={"analyzer": {"commit": "deadbeef"}},
    )


def _report_with(committed_preflight: PreflightResult, **kwargs: Any) -> dict:
    return build_report(
        records=_records(),
        preflight=committed_preflight,
        provenance={"analyzer": {"commit": "deadbeef"}},
        **kwargs,
    )


def _pass(task_id: str, arm: str = "arm-a", task_class: str = "bugfix") -> Attempt:
    return Attempt(task_id, task_class, "fixtures/dispatch_app", arm, "PASS")


def _fail(task_id: str, arm: str = "arm-a", task_class: str = "bugfix") -> Attempt:
    return Attempt(
        task_id, task_class, "fixtures/dispatch_app", arm, "FAIL", "ORACLE_FAILED"
    )


def _unknown(task_id: str, reason: str, arm: str = "arm-a") -> Attempt:
    return Attempt(task_id, "bugfix", "fixtures/dispatch_app", arm, "UNKNOWN", reason)


# --- frozen parameters ----------------------------------------------------


def test_reliability_threshold_is_the_roadmap_gate() -> None:
    assert RELIABILITY_THRESHOLD == 0.99


def test_paired_endpoint_parameters_are_the_frozen_values() -> None:
    assert (PAIRED_MINIMUM_EFFECT, PAIRED_ALPHA) == (0.05, 0.05)


# --- VCSR computed from attempts -----------------------------------------


def test_zero_attempts_render_vcsr_as_not_produced() -> None:
    assert vcsr_block([])["state"] == "NOT_PRODUCED"


def test_unproduced_vcsr_value_is_null_not_zero() -> None:
    """A 0/0 endpoint has no value; emitting 0.0 would fabricate a measurement."""
    assert vcsr_block([])["value"] is None


def test_a_run_with_attempts_is_never_rendered_as_not_produced() -> None:
    """The falsifiability invariant: 8-of-10 passing must not read NOT_PRODUCED.

    An earlier draft returned literals from zero-argument helpers, so a run that
    genuinely measured something would still have reported NOT_PRODUCED with
    every test green - a test protecting a bug (CLAUDE.md §11).
    """
    attempts = [_pass(f"t{i}") for i in range(8)] + [_fail(f"t{i}") for i in (8, 9)]
    assert vcsr_block(attempts)["state"] == "PRODUCED"


def test_vcsr_value_is_the_exact_pass_rate() -> None:
    attempts = [_pass(f"t{i}") for i in range(8)] + [_fail(f"t{i}") for i in (8, 9)]
    assert vcsr_block(attempts)["value"] == 0.8


def test_vcsr_numerator_and_denominator_are_exact() -> None:
    attempts = [_pass(f"t{i}") for i in range(8)] + [_fail(f"t{i}") for i in (8, 9)]
    block = vcsr_block(attempts)
    assert (block["numerator"], block["denominator"]) == (8, 10)


def test_unknown_attempts_stay_in_the_vcsr_denominator() -> None:
    """``unknown`` is never a pass, so dropping it would flatter the numerator."""
    attempts = [_pass("t0"), _unknown("t1", "SANDBOX_FAILURE")]
    assert vcsr_block(attempts)["value"] == 0.5


def test_vcsr_per_arm_is_reported_separately_and_never_pooled() -> None:
    attempts = [_pass("t0", "arm-a"), _fail("t1", "arm-b")]
    assert vcsr_block(attempts)["per_arm"] == {
        "arm-a": {"numerator": 1, "denominator": 1, "value": 1.0},
        "arm-b": {"numerator": 0, "denominator": 1, "value": 0.0},
    }


def test_vcsr_per_class_is_computed_from_the_attempt_task_class() -> None:
    attempts = [
        _pass("t0", task_class="bugfix"),
        _fail("t1", task_class="refactor"),
    ]
    assert vcsr_block(attempts)["per_class"] == {
        "bugfix": {"numerator": 1, "denominator": 1, "value": 1.0},
        "refactor": {"numerator": 0, "denominator": 1, "value": 0.0},
    }


# --- reliability computed from the §3 mapping ----------------------------


def test_reliability_gate_is_not_evaluated_without_attempts() -> None:
    assert reliability_block([])["gate_status"] == "NOT_EVALUATED"


def test_reliability_numerator_counts_every_product_outcome() -> None:
    """§3: PASS and every named FAIL reason reached a verdict."""
    attempts = [_pass("t0"), _fail("t1"), _fail("t2")]
    block = reliability_block(attempts)
    assert (block["successful_indexed_trials"], block["all_trials"]) == (3, 3)


def test_reliability_gate_is_met_when_every_attempt_reached_a_verdict() -> None:
    assert reliability_block([_pass("t0"), _fail("t1")])["gate_status"] == "MET"


def test_reliability_gate_is_not_met_with_one_unknown_in_ten() -> None:
    attempts = [_pass(f"t{i}") for i in range(9)] + [_unknown("t9", "SANDBOX_FAILURE")]
    assert reliability_block(attempts)["gate_status"] == "NOT_MET"


def test_reliability_ratio_is_exact() -> None:
    attempts = [_pass(f"t{i}") for i in range(9)] + [_unknown("t9", "SANDBOX_FAILURE")]
    assert reliability_block(attempts)["ratio"] == 0.9


def test_infrastructure_unknown_is_classified_as_infrastructure() -> None:
    block = reliability_block([_unknown("t0", "SANDBOX_FAILURE")])
    assert block["failure_classes"] == {"product": 0, "infrastructure": 1}


def test_input_unknown_is_classified_as_product() -> None:
    """§3 puts PROVENANCE_MISSING in the product (input/output) class."""
    block = reliability_block([_unknown("t0", "PROVENANCE_MISSING")])
    assert block["failure_classes"] == {"product": 1, "infrastructure": 0}


def test_named_fail_reason_is_classified_as_product() -> None:
    block = reliability_block([_fail("t0")])
    assert block["failure_classes"] == {"product": 1, "infrastructure": 0}


def test_failure_class_breakdown_counts_each_reason_code() -> None:
    attempts = [_unknown("t0", "ORACLE_TIMEOUT"), _unknown("t1", "ORACLE_TIMEOUT")]
    assert reliability_block(attempts)["failure_class_breakdown"]["infrastructure"] == {
        "ORACLE_TIMEOUT": 2
    }


def test_reliability_is_reported_per_arm() -> None:
    attempts = [_pass("t0", "arm-a"), _unknown("t1", "SANDBOX_FAILURE", "arm-b")]
    per_arm = reliability_block(attempts)["per_arm"]
    assert per_arm["arm-b"]["gate_status"] == "NOT_MET"


# --- paired evidence endpoint (§2 exact test) ---------------------------


def test_paired_endpoint_is_not_evaluated_without_cells() -> None:
    block = paired_endpoint_block(
        [], reliability_gate="NOT_EVALUATED", unknown_attempts=0, matrix_complete=False
    )
    assert block["state"] == "NOT_EVALUATED"


def test_paired_endpoint_counts_discordant_pairs_exactly() -> None:
    cells = [PairedCell("p1", f"t{i}", 0, True, False) for i in range(8)] + [
        PairedCell("p1", "t8", 0, False, True),
        PairedCell("p1", "t9", 0, True, True),
    ]
    block = paired_endpoint_block(
        cells, reliability_gate="MET", unknown_attempts=0, matrix_complete=True
    )
    assert (block["n11"], block["n10"], block["n01"], block["n00"]) == (1, 8, 1, 0)


def test_paired_effect_is_the_registered_formula() -> None:
    cells = [PairedCell("p1", f"t{i}", 0, True, False) for i in range(8)] + [
        PairedCell("p1", "t8", 0, False, True),
        PairedCell("p1", "t9", 0, True, True),
    ]
    block = paired_endpoint_block(
        cells, reliability_gate="MET", unknown_attempts=0, matrix_complete=True
    )
    assert block["paired_effect"] == 0.7


def test_zero_discordant_pairs_give_p_of_one() -> None:
    cells = [PairedCell("p1", "t0", 0, True, True)]
    block = paired_endpoint_block(
        cells, reliability_gate="MET", unknown_attempts=0, matrix_complete=True
    )
    assert block["p_value"] == 1.0


def test_paired_endpoint_admits_a_significant_positive_effect() -> None:
    cells = [PairedCell("p1", f"t{i}", 0, True, False) for i in range(8)] + [
        PairedCell("p1", "t8", 0, False, True),
        PairedCell("p1", "t9", 0, True, True),
    ]
    block = paired_endpoint_block(
        cells, reliability_gate="MET", unknown_attempts=0, matrix_complete=True
    )
    assert block["admission"] == "ADMITTED"


def test_an_incomplete_matrix_blocks_admission() -> None:
    cells = [PairedCell("p1", f"t{i}", 0, True, False) for i in range(8)]
    block = paired_endpoint_block(
        cells, reliability_gate="MET", unknown_attempts=0, matrix_complete=False
    )
    assert block["admission"] == "NOT_ADMITTED"


def test_an_unmet_reliability_gate_blocks_admission() -> None:
    cells = [PairedCell("p1", f"t{i}", 0, True, False) for i in range(8)]
    block = paired_endpoint_block(
        cells, reliability_gate="NOT_MET", unknown_attempts=0, matrix_complete=True
    )
    assert block["admission"] == "NOT_ADMITTED"


def test_any_unknown_attempt_blocks_admission() -> None:
    cells = [PairedCell("p1", f"t{i}", 0, True, False) for i in range(8)]
    block = paired_endpoint_block(
        cells, reliability_gate="MET", unknown_attempts=1, matrix_complete=True
    )
    assert block["admission"] == "NOT_ADMITTED"


# --- assembled report ----------------------------------------------------


def test_preflight_rejection_is_reported_as_the_run_status(report: dict) -> None:
    assert report["run_status"] == "REJECTED_AT_PREFLIGHT"


def test_report_records_the_run_as_model_free_when_no_arm_ran(report: dict) -> None:
    assert report["arm_mode"] == "model_free"


def test_report_lists_arms_derived_from_the_attempts(
    committed_preflight: PreflightResult,
) -> None:
    report = _report_with(committed_preflight, attempts=[_pass("t0", "arm-a")])
    assert report["arms"] == ["arm-a"]


def test_report_emits_no_public_claim_at_e0(report: dict) -> None:
    assert (report["evidence_level"], report["public_claim"]) == ("E0", None)


def test_b2_is_not_complete_while_gates_are_unsatisfied(report: dict) -> None:
    assert report["b2_complete"] is False


def test_b2_is_not_complete_when_the_reliability_gate_is_unmet() -> None:
    """Even a clean preflight cannot complete B2 below the 99% gate (C39)."""
    accepted = PreflightResult(status="ACCEPTED", checks=(), gates=())
    attempts = [_pass(f"t{i}") for i in range(9)] + [_unknown("t9", "SANDBOX_FAILURE")]
    report = build_report(
        records=_records(),
        preflight=accepted,
        provenance={},
        attempts=attempts,
    )
    assert report["b2_complete"] is False


def test_b2_completes_only_with_a_clean_preflight_and_a_met_gate() -> None:
    accepted = PreflightResult(status="ACCEPTED", checks=(), gates=())
    report = build_report(
        records=_records(),
        preflight=accepted,
        provenance={},
        attempts=[_pass(f"t{i}") for i in range(10)],
    )
    assert report["b2_complete"] is True


def test_b2_block_reasons_list_every_unsatisfied_gate(report: dict) -> None:
    assert report["b2_block_reasons"] == [
        gate["gate"] for gate in report["preflight"]["unsatisfied_gates"]
    ]


def test_report_separates_code_blocked_from_budget_blocked_gates(
    report: dict,
) -> None:
    categories = {
        gate["gate"]: gate["category"]
        for gate in report["preflight"]["unsatisfied_gates"]
    }
    assert (
        categories["patch_verifier_runner"] != categories["three_non_pooled_agent_arms"]
    )


def test_report_corpus_block_pins_the_registered_task_count(report: dict) -> None:
    assert report["corpus"]["task_count"] == 10


def test_report_corpus_block_pins_the_expected_terminal_distribution(
    report: dict,
) -> None:
    assert report["corpus"]["expected_terminals"] == {
        "PASS/null": 9,
        "FAIL/VERIFICATION_FAILED": 1,
    }


def test_signed_oracles_clear_the_signature_gate_in_the_report() -> None:
    records = _records()[:1]
    preflight = run_preflight(
        records,
        CORPUS_ROOT,
        oracle_signatures=[
            OracleSignature(item.id, "reviewer", "fp", "sig") for item in records
        ],
    )
    report = build_report(records=records, preflight=preflight, provenance={})
    assert "independent_oracle_signature" not in report["b2_block_reasons"]
