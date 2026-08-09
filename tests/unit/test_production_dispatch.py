"""Security behaviors for the external-authority production dispatcher."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare import production_dispatch_validation
from benchmarks.codegraph_compare.canary_evidence import create_canary_manifest
from benchmarks.codegraph_compare.production_anchor import (
    AnchorKey,
    prepare_attestation,
)
from benchmarks.codegraph_compare.production_authorities import (
    ClaimAuthorityReceiptV1,
    EvidenceAuthorityReceiptV1,
    ExperimentAuthorityReceiptV1,
    ProviderReservationReceiptV1,
    ProviderUsageReceiptV1,
    SupervisedTransportReceiptV1,
    _canonical,
    ledger_identity_sha256,
    provider_usage_receipt_sha256,
    verify_experiment_receipt,
)
from benchmarks.codegraph_compare.production_dispatch import (
    ProductionDispatchReceiptV1,
    ProductionDispatchRequestV1,
    ProviderRunResult,
    TrustedOfflineTestAdapter,
    dispatch_once,
    load_journal_event_v1,
    load_production_dispatch_receipt_v1,
    load_verified_production_dispatch_receipt_v1,
)
from benchmarks.codegraph_compare.production_judge import submit_verdict
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
    capture_ledger_identity,
    qualify_production_trust_v2,
)

NOW = 1_900_000_000
SPEND = AnchorKey(b"s" * 32)
JUDGE = AnchorKey(b"j" * 32)
DIGEST = "e" * 64


def _require_trusted_dirfd_platform():
    if not production_dispatch_validation._trusted_dirfd_supported():
        pytest.skip("tracked: NO1-003D production dispatch requires openat/O_NOFOLLOW")


def _signed(private, receipt_type, **fields):
    unsigned = receipt_type(signature_ed25519="0" * 128, **fields)
    return replace(
        unsigned,
        signature_ed25519=private.sign(_canonical(unsigned.signed_fields())).hex(),
    )


class Authorities:
    def __init__(self):
        self.provider = Ed25519PrivateKey.generate()
        self.claim = Ed25519PrivateKey.generate()
        self.evidence = Ed25519PrivateKey.generate()
        self.experiment = Ed25519PrivateKey.generate()
        self.transport = Ed25519PrivateKey.generate()
        self.claimed = set()
        self.last_claim = None

    def claim_once(self, request, challenge, now):
        identity = (request.spec.spec_hash, request.spec.nonce)
        if identity in self.claimed:
            raise RuntimeError("nonce already claimed")
        self.claimed.add(identity)
        self.last_claim = _signed(
            self.claim,
            ClaimAuthorityReceiptV1,
            spec_hash=request.spec.spec_hash,
            nonce=request.spec.nonce,
            ledger_identity_sha256=ledger_identity_sha256(request.spec),
            run_expires_at_unix=request.spec.expires_at_unix,
            claim_id="claim-1",
            dispatch_challenge=challenge,
            issued_at_unix=now,
            issuer_role="nonce-claim-authority",
            key_id="claim-v1",
            schema_version=1,
        )
        return self.last_claim

    def reserve_experiment(self, request, previous, now):
        return _signed(
            self.experiment,
            ExperimentAuthorityReceiptV1,
            manifest_hash=request.manifest.manifest_hash,
            spec_hash=request.spec.spec_hash,
            nonce=request.spec.nonce,
            cell_order=request.cell_order,
            cell_reservation_id="reservation-1",
            authorized_budget_microusd=1_500_000,
            cumulative_reserved_before_microusd=0,
            cumulative_reserved_after_microusd=1_500_000,
            previous_terminal_receipt_sha256=previous,
            issued_at_unix=now,
            issuer_role="experiment-authority",
            key_id="experiment-v1",
            schema_version=1,
        )

    def supervised(self, request, claim, experiment, now):
        common = {
            "spec_hash": request.spec.spec_hash,
            "nonce": request.spec.nonce,
            "reservation_id": experiment.cell_reservation_id,
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
            budget_ceiling_microusd=experiment.authorized_budget_microusd,
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
        transport = _signed(
            self.transport,
            SupervisedTransportReceiptV1,
            spec_hash=request.spec.spec_hash,
            nonce=request.spec.nonce,
            reservation_id=experiment.cell_reservation_id,
            provider_usage_receipt_sha256=provider_usage_receipt_sha256(usage),
            timeout_seconds=request.timeout_seconds,
            provider_request_count=1,
            whole_process_terminated=True,
            issued_at_unix=now,
            issuer_role="supervised-transport-authority",
            key_id="transport-v1",
            schema_version=1,
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
            transport_receipt=transport,
        )

    def terminal(self, request, digest, result, claim, status, usage_hash, now):
        return _signed(
            self.evidence,
            EvidenceAuthorityReceiptV1,
            spec_hash=request.spec.spec_hash,
            nonce=request.spec.nonce,
            evidence_digest=digest,
            terminal_status=status,
            provider_usage_receipt_sha256=usage_hash,
            run_expires_at_unix=request.spec.expires_at_unix,
            terminal_id="terminal-1",
            claim_id=claim.claim_id,
            issued_at_unix=now,
            issuer_role="immutable-evidence-authority",
            key_id="evidence-v1",
            schema_version=1,
        )


def _write(path, raw):
    path.write_text(raw.hex())
    return path


def _inputs(tmp_path):
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
    store = operator / "roles.json"
    store.write_text("{}")
    keys = {
        "spend": SPEND.public_bytes(),
        "judge": JUDGE.public_bytes(),
        "provider": authorities.provider.public_key().public_bytes_raw(),
        "claim": authorities.claim.public_key().public_bytes_raw(),
        "evidence": authorities.evidence.public_key().public_bytes_raw(),
        "experiment": authorities.experiment.public_key().public_bytes_raw(),
        "transport": authorities.transport.public_key().public_bytes_raw(),
    }
    paths = {name: _write(operator / f"{name}.pub", raw) for name, raw in keys.items()}
    config = OperatorTrustConfigV1(
        store,
        paths["spend"],
        evidence,
        frozenset({"anchor-custodian", "budget-gateway", "evidence-collector"}),
        True,
        True,
        True,
        True,
        True,
        True,
        "provider",
        paths["judge"],
        "spend-v1",
        "judge-v1",
        journal,
        ledger,
        paths["provider"],
        "provider-budget-gateway",
        "provider-v1",
        paths["claim"],
        "claim-v1",
        paths["evidence"],
        "evidence-v1",
        paths["experiment"],
        "experiment-v1",
        paths["transport"],
        "transport-v1",
    )
    spec = replace(spec, **capture_ledger_identity(ledger))
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


def _kwargs(request, a):
    return {
        "evidence_bundle_root": request.evidence_root.parent / "bundle",
        "clock": lambda: NOW,
        "current_state": lambda: (
            request.spec.launch_identity_sha256,
            request.spec.workspace_baseline_sha256,
        ),
        "transport_authority": a.supervised,
        "experiment_authority": a.reserve_experiment,
        "claim_authority": a.claim_once,
        "evidence_authority": a.terminal,
    }


def test_external_receipts_authorize_exactly_one_supervised_transport(tmp_path):
    _require_trusted_dirfd_platform()
    request, config, attestation, judge, a = _inputs(tmp_path)
    receipt = dispatch_once(request, config, attestation, judge, **_kwargs(request, a))
    assert receipt.status == "PASS"
    assert receipt.model_callbacks_invoked == 1
    assert receipt.terminal_durable is True
    assert receipt.evidence_level == "E0"
    assert len(receipt.authority_receipts) == 6


def test_unrestricted_provider_callable_is_rejected_without_callback(tmp_path):
    request, config, attestation, judge, a = _inputs(tmp_path)
    calls = []
    kwargs = _kwargs(request, a)
    kwargs["provider_call"] = lambda *_: calls.append("called")
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert receipt.status == "NOT_EVALUATED"
    assert receipt.model_callbacks_invoked == 0
    assert calls == []
    assert receipt.violations == ("UNRESTRICTED_PROVIDER_CALLABLE_FORBIDDEN",)


def test_missing_real_transport_authority_is_zero_callback(tmp_path):
    request, config, attestation, judge, a = _inputs(tmp_path)
    kwargs = _kwargs(request, a)
    kwargs["transport_authority"] = None
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert receipt.status == "NOT_EVALUATED"
    assert receipt.model_callbacks_invoked == 0


def test_started_claim_failure_gets_durable_invalid_terminal(tmp_path):
    _require_trusted_dirfd_platform()
    request, config, attestation, judge, a = _inputs(tmp_path)
    kwargs = _kwargs(request, a)
    kwargs["experiment_authority"] = lambda *_: (_ for _ in ()).throw(
        RuntimeError("refused")
    )
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert receipt.status == "INVALID"
    assert receipt.reservation_durable is True
    assert receipt.terminal_durable is True
    assert receipt.model_callbacks_invoked == 0


def test_signed_ledger_inode_is_revalidated_after_claim(tmp_path, monkeypatch):
    _require_trusted_dirfd_platform()
    # PR #1248: inode reuse must not hide replacement of the signed ledger root.
    request, config, attestation, judge, a = _inputs(tmp_path)
    kwargs = _kwargs(request, a)
    original = a.claim_once
    real_capture = capture_ledger_identity

    def substitute(req, challenge, now):
        claim = original(req, challenge, now)
        root = Path(req.spec.global_nonce_ledger_root)
        for _ in range(32):
            shutil.rmtree(root)
            root.mkdir()
        return claim

    def capture_with_reused_inodes(root):
        live = real_capture(root)
        live["ledger_root_device"] = request.spec.ledger_root_device
        live["ledger_root_inode"] = request.spec.ledger_root_inode
        live["ledger_parent_device"] = request.spec.ledger_parent_device
        live["ledger_parent_inode"] = request.spec.ledger_parent_inode
        return live

    monkeypatch.setattr(
        "benchmarks.codegraph_compare.production_dispatch_validation.capture_ledger_identity",
        capture_with_reused_inodes,
    )
    kwargs["claim_authority"] = substitute
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert receipt.status == "INVALID"
    assert receipt.model_callbacks_invoked == 0
    assert "SIGNED_LEDGER_IDENTITY_CHANGED" in receipt.violations


def test_independent_judge_flag_blocks_dispatch(tmp_path):
    request, config, attestation, judge, a = _inputs(tmp_path)
    receipt = dispatch_once(
        request,
        replace(config, independent_judge=False),
        attestation,
        judge,
        **_kwargs(request, a),
    )
    assert receipt.status == "NOT_EVALUATED"
    assert "INDEPENDENT_JUDGE_UNAVAILABLE" in receipt.violations


def test_long_signed_termination_reason_is_durable_invalid(tmp_path):
    _require_trusted_dirfd_platform()
    request, config, attestation, judge, a = _inputs(tmp_path)
    kwargs = _kwargs(request, a)
    original = a.supervised

    def malformed(*args):
        result = original(*args)
        usage = result.provider_usage_receipt
        bad = _signed(
            a.provider,
            ProviderUsageReceiptV1,
            **{**usage.signed_fields(), "termination_reason": "x" * 257},
        )
        return replace(result, termination_reason="x" * 257, provider_usage_receipt=bad)

    kwargs["transport_authority"] = malformed
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert receipt.status == "INVALID"
    assert receipt.terminal_durable is True


def test_runner_is_never_executed(tmp_path):
    request, config, attestation, judge, a = _inputs(tmp_path)
    calls = []
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        runner=TrustedOfflineTestAdapter(lambda *_: calls.append(1)),
        **_kwargs(request, a),
    )
    assert receipt.status == "NOT_EVALUATED"
    assert calls == []


def test_pass_receipt_with_violations_is_rejected():
    authority_receipt = _canonical({"signature_ed25519": "0" * 128}).decode()
    receipt = ProductionDispatchReceiptV1(
        status="PASS",
        violations=("INVALID",),
        envelope_hash="a" * 64,
        reservation_durable=True,
        terminal_durable=True,
        model_callbacks_invoked=1,
        provider_requests=1,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        termination_reason="completed",
        evidence_digest="b" * 64,
        authority_receipts=(authority_receipt,) * 6,
    )
    with pytest.raises(ValueError, match="PASS receipt"):
        load_production_dispatch_receipt_v1(receipt.to_json())


def test_terminal_pass_with_violations_is_rejected():
    value = {
        "schema_version": 1,
        "event": "TERMINAL",
        "status": "PASS",
        "violations": ["INVALID"],
        "evidence_digest": "b" * 64,
    }
    with pytest.raises(ValueError, match="terminal event invalid"):
        load_journal_event_v1(_canonical(value))


def test_experiment_authority_rejects_cell_one_without_previous_terminal(tmp_path):
    request, _, _, _, authorities = _inputs(tmp_path)
    receipt = authorities.reserve_experiment(request, None, NOW)
    fields = receipt.signed_fields()
    fields.update(
        cell_order=1,
        cumulative_reserved_before_microusd=1_500_000,
        cumulative_reserved_after_microusd=3_000_000,
    )
    attacked = _signed(authorities.experiment, ExperimentAuthorityReceiptV1, **fields)
    with pytest.raises(ValueError, match="previous-terminal"):
        verify_experiment_receipt(
            attacked,
            spec=request.spec,
            manifest_hash=request.manifest.manifest_hash,
            cell_order=1,
            previous_terminal_receipt_sha256=None,
            public_key=authorities.experiment.public_key().public_bytes_raw(),
            key_id="experiment-v1",
            now_unix=NOW,
        )


def test_experiment_authority_rejects_independent_three_dollar_cell_reservation(
    tmp_path,
):
    request, _, _, _, authorities = _inputs(tmp_path)
    receipt = authorities.reserve_experiment(request, None, NOW)
    fields = receipt.signed_fields()
    fields.update(
        authorized_budget_microusd=3_000_000,
        cumulative_reserved_after_microusd=3_000_001,
    )
    attacked = _signed(authorities.experiment, ExperimentAuthorityReceiptV1, **fields)
    with pytest.raises(ValueError, match="budget/order"):
        verify_experiment_receipt(
            attacked,
            spec=request.spec,
            manifest_hash=request.manifest.manifest_hash,
            cell_order=0,
            previous_terminal_receipt_sha256=None,
            public_key=authorities.experiment.public_key().public_bytes_raw(),
            key_id="experiment-v1",
            now_unix=NOW,
        )


def test_transport_exception_is_counted_and_terminalized(tmp_path):
    _require_trusted_dirfd_platform()
    # PR #1248: a started transport remains one callback on exception paths.
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    kwargs = _kwargs(request, authorities)
    kwargs["transport_authority"] = lambda *_: (_ for _ in ()).throw(
        RuntimeError("transport failed")
    )
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert (
        receipt.status,
        receipt.model_callbacks_invoked,
        receipt.terminal_durable,
    ) == (
        "INVALID",
        1,
        True,
    )


def test_wrong_type_embedded_provider_receipt_is_durable_invalid(tmp_path):
    _require_trusted_dirfd_platform()
    # PR #1248: malformed exact-result receipts must not escape serialization.
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    original = authorities.supervised
    kwargs = _kwargs(request, authorities)

    def malformed(*args):
        return replace(original(*args), provider_usage_receipt="not-a-receipt")

    kwargs["transport_authority"] = malformed
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert (
        receipt.status,
        receipt.model_callbacks_invoked,
        receipt.terminal_durable,
    ) == (
        "INVALID",
        1,
        True,
    )


def test_experiment_state_mutation_blocks_transport(tmp_path):
    _require_trusted_dirfd_platform()
    # PR #1248: experiment admission must be revalidated immediately before use.
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    state = [request.spec.workspace_baseline_sha256]
    calls = []
    original = authorities.reserve_experiment
    kwargs = _kwargs(request, authorities)
    kwargs["current_state"] = lambda: (
        request.spec.launch_identity_sha256,
        state[0],
    )

    def mutate(*args):
        receipt = original(*args)
        state[0] = "0" * 64
        return receipt

    kwargs["experiment_authority"] = mutate
    kwargs["transport_authority"] = lambda *args: calls.append(args)
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert (receipt.status, receipt.model_callbacks_invoked, len(calls)) == (
        "INVALID",
        0,
        0,
    )


def test_unsupported_dirfd_platform_blocks_all_authorities(tmp_path, monkeypatch):
    # PR #1248: unsupported dirfd platforms must fail before any authority call.
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    calls = []
    kwargs = _kwargs(request, authorities)
    kwargs["claim_authority"] = lambda *args: calls.append(args)
    monkeypatch.setattr(
        "benchmarks.codegraph_compare.production_dispatch_validation._trusted_dirfd_supported",
        lambda: False,
    )
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    assert (
        receipt.status,
        len(receipt.authority_receipts),
        receipt.model_callbacks_invoked,
        len(calls),
    ) == (
        "NOT_EVALUATED",
        0,
        0,
        0,
    )


def test_generated_transport_violation_is_wire_bounded(tmp_path):
    _require_trusted_dirfd_platform()
    # PR #1248: authority diagnostics must remain persistable in strict v1 wire form.
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    kwargs = _kwargs(request, authorities)
    kwargs["transport_authority"] = lambda *_: (_ for _ in ()).throw(
        RuntimeError("x" * 2000)
    )
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    loaded = load_production_dispatch_receipt_v1(receipt.to_json())
    assert tuple(map(len, loaded.violations)) == (1024,)


def test_pass_loader_requires_and_verifies_trusted_context(tmp_path):
    _require_trusted_dirfd_platform()
    # PR #1248: persisted PASS cannot be accepted from shape-only embedded receipts.
    request, config, attestation, judge, authorities = _inputs(tmp_path)
    qualification = qualify_production_trust_v2(
        request.spec,
        config,
        attestation,
        judge,
        evidence_bundle_root=request.evidence_root.parent / "bundle",
        now_unix=NOW,
        expected_evidence_digest=request.qualification_evidence_digest,
    )
    receipt = dispatch_once(
        request, config, attestation, judge, **_kwargs(request, authorities)
    )
    with pytest.raises(ValueError, match="trusted verification context"):
        load_production_dispatch_receipt_v1(receipt.to_json())
    loaded = load_verified_production_dispatch_receipt_v1(
        receipt.to_json(),
        request=request,
        config=config,
        qualification=qualification,
        now_unix=NOW,
    )
    assert loaded.status == "PASS"
