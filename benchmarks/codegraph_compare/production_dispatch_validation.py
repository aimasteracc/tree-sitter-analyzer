"""Internal validation helpers for the production dispatcher."""

from __future__ import annotations

import math
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.canary_evidence import validate_canary_manifest
from benchmarks.codegraph_compare.production_authorities import (
    ClaimAuthorityReceiptV1,
    EvidenceAuthorityReceiptV1,
    ExperimentAuthorityReceiptV1,
    ProviderReservationReceiptV1,
    ProviderUsageReceiptV1,
    SupervisedTransportReceiptV1,
    provider_usage_receipt_sha256,
    verify_claim_receipt,
    verify_evidence_receipt,
    verify_experiment_receipt,
    verify_provider_receipts,
    verify_transport_receipt,
)
from benchmarks.codegraph_compare.production_dispatch_wire import (
    ProductionDispatchReceiptV1,
    ProductionDispatchRequestV1,
    ProviderRunResult,
    _assert_canonical_input,
    _load_production_dispatch_receipt_v1,
    _strict_json,
)
from benchmarks.codegraph_compare.production_run_spec import (
    capture_ledger_identity,  # noqa: F401
)
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionQualification,
    validate_production_run_spec,
)


@dataclass
class PinnedLedgerDirectory:
    """Open root and parent handles that prevent signed inode identity reuse."""

    root: Path
    parent_fd: int
    root_fd: int

    def close(self) -> None:
        os.close(self.root_fd)
        os.close(self.parent_fd)


def _directory_identity(prefix: str, value: os.stat_result) -> dict[str, int]:
    return {
        f"ledger_{prefix}_device": value.st_dev,
        f"ledger_{prefix}_inode": value.st_ino,
        f"ledger_{prefix}_uid": value.st_uid,
        f"ledger_{prefix}_mode": value.st_mode,
        f"ledger_{prefix}_ctime_ns": value.st_ctime_ns,
    }


def pin_ledger_directory(request: ProductionDispatchRequestV1) -> PinnedLedgerDirectory:
    """Open the signed ledger root relative to a pinned trusted parent directory."""
    if (
        os.name == "nt"
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.stat not in os.supports_follow_symlinks
    ):
        raise OSError("trusted dirfd ledger pinning is unsupported on this platform")
    root = Path(request.spec.global_nonce_ledger_root)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open(root.parent, flags)
    try:
        root_fd = os.open(root.name, flags, dir_fd=parent_fd)
    except Exception:
        os.close(parent_fd)
        raise
    pin = PinnedLedgerDirectory(root, parent_fd, root_fd)
    violations = _pinned_ledger_violations(request, pin)
    if violations:
        pin.close()
        raise ValueError(",".join(violations))
    return pin


def _pinned_ledger_violations(
    request: ProductionDispatchRequestV1, pin: PinnedLedgerDirectory
) -> tuple[str, ...]:
    """Revalidate handles and both parent-path and dirfd-name mappings."""
    try:
        parent = os.fstat(pin.parent_fd)
        root = os.fstat(pin.root_fd)
        by_name = os.stat(pin.root.name, dir_fd=pin.parent_fd, follow_symlinks=False)
        parent_by_path = os.stat(pin.root.parent, follow_symlinks=False)
        if not all(
            stat.S_ISDIR(item.st_mode)
            for item in (parent, root, by_name, parent_by_path)
        ):
            return ("SIGNED_LEDGER_IDENTITY_CHANGED",)
        expected = {
            name: getattr(request.spec, name)
            for name in (
                "ledger_root_device",
                "ledger_root_inode",
                "ledger_root_uid",
                "ledger_root_mode",
                "ledger_root_ctime_ns",
                "ledger_parent_device",
                "ledger_parent_inode",
                "ledger_parent_uid",
                "ledger_parent_mode",
                "ledger_parent_ctime_ns",
            )
        }
        live = {
            **_directory_identity("root", root),
            **_directory_identity("parent", parent),
        }
        mappings_match = (by_name.st_dev, by_name.st_ino) == (
            root.st_dev,
            root.st_ino,
        ) and (parent_by_path.st_dev, parent_by_path.st_ino) == (
            parent.st_dev,
            parent.st_ino,
        )
        if live != expected or not mappings_match:
            return ("SIGNED_LEDGER_IDENTITY_CHANGED",)
    except Exception as error:
        return (_bounded_violation("LIVE_REVALIDATION_UNAVAILABLE", error),)
    return ()


def _bounded_violation(label: str, error: object) -> str:
    prefix = f"{label}:{type(error).__name__}:"
    return (prefix + str(error))[:1024]


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
        violations.append(_bounded_violation("LIVE_STATE_UNAVAILABLE", error))
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
    ledger: PinnedLedgerDirectory,
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
        violations.append(_bounded_violation("LIVE_REVALIDATION_UNAVAILABLE", error))
    violations.extend(_pinned_ledger_violations(request, ledger))
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
        return (_bounded_violation("PROVIDER_OR_TRANSPORT_RECEIPTS_INVALID", error),)
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


def _load_authority_receipt(item: str, receipt_type: type[Any]) -> Any:
    value = _strict_json(item)
    if set(value) != set(receipt_type.__dataclass_fields__):
        raise ValueError("embedded authority receipt fields do not match exact schema")
    _assert_canonical_input(item, value)
    return receipt_type(**value)


def load_verified_production_dispatch_receipt_v1(
    data: str | bytes,
    *,
    request: ProductionDispatchRequestV1,
    config: OperatorTrustConfigV1,
    qualification: ProductionQualification,
    now_unix: int,
) -> ProductionDispatchReceiptV1:
    """Load PASS only after verifying all six signed receipts and outer bindings."""
    receipt = _load_production_dispatch_receipt_v1(data, allow_unverified_pass=True)
    if receipt.status != "PASS":
        return receipt
    if type(request) is not ProductionDispatchRequestV1:
        raise ValueError("verified PASS request context has wrong type")
    if qualification.status != "ACCEPT" or not qualification.model_callbacks_allowed:
        raise ValueError("verified PASS requires accepted production qualification")
    pins = (
        qualification.claim_authority_key,
        qualification.experiment_authority_key,
        qualification.provider_receipt_key,
        qualification.transport_authority_key,
        qualification.evidence_authority_key,
    )
    if any(pin is None or len(pin.material) != 32 for pin in pins):
        raise ValueError("verified PASS authority key context is incomplete")
    claim_pin, experiment_pin, provider_pin, transport_pin, evidence_pin = pins
    assert (
        claim_pin and experiment_pin and provider_pin and transport_pin and evidence_pin
    )
    types = (
        ClaimAuthorityReceiptV1,
        ExperimentAuthorityReceiptV1,
        ProviderReservationReceiptV1,
        ProviderUsageReceiptV1,
        SupervisedTransportReceiptV1,
        EvidenceAuthorityReceiptV1,
    )
    claim, experiment, reservation, usage, transport, evidence = tuple(
        _load_authority_receipt(item, receipt_type)
        for item, receipt_type in zip(receipt.authority_receipts, types, strict=True)
    )
    verify_claim_receipt(
        claim,
        spec=request.spec,
        public_key=claim_pin.material,
        key_id=config.claim_authority_key_id,
        now_unix=now_unix,
        dispatch_challenge=claim.dispatch_challenge,
    )
    verify_experiment_receipt(
        experiment,
        spec=request.spec,
        manifest_hash=request.manifest.manifest_hash,
        cell_order=request.cell_order,
        previous_terminal_receipt_sha256=request.previous_terminal_receipt_sha256,
        public_key=experiment_pin.material,
        key_id=config.experiment_authority_key_id,
        now_unix=now_unix,
    )
    verify_provider_receipts(
        reservation,
        usage,
        spec=request.spec,
        public_key=provider_pin.material,
        key_id=config.provider_receipt_key_id,
        authorized_budget_microusd=experiment.authorized_budget_microusd,
        reservation_id=experiment.cell_reservation_id,
    )
    verify_transport_receipt(
        transport,
        spec=request.spec,
        usage=usage,
        timeout_seconds=request.timeout_seconds,
        public_key=transport_pin.material,
        key_id=config.transport_authority_key_id,
        now_unix=now_unix,
    )
    assert receipt.evidence_digest is not None
    verify_evidence_receipt(
        evidence,
        spec=request.spec,
        evidence_digest=receipt.evidence_digest,
        usage_receipt_sha256=provider_usage_receipt_sha256(usage),
        claim=claim,
        terminal_status="PASS",
        public_key=evidence_pin.material,
        key_id=config.evidence_authority_key_id,
        now_unix=now_unix,
    )
    if (
        receipt.envelope_hash != request.envelope_hash
        or receipt.provider_requests != usage.provider_request_count
        or receipt.input_tokens != usage.input_tokens
        or receipt.output_tokens != usage.output_tokens
        or receipt.cost_usd != usage.cost_microusd / 1_000_000
        or receipt.termination_reason != usage.termination_reason
        or evidence.evidence_digest != receipt.evidence_digest
    ):
        raise ValueError("verified PASS outer receipt bindings mismatch")
    return receipt
