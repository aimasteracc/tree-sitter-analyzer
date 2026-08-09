"""Fail-closed production dispatch verified by external Ed25519 authorities.

The dispatcher owns no signing secret and accepts no unrestricted provider
callable.  A trusted external transport authority owns/supervises the whole
provider process and returns signed exact-one, timeout, and termination proof.
"""

from __future__ import annotations

import math
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.canary_evidence import canonical_sha256
from benchmarks.codegraph_compare.production_authorities import (
    ClaimAuthorityReceiptV1,
    EvidenceAuthorityReceiptV1,
    ExperimentAuthorityReceiptV1,
    ProviderUsageReceiptV1,
    provider_usage_receipt_sha256,
    verify_claim_receipt,
    verify_evidence_receipt,
    verify_experiment_receipt,
)
from benchmarks.codegraph_compare.production_collector import EvidenceCollector
from benchmarks.codegraph_compare.production_dispatch_validation import (
    _bounded_violation,
    _result_violations,
    _revalidate,
    _validate_envelope,
    pin_ledger_directory,
)
from benchmarks.codegraph_compare.production_dispatch_wire import (
    ProductionDispatchReceiptV1,
    ProductionDispatchRequestV1,
    ProviderRunFailure,
    ProviderRunResult,
    TrustedOfflineTestAdapter,
    _canonical,
    load_journal_event_v1,
    load_production_dispatch_receipt_v1,
    load_production_dispatch_request_v1,
    load_verified_production_dispatch_receipt_v1,
)
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    qualify_production_trust_v2,
)

__all__ = [
    "ProductionDispatchRequestV1",
    "ProviderRunFailure",
    "ProviderRunResult",
    "TrustedOfflineTestAdapter",
    "dispatch_once",
    "load_journal_event_v1",
    "load_production_dispatch_receipt_v1",
    "load_verified_production_dispatch_receipt_v1",
    "load_production_dispatch_request_v1",
]

ClaimAuthorityCall = Callable[
    [ProductionDispatchRequestV1, str, int], ClaimAuthorityReceiptV1
]
ExperimentAuthorityCall = Callable[
    [ProductionDispatchRequestV1, str | None, int], ExperimentAuthorityReceiptV1
]
TransportAuthorityCall = Callable[
    [
        ProductionDispatchRequestV1,
        ClaimAuthorityReceiptV1,
        ExperimentAuthorityReceiptV1,
        int,
    ],
    ProviderRunResult,
]
EvidenceAuthorityCall = Callable[
    [
        ProductionDispatchRequestV1,
        str,
        ProviderRunResult | None,
        ClaimAuthorityReceiptV1,
        str,
        str,
        int,
    ],
    EvidenceAuthorityReceiptV1,
]


def _receipt(
    status: str,
    violations: tuple[str, ...],
    request: ProductionDispatchRequestV1 | None = None,
    *,
    claimed: bool = False,
    terminal: bool = False,
    callbacks: int = 0,
    result: ProviderRunResult | None = None,
    digest: str | None = None,
    authority_receipts: tuple[str, ...] = (),
) -> ProductionDispatchReceiptV1:
    if status == "PASS" and (
        violations
        or not claimed
        or not terminal
        or callbacks != 1
        or result is None
        or digest is None
        or len(authority_receipts) != 6
    ):
        raise ValueError("PASS receipt invariant violated")
    safe_result = result if type(result) is ProviderRunResult else None
    provider_requests = (
        safe_result.provider_request_count
        if safe_result is not None
        and type(safe_result.provider_request_count) is int
        and safe_result.provider_request_count >= 0
        else None
    )
    input_tokens = (
        safe_result.input_tokens
        if safe_result is not None
        and type(safe_result.input_tokens) is int
        and safe_result.input_tokens >= 0
        else None
    )
    output_tokens = (
        safe_result.output_tokens
        if safe_result is not None
        and type(safe_result.output_tokens) is int
        and safe_result.output_tokens >= 0
        else None
    )
    cost_usd = (
        safe_result.cost_usd
        if safe_result is not None
        and type(safe_result.cost_usd) is float
        and math.isfinite(safe_result.cost_usd)
        and safe_result.cost_usd >= 0
        else None
    )
    termination_reason = (
        safe_result.termination_reason
        if safe_result is not None
        and type(safe_result.termination_reason) is str
        and 0 < len(safe_result.termination_reason) <= 256
        else "unknown"
    )
    return ProductionDispatchReceiptV1(
        status,
        tuple(item[:1024] for item in violations),
        None if request is None else request.envelope_hash,
        claimed,
        terminal,
        callbacks,
        provider_requests,
        input_tokens,
        output_tokens,
        cost_usd,
        termination_reason,
        digest,
        "E0",
        authority_receipts,
    )


def _signed_json(receipt: Any) -> str:
    return _canonical(
        {**receipt.signed_fields(), "signature_ed25519": receipt.signature_ed25519}
    ).decode()


def dispatch_once(
    request: object,
    config: OperatorTrustConfigV1,
    attestation: object,
    judge_record: object,
    *,
    evidence_bundle_root: Path,
    clock: Callable[[], int],
    current_state: Callable[[], tuple[str, str]],
    transport_authority: TransportAuthorityCall | None = None,
    experiment_authority: ExperimentAuthorityCall | None = None,
    claim_authority: ClaimAuthorityCall | None = None,
    evidence_authority: EvidenceAuthorityCall | None = None,
    provider_call: object | None = None,
    runner: object | None = None,
) -> ProductionDispatchReceiptV1:
    """Dispatch only through an external supervised authority; never a provider callable."""
    violations = list(
        _validate_envelope(request, config, evidence_bundle_root, current_state)
    )
    if runner is not None:
        violations.append("OFFLINE_FAKE_QUALIFICATION_DOES_NOT_AUTHORIZE_REAL_CALL")
    if provider_call is not None:
        violations.append("UNRESTRICTED_PROVIDER_CALLABLE_FORBIDDEN")
    if transport_authority is None:
        violations.append("EXTERNAL_SUPERVISED_TRANSPORT_AUTHORITY_REQUIRED")
    if experiment_authority is None:
        violations.append("EXTERNAL_EXPERIMENT_AUTHORITY_REQUIRED")
    if claim_authority is None:
        violations.append("EXTERNAL_ONE_SHOT_CLAIM_AUTHORITY_REQUIRED")
    if evidence_authority is None:
        violations.append("EXTERNAL_IMMUTABLE_EVIDENCE_AUTHORITY_REQUIRED")
    if violations:
        return _receipt("NOT_EVALUATED", tuple(violations))
    assert (
        type(request) is ProductionDispatchRequestV1
        and transport_authority
        and experiment_authority
        and claim_authority
        and evidence_authority
    )
    qualification = qualify_production_trust_v2(
        request.spec,
        config,
        attestation,
        judge_record,
        evidence_bundle_root=evidence_bundle_root,
        now_unix=clock(),
        expected_evidence_digest=request.qualification_evidence_digest,
    )
    if qualification.status != "ACCEPT" or not qualification.model_callbacks_allowed:
        return _receipt("NOT_EVALUATED", qualification.violations, request)
    claim_key = qualification.claim_authority_key
    evidence_key = qualification.evidence_authority_key
    provider_key = qualification.provider_receipt_key
    experiment_key = qualification.experiment_authority_key
    transport_key = qualification.transport_authority_key
    if any(
        pin is None
        for pin in (
            claim_key,
            evidence_key,
            provider_key,
            experiment_key,
            transport_key,
        )
    ):
        return _receipt(
            "NOT_EVALUATED", ("AUTHORITY_PUBLIC_KEY_PIN_UNAVAILABLE",), request
        )
    assert (
        claim_key is not None and evidence_key is not None and provider_key is not None
    )
    assert experiment_key is not None and transport_key is not None
    try:
        ledger = pin_ledger_directory(request)
    except Exception as error:
        return _receipt(
            "NOT_EVALUATED",
            (_bounded_violation("SIGNED_LEDGER_PIN_UNAVAILABLE", error),),
            request,
        )
    try:
        challenge = secrets.token_hex(32)
        try:
            now = clock()
            claim = claim_authority(request, challenge, now)
            verify_claim_receipt(
                claim,
                spec=request.spec,
                public_key=claim_key.material,
                key_id=config.claim_authority_key_id,
                now_unix=now,
                dispatch_challenge=challenge,
            )
        except Exception as error:
            return _receipt(
                "NOT_EVALUATED",
                (_bounded_violation("EXTERNAL_CLAIM_REFUSED", error),),
                request,
            )
        run_violations = list(_revalidate(request, clock, current_state, ledger))
        result = None
        experiment = None
        digest = None
        signed: list[str] = [_signed_json(claim)]
        try:
            now = clock()
            experiment = experiment_authority(
                request, request.previous_terminal_receipt_sha256, now
            )
            verify_experiment_receipt(
                experiment,
                spec=request.spec,
                manifest_hash=request.manifest.manifest_hash,
                cell_order=request.cell_order,
                previous_terminal_receipt_sha256=request.previous_terminal_receipt_sha256,
                public_key=experiment_key.material,
                key_id=config.experiment_authority_key_id,
                now_unix=now,
            )
            signed.append(_signed_json(experiment))
            run_violations.extend(_revalidate(request, clock, current_state, ledger))
        except Exception as error:
            run_violations.append(
                _bounded_violation("EXPERIMENT_AUTHORITY_INVALID", error)
            )
        callbacks = 0
        if not run_violations and experiment is not None:
            run_violations.extend(_revalidate(request, clock, current_state, ledger))
        if not run_violations and experiment is not None:
            try:
                callbacks = 1
                result = transport_authority(request, claim, experiment, clock())
                run_violations.extend(
                    _result_violations(
                        result, request, config, qualification, experiment, clock()
                    )
                )
                run_violations.extend(
                    _revalidate(request, clock, current_state, ledger)
                )
            except ProviderRunFailure as error:
                result = error.partial
                run_violations.append(_bounded_violation("PROVIDER_FAILURE", error))
            except Exception as error:
                run_violations.append(
                    _bounded_violation("TRANSPORT_AUTHORITY_EXCEPTION", error)
                )
        if result is not None:
            try:
                for authority_receipt in (
                    result.provider_reservation_receipt,
                    result.provider_usage_receipt,
                    result.transport_receipt,
                ):
                    if authority_receipt is not None:
                        signed.append(_signed_json(authority_receipt))
                collector = EvidenceCollector(request.evidence_root)
                collector.collect(request.spec.cell_id, "transcript", result.transcript)
                collector.collect(
                    request.spec.cell_id, "tool-receipt", result.tool_receipt
                )
                collector.collect(
                    request.spec.cell_id, "authority-receipts", _canonical(signed)
                )
                digest = collector.finalize().ledger_sha256
                collector.close()
            except Exception as error:
                run_violations.append(
                    _bounded_violation("LOCAL_E0_COLLECTION_FAILED", error)
                )
        if digest is None:
            digest = canonical_sha256(
                {
                    "spec_hash": request.spec.spec_hash,
                    "violations": run_violations,
                    "status": "INVALID",
                }
            )
        terminal_status = "INVALID" if run_violations or result is None else "PASS"
        usage_hash = (
            provider_usage_receipt_sha256(result.provider_usage_receipt)
            if result is not None
            and type(result.provider_usage_receipt) is ProviderUsageReceiptV1
            else canonical_sha256(
                {
                    "spec_hash": request.spec.spec_hash,
                    "terminal_status": terminal_status,
                    "violations": run_violations,
                }
            )
        )
        try:
            now = clock()
            terminal_receipt = evidence_authority(
                request, digest, result, claim, terminal_status, usage_hash, now
            )
            verify_evidence_receipt(
                terminal_receipt,
                spec=request.spec,
                evidence_digest=digest,
                usage_receipt_sha256=usage_hash,
                claim=claim,
                terminal_status=terminal_status,
                public_key=evidence_key.material,
                key_id=config.evidence_authority_key_id,
                now_unix=now,
            )
            signed.append(_signed_json(terminal_receipt))
        except Exception as error:
            run_violations.append(
                _bounded_violation("EXTERNAL_EVIDENCE_NOT_DURABLE", error)
            )
            return _receipt(
                "NOT_EVALUATED",
                tuple(run_violations),
                request,
                claimed=True,
                callbacks=callbacks,
                result=result,
                digest=digest,
                authority_receipts=tuple(signed),
            )
        if terminal_status == "INVALID":
            return _receipt(
                "INVALID",
                tuple(run_violations),
                request,
                claimed=True,
                terminal=True,
                callbacks=callbacks,
                result=result,
                digest=digest,
                authority_receipts=tuple(signed),
            )
        return _receipt(
            "PASS",
            (),
            request,
            claimed=True,
            terminal=True,
            callbacks=1,
            result=result,
            digest=digest,
            authority_receipts=tuple(signed),
        )
    finally:
        ledger.close()
