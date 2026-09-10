"""One-shot, model-free orchestration for the NO1-002C canary."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare._canary_evidence_replay import (
    read_if_file,
    workspace_envelope,
)
from benchmarks.codegraph_compare.canary_evidence import (
    ARTIFACT_KINDS,
    SCHEMA_VERSION,
    CanaryArtifactV1,
    CanaryAttemptV1,
    CanaryManifestV1,
    CanaryRegistryEventV1,
    canonical_json_bytes,
    canonical_sha256,
    validate_canary_evidence,
    validate_canary_manifest,
)
from benchmarks.codegraph_compare.canary_policy import CanaryAudit
from benchmarks.codegraph_compare.canary_workspace import (
    audit_canary_checkout,
    cleanup_and_verify_canary_checkout,
    snapshot_canary_checkout,
)

_ORACLE_PATH = "gin.go"
_ORACLE_SYMBOL = "Engine.ServeHTTP"
_ORACLE_KIND = "method"
_TOOLS = {"tsa-warm": "nav", "codegraph-warm": "codegraph_search"}
_ZERO_HASH = "0" * 64


def _fsync_directory(path: Path) -> None:
    """Flush a directory entry where the platform exposes directory handles."""

    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class CanaryRunResult:
    transcript_path: Path
    cost_usd: float
    reported_index_queries: int


class CanaryRunFailure(Exception):
    """A failed model call carrying evidence already produced by that call."""

    def __init__(self, message: str, result: CanaryRunResult) -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class CanaryProtocolCallbacks:
    validate_launch: Callable[
        [Mapping[str, Mapping[str, Any]], Mapping[str, Path]], None
    ]
    snapshot: Callable[[Path, str], Any] | None
    setup_index: Callable[[str, Path], None]
    run_cell: Callable[
        [Any, Path, str, str, Mapping[str, Any], float, float], CanaryRunResult
    ]
    audit_policy: Callable[..., CanaryAudit]
    audit_workspace: Callable[[Any], Any] | None
    cleanup_workspace: Callable[[Any, Any], None] | None
    runtime_hash: Callable[[str, Path, Any], str]
    new_id: Callable[[str], str]


@dataclass(frozen=True)
class CanaryProtocolResult:
    attempts: tuple[CanaryAttemptV1, ...]
    artifacts: tuple[CanaryArtifactV1, ...]
    registry: tuple[CanaryRegistryEventV1, ...]
    status: str
    violations: tuple[str, ...]
    cumulative_cost_usd: float


def _transcript_hash(path: Path) -> str:
    if not path.is_file():
        raise ValueError("transcript is missing")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_cost(result: CanaryRunResult, cumulative_cost: float) -> float:
    cost = result.cost_usd
    if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
        raise ValueError("reported cost must be a finite non-negative number")
    return cumulative_cost + float(cost)


def _canonical_object_hash(value: Any) -> str:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    return canonical_sha256(_json_value(value))


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


class CanaryProtocol:
    def __init__(
        self,
        manifest: CanaryManifestV1,
        launch_contracts: Mapping[str, Mapping[str, Any]],
        checkouts: Mapping[str, Path],
        callbacks: CanaryProtocolCallbacks,
        journal_path: Path,
        fixture_cost_plan_usd: Mapping[str, float],
        execution_mode: str = "production",
    ) -> None:
        self._manifest = manifest
        self._launch_contracts = launch_contracts
        self._checkouts = checkouts
        self._callbacks = callbacks
        self._journal_path = journal_path
        self._fixture_cost_plan_usd = fixture_cost_plan_usd
        self._execution_mode = execution_mode
        self._started = False

    def _snapshot_workspace(self, checkout: Path, arm: str) -> Any:
        callback = self._callbacks.snapshot or snapshot_canary_checkout
        return callback(checkout, arm)

    def _audit_workspace(self, snapshot: Any) -> Any:
        callback = self._callbacks.audit_workspace or audit_canary_checkout
        return callback(snapshot)

    def _cleanup_workspace(self, snapshot: Any, audit: Any) -> None:
        callback = (
            self._callbacks.cleanup_workspace or cleanup_and_verify_canary_checkout
        )
        callback(snapshot, audit)

    def _reserve(self, session_id: str) -> None:
        """Persist a one-shot fixture reservation before simulation starts."""

        self._journal_path.parent.mkdir(parents=True, exist_ok=True)
        journal = self._journal_path.resolve(strict=False)
        for checkout in self._checkouts.values():
            checkout_root = checkout.resolve(strict=False)
            if journal == checkout_root or checkout_root in journal.parents:
                raise ValueError("canary journal must be outside every checkout")
        payload = canonical_sha256(
            {
                "manifest_hash": self._manifest.manifest_hash,
                "session_id": session_id,
                "fixture_cost_plan_usd": dict(
                    sorted(self._fixture_cost_plan_usd.items())
                ),
            }
        )
        record = {
            "schema_version": 1,
            "state": "RESERVED",
            "manifest_hash": self._manifest.manifest_hash,
            "session_id": session_id,
            "fixture_cost_plan_usd": dict(sorted(self._fixture_cost_plan_usd.items())),
            "reservation_hash": payload,
        }
        try:
            descriptor = os.open(
                self._journal_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError as error:
            raise RuntimeError(
                "canary fixture reservation already exists; retry is forbidden"
            ) from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(self._journal_path.parent)

    def _terminalize(self, result: CanaryProtocolResult) -> CanaryProtocolResult:
        """Atomically replace the reservation with durable terminal evidence."""

        record = {
            "schema_version": 1,
            "state": "TERMINAL",
            "manifest_hash": self._manifest.manifest_hash,
            "status": result.status,
            "result": _json_value(asdict(result)),
        }
        temporary = self._journal_path.with_name(self._journal_path.name + ".terminal")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self._journal_path)
        _fsync_directory(self._journal_path.parent)
        return result

    def _persist_artifact(
        self, run_id: str, kind: str, payload: bytes
    ) -> tuple[str, str]:
        root = self._journal_path.with_name(self._journal_path.name + ".artifacts")
        root.mkdir(mode=0o700, exist_ok=True)
        target = (root / f"{run_id}.{kind}").resolve(strict=False)
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return hashlib.sha256(payload).hexdigest(), str(target)

    def execute(self) -> CanaryProtocolResult:
        if self._started:
            raise RuntimeError("canary protocol is one-shot; retry is forbidden")
        self._started = True
        if self._execution_mode != "fixture":
            return CanaryProtocolResult(
                (),
                (),
                (),
                "NOT_EVALUATED",
                ("QUALIFICATION_SCAFFOLD_NOT_PRODUCTION_READY",),
                0.0,
            )
        attempts: list[CanaryAttemptV1] = []
        artifacts: list[CanaryArtifactV1] = []
        violations: list[str] = []
        completed: list[str] = []
        cumulative_cost = 0.0
        session_id = self._callbacks.new_id("session")
        seen_ids = {session_id}

        try:
            validate_canary_manifest(self._manifest)
            if not session_id:
                raise ValueError("session id must be fresh and non-empty")
            expected_arms = {cell.arm for cell in self._manifest.cells}
            if set(self._checkouts) != expected_arms:
                raise ValueError("checkout arm set does not match frozen schedule")
            if set(self._launch_contracts) != expected_arms:
                raise ValueError("launch arm set does not match frozen schedule")
            self._callbacks.validate_launch(self._launch_contracts, self._checkouts)
            expected_cells = {cell.cell_id for cell in self._manifest.cells}
            if set(self._fixture_cost_plan_usd) != expected_cells:
                raise ValueError("fixture cost plan must bind every canary cell")
            reservations = tuple(
                self._fixture_cost_plan_usd[cell.cell_id]
                for cell in self._manifest.cells
            )
            if any(
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value <= 0
                for value in reservations
            ):
                raise ValueError("fixture cost plans must be finite and positive")
            if sum(reservations) > self._manifest.budget_ceiling_usd:
                raise ValueError("fixture cost plan exceeds declared simulation budget")
        except Exception as error:
            violations.append(f"PREFLIGHT_INVALID:{error}")
            return self._finish(
                session_id, attempts, artifacts, completed, violations, cumulative_cost
            )

        self._reserve(session_id)

        for cell in self._manifest.cells:
            run_id = self._callbacks.new_id(f"run:{cell.cell_id}")
            if not run_id or run_id in seen_ids:
                violations.append(f"RUN_ID_NOT_FRESH:{cell.cell_id}")
                break
            seen_ids.add(run_id)
            snapshot = None
            audit = None
            run_result = None
            policy = None
            transcript_hash = _ZERO_HASH
            workspace_hash = _ZERO_HASH
            runtime_hash = _ZERO_HASH
            receipt_id = ""
            failures: list[str] = []
            setup_started = False
            checkout = self._checkouts[cell.arm]
            remaining_usd = self._manifest.budget_ceiling_usd - cumulative_cost
            fixture_cost_limit_usd = float(self._fixture_cost_plan_usd[cell.cell_id])
            if fixture_cost_limit_usd > remaining_usd:
                violations.append(
                    f"CELL_BUDGET_UNAVAILABLE:{cell.cell_id}:"
                    f"remaining={remaining_usd}:fixture_limit={fixture_cost_limit_usd}"
                )
                break
            try:
                snapshot = self._snapshot_workspace(checkout, cell.arm)
                setup_started = True
                self._callbacks.setup_index(cell.arm, checkout)
                run_result = self._callbacks.run_cell(
                    cell,
                    checkout,
                    session_id,
                    run_id,
                    self._launch_contracts[cell.arm],
                    remaining_usd,
                    fixture_cost_limit_usd,
                )
                cumulative_cost = _record_cost(run_result, cumulative_cost)
                if run_result.cost_usd > fixture_cost_limit_usd:
                    raise ValueError("fixture reported cost above its declared plan")
                transcript_hash = _transcript_hash(run_result.transcript_path)
                if cumulative_cost > self._manifest.budget_ceiling_usd:
                    raise ValueError(
                        "fixture reported cumulative cost above simulation budget"
                    )
                policy = self._callbacks.audit_policy(
                    run_result.transcript_path,
                    cell.arm,
                    expected_tool=_TOOLS[cell.arm],
                    expected_path=_ORACLE_PATH,
                    expected_symbol=_ORACLE_SYMBOL,
                    expected_kind=_ORACLE_KIND,
                )
                qualifying_receipts = int(policy.receipt is not None)
                receipt_id = policy.receipt.call_id if policy.receipt else ""
                if policy.violations:
                    raise ValueError("policy audit rejected transcript")
                if run_result.reported_index_queries != qualifying_receipts:
                    raise ValueError("qualifying receipt/query count mismatch")
            except CanaryRunFailure as error:
                failures.append(f"primary={error}")
                run_result = error.result
                try:
                    cumulative_cost = _record_cost(error.result, cumulative_cost)
                    if error.result.cost_usd > fixture_cost_limit_usd:
                        raise ValueError(
                            "fixture reported cost above its declared plan"
                        )
                    transcript_hash = _transcript_hash(error.result.transcript_path)
                    if cumulative_cost > self._manifest.budget_ceiling_usd:
                        raise ValueError(
                            "fixture reported cumulative cost above simulation budget"
                        )
                except Exception as evidence_error:
                    failures.append(f"failure_evidence={evidence_error}")
            except Exception as error:
                failures.append(f"primary={error}")
            finally:
                if setup_started:
                    try:
                        audit = self._audit_workspace(snapshot)
                        workspace_hash = _canonical_object_hash(audit)
                        runtime_hash = self._callbacks.runtime_hash(
                            cell.arm, checkout, audit
                        )
                        if len(runtime_hash) != 64 or any(
                            character not in "0123456789abcdef"
                            for character in runtime_hash
                        ):
                            raise ValueError(
                                "runtime callback returned invalid SHA-256"
                            )
                    except Exception as error:
                        failures.append(f"workspace={error}")
                    try:
                        self._cleanup_workspace(snapshot, audit)
                    except Exception as error:
                        failures.append(f"cleanup={error}")

            status = "SUCCESS" if not failures else "INVALID"
            attempt = CanaryAttemptV1(
                SCHEMA_VERSION,
                self._manifest.manifest_hash,
                session_id,
                run_id,
                cell.cell_id,
                cell.arm,
                1,
                receipt_id,
                transcript_hash,
                workspace_hash,
                runtime_hash,
                status,
            )
            attempts.append(attempt)
            digest_by_kind = {
                "receipt": canonical_json_bytes({"call_id": receipt_id})
                if receipt_id
                else None,
                "transcript": read_if_file(
                    run_result.transcript_path if run_result is not None else None
                ),
                "workspace_audit": canonical_json_bytes(
                    workspace_envelope(
                        self._manifest.manifest_hash,
                        session_id,
                        run_id,
                        cell,
                        workspace_hash,
                        _json_value(audit),
                    )
                )
                if workspace_hash != _ZERO_HASH
                else None,
                "runtime": runtime_hash.encode("ascii")
                if runtime_hash != _ZERO_HASH
                else None,
            }
            for kind in ARTIFACT_KINDS:
                payload = digest_by_kind[kind]
                if payload is not None:
                    digest, evidence_path = self._persist_artifact(
                        run_id, kind, payload
                    )
                    artifacts.append(
                        CanaryArtifactV1(
                            SCHEMA_VERSION,
                            self._manifest.manifest_hash,
                            session_id,
                            run_id,
                            cell.cell_id,
                            cell.arm,
                            kind,
                            digest,
                            evidence_path,
                            receipt_id if kind == "receipt" else None,
                        )
                    )
            if not failures:
                completed.append(run_id)
            else:
                violations.append(f"CELL_INVALID:{cell.cell_id}:{'|'.join(failures)}")
                break

        return self._terminalize(
            self._finish(
                session_id,
                attempts,
                artifacts,
                completed,
                violations,
                cumulative_cost,
            )
        )

    def _finish(
        self,
        session_id: str,
        attempts: list[CanaryAttemptV1],
        artifacts: list[CanaryArtifactV1],
        completed: list[str],
        violations: list[str],
        cumulative_cost: float,
    ) -> CanaryProtocolResult:
        simulated_complete = not violations and len(attempts) == len(
            self._manifest.cells
        )
        if simulated_complete:
            violations.append("FIXTURE_SIMULATION_NOT_QUALIFICATION")
        registry = (
            CanaryRegistryEventV1(
                SCHEMA_VERSION,
                self._manifest.manifest_hash,
                session_id,
                "INVALID",
                "fixture_not_evaluated" if simulated_complete else "canary_invalid",
                tuple(completed),
            ),
        )
        verdict = validate_canary_evidence(
            self._manifest, tuple(attempts), tuple(artifacts), registry
        )
        status = "NOT_EVALUATED" if simulated_complete else "INVALID"
        combined = tuple(dict.fromkeys((*violations, *verdict.violations)))
        return CanaryProtocolResult(
            tuple(attempts),
            tuple(artifacts),
            registry,
            status,
            combined,
            cumulative_cost,
        )
