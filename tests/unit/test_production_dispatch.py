"""Security behaviors for the external-authority production dispatcher."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare import production_collector
from benchmarks.codegraph_compare.canary_evidence import create_canary_manifest
from benchmarks.codegraph_compare.production_anchor import (
    AnchorKey,
    prepare_attestation,
)
from benchmarks.codegraph_compare.production_authorities import (
    ClaimAuthorityReceiptV1,
    EvidenceAuthorityReceiptV1,
    ProviderReservationReceiptV1,
    ProviderUsageReceiptV1,
    _canonical,
    ledger_identity_sha256,
    provider_usage_receipt_sha256,
)
from benchmarks.codegraph_compare.production_dispatch import (
    ProductionDispatchRequestV1,
    ProviderRunResult,
    TrustedOfflineTestAdapter,
    dispatch_once,
    load_journal_event_v1,
    load_production_dispatch_receipt_v1,
)
from benchmarks.codegraph_compare.production_judge import submit_verdict
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
    capture_ledger_identity,
)

NOW = 1_900_000_000
SPEND = AnchorKey(b"s" * 32)
JUDGE = AnchorKey(b"j" * 32)
DIGEST = "e" * 64


def _signed(private: Ed25519PrivateKey, receipt_type, **fields):
    unsigned = receipt_type(signature_ed25519="0" * 128, **fields)
    signature = private.sign(_canonical(unsigned.signed_fields())).hex()
    return replace(unsigned, signature_ed25519=signature)


class Authorities:
    def __init__(self):
        self.provider = Ed25519PrivateKey.generate()
        self.claim = Ed25519PrivateKey.generate()
        self.evidence = Ed25519PrivateKey.generate()
        self.claimed: set[tuple[str, str]] = set()
        self.last_claim = None

    def claim_once(self, request, challenge, now):
        identity = (request.spec.spec_hash, request.spec.nonce)
        if identity in self.claimed:
            raise RuntimeError("nonce already claimed")
        self.claimed.add(identity)
        receipt = _signed(
            self.claim,
            ClaimAuthorityReceiptV1,
            spec_hash=request.spec.spec_hash,
            nonce=request.spec.nonce,
            ledger_identity_sha256=ledger_identity_sha256(request.spec),
            run_expires_at_unix=request.spec.expires_at_unix,
            claim_id="external-claim-1",
            dispatch_challenge=challenge,
            issued_at_unix=now,
            issuer_role="nonce-claim-authority",
            key_id="claim-v1",
            schema_version=1,
        )
        self.last_claim = receipt
        return receipt

    def provider_result(self, request):
        common = {
            "spec_hash": request.spec.spec_hash,
            "nonce": request.spec.nonce,
            "reservation_id": "reservation-1",
            "run_expires_at_unix": request.spec.expires_at_unix,
            "issuer_role": "provider-budget-gateway",
            "key_id": "provider-v1",
            "schema_version": 1,
        }
        reservation = _signed(
            self.provider,
            ProviderReservationReceiptV1,
            request_limit=1,
            token_limit=request.spec.token_limit,
            budget_ceiling_microusd=3_000_000,
            **common,
        )
        usage = _signed(
            self.provider,
            ProviderUsageReceiptV1,
            provider_request_count=1,
            input_tokens=10,
            output_tokens=20,
            cost_microusd=250_000,
            termination_reason="completed",
            **common,
        )
        return ProviderRunResult(
            1,
            10,
            20,
            0.25,
            "completed",
            b"transcript",
            b"tool",
            usage_complete=True,
            provider_reservation_receipt=reservation,
            provider_usage_receipt=usage,
        )

    def terminal(self, request, digest, result, claim, now):
        return _signed(
            self.evidence,
            EvidenceAuthorityReceiptV1,
            spec_hash=request.spec.spec_hash,
            nonce=request.spec.nonce,
            evidence_digest=digest,
            terminal_status="PASS",
            provider_usage_receipt_sha256=provider_usage_receipt_sha256(
                result.provider_usage_receipt
            ),
            run_expires_at_unix=request.spec.expires_at_unix,
            terminal_id="terminal-1",
            claim_id=claim.claim_id,
            issued_at_unix=now,
            issuer_role="immutable-evidence-authority",
            key_id="evidence-v1",
            schema_version=1,
        )


def _write_key(path: Path, raw: bytes):
    path.write_text(raw.hex())
    return path


def _inputs(tmp_path: Path):
    authorities = Authorities()
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
    journal, evidence, ledger = (
        (tmp_path / name).resolve() for name in ("journal", "evidence", "ledger")
    )
    ledger.mkdir()
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
        str(journal),
        str(evidence),
        str(ledger),
        **capture_ledger_identity(ledger),
    )
    operator = tmp_path / "operator"
    operator.mkdir()
    spend = _write_key(operator / "spend.key", SPEND.raw)
    judge_key = _write_key(operator / "judge.key", JUDGE.raw)
    provider = _write_key(
        operator / "provider.pub", authorities.provider.public_key().public_bytes_raw()
    )
    claim = _write_key(
        operator / "claim.pub", authorities.claim.public_key().public_bytes_raw()
    )
    evidence_key = _write_key(
        operator / "evidence.pub", authorities.evidence.public_key().public_bytes_raw()
    )
    store = operator / "roles.json"
    store.write_text("{}")
    config = OperatorTrustConfigV1(
        store,
        spend,
        evidence,
        frozenset({"anchor-custodian", "budget-gateway", "evidence-collector"}),
        True,
        True,
        True,
        True,
        True,
        True,
        "provider",
        judge_key,
        "spend-v1",
        "judge-v1",
        journal,
        ledger,
        provider,
        "provider-budget-gateway",
        "provider-v1",
        claim,
        "claim-v1",
        evidence_key,
        "evidence-v1",
    )
    request = ProductionDispatchRequestV1(
        manifest, spec, 0, 30, DIGEST, journal, evidence
    )
    attestation = prepare_attestation(
        spec.spec_hash,
        spec.nonce,
        spec.expires_at_unix,
        SPEND,
        budget_enforcement_mode="provider",
        now_unix=NOW,
        key_id="spend-v1",
    )
    judge = submit_verdict(
        "ACCEPT", DIGEST, spec.spec_hash, JUDGE, now_unix=NOW, key_id="judge-v1"
    )
    return request, config, attestation, judge, authorities


def _kwargs(request, authorities):
    return {
        "evidence_bundle_root": request.evidence_root.parent / "bundle",
        "clock": lambda: NOW,
        "current_state": lambda: (
            request.spec.launch_identity_sha256,
            request.spec.workspace_baseline_sha256,
        ),
        "provider_call": authorities.provider_result,
        "claim_authority": authorities.claim_once,
        "evidence_authority": authorities.terminal,
    }


def test_external_receipts_authorize_exactly_one_direct_transport(tmp_path: Path):
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    calls = []
    kwargs = _kwargs(request, authorities)
    kwargs["provider_call"] = lambda current: (
        calls.append(current.spec.nonce) or authorities.provider_result(current)
    )
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert receipt.status == "PASS"
    assert receipt.violations == ()
    assert receipt.model_callbacks_invoked == 1
    assert receipt.reservation_durable is True
    assert receipt.terminal_durable is True
    assert receipt.evidence_level == "E1"
    assert calls == ["one-shot-nonce"]


def test_provider_gate_and_private_transport_are_not_exposed():
    # Incident 2026-07-03: hostile runner accessed gate._call for a second spend.
    import benchmarks.codegraph_compare.production_dispatch as dispatch
    import benchmarks.codegraph_compare.production_dispatch_wire as wire

    assert hasattr(dispatch, "ProviderRequestGate") is False
    assert hasattr(wire, "ProviderRequestGate") is False


def test_runner_is_never_executed_and_cannot_authorize_real_call(tmp_path: Path):
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    calls = []
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        **_kwargs(request, authorities),
        runner=lambda *_: calls.append("runner"),
    )
    assert receipt.status == "NOT_EVALUATED"
    assert receipt.model_callbacks_invoked == 0
    assert calls == []
    assert receipt.violations == (
        "OFFLINE_FAKE_QUALIFICATION_DOES_NOT_AUTHORIZE_REAL_CALL",
    )


def test_offline_adapter_does_not_invoke_fake_or_real_transport(tmp_path: Path):
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    calls = []
    kwargs = _kwargs(request, authorities)
    kwargs["provider_call"] = lambda current: (
        calls.append("real") or authorities.provider_result(current)
    )
    adapter = TrustedOfflineTestAdapter(
        lambda current: calls.append("fake") or authorities.provider_result(current)
    )
    receipt = dispatch_once(
        request, config, attestation, judge, runner=adapter, **kwargs
    )
    assert receipt.status == "NOT_EVALUATED"
    assert calls == []


def test_unlinking_local_claim_state_cannot_replay_callback(tmp_path: Path):
    # Incident 2026-07-03: unlinking a local 0400 claim allowed a second callback.
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    calls = []
    kwargs = _kwargs(request, authorities)
    kwargs["provider_call"] = lambda current: (
        calls.append("called") or authorities.provider_result(current)
    )
    first = dispatch_once(request, config, attestation, judge, **kwargs)
    shutil.rmtree(request.evidence_root)
    second = dispatch_once(request, config, attestation, judge, **kwargs)
    assert first.status == "PASS"
    assert second.status == "NOT_EVALUATED"
    assert second.model_callbacks_invoked == 0
    assert calls == ["called"]
    assert second.violations == (
        "EXTERNAL_CLAIM_REFUSED:RuntimeError:nonce already claimed",
    )


def test_replayed_signed_claim_fails_fresh_dispatch_challenge(tmp_path: Path):
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    calls = []
    kwargs = _kwargs(request, authorities)
    kwargs["provider_call"] = lambda current: (
        calls.append("called") or authorities.provider_result(current)
    )
    first = dispatch_once(request, config, attestation, judge, **kwargs)
    shutil.rmtree(request.evidence_root)
    cached = authorities.last_claim
    kwargs["claim_authority"] = lambda *_: cached
    second = dispatch_once(request, config, attestation, judge, **kwargs)
    assert first.status == "PASS"
    assert second.model_callbacks_invoked == 0
    assert calls == ["called"]
    assert "claim receipt binding or lifetime mismatch" in second.violations[0]


def test_rename_race_local_evidence_cannot_claim_terminal_durability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Incident 2026-07-03 / CI job 93194929365: local Windows E0 is not authority.
    monkeypatch.setattr(production_collector, "_dirfd_supported", lambda: False)
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    moved = tmp_path / "moved-evidence"

    def provider(current):
        current.evidence_root.mkdir()
        current.evidence_root.rename(moved)
        return authorities.provider_result(current)

    kwargs = _kwargs(request, authorities)
    kwargs["provider_call"] = provider
    kwargs["evidence_authority"] = lambda *_: (_ for _ in ()).throw(
        RuntimeError("immutable ingest absent")
    )
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert receipt.status == "NOT_EVALUATED"
    assert receipt.terminal_durable is False
    assert receipt.evidence_level == "E0"


def test_missing_external_evidence_authority_prevents_real_call(tmp_path: Path):
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    calls = []
    kwargs = _kwargs(request, authorities)
    kwargs["provider_call"] = lambda current: (
        calls.append("called") or authorities.provider_result(current)
    )
    kwargs["evidence_authority"] = None
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert receipt.status == "NOT_EVALUATED"
    assert calls == []
    assert receipt.evidence_level == "E0"


def test_pass_receipt_with_violations_is_rejected():
    value = {
        "cost_usd": 0.0,
        "dominance_allowed": False,
        "envelope_hash": "a" * 64,
        "evidence_digest": "b" * 64,
        "evidence_level": "E1",
        "input_tokens": 0,
        "model_callbacks_invoked": 1,
        "output_tokens": 0,
        "provider_requests": 1,
        "publishable": False,
        "reservation_durable": True,
        "schema_version": 1,
        "status": "PASS",
        "terminal_durable": True,
        "termination_reason": "completed",
        "violations": ["PROVIDER_RESERVATION_INVALID"],
        "winner": None,
    }
    with pytest.raises(ValueError, match="PASS receipt"):
        load_production_dispatch_receipt_v1(_canonical(value))


def test_terminal_pass_with_violations_is_rejected():
    value = {
        "schema_version": 1,
        "event": "TERMINAL",
        "status": "PASS",
        "violations": ["PROVIDER_RESERVATION_INVALID"],
        "evidence_digest": "b" * 64,
    }
    with pytest.raises(ValueError, match="terminal event invalid"):
        load_journal_event_v1(_canonical(value))
