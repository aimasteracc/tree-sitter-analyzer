"""One-shot, offline-qualifiable production canary dispatch boundary.

No provider implementation is imported here.  A human operator must inject a
restricted runner
tests inject fakes.  CanaryProtocol production mode remains closed.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from benchmarks.codegraph_compare.canary_evidence import (
    CanaryManifestV1,
    canonical_sha256,
    validate_canary_manifest,
)
from benchmarks.codegraph_compare.production_collector import EvidenceCollector
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
    qualify_production_trust_v2,
    validate_production_run_spec,
)


@dataclass(frozen=True)
class ProductionDispatchRequestV1:
    manifest: CanaryManifestV1
    spec: ProductionRunSpecV1
    cell_order: int
    timeout_seconds: int
    qualification_evidence_digest: str
    journal_root: Path
    evidence_root: Path

    @property
    def envelope_hash(self) -> str:
        return canonical_sha256(
            {
                "schema_version": 1,
                "manifest_hash": self.manifest.manifest_hash,
                "spec_hash": self.spec.spec_hash,
                "cell_order": self.cell_order,
                "qualification_evidence_digest": self.qualification_evidence_digest,
                "journal_root": str(self.journal_root.absolute()),
                "evidence_root": str(self.evidence_root.absolute()),
            }
        )


@dataclass(frozen=True)
class ProviderRunResult:
    provider_request_count: int
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    termination_reason: str
    transcript: bytes
    tool_receipt: bytes = b""
    provider_reservation_id: str | None = None
    kill_attempted: bool = False
    wait_completed: bool = False
    usage_complete: bool = False


class ProviderRunFailure(RuntimeError):
    """Runner failure carrying evidence obtained before timeout/kill/error."""

    def __init__(self, message: str, partial: ProviderRunResult) -> None:
        super().__init__(message)
        self.partial = partial


@dataclass(frozen=True)
class ProductionDispatchReceiptV1:
    status: str
    violations: tuple[str, ...]
    envelope_hash: str | None
    reservation_durable: bool
    terminal_durable: bool
    model_callbacks_invoked: int
    provider_requests: int | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    termination_reason: str
    evidence_digest: str | None
    evidence_level: str = "E0"
    winner: None = None
    dominance_allowed: bool = False
    publishable: bool = False


def _write_exclusive(path: Path, value: object) -> None:
    data = (
        json.dumps(
            value, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()
        + b"\n"
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _reserve(request: ProductionDispatchRequestV1) -> Path:
    request.journal_root.mkdir(parents=True, mode=0o700, exist_ok=False)
    event = request.journal_root / "000-reserved.json"
    _write_exclusive(
        event,
        {
            "event": "RESERVED",
            "envelope_hash": request.envelope_hash,
            "spec_hash": request.spec.spec_hash,
            "nonce": request.spec.nonce,
        },
    )
    return event


def _terminal(request: ProductionDispatchRequestV1, payload: object) -> None:
    _write_exclusive(request.journal_root / "999-terminal.json", payload)


def _validate_envelope(
    request: object,
    config: OperatorTrustConfigV1,
    evidence_bundle_root: Path,
    current_state: Callable[[], tuple[str, str]],
) -> tuple[str, ...]:
    if type(request) is not ProductionDispatchRequestV1:
        return ("DISPATCH_REQUEST_WRONG_TYPE",)
    try:
        validate_canary_manifest(request.manifest)
        validate_production_run_spec(request.spec)
    except (TypeError, ValueError) as error:
        return (f"FROZEN_INPUT_INVALID:{error}",)
    manifest, spec = request.manifest, request.spec
    violations: list[str] = []
    if spec.manifest_hash != manifest.manifest_hash:
        violations.append("MANIFEST_HASH_MISMATCH")
    if type(request.cell_order) is not int or request.cell_order not in (0, 1):
        violations.append("CELL_ORDER_INVALID")
        cell = None
    else:
        cell = manifest.cells[request.cell_order]
    if cell is not None:
        launch = dict(manifest.launch_config_hashes)[cell.arm]
        for okay, violation in (
            (cell.attempt_count == 1, "ATTEMPT_COUNT_NOT_ONE"),
            (cell.schedule_order == request.cell_order, "SCHEDULE_ORDER_MISMATCH"),
            (spec.cell_id == cell.cell_id, "CELL_ID_MISMATCH"),
            (spec.model == manifest.model, "MODEL_MISMATCH"),
            (spec.prompt_sha256 == manifest.canary_prompt_sha256, "PROMPT_MISMATCH"),
            (spec.launch_identity_sha256 == launch, "LAUNCH_IDENTITY_MISMATCH"),
        ):
            if not okay:
                violations.append(violation)
    if spec.request_limit != 1:
        violations.append("REQUEST_LIMIT_NOT_ONE")
    if (
        spec.budget_ceiling_usd != manifest.budget_ceiling_usd
        or manifest.budget_ceiling_usd != 3.0
    ):
        violations.append("BUDGET_NOT_EXACTLY_FROZEN")
    if request.timeout_seconds != manifest.timeout_seconds:
        violations.append("TIMEOUT_MISMATCH")
    bundle = evidence_bundle_root.absolute()
    for root, label in (
        (request.journal_root, "JOURNAL"),
        (request.evidence_root, "EVIDENCE"),
    ):
        lexical = root.absolute()
        if lexical == bundle or bundle in lexical.parents:
            violations.append(f"{label}_ROOT_BUNDLE_CONTROLLED")
        if any(part.is_symlink() for part in (lexical, *lexical.parents)):
            violations.append(f"{label}_ROOT_SYMLINK")
    if config.immutable_artifact_root.absolute() != request.evidence_root.absolute():
        violations.append("EVIDENCE_ROOT_NOT_OPERATOR_BOUND")
    if request.journal_root.exists():
        violations.append("JOURNAL_ROOT_PREEXISTS")
    if request.evidence_root.exists():
        violations.append("EVIDENCE_ROOT_PREEXISTS")
    try:
        launch_now, workspace_now = current_state()
        if launch_now != spec.launch_identity_sha256:
            violations.append("LIVE_LAUNCH_IDENTITY_MISMATCH")
        if workspace_now != spec.workspace_baseline_sha256:
            violations.append("LIVE_WORKSPACE_MISMATCH")
    except Exception as error:
        violations.append(f"LIVE_STATE_UNAVAILABLE:{error}")
    if len(request.qualification_evidence_digest) != 64 or any(
        c not in "0123456789abcdef" for c in request.qualification_evidence_digest
    ):
        violations.append("QUALIFICATION_EVIDENCE_DIGEST_INVALID")
    return tuple(violations)


def _revalidate(
    request: ProductionDispatchRequestV1,
    clock: Callable[[], int],
    current_state: Callable[[], tuple[str, str]],
) -> tuple[str, ...]:
    violations: list[str] = []
    if request.spec.spec_hash != canonical_sha256(
        {
            "schema_version": 1,
            "manifest_hash": request.spec.manifest_hash,
            "cell_id": request.spec.cell_id,
            "model": request.spec.model,
            "prompt_sha256": request.spec.prompt_sha256,
            "launch_identity_sha256": request.spec.launch_identity_sha256,
            "workspace_baseline_sha256": request.spec.workspace_baseline_sha256,
            "budget_ceiling_usd": request.spec.budget_ceiling_usd,
            "token_limit": request.spec.token_limit,
            "request_limit": request.spec.request_limit,
            "nonce": request.spec.nonce,
            "expires_at_unix": request.spec.expires_at_unix,
        }
    ):
        violations.append("SPEC_HASH_CHANGED")
    try:
        if request.spec.expires_at_unix <= clock():
            violations.append("RUN_SPEC_EXPIRED")
        launch, workspace = current_state()
        if launch != request.spec.launch_identity_sha256:
            violations.append("LIVE_LAUNCH_IDENTITY_MISMATCH")
        if workspace != request.spec.workspace_baseline_sha256:
            violations.append("LIVE_WORKSPACE_MISMATCH")
    except Exception as error:
        violations.append(f"LIVE_REVALIDATION_UNAVAILABLE:{error}")
    return tuple(violations)


def _usage_violations(
    result: ProviderRunResult,
    spec: ProductionRunSpecV1,
    config: OperatorTrustConfigV1,
) -> tuple[str, ...]:
    values = (result.input_tokens, result.output_tokens, result.cost_usd)
    if result.usage_complete is not True or any(
        v is None
        or isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(float(v))
        or v < 0
        for v in values
    ):
        return ("USAGE_MISSING_OR_INVALID",)
    violations: list[str] = []
    if (
        config.budget_enforcement_mode == "provider"
        and not result.provider_reservation_id
    ):
        violations.append("PROVIDER_RESERVATION_MISSING")
    if config.budget_enforcement_mode == "client-process-kill":
        if result.wait_completed is not True:
            violations.append("CLIENT_PROCESS_WAIT_INCOMPLETE")
        if "timeout" in result.termination_reason and result.kill_attempted is not True:
            violations.append("TIMEOUT_KILL_NOT_CONFIRMED")
    if result.provider_request_count != 1:
        violations.append("PROVIDER_REQUEST_COUNT_NOT_ONE")
    assert (
        result.input_tokens is not None
        and result.output_tokens is not None
        and result.cost_usd is not None
    )
    if result.input_tokens + result.output_tokens > spec.token_limit:
        violations.append("TOKEN_LIMIT_EXCEEDED")
    if result.cost_usd > spec.budget_ceiling_usd:
        violations.append("BUDGET_EXCEEDED")
    return tuple(violations)


def dispatch_once(
    request: object,
    config: OperatorTrustConfigV1,
    attestation: object,
    judge_record: object,
    *,
    evidence_bundle_root: Path,
    runner: Callable[[ProductionDispatchRequestV1], ProviderRunResult],
    clock: Callable[[], int],
    current_state: Callable[[], tuple[str, str]],
) -> ProductionDispatchReceiptV1:
    """Atomically consume one qualified frozen cell and call the injected runner once."""
    violations = _validate_envelope(
        request, config, evidence_bundle_root, current_state
    )
    if violations:
        return ProductionDispatchReceiptV1(
            "NOT_EVALUATED",
            violations,
            None,
            False,
            False,
            0,
            None,
            None,
            None,
            None,
            "not-started",
            None,
        )
    assert type(request) is ProductionDispatchRequestV1
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
        return ProductionDispatchReceiptV1(
            "NOT_EVALUATED",
            qualification.violations,
            request.envelope_hash,
            False,
            False,
            0,
            None,
            None,
            None,
            None,
            "not-started",
            None,
        )
    try:
        _reserve(request)
    except (FileExistsError, OSError) as error:
        return ProductionDispatchReceiptV1(
            "NOT_EVALUATED",
            (f"RESERVATION_REFUSED:{error}",),
            request.envelope_hash,
            False,
            False,
            0,
            None,
            None,
            None,
            None,
            "not-started",
            None,
        )
    callbacks = 0
    result: ProviderRunResult | None = None
    evidence_digest = None
    status = "INVALID"
    terminal = False
    run_violations: list[str] = []
    collector: EvidenceCollector | None = None
    try:
        # Durable reservation is followed by a second trust check and live revalidation.
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
        if run_violations:
            collector.collect(
                request.spec.cell_id,
                "admission-error",
                json.dumps(run_violations).encode(),
            )
        else:
            callbacks = 1
            try:
                result = runner(request)
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
                    b'{"reason":"provider-exception","usage":"unknown"}',
                )
                run_violations.append("PROVIDER_RESULT_UNAVAILABLE")
            else:
                collector.collect(request.spec.cell_id, "transcript", result.transcript)
                collector.collect(
                    request.spec.cell_id, "tool-receipt", result.tool_receipt
                )
                collector.collect(
                    request.spec.cell_id,
                    "termination",
                    json.dumps(
                        {
                            "reason": result.termination_reason,
                            "kill_attempted": result.kill_attempted,
                            "wait_completed": result.wait_completed,
                            "provider_reservation_id": result.provider_reservation_id,
                        }
                    ).encode(),
                )
                usage_violations = _usage_violations(result, request.spec, config)
                run_violations.extend(usage_violations)
                usage = {
                    "provider_requests": result.provider_request_count,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cost_usd": result.cost_usd,
                    "status": "INVALID" if usage_violations else "VALID",
                }
                if usage_violations:
                    for field in ("input_tokens", "output_tokens", "cost_usd"):
                        value = usage[field]
                        if isinstance(value, float) and not math.isfinite(value):
                            usage[field] = None
                collector.collect(
                    request.spec.cell_id,
                    "usage",
                    json.dumps(usage, allow_nan=False).encode(),
                )
        collection = collector.finalize()
        evidence_digest = collection.ledger_sha256
        status = "PASS" if not run_violations else "INVALID"
    except Exception as error:
        run_violations.append(
            f"EVIDENCE_FINALIZATION_FAILED:{type(error).__name__}:{error}"
        )
    finally:
        payload = {
            "event": "TERMINAL",
            "status": status,
            "violations": run_violations,
            "evidence_digest": evidence_digest,
        }
        try:
            _terminal(request, payload)
            terminal = True
        except Exception as error:
            run_violations.append(
                f"TERMINAL_WRITE_FAILED:{type(error).__name__}:{error}"
            )
            status = "INVALID"
    return ProductionDispatchReceiptV1(
        status,
        tuple(run_violations),
        request.envelope_hash,
        True,
        terminal,
        callbacks,
        None if result is None else result.provider_request_count,
        None if result is None else result.input_tokens,
        None if result is None else result.output_tokens,
        None if result is None else result.cost_usd,
        "unknown" if result is None else result.termination_reason,
        evidence_digest,
    )
