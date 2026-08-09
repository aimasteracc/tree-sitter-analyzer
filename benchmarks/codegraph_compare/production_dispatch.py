"""Fail-closed production dispatch owned entirely by the trusted dispatcher.

Untrusted runners are never invoked and never receive a provider transport.  A
production PASS needs three external facts: a fresh one-shot nonce claim, signed
provider reservation/usage, and an immutable evidence terminal receipt.
"""

from __future__ import annotations

import math
import secrets
from collections.abc import Callable
from pathlib import Path

from benchmarks.codegraph_compare.canary_evidence import validate_canary_manifest
from benchmarks.codegraph_compare.production_authorities import (
    ClaimAuthorityReceiptV1,
    EvidenceAuthorityReceiptV1,
    ProviderUsageReceiptV1,
    verify_claim_receipt,
    verify_evidence_receipt,
    verify_provider_receipts,
)
from benchmarks.codegraph_compare.production_collector import EvidenceCollector
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
)
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    qualify_production_trust_v2,
    validate_production_run_spec,
)

__all__ = [
    "ProductionDispatchRequestV1",
    "ProviderRunFailure",
    "ProviderRunResult",
    "TrustedOfflineTestAdapter",
    "dispatch_once",
    "load_journal_event_v1",
    "load_production_dispatch_receipt_v1",
    "load_production_dispatch_request_v1",
]

ClaimAuthorityCall = Callable[
    [ProductionDispatchRequestV1, str, int], ClaimAuthorityReceiptV1
]
EvidenceAuthorityCall = Callable[
    [ProductionDispatchRequestV1, str, ProviderRunResult, ClaimAuthorityReceiptV1, int],
    EvidenceAuthorityReceiptV1,
]
ProviderTransport = Callable[[ProductionDispatchRequestV1], ProviderRunResult]


def _validate_envelope(
    request: object,
    config: OperatorTrustConfigV1,
    bundle: Path,
    state: Callable[[], tuple[str, str]],
) -> tuple[str, ...]:
    if type(request) is not ProductionDispatchRequestV1:
        return ("DISPATCH_REQUEST_WRONG_TYPE",)
    try:
        validate_canary_manifest(request.manifest)
        validate_production_run_spec(request.spec)
    except (TypeError, ValueError) as error:
        return (f"FROZEN_INPUT_INVALID:{error}",)
    spec, manifest = request.spec, request.manifest
    violations: list[str] = []
    if str(request.journal_root.resolve(strict=False)) != spec.journal_root:
        violations.append("JOURNAL_ROOT_NOT_SPEC_BOUND")
    if str(request.evidence_root.resolve(strict=False)) != spec.evidence_root:
        violations.append("EVIDENCE_ROOT_NOT_SPEC_BOUND")
    if (
        config.immutable_journal_root is None
        or str(config.immutable_journal_root.resolve(strict=False)) != spec.journal_root
    ):
        violations.append("JOURNAL_ROOT_NOT_OPERATOR_BOUND")
    if str(config.immutable_artifact_root.resolve(strict=False)) != spec.evidence_root:
        violations.append("EVIDENCE_ROOT_NOT_OPERATOR_BOUND")
    if (
        config.global_nonce_ledger_root is None
        or str(config.global_nonce_ledger_root.resolve(strict=False))
        != spec.global_nonce_ledger_root
    ):
        violations.append("GLOBAL_LEDGER_ROOT_NOT_OPERATOR_BOUND")
    bundle = bundle.resolve(strict=False)
    for root, label in (
        (request.journal_root, "JOURNAL"),
        (request.evidence_root, "EVIDENCE"),
    ):
        lexical = root.resolve(strict=False)
        if lexical == bundle or bundle in lexical.parents:
            violations.append(f"{label}_ROOT_BUNDLE_CONTROLLED")
        if root.exists():
            violations.append(f"{label}_ROOT_PREEXISTS")
    if spec.manifest_hash != manifest.manifest_hash:
        violations.append("MANIFEST_HASH_MISMATCH")
    if type(request.cell_order) is not int or request.cell_order not in (0, 1):
        violations.append("CELL_ORDER_INVALID")
    else:
        cell = manifest.cells[request.cell_order]
        launch = dict(manifest.launch_config_hashes)[cell.arm]
        checks = (
            (cell.attempt_count == 1, "ATTEMPT_COUNT_NOT_ONE"),
            (cell.schedule_order == request.cell_order, "SCHEDULE_ORDER_MISMATCH"),
            (spec.cell_id == cell.cell_id, "CELL_ID_MISMATCH"),
            (spec.model == manifest.model, "MODEL_MISMATCH"),
            (spec.prompt_sha256 == manifest.canary_prompt_sha256, "PROMPT_MISMATCH"),
            (spec.launch_identity_sha256 == launch, "LAUNCH_IDENTITY_MISMATCH"),
        )
        violations.extend(label for okay, label in checks if not okay)
    if spec.request_limit != 1:
        violations.append("REQUEST_LIMIT_NOT_ONE")
    if (
        spec.budget_ceiling_usd != manifest.budget_ceiling_usd
        or manifest.budget_ceiling_usd != 3.0
    ):
        violations.append("BUDGET_NOT_EXACTLY_FROZEN")
    if (
        type(request.timeout_seconds) is not int
        or request.timeout_seconds != manifest.timeout_seconds
    ):
        violations.append("TIMEOUT_MISMATCH")
    try:
        launch, workspace = state()
        if launch != spec.launch_identity_sha256:
            violations.append("LIVE_LAUNCH_IDENTITY_MISMATCH")
        if workspace != spec.workspace_baseline_sha256:
            violations.append("LIVE_WORKSPACE_MISMATCH")
    except Exception as error:
        violations.append(f"LIVE_STATE_UNAVAILABLE:{error}")
    digest = request.qualification_evidence_digest
    if (
        type(digest) is not str
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        violations.append("QUALIFICATION_EVIDENCE_DIGEST_INVALID")
    return tuple(violations)


def _revalidate(
    request: ProductionDispatchRequestV1,
    clock: Callable[[], int],
    state: Callable[[], tuple[str, str]],
) -> tuple[str, ...]:
    violations: list[str] = []
    try:
        if request.spec.expires_at_unix <= clock():
            violations.append("RUN_SPEC_EXPIRED")
        launch, workspace = state()
        if launch != request.spec.launch_identity_sha256:
            violations.append("LIVE_LAUNCH_IDENTITY_MISMATCH")
        if workspace != request.spec.workspace_baseline_sha256:
            violations.append("LIVE_WORKSPACE_MISMATCH")
    except Exception as error:
        violations.append(f"LIVE_REVALIDATION_UNAVAILABLE:{error}")
    return tuple(violations)


def _result_violations(
    result: object,
    request: ProductionDispatchRequestV1,
    config: OperatorTrustConfigV1,
    provider_key: bytes,
) -> tuple[str, ...]:
    if type(result) is not ProviderRunResult:
        return ("PROVIDER_RESULT_WRONG_TYPE",)
    usage = result.provider_usage_receipt
    try:
        verify_provider_receipts(
            result.provider_reservation_receipt,
            usage,
            spec=request.spec,
            public_key=provider_key,
            key_id=config.provider_receipt_key_id,
        )
    except (TypeError, ValueError) as error:
        return (f"PROVIDER_RECEIPTS_INVALID:{error}",)
    assert type(usage) is ProviderUsageReceiptV1
    expected_cost = usage.cost_microusd / 1_000_000
    if (
        result.usage_complete is not True
        or type(result.provider_request_count) is not int
        or type(result.input_tokens) is not int
        or type(result.output_tokens) is not int
        or type(result.cost_usd) is not float
        or not math.isfinite(result.cost_usd)
        or (
            result.provider_request_count,
            result.input_tokens,
            result.output_tokens,
            result.cost_usd,
            result.termination_reason,
        )
        != (
            usage.provider_request_count,
            usage.input_tokens,
            usage.output_tokens,
            expected_cost,
            usage.termination_reason,
        )
    ):
        return ("PROVIDER_RESULT_USAGE_RECEIPT_MISMATCH",)
    return ()


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
) -> ProductionDispatchReceiptV1:
    # Semantic invariant: contradictory PASS objects cannot be constructed here.
    if status == "PASS" and (
        violations
        or not claimed
        or not terminal
        or callbacks != 1
        or result is None
        or digest is None
    ):
        raise ValueError("PASS receipt invariant violated")
    return ProductionDispatchReceiptV1(
        status,
        violations,
        None if request is None else request.envelope_hash,
        claimed,
        terminal,
        callbacks,
        None if result is None else result.provider_request_count,
        None if result is None else result.input_tokens,
        None if result is None else result.output_tokens,
        None if result is None else result.cost_usd,
        "unknown" if result is None else result.termination_reason,
        digest,
        "E1" if status == "PASS" else "E0",
    )


def dispatch_once(
    request: object,
    config: OperatorTrustConfigV1,
    attestation: object,
    judge_record: object,
    *,
    evidence_bundle_root: Path,
    clock: Callable[[], int],
    current_state: Callable[[], tuple[str, str]],
    provider_call: ProviderTransport | None = None,
    claim_authority: ClaimAuthorityCall | None = None,
    evidence_authority: EvidenceAuthorityCall | None = None,
    runner: object | None = None,
) -> ProductionDispatchReceiptV1:
    """Perform one direct transport call; never execute a caller-supplied runner.

    ``runner`` remains only as a fail-closed compatibility marker.  Even a
    ``TrustedOfflineTestAdapter`` qualifies fake plumbing, not a real call, and
    therefore returns E0/NOT_EVALUATED without invoking either fake or transport.
    """
    violations = list(
        _validate_envelope(request, config, evidence_bundle_root, current_state)
    )
    if runner is not None:
        violations.append("OFFLINE_FAKE_QUALIFICATION_DOES_NOT_AUTHORIZE_REAL_CALL")
    if provider_call is None:
        violations.append("DISPATCHER_OWNED_PROVIDER_TRANSPORT_REQUIRED")
    if claim_authority is None:
        violations.append("EXTERNAL_ONE_SHOT_CLAIM_AUTHORITY_REQUIRED")
    if evidence_authority is None:
        violations.append("EXTERNAL_IMMUTABLE_EVIDENCE_AUTHORITY_REQUIRED")
    if violations:
        return _receipt("NOT_EVALUATED", tuple(violations))
    assert type(request) is ProductionDispatchRequestV1
    assert provider_call is not None
    assert claim_authority is not None
    assert evidence_authority is not None
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
    if (
        qualification.claim_authority_key is None
        or qualification.evidence_authority_key is None
        or qualification.provider_receipt_key is None
    ):
        return _receipt(
            "NOT_EVALUATED", ("AUTHORITY_PUBLIC_KEY_PIN_UNAVAILABLE",), request
        )

    challenge = secrets.token_hex(32)
    try:
        now = clock()
        claim = claim_authority(request, challenge, now)
        verify_claim_receipt(
            claim,
            spec=request.spec,
            public_key=qualification.claim_authority_key.material,
            key_id=config.claim_authority_key_id,
            now_unix=now,
            dispatch_challenge=challenge,
        )
    except Exception as error:
        return _receipt(
            "NOT_EVALUATED",
            (f"EXTERNAL_CLAIM_REFUSED:{type(error).__name__}:{error}",),
            request,
        )

    run_violations = list(_revalidate(request, clock, current_state))
    if run_violations:
        return _receipt("INVALID", tuple(run_violations), request, claimed=True)

    callbacks = 1
    result: ProviderRunResult | None = None
    try:
        # The sole production transport invocation in this module.  No gate or
        # internal callable is ever exposed to runner-controlled code.
        result = provider_call(request)
    except ProviderRunFailure as error:
        result = error.partial
        run_violations.append(f"PROVIDER_FAILURE:{error}")
    except Exception as error:
        run_violations.append(f"PROVIDER_EXCEPTION:{type(error).__name__}:{error}")

    digest: str | None = None
    if result is not None:
        run_violations.extend(
            _result_violations(
                result, request, config, qualification.provider_receipt_key.material
            )
        )
        run_violations.extend(_revalidate(request, clock, current_state))
        try:
            collector = EvidenceCollector(request.evidence_root)
            collector.collect(request.spec.cell_id, "transcript", result.transcript)
            collector.collect(request.spec.cell_id, "tool-receipt", result.tool_receipt)
            collector.collect(
                request.spec.cell_id,
                "usage",
                _canonical(
                    {
                        "provider_requests": result.provider_request_count,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "cost_usd": result.cost_usd,
                        "termination_reason": result.termination_reason,
                        "schema_version": 1,
                    }
                ),
            )
            digest = collector.finalize().ledger_sha256
            collector.close()
        except Exception as error:
            run_violations.append(
                f"LOCAL_E0_COLLECTION_FAILED:{type(error).__name__}:{error}"
            )
    else:
        run_violations.append("PROVIDER_RESULT_UNAVAILABLE")

    if run_violations or result is None or digest is None:
        return _receipt(
            "INVALID",
            tuple(run_violations),
            request,
            claimed=True,
            callbacks=callbacks,
            result=result,
            digest=digest,
        )
    assert type(result.provider_usage_receipt) is ProviderUsageReceiptV1
    try:
        now = clock()
        terminal_receipt = evidence_authority(request, digest, result, claim, now)
        verify_evidence_receipt(
            terminal_receipt,
            spec=request.spec,
            evidence_digest=digest,
            usage=result.provider_usage_receipt,
            claim=claim,
            public_key=qualification.evidence_authority_key.material,
            key_id=config.evidence_authority_key_id,
            now_unix=now,
        )
    except Exception as error:
        return _receipt(
            "NOT_EVALUATED",
            (f"EXTERNAL_EVIDENCE_NOT_DURABLE:{type(error).__name__}:{error}",),
            request,
            claimed=True,
            callbacks=callbacks,
            result=result,
            digest=digest,
        )
    return _receipt(
        "PASS",
        (),
        request,
        claimed=True,
        terminal=True,
        callbacks=callbacks,
        result=result,
        digest=digest,
    )
