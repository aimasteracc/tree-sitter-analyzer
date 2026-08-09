"""Internal validation helpers for the production dispatcher."""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

from benchmarks.codegraph_compare.canary_evidence import validate_canary_manifest
from benchmarks.codegraph_compare.production_authorities import (
    ExperimentAuthorityReceiptV1,
    ProviderUsageReceiptV1,
    verify_provider_receipts,
    verify_transport_receipt,
)
from benchmarks.codegraph_compare.production_dispatch_wire import (
    ProductionDispatchRequestV1,
    ProviderRunResult,
)
from benchmarks.codegraph_compare.production_run_spec import capture_ledger_identity
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionQualification,
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
    spec, manifest = request.spec, request.manifest
    violations: list[str] = []
    bindings = (
        (
            str(request.journal_root.resolve(strict=False)) == spec.journal_root,
            "JOURNAL_ROOT_NOT_SPEC_BOUND",
        ),
        (
            str(request.evidence_root.resolve(strict=False)) == spec.evidence_root,
            "EVIDENCE_ROOT_NOT_SPEC_BOUND",
        ),
        (
            config.immutable_journal_root is not None
            and str(config.immutable_journal_root.resolve(strict=False))
            == spec.journal_root,
            "JOURNAL_ROOT_NOT_OPERATOR_BOUND",
        ),
        (
            str(config.immutable_artifact_root.resolve(strict=False))
            == spec.evidence_root,
            "EVIDENCE_ROOT_NOT_OPERATOR_BOUND",
        ),
        (
            config.global_nonce_ledger_root is not None
            and str(config.global_nonce_ledger_root.resolve(strict=False))
            == spec.global_nonce_ledger_root,
            "GLOBAL_LEDGER_ROOT_NOT_OPERATOR_BOUND",
        ),
        (spec.manifest_hash == manifest.manifest_hash, "MANIFEST_HASH_MISMATCH"),
        (spec.request_limit == 1, "REQUEST_LIMIT_NOT_ONE"),
        (
            spec.budget_ceiling_usd == manifest.budget_ceiling_usd == 3.0,
            "BUDGET_NOT_EXACTLY_FROZEN",
        ),
        (
            type(request.timeout_seconds) is int
            and request.timeout_seconds == manifest.timeout_seconds,
            "TIMEOUT_MISMATCH",
        ),
    )
    violations.extend(label for okay, label in bindings if not okay)
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
            (
                (request.cell_order == 0)
                == (request.previous_terminal_receipt_sha256 is None),
                "PREVIOUS_TERMINAL_ORDER_BINDING_INVALID",
            ),
        )
        violations.extend(label for okay, label in checks if not okay)
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
        live = capture_ledger_identity(Path(request.spec.global_nonce_ledger_root))
        expected = {name: getattr(request.spec, name) for name in live}
        if live != expected:
            violations.append("SIGNED_LEDGER_IDENTITY_CHANGED")
    except Exception as error:
        violations.append(f"LIVE_REVALIDATION_UNAVAILABLE:{error}")
    return tuple(violations)


def _result_violations(
    result: object,
    request: ProductionDispatchRequestV1,
    config: OperatorTrustConfigV1,
    qualification: ProductionQualification,
    experiment: ExperimentAuthorityReceiptV1,
    now_unix: int,
) -> tuple[str, ...]:
    if type(result) is not ProviderRunResult:
        return ("PROVIDER_RESULT_WRONG_TYPE",)
    assert qualification.provider_receipt_key is not None
    assert qualification.transport_authority_key is not None
    try:
        verify_provider_receipts(
            result.provider_reservation_receipt,
            result.provider_usage_receipt,
            spec=request.spec,
            public_key=qualification.provider_receipt_key.material,
            key_id=config.provider_receipt_key_id,
            authorized_budget_microusd=experiment.authorized_budget_microusd,
            reservation_id=experiment.cell_reservation_id,
        )
        assert type(result.provider_usage_receipt) is ProviderUsageReceiptV1
        verify_transport_receipt(
            result.transport_receipt,
            spec=request.spec,
            usage=result.provider_usage_receipt,
            timeout_seconds=request.timeout_seconds,
            public_key=qualification.transport_authority_key.material,
            key_id=config.transport_authority_key_id,
            now_unix=now_unix,
        )
    except (TypeError, ValueError) as error:
        return (f"PROVIDER_OR_TRANSPORT_RECEIPTS_INVALID:{error}",)
    usage = result.provider_usage_receipt
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
