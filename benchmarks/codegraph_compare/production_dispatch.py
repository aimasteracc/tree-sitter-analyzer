"""Fail-closed one-shot production canary dispatch boundary."""

from __future__ import annotations

import hashlib
import hmac
import math
from collections.abc import Callable
from pathlib import Path

from benchmarks.codegraph_compare.canary_evidence import validate_canary_manifest
from benchmarks.codegraph_compare.production_collector import EvidenceCollector
from benchmarks.codegraph_compare.production_dispatch_wire import (
    ProductionDispatchReceiptV1,
    ProductionDispatchRequestV1,
    ProviderRequestGate,
    ProviderReservationReceiptV1,
    ProviderRunFailure,
    ProviderRunResult,
    TrustedOfflineTestAdapter,
    _canonical,
    _claim_global,
    _Journal,
)
from benchmarks.codegraph_compare.production_dispatch_wire import (
    issue_provider_reservation_receipt as issue_provider_reservation_receipt,
)
from benchmarks.codegraph_compare.production_dispatch_wire import (
    load_journal_event_v1 as load_journal_event_v1,
)
from benchmarks.codegraph_compare.production_dispatch_wire import (
    load_production_dispatch_receipt_v1 as load_production_dispatch_receipt_v1,
)
from benchmarks.codegraph_compare.production_dispatch_wire import (
    load_production_dispatch_request_v1 as load_production_dispatch_request_v1,
)
from benchmarks.codegraph_compare.production_journal_recovery import (
    recover_hanging_journal,
)
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
    qualify_production_trust_v2,
    validate_production_run_spec,
)


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
    spec = request.spec
    manifest = request.manifest
    violations: list[str] = []
    canonical_journal = str(request.journal_root.resolve(strict=False))
    canonical_evidence = str(request.evidence_root.resolve(strict=False))
    if canonical_journal != spec.journal_root:
        violations.append("JOURNAL_ROOT_NOT_SPEC_BOUND")
    if canonical_evidence != spec.evidence_root:
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
    if (
        type(request.qualification_evidence_digest) is not str
        or len(request.qualification_evidence_digest) != 64
        or any(
            c not in "0123456789abcdef" for c in request.qualification_evidence_digest
        )
    ):
        violations.append("QUALIFICATION_EVIDENCE_DIGEST_INVALID")
    return tuple(violations)


def _revalidate(
    request: ProductionDispatchRequestV1,
    clock: Callable[[], int],
    state: Callable[[], tuple[str, str]],
) -> tuple[str, ...]:
    violations = []
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


def _verify_provider_receipt(
    result: ProviderRunResult, spec: ProductionRunSpecV1, config: OperatorTrustConfigV1
) -> tuple[str, ...]:
    receipt = result.provider_reservation_receipt
    if (
        type(receipt) is not ProviderReservationReceiptV1
        or config.pinned_provider_receipt_key is None
    ):
        return ("VERIFIABLE_PROVIDER_RESERVATION_MISSING",)
    try:
        key = bytes.fromhex(config.pinned_provider_receipt_key.read_text().strip())
    except Exception:
        return ("PROVIDER_RESERVATION_KEY_UNAVAILABLE",)
    fields = {
        "schema_version": receipt.schema_version,
        "spec_hash": receipt.spec_hash,
        "reservation_id": receipt.reservation_id,
        "request_limit": receipt.request_limit,
        "token_limit": receipt.token_limit,
        "budget_ceiling_usd": receipt.budget_ceiling_usd,
    }
    expected = hmac.new(key, _canonical(fields), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, receipt.hmac_sha256) or fields != {
        "schema_version": 1,
        "spec_hash": spec.spec_hash,
        "reservation_id": receipt.reservation_id,
        "request_limit": 1,
        "token_limit": spec.token_limit,
        "budget_ceiling_usd": spec.budget_ceiling_usd,
    }:
        return ("PROVIDER_RESERVATION_INVALID",)
    return ()


def _usage_violations(
    result: ProviderRunResult,
    spec: ProductionRunSpecV1,
    config: OperatorTrustConfigV1,
    actual_count: int,
) -> tuple[str, ...]:
    if type(result) is not ProviderRunResult:
        return ("PROVIDER_RESULT_WRONG_TYPE",)
    if (
        result.usage_complete is not True
        or type(result.provider_request_count) is not int
        or type(result.input_tokens) is not int
        or type(result.output_tokens) is not int
        or type(result.cost_usd) is not float
        or not math.isfinite(result.cost_usd)
        or min(result.provider_request_count, result.input_tokens, result.output_tokens)
        < 0
        or result.cost_usd < 0
    ):
        return ("USAGE_MISSING_OR_INVALID",)
    violations = list(_verify_provider_receipt(result, spec, config))
    if actual_count != 1 or result.provider_request_count != actual_count:
        violations.append("PROVIDER_REQUEST_COUNT_NOT_ONE")
    if result.input_tokens + result.output_tokens > spec.token_limit:
        violations.append("TOKEN_LIMIT_EXCEEDED")
    if result.cost_usd > spec.budget_ceiling_usd:
        violations.append("BUDGET_EXCEEDED")
    return tuple(violations)


def _receipt(
    status: str,
    violations: tuple[str, ...],
    request: ProductionDispatchRequestV1 | None = None,
    *,
    reserved: bool = False,
    terminal: bool = False,
    callbacks: int = 0,
    result: ProviderRunResult | None = None,
    digest: str | None = None,
) -> ProductionDispatchReceiptV1:
    return ProductionDispatchReceiptV1(
        status,
        violations,
        None if request is None else request.envelope_hash,
        reserved,
        terminal,
        callbacks,
        None if result is None else result.provider_request_count,
        None if result is None else result.input_tokens,
        None if result is None else result.output_tokens,
        None if result is None else result.cost_usd,
        "unknown" if result is None else result.termination_reason,
        digest,
    )


def dispatch_once(
    request: object,
    config: OperatorTrustConfigV1,
    attestation: object,
    judge_record: object,
    *,
    evidence_bundle_root: Path,
    runner: Callable[
        [ProductionDispatchRequestV1, ProviderRequestGate], ProviderRunResult
    ]
    | TrustedOfflineTestAdapter,
    clock: Callable[[], int],
    current_state: Callable[[], tuple[str, str]],
    provider_call: Callable[[ProductionDispatchRequestV1], ProviderRunResult]
    | None = None,
) -> ProductionDispatchReceiptV1:
    violations = _validate_envelope(
        request, config, evidence_bundle_root, current_state
    )
    if isinstance(runner, TrustedOfflineTestAdapter):
        violations += ("OFFLINE_TEST_ADAPTER_NOT_PRODUCTION",)
    if provider_call is None:
        violations += ("DISPATCHER_OWNED_PROVIDER_WRAPPER_REQUIRED",)
    if violations:
        if (
            type(request) is ProductionDispatchRequestV1
            and "JOURNAL_ROOT_PREEXISTS" in violations
        ):
            try:
                if recover_hanging_journal(request):
                    violations += ("HANGING_CLAIM_TERMINALIZED_UNKNOWN",)
            except Exception as error:
                violations += (
                    f"HANGING_CLAIM_RECOVERY_FAILED:{type(error).__name__}:{error}",
                )
        return _receipt("NOT_EVALUATED", violations)
    assert type(request) is ProductionDispatchRequestV1 and provider_call is not None
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
    journal = None
    reserved = False
    terminal = False
    result = None
    digest = None
    run_violations = []
    status = "INVALID"
    gate = ProviderRequestGate(provider_call)
    try:
        try:
            journal = _Journal(request.journal_root)
            journal.write(
                "000-reserved.json",
                {
                    "schema_version": 1,
                    "event": "RESERVED",
                    "envelope_hash": request.envelope_hash,
                    "spec_hash": request.spec.spec_hash,
                    "nonce": request.spec.nonce,
                },
            )
            _claim_global(request, config)
            reserved = True
        except FileExistsError as error:
            run_violations.append(f"RESERVATION_REFUSED:{error}")
            if journal is not None:
                try:
                    journal.write(
                        "999-terminal.json",
                        {
                            "schema_version": 1,
                            "event": "TERMINAL",
                            "status": "UNKNOWN",
                            "violations": run_violations,
                            "evidence_digest": None,
                        },
                    )
                    terminal = True
                except Exception:
                    terminal = False
                journal.close()
                journal = None
            return _receipt(
                "NOT_EVALUATED",
                tuple(run_violations),
                request,
                reserved=False,
                terminal=terminal,
            )
        except Exception as error:
            run_violations.append(
                f"RESERVATION_DURABILITY_UNKNOWN:{type(error).__name__}:{error}"
            )
            if journal is not None:
                try:
                    journal.write(
                        "999-terminal.json",
                        {
                            "schema_version": 1,
                            "event": "TERMINAL",
                            "status": "UNKNOWN",
                            "violations": run_violations,
                            "evidence_digest": None,
                        },
                    )
                    terminal = True
                except Exception:
                    terminal = False
                journal.close()
                journal = None
            return _receipt(
                "INVALID",
                tuple(run_violations),
                request,
                reserved=False,
                terminal=terminal,
            )
        second = qualify_production_trust_v2(
            request.spec,
            config,
            attestation,
            judge_record,
            evidence_bundle_root=evidence_bundle_root,
            now_unix=clock(),
            expected_evidence_digest=request.qualification_evidence_digest,
        )
        run_violations.extend(second.violations)
        run_violations.extend(_revalidate(request, clock, current_state))
        collector = EvidenceCollector(request.evidence_root)
        if not run_violations:
            try:
                result = runner(request, gate)  # type: ignore[operator]
            except ProviderRunFailure as error:
                result = error.partial
                run_violations.append(f"PROVIDER_FAILURE:{error}")
            except Exception as error:
                run_violations.append(
                    f"PROVIDER_EXCEPTION:{type(error).__name__}:{error}"
                )
            run_violations.extend(_revalidate(request, clock, current_state))
        if result is None:
            collector.collect(
                request.spec.cell_id,
                "termination",
                b'{"reason":"unknown","usage":"unknown"}',
            )
            if gate.count != 0 or not run_violations:
                run_violations.append("PROVIDER_RESULT_UNAVAILABLE")
        else:
            collector.collect(request.spec.cell_id, "transcript", result.transcript)
            collector.collect(request.spec.cell_id, "tool-receipt", result.tool_receipt)
            usage_violations = _usage_violations(
                result, request.spec, config, gate.count
            )
            run_violations.extend(usage_violations)
            collector.collect(
                request.spec.cell_id,
                "termination",
                _canonical(
                    {
                        "schema_version": 1,
                        "reason": result.termination_reason,
                        "provider_reservation_id": result.provider_reservation_receipt.reservation_id
                        if result.provider_reservation_receipt
                        else None,
                    }
                ),
            )
            usage = {
                "schema_version": 1,
                "provider_requests": result.provider_request_count,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "status": "INVALID" if usage_violations else "VALID",
            }
            cost_value = usage["cost_usd"]
            if isinstance(cost_value, float) and not math.isfinite(cost_value):
                usage["cost_usd"] = None
            collector.collect(request.spec.cell_id, "usage", _canonical(usage))
        digest = collector.finalize().ledger_sha256
        status = "PASS" if not run_violations else "INVALID"
    except Exception as error:
        run_violations.append(
            f"EVIDENCE_FINALIZATION_FAILED:{type(error).__name__}:{error}"
        )
        status = "INVALID"
    finally:
        if journal is not None:
            try:
                journal.write(
                    "999-terminal.json",
                    {
                        "schema_version": 1,
                        "event": "TERMINAL",
                        "status": status if reserved else "UNKNOWN",
                        "violations": run_violations,
                        "evidence_digest": digest,
                    },
                )
                terminal = True
            except Exception as error:
                run_violations.append(
                    f"TERMINAL_WRITE_FAILED:{type(error).__name__}:{error}"
                )
                status = "INVALID"
            journal.close()
    return _receipt(
        status,
        tuple(run_violations),
        request,
        reserved=reserved,
        terminal=terminal,
        callbacks=gate.count,
        result=result,
        digest=digest,
    )
