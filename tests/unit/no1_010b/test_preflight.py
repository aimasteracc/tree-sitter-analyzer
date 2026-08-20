"""Contracts for NO1-010B corpus preflight against the committed seed corpus.

These run against ``benchmarks/no1_010b/`` — the real registered data, not an
inline fixture — so the RFC-0026 §5 seed-corpus shape and §3's oracle
red-baseline requirement are executable invariants rather than prose.

Negative cases operate on a temporary copy of the corpus tree; nothing here
mutates committed data.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.preflight import (
    BUDGET_BLOCKED,
    CODE_BLOCKED,
    EXPECTED_CLASS_COUNTS,
    EXTERNAL_PARTY_BLOCKED,
    Check,
    OracleSignature,
    run_oracle_baseline,
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
SELECTION_TASK_ID = "no1-010b/0004-test-selection-dispatch-version"
DISPATCH_TASK_ID = "no1-010b/0001-bugfix-dispatch-unknown-route"


@pytest.fixture(scope="module")
def records() -> list[BenchmarkRecord]:
    return load_corpus_records(str(CORPUS_PATH))


@pytest.fixture
def corpus_copy(tmp_path: Path) -> Path:
    """A writable copy of the committed corpus tree for negative cases."""
    target = tmp_path / "no1_010b"
    shutil.copytree(CORPUS_ROOT, target)
    return target


def _checks(root: Path, only: str | None = None) -> dict[str, str]:
    """Run preflight over the corpus at ``root``.

    ``only`` restricts the run to one task id. Each oracle baseline check spawns
    a real subprocess, so negative cases that care about a single task stay well
    inside the unit-suite per-test budget by not re-running the other nine.
    """
    corpus = root / "corpus.jsonl"
    records = load_corpus_records(str(corpus))
    if only is not None:
        records = [item for item in records if item.id == only]
    return {
        check.check: check.status
        for check in static_checks(records, root, corpus_path=corpus)
    }


@pytest.fixture(scope="module")
def committed_checks() -> dict[str, str]:
    """Full preflight over the committed corpus, computed once per module.

    Executing ten oracles is real work; doing it in module setup keeps it out of
    the per-test call budget while still asserting on the real committed data.
    """
    return _checks(CORPUS_ROOT)


@pytest.fixture(scope="module")
def committed_baselines(
    records: list[BenchmarkRecord],
) -> list[tuple[bool, str]]:
    return [run_oracle_baseline(item, CORPUS_ROOT) for item in records]


# --- committed corpus shape ------------------------------------------------


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


def test_committed_corpus_task_ids_are_unique(records: list[BenchmarkRecord]) -> None:
    assert len({item.id for item in records}) == 10


def test_committed_corpus_baseline_reason_tokens_are_unique(
    records: list[BenchmarkRecord],
) -> None:
    assert len({item.oracle_baseline_reason for item in records}) == 10


def test_registered_verification_argv_is_self_contained(
    records: list[BenchmarkRecord],
) -> None:
    """An unpinned bare ``python`` resolves off PATH and cannot find pytest.

    RFC-0026 §3 scores an ordinary nonzero verification exit as the *product*
    verdict VERIFICATION_FAILED, so a non-executable argv would report product
    failures at 100% reliability - a silently wrong VCSR.
    """
    assert {item.verification_argv[0] for item in records} == {"uv"}


# --- B0 exit contract: oracle red baseline (RFC-0026 §3) -------------------


def test_every_oracle_is_red_on_its_unmodified_fixture(
    committed_baselines: list[tuple[bool, str]],
) -> None:
    not_red = [detail for red, detail in committed_baselines if not red]
    assert not_red == []


def test_oracle_red_baseline_check_passes_on_the_committed_corpus(
    committed_checks: dict[str, str],
) -> None:
    assert committed_checks["oracle_red_baseline"] == "PASS"


def test_oracle_red_baseline_rejects_a_fixture_whose_defect_is_gone(
    corpus_copy: Path,
) -> None:
    """The defect-removal case that no other check can see."""
    fixture = corpus_copy / "fixtures" / "dispatch_app" / "src" / "dispatch.py"
    fixture.write_text(
        fixture.read_text(encoding="utf-8").replace(
            "    return None\n", '    return Response(404, "not found")\n'
        ),
        encoding="utf-8",
    )
    assert _checks(corpus_copy, only=DISPATCH_TASK_ID)["oracle_red_baseline"] == (
        "FAIL"
    )


def test_oracle_red_baseline_rejects_a_mismatched_reason_token(
    corpus_copy: Path,
) -> None:
    oracle = corpus_copy / "oracles" / "0001.py"
    oracle.write_text(
        oracle.read_text(encoding="utf-8").replace(
            'REASON = "dispatch-returns-none"', 'REASON = "some-other-token"'
        ),
        encoding="utf-8",
    )
    assert _checks(corpus_copy, only=DISPATCH_TASK_ID)["oracle_red_baseline"] == (
        "FAIL"
    )


def test_oracle_red_baseline_rejects_an_oracle_that_fails_at_load(
    corpus_copy: Path,
) -> None:
    """A load failure is not a behavioral verdict (C19)."""
    fixture = corpus_copy / "fixtures" / "dispatch_app" / "src" / "dispatch.py"
    fixture.write_text("def broken(:\n", encoding="utf-8")
    assert _checks(corpus_copy, only=DISPATCH_TASK_ID)["oracle_red_baseline"] == (
        "FAIL"
    )


# --- manifest drift detection ---------------------------------------------


def test_manifest_digests_match_the_committed_corpus(
    committed_checks: dict[str, str],
) -> None:
    assert committed_checks["manifest_digests_match"] == "PASS"


def test_manifest_check_detects_fixture_tree_drift(corpus_copy: Path) -> None:
    fixture = corpus_copy / "fixtures" / "dispatch_app" / "src" / "dispatch.py"
    fixture.write_text(
        fixture.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8"
    )
    assert _checks(corpus_copy, only=DISPATCH_TASK_ID)["manifest_digests_match"] == (
        "FAIL"
    )


def test_manifest_check_detects_a_missing_manifest(corpus_copy: Path) -> None:
    (corpus_copy / "manifest.json").unlink()
    assert _checks(corpus_copy, only=DISPATCH_TASK_ID)["manifest_digests_match"] == (
        "FAIL"
    )


def test_manifest_records_a_fixture_tree_digest() -> None:
    recorded = json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert len(recorded["fixture_tree_sha256"]) == 64


# --- remaining static checks ---------------------------------------------


def test_every_static_preflight_check_passes_on_the_committed_corpus(
    committed_checks: dict[str, str],
) -> None:
    assert [name for name, status in committed_checks.items() if status != "PASS"] == []


def test_static_preflight_reports_exactly_eight_checks(
    committed_checks: dict[str, str],
) -> None:
    assert list(committed_checks) == [
        "task_count_exact",
        "per_class_counts_exact",
        "expected_terminal_distribution_exact",
        "oracle_files_present",
        "fixture_repos_present",
        "affected_test_oracle_strict_subset",
        "manifest_digests_match",
        "oracle_red_baseline",
    ]


def test_preflight_flags_a_full_suite_affected_test_oracle(
    records: list[BenchmarkRecord],
) -> None:
    """C43: a full-suite oracle carries no selection signal and must fail.

    Bound to the task id, not to a position: reordering the corpus must not
    silently retarget this test at a task with no ``selected_tests``.
    """
    selection = next(item for item in records if item.id == SELECTION_TASK_ID)
    suite = sorted(
        path.relative_to(CORPUS_ROOT / selection.repo).as_posix()
        for path in (CORPUS_ROOT / selection.repo).glob("tests/**/test_*.py")
    )
    full_suite = BenchmarkRecord(
        **{**selection.__dict__, "selected_tests": tuple(suite)}
    )
    results = {
        check.check: check.status for check in static_checks([full_suite], CORPUS_ROOT)
    }
    assert results["affected_test_oracle_strict_subset"] == "FAIL"


def test_preflight_rejects_the_run_while_gates_are_unsatisfied(
    records: list[BenchmarkRecord],
) -> None:
    # One record is enough: the gates are derived from the records and every one
    # of them already rejects the run, so the other nine oracles need not re-run.
    assert run_preflight(records[:1], CORPUS_ROOT).status == "REJECTED"


# --- computed gates ------------------------------------------------------


def test_unsatisfied_gates_name_every_blocking_constraint(
    records: list[BenchmarkRecord],
) -> None:
    assert [gate.gate for gate in unsatisfied_gates(records)] == [
        "patch_verifier_runner",
        "fixture_commit_pinning",
        "external_registration_anchor",
        "independent_oracle_signature",
        "three_non_pooled_agent_arms",
        "paired_control_arms",
    ]


def test_b1_gates_are_code_blocked_not_budget_blocked(
    records: list[BenchmarkRecord],
) -> None:
    """B1 is entirely model-free; conflating it with the arm gates would teach
    the next reader that nothing progresses without a budget decision."""
    categories = {gate.gate: gate.category for gate in unsatisfied_gates(records)}
    assert categories["patch_verifier_runner"] == CODE_BLOCKED


def test_arm_gates_are_budget_blocked(records: list[BenchmarkRecord]) -> None:
    categories = {gate.gate: gate.category for gate in unsatisfied_gates(records)}
    assert categories["three_non_pooled_agent_arms"] == BUDGET_BLOCKED


def test_signature_gate_is_external_party_blocked(
    records: list[BenchmarkRecord],
) -> None:
    categories = {gate.gate: gate.category for gate in unsatisfied_gates(records)}
    assert categories["independent_oracle_signature"] == EXTERNAL_PARTY_BLOCKED


def test_verifier_gate_clears_when_a_verifier_is_supplied(
    records: list[BenchmarkRecord],
) -> None:
    gates = unsatisfied_gates(records, verifier_available=True)
    assert "patch_verifier_runner" not in {gate.gate for gate in gates}


def test_arm_gate_clears_at_three_distinct_arms(
    records: list[BenchmarkRecord],
) -> None:
    gates = unsatisfied_gates(records, arm_ids=("a", "b", "c"))
    assert "three_non_pooled_agent_arms" not in {gate.gate for gate in gates}


def test_arm_gate_holds_when_three_arm_ids_are_pooled_duplicates(
    records: list[BenchmarkRecord],
) -> None:
    gates = unsatisfied_gates(records, arm_ids=("a", "a", "a"))
    assert "three_non_pooled_agent_arms" in {gate.gate for gate in gates}


def test_signature_gate_clears_when_every_task_is_signed(
    records: list[BenchmarkRecord],
) -> None:
    signatures = [OracleSignature(item.id, "reviewer", "fp", "sig") for item in records]
    gates = unsatisfied_gates(records, oracle_signatures=signatures)
    assert "independent_oracle_signature" not in {gate.gate for gate in gates}


def test_signature_gate_holds_when_one_task_is_unsigned(
    records: list[BenchmarkRecord],
) -> None:
    signatures = [
        OracleSignature(item.id, "reviewer", "fp", "sig") for item in records[:-1]
    ]
    gates = unsatisfied_gates(records, oracle_signatures=signatures)
    assert "independent_oracle_signature" in {gate.gate for gate in gates}


def test_commit_pinning_gate_is_derived_from_the_records(
    records: list[BenchmarkRecord],
) -> None:
    """Every seed record carries the all-zero placeholder, so the gate fires."""
    gates = {gate.gate for gate in unsatisfied_gates(records)}
    assert "fixture_commit_pinning" in gates


def test_commit_pinning_gate_clears_for_a_really_pinned_record(
    records: list[BenchmarkRecord],
) -> None:
    pinned = BenchmarkRecord(**{**records[0].__dict__, "repo_commit": "a" * 40})
    gates = {gate.gate for gate in unsatisfied_gates([pinned])}
    assert "fixture_commit_pinning" not in gates


def test_check_is_immutable() -> None:
    check = Check("x", "PASS", "y")
    with pytest.raises(AttributeError):
        check.status = "FAIL"  # type: ignore[misc]
