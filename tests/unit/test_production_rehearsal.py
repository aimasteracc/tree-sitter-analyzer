"""Behavioral tests for the offline production trust rehearsal."""

from pathlib import Path

import pytest

from benchmarks.codegraph_compare.production_rehearsal import run_offline_rehearsal


@pytest.fixture
def receipt(tmp_path: Path):
    return run_offline_rehearsal(tmp_path / "offline-rehearsal", now_unix=1_900_000_000)


def test_offline_rehearsal_seals_synthetic_trust_artifacts(receipt) -> None:
    # Issue #1223: operator qualification needs a model-free trust rehearsal.
    assert (
        receipt.status,
        receipt.execution_mode,
        receipt.artifact_count,
        receipt.attestation_verified,
        receipt.synthetic_judge_signature_verified,
    ) == ("PASS", "offline-rehearsal", 2, True, True)


def test_offline_rehearsal_denial_probe_fails_closed(receipt) -> None:
    assert (
        receipt.independent_judge_available,
        receipt.denial_probe_qualification_status,
        receipt.denial_probe_violations,
    ) == (False, "NOT_EVALUATED", ("INDEPENDENT_JUDGE_UNAVAILABLE",))


def test_offline_rehearsal_bound_fixture_traverses_v2_bindings(receipt) -> None:
    assert (
        receipt.bound_fixture_probe_assumes_independent_judge,
        receipt.bound_fixture_qualification_status,
        receipt.bound_fixture_violations,
        receipt.bound_fixture_gate_eligible,
    ) == (True, "ACCEPT", (), True)


def test_offline_rehearsal_never_consumes_dispatch_eligibility(receipt) -> None:
    assert (
        receipt.production_dispatch_allowed,
        receipt.model_callbacks_invoked,
        receipt.provider_requests,
        receipt.input_tokens,
        receipt.output_tokens,
        receipt.cost_usd,
    ) == (False, 0, 0, 0, 0, 0.0)


def test_offline_rehearsal_remains_unpublishable_e0_evidence(receipt) -> None:
    assert (
        receipt.evidence_level,
        receipt.winner,
        receipt.dominance_allowed,
        receipt.publishable,
    ) == ("E0", None, False, False)


def test_offline_rehearsal_rejects_reuse_of_work_root(tmp_path: Path) -> None:
    work_root = tmp_path / "offline-rehearsal"
    work_root.mkdir()
    with pytest.raises(ValueError, match="must not pre-exist"):
        run_offline_rehearsal(work_root, now_unix=1_900_000_000)
