"""Contracts for NO1-010B corpus preflight against the committed seed corpus.

These run against ``benchmarks/no1_010b/corpus.jsonl`` — the real registered
data, not an inline fixture — so the RFC-0026 §5 seed-corpus shape is an
executable invariant rather than prose.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.preflight import (
    EXPECTED_CLASS_COUNTS,
    Check,
    run_preflight,
    static_checks,
    unsatisfied_gates,
)
from tree_sitter_analyzer.no1_010b.record import BenchmarkRecord
from tree_sitter_analyzer.no1_010b.record_loader import (
    load_corpus_records,
    per_class_counts,
)

CORPUS_ROOT = Path(__file__).resolve().parents[3] / "benchmarks" / "no1_010b"
CORPUS_PATH = CORPUS_ROOT / "corpus.jsonl"


@pytest.fixture(scope="module")
def records() -> list[BenchmarkRecord]:
    return load_corpus_records(str(CORPUS_PATH))


def test_committed_corpus_has_exactly_ten_tasks(
    records: list[BenchmarkRecord],
) -> None:
    assert len(records) == 10


def test_committed_corpus_per_class_counts_match_registration(
    records: list[BenchmarkRecord],
) -> None:
    assert per_class_counts(records) == EXPECTED_CLASS_COUNTS


def test_committed_corpus_registers_nine_pass_terminals(
    records: list[BenchmarkRecord],
) -> None:
    passes = [item for item in records if item.expected_terminal.verdict == "PASS"]
    assert len(passes) == 9


def test_committed_corpus_registers_one_named_product_fail(
    records: list[BenchmarkRecord],
) -> None:
    fails = [
        item.expected_terminal.reason_code
        for item in records
        if item.expected_terminal.verdict == "FAIL"
    ]
    assert fails == ["VERIFICATION_FAILED"]


def test_committed_corpus_spans_three_pinned_repos(
    records: list[BenchmarkRecord],
) -> None:
    assert sorted({item.repo for item in records}) == [
        "fixtures/config_loader",
        "fixtures/dispatch_app",
        "fixtures/orders_service",
    ]


def test_committed_corpus_task_ids_are_unique(
    records: list[BenchmarkRecord],
) -> None:
    ids = [item.id for item in records]
    assert len(set(ids)) == 10


def test_committed_corpus_baseline_reason_tokens_are_unique(
    records: list[BenchmarkRecord],
) -> None:
    tokens = [item.oracle_baseline_reason for item in records]
    assert len(set(tokens)) == 10


def test_every_static_preflight_check_passes_on_the_committed_corpus(
    records: list[BenchmarkRecord],
) -> None:
    failed = [
        check.check
        for check in static_checks(records, CORPUS_ROOT)
        if check.status != "PASS"
    ]
    assert failed == []


def test_static_preflight_reports_exactly_six_checks(
    records: list[BenchmarkRecord],
) -> None:
    assert [check.check for check in static_checks(records, CORPUS_ROOT)] == [
        "task_count_exact",
        "per_class_counts_exact",
        "expected_terminal_distribution_exact",
        "oracle_files_present",
        "fixture_repos_present",
        "affected_test_oracle_strict_subset",
    ]


def test_preflight_flags_a_full_suite_affected_test_oracle(
    records: list[BenchmarkRecord],
) -> None:
    """C43: a full-suite oracle carries no selection signal and must fail."""
    selection = next(item for item in records if item.task_class == "test_selection")
    full_suite = BenchmarkRecord(
        **{
            **selection.__dict__,
            "selected_tests": ("tests/test_dispatch.py", "tests/test_registry.py"),
        }
    )
    results = {
        check.check: check.status for check in static_checks([full_suite], CORPUS_ROOT)
    }
    assert results["affected_test_oracle_strict_subset"] == "FAIL"


def test_preflight_rejects_the_run_while_gates_are_unsatisfied(
    records: list[BenchmarkRecord],
) -> None:
    assert run_preflight(records, CORPUS_ROOT).status == "REJECTED"


def test_unsatisfied_gates_name_every_blocking_rfc_constraint() -> None:
    assert [gate.gate for gate in unsatisfied_gates()] == [
        "patch_verifier_runner",
        "oracle_red_baseline",
        "fixture_commit_pinning",
        "external_registration_anchor",
        "independent_oracle_signature",
        "three_non_pooled_agent_arms",
        "paired_control_arms",
    ]


def test_check_is_immutable() -> None:
    check = Check("x", "PASS", "y")
    with pytest.raises(AttributeError):
        check.status = "FAIL"  # type: ignore[misc]
