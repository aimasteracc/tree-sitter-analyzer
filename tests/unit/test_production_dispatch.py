"""Behavioral tests for the one-shot production dispatch subsystem."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from benchmarks.codegraph_compare.canary_evidence import create_canary_manifest
from benchmarks.codegraph_compare.production_anchor import (
    AnchorKey,
    prepare_attestation,
)
from benchmarks.codegraph_compare.production_dispatch import (
    ProductionDispatchRequestV1,
    ProviderRunFailure,
    ProviderRunResult,
    dispatch_once,
)
from benchmarks.codegraph_compare.production_judge import submit_verdict
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
)

NOW = 1_900_000_000
SPEND = AnchorKey(b"s" * 32)
JUDGE = AnchorKey(b"j" * 32)
DIGEST = "e" * 64


def _inputs(tmp_path: Path):
    manifest = create_canary_manifest(
        benchmark_git_sha="git",
        benchmark_version="v1",
        model="frozen-model",
        agent_cli_fingerprint="cli",
        gin_commit="gin",
        gin_source_fingerprint="a" * 64,
        canary_prompt_sha256="b" * 64,
        launch_config_hashes={"tsa-warm": "c" * 64, "codegraph-warm": "d" * 64},
        timeout_seconds=30,
        seed=7,
    )
    cell = manifest.cells[0]
    spec = ProductionRunSpecV1(
        manifest.manifest_hash,
        cell.cell_id,
        manifest.model,
        manifest.canary_prompt_sha256,
        dict(manifest.launch_config_hashes)[cell.arm],
        "f" * 64,
        3.0,
        100,
        1,
        "one-shot-nonce",
        NOW + 100,
    )
    operator = tmp_path / "operator"
    operator.mkdir()
    spend_path = operator / "spend.key"
    spend_path.write_text(SPEND.raw.hex())
    judge_path = operator / "judge.key"
    judge_path.write_text(JUDGE.raw.hex())
    store = operator / "roles.json"
    store.write_text("{}")
    evidence = tmp_path / "evidence"
    config = OperatorTrustConfigV1(
        store,
        spend_path,
        evidence,
        frozenset({"anchor-custodian", "budget-gateway", "evidence-collector"}),
        False,
        True,
        True,
        True,
        True,
        True,
        "client-process-kill",
        judge_path,
        "spend-2026",
        "judge-2026",
    )
    request = ProductionDispatchRequestV1(
        manifest, spec, 0, 30, DIGEST, tmp_path / "journal", evidence
    )
    attestation = prepare_attestation(
        spec.spec_hash,
        spec.nonce,
        spec.expires_at_unix,
        SPEND,
        now_unix=NOW,
        key_id="spend-2026",
    )
    judge = submit_verdict(
        "ACCEPT", DIGEST, spec.spec_hash, JUDGE, now_unix=NOW, key_id="judge-2026"
    )
    return request, config, attestation, judge


def _state(request: ProductionDispatchRequestV1):
    return lambda: (
        request.spec.launch_identity_sha256,
        request.spec.workspace_baseline_sha256,
    )


def _result(**changes):
    values = {
        "provider_request_count": 1,
        "input_tokens": 10,
        "output_tokens": 20,
        "cost_usd": 0.25,
        "termination_reason": "completed",
        "transcript": b"partial transcript",
        "tool_receipt": b"tool receipt",
    }
    values.update(changes)
    return ProviderRunResult(**values)


def test_success_consumes_reservation_before_exactly_one_callback(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    observations = []

    def runner(_request):
        observations.append((request.journal_root / "000-reserved.json").is_file())
        return _result()

    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=runner,
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert observations == [True]
    assert receipt.status == "PASS"
    assert receipt.model_callbacks_invoked == 1
    assert receipt.provider_requests == 1
    assert receipt.terminal_durable is True
    assert receipt.evidence_level == "E0"
    assert receipt.winner is None
    assert receipt.dominance_allowed is False
    assert receipt.publishable is False


def test_second_consumption_invokes_zero_callbacks(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    calls = []

    def runner(_request):
        calls.append("call")
        return _result()

    first = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=runner,
        clock=lambda: NOW,
        current_state=_state(request),
    )
    second = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=runner,
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert first.model_callbacks_invoked == 1
    assert second.model_callbacks_invoked == 0
    assert calls == ["call"]


def test_non_single_request_is_rejected_before_callback(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    bad = replace(request, spec=replace(request.spec, request_limit=2))
    receipt = dispatch_once(
        bad,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda _: _result(),
        clock=lambda: NOW,
        current_state=_state(bad),
    )
    assert receipt.violations == ("REQUEST_LIMIT_NOT_ONE",)
    assert receipt.model_callbacks_invoked == 0
    assert receipt.reservation_durable is False


def test_expiry_after_reservation_is_terminal_without_callback(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    ticks = iter((NOW, request.spec.expires_at_unix, request.spec.expires_at_unix))
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda _: _result(),
        clock=lambda: next(ticks),
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.model_callbacks_invoked == 0
    assert receipt.violations == ("RUN_SPEC_EXPIRED", "RUN_SPEC_EXPIRED")
    assert receipt.reservation_durable is True
    assert receipt.terminal_durable is True


def test_workspace_change_after_callback_invalidates_result(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    states = iter(
        (
            (
                request.spec.launch_identity_sha256,
                request.spec.workspace_baseline_sha256,
            ),
            (
                request.spec.launch_identity_sha256,
                request.spec.workspace_baseline_sha256,
            ),
            (request.spec.launch_identity_sha256, "0" * 64),
        )
    )
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda _: _result(),
        clock=lambda: NOW,
        current_state=lambda: next(states),
    )
    assert receipt.status == "INVALID"
    assert receipt.violations == ("LIVE_WORKSPACE_MISMATCH",)
    assert receipt.model_callbacks_invoked == 1


def test_timeout_failure_preserves_partial_evidence_and_terminal(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    partial = _result(
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
        termination_reason="timeout-killed-waited",
    )

    def runner(_):
        raise ProviderRunFailure("timeout", partial)

    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=runner,
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.violations == (
        "PROVIDER_FAILURE:timeout",
        "USAGE_MISSING_OR_INVALID",
    )
    assert receipt.model_callbacks_invoked == 1
    assert receipt.provider_requests == 1
    assert receipt.evidence_digest is not None
    assert (
        request.evidence_root / request.spec.cell_id / "transcript"
    ).read_bytes() == b"partial transcript"
    assert receipt.terminal_durable is True


def test_unknown_nonfinite_usage_fails_closed(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda _: _result(cost_usd=float("nan")),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.model_callbacks_invoked == 1
    assert receipt.evidence_digest is not None
    assert receipt.terminal_durable is True
    assert receipt.violations == ("USAGE_MISSING_OR_INVALID",)
