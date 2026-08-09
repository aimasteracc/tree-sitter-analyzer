"""Executable mutation gate for the NO1-003D external-authority dispatcher.

This is a model-free synthetic harness.  It constructs independent authority
services around the public dispatch API and exits non-zero if any mutation can
cross the direct, exactly-once transport boundary or overstate local E0 evidence.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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
    ledger_identity_sha256,
    provider_usage_receipt_sha256,
)
from benchmarks.codegraph_compare.production_collector import EvidenceCollector
from benchmarks.codegraph_compare.production_dispatch import (
    ProductionDispatchRequestV1,
    ProviderRunResult,
    dispatch_once,
)
from benchmarks.codegraph_compare.production_judge import submit_verdict
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
    capture_ledger_identity,
)

NOW = 1_900_000_000
QUALIFICATION_DIGEST = "e" * 64
ROLES = frozenset({"anchor-custodian", "budget-gateway", "evidence-collector"})


def canonical(value: object) -> bytes:
    return json.dumps(
        value, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()


def signed(private_key: Ed25519PrivateKey, receipt_type: type, **fields: Any):
    """Act as an external service by signing that service's public wire receipt."""
    unsigned = receipt_type(signature_ed25519="0" * 128, **fields)
    return replace(
        unsigned,
        signature_ed25519=private_key.sign(canonical(unsigned.signed_fields())).hex(),
    )


class SyntheticAuthorities:
    """Stateful external services; their one-shot state is not stored locally."""

    def __init__(self) -> None:
        self.provider_key = Ed25519PrivateKey.generate()
        self.claim_key = Ed25519PrivateKey.generate()
        self.evidence_key = Ed25519PrivateKey.generate()
        self.claimed: set[tuple[str, str]] = set()
        self.last_claim: ClaimAuthorityReceiptV1 | None = None

    def issue_claim(
        self,
        request: ProductionDispatchRequestV1,
        challenge: str,
        now: int,
        *,
        role: str = "nonce-claim-authority",
        signing_key: Ed25519PrivateKey | None = None,
    ) -> ClaimAuthorityReceiptV1:
        identity = (request.spec.spec_hash, request.spec.nonce)
        if identity in self.claimed:
            raise RuntimeError("external nonce already claimed")
        self.claimed.add(identity)
        receipt = signed(
            signing_key or self.claim_key,
            ClaimAuthorityReceiptV1,
            spec_hash=request.spec.spec_hash,
            nonce=request.spec.nonce,
            ledger_identity_sha256=ledger_identity_sha256(request.spec),
            run_expires_at_unix=request.spec.expires_at_unix,
            claim_id="external-claim-1",
            dispatch_challenge=challenge,
            issued_at_unix=now,
            issuer_role=role,
            key_id="claim-v1",
            schema_version=1,
        )
        self.last_claim = receipt
        return receipt

    def provider_result(
        self, request: ProductionDispatchRequestV1
    ) -> ProviderRunResult:
        common = {
            "spec_hash": request.spec.spec_hash,
            "nonce": request.spec.nonce,
            "reservation_id": "external-reservation-1",
            "run_expires_at_unix": request.spec.expires_at_unix,
            "issuer_role": "provider-budget-gateway",
            "key_id": "provider-v1",
            "schema_version": 1,
        }
        reservation = signed(
            self.provider_key,
            ProviderReservationReceiptV1,
            request_limit=1,
            token_limit=request.spec.token_limit,
            budget_ceiling_microusd=3_000_000,
            **common,
        )
        usage = signed(
            self.provider_key,
            ProviderUsageReceiptV1,
            provider_request_count=1,
            input_tokens=10,
            output_tokens=20,
            cost_microusd=250_000,
            termination_reason="completed",
            **common,
        )
        return ProviderRunResult(
            provider_request_count=1,
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.25,
            termination_reason="completed",
            transcript=b"synthetic transcript",
            tool_receipt=b"synthetic tool receipt",
            usage_complete=True,
            provider_reservation_receipt=reservation,
            provider_usage_receipt=usage,
        )

    def issue_terminal(
        self,
        request: ProductionDispatchRequestV1,
        digest: str,
        result: ProviderRunResult,
        claim: ClaimAuthorityReceiptV1,
        now: int,
    ) -> EvidenceAuthorityReceiptV1:
        assert isinstance(result.provider_usage_receipt, ProviderUsageReceiptV1)
        return signed(
            self.evidence_key,
            EvidenceAuthorityReceiptV1,
            spec_hash=request.spec.spec_hash,
            nonce=request.spec.nonce,
            evidence_digest=digest,
            terminal_status="PASS",
            provider_usage_receipt_sha256=provider_usage_receipt_sha256(
                result.provider_usage_receipt
            ),
            run_expires_at_unix=request.spec.expires_at_unix,
            terminal_id="external-terminal-1",
            claim_id=claim.claim_id,
            issued_at_unix=now,
            issuer_role="immutable-evidence-authority",
            key_id="evidence-v1",
            schema_version=1,
        )


@dataclass(frozen=True)
class Scenario:
    request: ProductionDispatchRequestV1
    config: OperatorTrustConfigV1
    attestation: object
    judge: object
    authorities: SyntheticAuthorities
    bundle: Path

    def dispatch(self, **overrides: Any):
        arguments = {
            "evidence_bundle_root": self.bundle,
            "clock": lambda: NOW,
            "current_state": lambda: (
                self.request.spec.launch_identity_sha256,
                self.request.spec.workspace_baseline_sha256,
            ),
            "provider_call": self.authorities.provider_result,
            "claim_authority": self.authorities.issue_claim,
            "evidence_authority": self.authorities.issue_terminal,
        }
        arguments.update(overrides)
        return dispatch_once(
            self.request,
            self.config,
            self.attestation,
            self.judge,
            **arguments,
        )


def write_hex(path: Path, material: bytes) -> Path:
    path.write_text(material.hex(), encoding="ascii")
    return path


def scenario(parent: Path, name: str) -> Scenario:
    root = (parent / name).resolve()
    root.mkdir()
    authorities = SyntheticAuthorities()
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
    journal = (root / "journal").resolve()
    evidence = (root / "evidence").resolve()
    ledger = (root / "external-ledger-identity").resolve()
    ledger.mkdir()
    spec = ProductionRunSpecV1(
        manifest_hash=manifest.manifest_hash,
        cell_id=cell.cell_id,
        model=manifest.model,
        prompt_sha256=manifest.canary_prompt_sha256,
        launch_identity_sha256=dict(manifest.launch_config_hashes)[cell.arm],
        workspace_baseline_sha256="f" * 64,
        budget_ceiling_usd=3.0,
        token_limit=100,
        request_limit=1,
        nonce=f"nonce-{name}",
        expires_at_unix=NOW + 100,
        journal_root=str(journal),
        evidence_root=str(evidence),
        global_nonce_ledger_root=str(ledger),
        **capture_ledger_identity(ledger),
    )
    operator = root / "operator"
    operator.mkdir()
    spend = AnchorKey(b"s" * 32)
    judge_key = AnchorKey(b"j" * 32)
    spend_path = write_hex(operator / "spend.key", spend.raw)
    judge_path = write_hex(operator / "judge.key", judge_key.raw)
    provider_path = write_hex(
        operator / "provider.pub",
        authorities.provider_key.public_key().public_bytes_raw(),
    )
    claim_path = write_hex(
        operator / "claim.pub", authorities.claim_key.public_key().public_bytes_raw()
    )
    evidence_path = write_hex(
        operator / "evidence.pub",
        authorities.evidence_key.public_key().public_bytes_raw(),
    )
    trust_store = operator / "roles.json"
    trust_store.write_text("{}", encoding="ascii")
    config = OperatorTrustConfigV1(
        trust_store=trust_store,
        pinned_anchor=spend_path,
        immutable_artifact_root=evidence,
        trusted_roles=ROLES,
        provider_budget_enforced=True,
        append_only_ledger=True,
        immutable_collector=True,
        isolated_execution=True,
        verification_to_use_closed=True,
        independent_judge=True,
        budget_enforcement_mode="provider",
        pinned_judge=judge_path,
        spend_key_id="spend-v1",
        judge_key_id="judge-v1",
        immutable_journal_root=journal,
        global_nonce_ledger_root=ledger,
        pinned_provider_receipt_key=provider_path,
        provider_receipt_role="provider-budget-gateway",
        provider_receipt_key_id="provider-v1",
        pinned_claim_authority_key=claim_path,
        claim_authority_key_id="claim-v1",
        pinned_evidence_authority_key=evidence_path,
        evidence_authority_key_id="evidence-v1",
    )
    request = ProductionDispatchRequestV1(
        manifest, spec, 0, 30, QUALIFICATION_DIGEST, journal, evidence
    )
    attestation = prepare_attestation(
        spec.spec_hash,
        spec.nonce,
        spec.expires_at_unix,
        spend,
        budget_enforcement_mode="provider",
        now_unix=NOW,
        key_id="spend-v1",
    )
    judge = submit_verdict(
        "ACCEPT",
        QUALIFICATION_DIGEST,
        spec.spec_hash,
        judge_key,
        now_unix=NOW,
        key_id="judge-v1",
    )
    return Scenario(request, config, attestation, judge, authorities, root / "bundle")


def tracked_transport(case: Scenario, calls: list[str]):
    def call(request: ProductionDispatchRequestV1) -> ProviderRunResult:
        calls.append(request.spec.nonce)
        return case.authorities.provider_result(request)

    return call


def require(condition: bool, label: str, detail: object) -> None:
    if not condition:
        raise RuntimeError(f"{label} mutation escaped: {detail}")
    print(json.dumps({"mutation": label, "result": "blocked"}, sort_keys=True))


def run_gate(parent: Path) -> None:
    case = scenario(parent, "single-transport")
    calls: list[str] = []
    receipt = case.dispatch(provider_call=tracked_transport(case, calls))
    require(
        receipt.status == "PASS"
        and receipt.model_callbacks_invoked == 1
        and calls == [case.request.spec.nonce],
        "single_direct_transport",
        (receipt, calls),
    )
    case = scenario(parent, "claim-unlink")
    calls = []

    def provider(request):
        return calls.append(request.spec.nonce) or case.authorities.provider_result(
            request
        )

    first = case.dispatch(provider_call=provider)
    shutil.rmtree(case.request.evidence_root)
    second = case.dispatch(provider_call=provider)
    require(
        first.status == "PASS"
        and second.status == "NOT_EVALUATED"
        and second.model_callbacks_invoked == 0
        and calls == [case.request.spec.nonce]
        and "already claimed" in second.violations[0],
        "claim_unlink_replay",
        (first, second, calls),
    )
    case = scenario(parent, "cross-challenge")
    stale = case.authorities.issue_claim(case.request, "0" * 64, NOW)
    case.authorities.claimed.clear()  # external service deliberately replays its wire value
    calls = []
    receipt = case.dispatch(
        claim_authority=lambda *_: stale,
        provider_call=tracked_transport(case, calls),
    )
    require(
        receipt.status == "NOT_EVALUATED"
        and receipt.model_callbacks_invoked == 0
        and calls == []
        and "binding or lifetime mismatch" in receipt.violations[0],
        "claim_cross_challenge",
        receipt,
    )
    case = scenario(parent, "authority-role")
    calls = []
    receipt = case.dispatch(
        claim_authority=lambda request, challenge, now: case.authorities.issue_claim(
            request, challenge, now, role="immutable-evidence-authority"
        ),
        provider_call=tracked_transport(case, calls),
    )
    require(
        receipt.status == "NOT_EVALUATED"
        and calls == []
        and "identity mismatch" in receipt.violations[0],
        "authority_role_substitution",
        receipt,
    )
    case = scenario(parent, "authority-key")
    rogue = Ed25519PrivateKey.generate()
    calls = []
    receipt = case.dispatch(
        claim_authority=lambda request, challenge, now: case.authorities.issue_claim(
            request, challenge, now, signing_key=rogue
        ),
        provider_call=tracked_transport(case, calls),
    )
    require(
        receipt.status == "NOT_EVALUATED"
        and calls == []
        and "signature is invalid" in receipt.violations[0],
        "authority_key_substitution",
        receipt,
    )
    case = scenario(parent, "missing-terminal")
    calls = []
    missing = case.dispatch(
        evidence_authority=None,
        provider_call=lambda request: calls.append(request.spec.nonce),
    )
    require(
        missing.status == "NOT_EVALUATED"
        and missing.evidence_level == "E0"
        and missing.model_callbacks_invoked == 0
        and calls == [],
        "missing_terminal_authority_e0",
        missing,
    )
    case = scenario(parent, "terminal-refused")
    calls = []
    refused = case.dispatch(
        provider_call=tracked_transport(case, calls),
        evidence_authority=lambda *_: (_ for _ in ()).throw(
            RuntimeError("immutable terminal absent")
        ),
    )
    require(
        refused.status == "NOT_EVALUATED"
        and refused.evidence_level == "E0"
        and refused.terminal_durable is False
        and refused.model_callbacks_invoked == 1
        and calls == [case.request.spec.nonce],
        "missing_terminal_receipt_e0",
        refused,
    )
    local = EvidenceCollector((parent / "local-durability").resolve())
    local.collect("run", "artifact", b"local")
    local_receipt = local.finalize()
    local.close()
    require(
        local_receipt.durable is False
        and local_receipt.durability in {"local-dirfd-diagnostic-only", "unsupported"},
        "local_collection_is_e0",
        local_receipt,
    )
    with patch(
        "benchmarks.codegraph_compare.production_collector._dirfd_supported",
        return_value=False,
    ):
        windows = EvidenceCollector((parent / "windows-durability").resolve())
        windows.collect("run", "artifact", b"windows")
        windows_receipt = windows.finalize()
        windows.close()
    require(
        windows_receipt.durable is False
        and windows_receipt.durability == "unsupported",
        "windows_collection_is_e0",
        windows_receipt,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="no1-003d-mutations-") as work:
        run_gate(Path(work).resolve())
    print(json.dumps({"gate": "NO1-003D", "status": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
