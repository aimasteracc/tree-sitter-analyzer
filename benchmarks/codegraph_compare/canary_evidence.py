"""Frozen, model-free evidence contract for the NO1-002C E0 canary."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from typing import Any

from benchmarks.codegraph_compare._canary_evidence_replay import artifacts_are_bound

SCHEMA_VERSION = 1
PROTOCOL = "NO1-002C"
EXPECTED_CELLS = (
    ("tsa-warm-canary", "tsa-warm", 0),
    ("codegraph-warm-canary", "codegraph-warm", 1),
)
EXPECTED_ORACLE = ("gin.go", "Engine.ServeHTTP", "method")
ARTIFACT_KINDS = ("receipt", "transcript", "workspace_audit", "runtime")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize evidence deterministically, rejecting non-JSON values."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("value is not canonical JSON") from error
    return encoded.encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _nonempty(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True)
class CanaryCellV1:
    cell_id: str
    arm: str
    attempt_count: int
    schedule_order: int
    phase: str
    native_allowed: bool


@dataclass(frozen=True)
class CanaryManifestV1:
    schema_version: int
    protocol: str
    manifest_hash: str
    experiment_id: str
    benchmark_git_sha: str
    benchmark_version: str
    model: str
    agent_cli_fingerprint: str
    gin_commit: str
    gin_source_fingerprint: str
    canary_prompt_sha256: str
    oracle: tuple[str, str, str]
    oracle_hash: str
    launch_config_hashes: tuple[tuple[str, str], ...]
    timeout_seconds: int
    seed: int
    budget_ceiling_usd: float
    cells: tuple[CanaryCellV1, ...]
    winner: None
    dominance_allowed: bool
    publishable: bool


@dataclass(frozen=True)
class CanaryAttemptV1:
    schema_version: int
    manifest_hash: str
    session_id: str
    run_id: str
    cell_id: str
    arm: str
    attempt_no: int
    receipt_call_id: str
    transcript_sha256: str
    workspace_audit_sha256: str
    runtime_hash: str
    status: str


@dataclass(frozen=True)
class CanaryArtifactV1:
    schema_version: int
    manifest_hash: str
    session_id: str
    run_id: str
    cell_id: str
    arm: str
    kind: str
    sha256: str
    evidence_path: str
    receipt_call_id: str | None = None


@dataclass(frozen=True)
class CanaryRegistryEventV1:
    schema_version: int
    manifest_hash: str
    session_id: str
    status: str
    outcome: str
    completed_run_ids: tuple[str, ...]


@dataclass(frozen=True)
class CanaryEvidenceVerdict:
    status: str
    violations: tuple[str, ...]
    accepted_cells: int
    required_cells: int
    winner: None
    dominance_allowed: bool
    publishable: bool


def _manifest_payload(manifest: CanaryManifestV1) -> dict[str, Any]:
    payload = asdict(manifest)
    payload.pop("manifest_hash")
    payload.pop("experiment_id")
    return payload


def _canary_cells() -> tuple[CanaryCellV1, ...]:
    return tuple(
        CanaryCellV1(cell_id, arm, 1, order, "E0", False)
        for cell_id, arm, order in EXPECTED_CELLS
    )


def _validate_manifest_scalars(
    values: tuple[tuple[str, object], ...],
    gin_source_fingerprint: object,
    canary_prompt_sha256: object,
    timeout_seconds: object,
    seed: object,
) -> None:
    for label, value in values:
        _nonempty(value, label)
    _digest(gin_source_fingerprint, "gin_source_fingerprint")
    _digest(canary_prompt_sha256, "canary_prompt_sha256")
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a positive integer")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")


def _launches(launch_config_hashes: dict[str, str]) -> tuple[tuple[str, str], ...]:
    if type(launch_config_hashes) is not dict:
        raise ValueError("launch_config_hashes must be an object")
    if set(launch_config_hashes) != {arm for _, arm, _ in EXPECTED_CELLS}:
        raise ValueError("launch_config_hashes must bind exactly both indexed arms")
    return tuple(
        (arm, _digest(launch_config_hashes[arm], f"launch_config_hashes.{arm}"))
        for _, arm, _ in EXPECTED_CELLS
    )


def create_canary_manifest(
    *,
    benchmark_git_sha: str,
    benchmark_version: str,
    model: str,
    agent_cli_fingerprint: str,
    gin_commit: str,
    gin_source_fingerprint: str,
    canary_prompt_sha256: str,
    launch_config_hashes: dict[str, str],
    timeout_seconds: int,
    seed: int,
    budget_ceiling_usd: float = 3.0,
) -> CanaryManifestV1:
    """Freeze the only admissible two-cell E0 schedule and claim posture."""

    _validate_manifest_scalars(
        (
            ("benchmark_git_sha", benchmark_git_sha),
            ("benchmark_version", benchmark_version),
            ("model", model),
            ("agent_cli_fingerprint", agent_cli_fingerprint),
            ("gin_commit", gin_commit),
        ),
        gin_source_fingerprint,
        canary_prompt_sha256,
        timeout_seconds,
        seed,
    )
    if type(budget_ceiling_usd) not in (int, float) or budget_ceiling_usd != 3.0:
        raise ValueError("budget_ceiling_usd must be exactly 3 USD")
    oracle_hash = canonical_sha256(list(EXPECTED_ORACLE))
    provisional = CanaryManifestV1(
        SCHEMA_VERSION,
        PROTOCOL,
        "",
        "",
        benchmark_git_sha,
        benchmark_version,
        model,
        agent_cli_fingerprint,
        gin_commit,
        gin_source_fingerprint,
        canary_prompt_sha256,
        EXPECTED_ORACLE,
        oracle_hash,
        _launches(launch_config_hashes),
        timeout_seconds,
        seed,
        3.0,
        _canary_cells(),
        None,
        False,
        False,
    )
    digest = canonical_sha256(_manifest_payload(provisional))
    return replace(provisional, manifest_hash=digest, experiment_id=f"sha256:{digest}")


def validate_canary_manifest(manifest: CanaryManifestV1) -> None:
    """Reject any mutation of the frozen protocol, schedule, or claim flags."""

    if type(manifest) is not CanaryManifestV1:
        raise ValueError("manifest must be CanaryManifestV1")
    if (
        type(manifest.schema_version) is not int
        or manifest.schema_version != SCHEMA_VERSION
    ):
        raise ValueError("unsupported canary manifest schema")
    if type(manifest.protocol) is not str or manifest.protocol != PROTOCOL:
        raise ValueError("unsupported canary manifest schema")
    _validate_manifest_scalars(
        (
            ("benchmark_git_sha", manifest.benchmark_git_sha),
            ("benchmark_version", manifest.benchmark_version),
            ("model", manifest.model),
            ("agent_cli_fingerprint", manifest.agent_cli_fingerprint),
            ("gin_commit", manifest.gin_commit),
        ),
        manifest.gin_source_fingerprint,
        manifest.canary_prompt_sha256,
        manifest.timeout_seconds,
        manifest.seed,
    )
    if manifest.oracle != EXPECTED_ORACLE:
        raise ValueError("oracle tuple is not the frozen canary oracle")
    if manifest.oracle_hash != canonical_sha256(list(manifest.oracle)):
        raise ValueError("oracle hash mismatch")
    if manifest.cells != _canary_cells():
        raise ValueError(
            "canary schedule must be exact, seeded, E0-only, and non-native"
        )
    if any(
        type(cell.attempt_count) is not int
        or type(cell.schedule_order) is not int
        or type(cell.native_allowed) is not bool
        for cell in manifest.cells
    ):
        raise ValueError("canary cell field types are invalid")
    if type(manifest.launch_config_hashes) is not tuple:
        raise ValueError("launch_config_hashes must be a tuple")
    if tuple(arm for arm, _ in manifest.launch_config_hashes) != tuple(
        arm for _, arm, _ in EXPECTED_CELLS
    ):
        raise ValueError("launch config arm order mismatch")
    for arm, digest in manifest.launch_config_hashes:
        _digest(digest, f"launch_config_hashes.{arm}")
    if (
        type(manifest.budget_ceiling_usd) is not float
        or manifest.budget_ceiling_usd != 3.0
    ):
        raise ValueError("budget ceiling mismatch")
    if (
        manifest.winner is not None
        or type(manifest.dominance_allowed) is not bool
        or manifest.dominance_allowed
        or type(manifest.publishable) is not bool
        or manifest.publishable
    ):
        raise ValueError("protected claim flags must remain false/null")
    expected_hash = canonical_sha256(_manifest_payload(manifest))
    if manifest.manifest_hash != expected_hash:
        raise ValueError("manifest hash mismatch")
    if manifest.experiment_id != f"sha256:{expected_hash}":
        raise ValueError("experiment id mismatch")


def _identity(record: CanaryAttemptV1 | CanaryArtifactV1) -> tuple[str, str, str]:
    return record.run_id, record.cell_id, record.arm


def _group_attempts(
    attempts: tuple[object, ...], violations: list[str]
) -> dict[tuple[str, str], list[CanaryAttemptV1]]:
    grouped = {(cell_id, arm): [] for cell_id, arm, _ in EXPECTED_CELLS}
    for attempt in attempts:
        if type(attempt) is not CanaryAttemptV1:
            violations.append("ATTEMPT_SCHEMA_INVALID")
        elif (attempt.cell_id, attempt.arm) not in grouped:
            violations.append("ATTEMPT_EXTRA_OR_CROSS_ARM")
        else:
            grouped[(attempt.cell_id, attempt.arm)].append(attempt)
    return grouped


def _attempt_hashes(
    attempt: CanaryAttemptV1, cell_id: str, violations: list[str]
) -> dict[str, str]:
    hashes = {
        "transcript": attempt.transcript_sha256,
        "workspace_audit": attempt.workspace_audit_sha256,
        "runtime": attempt.runtime_hash,
    }
    for label, digest in hashes.items():
        try:
            _digest(digest, f"{cell_id}.{label}")
        except ValueError:
            violations.append(f"ATTEMPT_HASH:{cell_id}:{label}")
    return hashes


def _attempt_is_bound(attempt: CanaryAttemptV1, manifest_hash: str) -> bool:
    return (
        type(attempt.schema_version) is int
        and attempt.schema_version == SCHEMA_VERSION
        and attempt.manifest_hash == manifest_hash
        and type(attempt.run_id) is str
        and bool(attempt.run_id)
        and type(attempt.attempt_no) is int
        and attempt.attempt_no == 1
        and attempt.status == "SUCCESS"
        and type(attempt.session_id) is str
        and bool(attempt.session_id)
        and type(attempt.receipt_call_id) is str
        and bool(attempt.receipt_call_id)
    )


def _validate_cell(
    cell_id: str,
    arm: str,
    manifest_hash: str,
    grouped: dict[tuple[str, str], list[CanaryAttemptV1]],
    artifacts: tuple[CanaryArtifactV1, ...],
    violations: list[str],
) -> bool:
    matches = grouped[(cell_id, arm)]
    if len(matches) != 1:
        violations.append(f"ATTEMPT_BIJECTION:{cell_id}")
        return False
    attempt = matches[0]
    if not _attempt_is_bound(attempt, manifest_hash):
        violations.append(f"ATTEMPT_BINDING:{cell_id}")
        return False
    expected_hashes = _attempt_hashes(attempt, cell_id, violations)
    related = tuple(item for item in artifacts if _identity(item) == _identity(attempt))
    if len(related) != 4 or {item.kind for item in related} != set(ARTIFACT_KINDS):
        violations.append(f"ARTIFACT_BIJECTION:{cell_id}")
        return False
    if not artifacts_are_bound(attempt, related, expected_hashes):
        violations.append(f"ARTIFACT_BINDING:{cell_id}")
        return False
    return True


def _registry_is_terminal(
    registry: tuple[object, ...],
    manifest_hash: str,
    attempts: tuple[object, ...],
    grouped: dict[tuple[str, str], list[CanaryAttemptV1]],
) -> bool:
    if len(registry) != 1 or type(registry[0]) is not CanaryRegistryEventV1:
        return False
    sessions = {item.session_id for item in attempts if type(item) is CanaryAttemptV1}
    if any(len(grouped[(cell_id, arm)]) != 1 for cell_id, arm, _ in EXPECTED_CELLS):
        return False
    run_ids = tuple(
        grouped[(cell_id, arm)][0].run_id for cell_id, arm, _ in EXPECTED_CELLS
    )
    event = registry[0]
    return (
        type(event.schema_version) is int
        and event.schema_version == SCHEMA_VERSION
        and event.manifest_hash == manifest_hash
        and event.session_id in sessions
        and event.status == "COMPLETE"
        and event.outcome == "canary_accepted"
        and event.completed_run_ids == run_ids
        and len(run_ids) == len(set(run_ids))
        and len(sessions) == 1
    )


def validate_canary_evidence(
    manifest: CanaryManifestV1,
    attempts: Iterable[CanaryAttemptV1],
    artifacts: Iterable[CanaryArtifactV1],
    registry: Iterable[CanaryRegistryEventV1],
) -> CanaryEvidenceVerdict:
    """Require a 2/2 bijection across terminal attempts and all four artifacts."""

    violations: list[str] = []
    try:
        validate_canary_manifest(manifest)
    except (AttributeError, TypeError, ValueError) as error:
        violations.append(f"MANIFEST_INVALID:{error}")
    if type(manifest) is not CanaryManifestV1:
        return CanaryEvidenceVerdict(
            "INVALID", tuple(violations), 0, 2, None, False, False
        )
    attempt_items = tuple(attempts)
    artifact_items = tuple(artifacts)
    registry_items = tuple(registry)
    if not attempt_items and not artifact_items and not registry_items:
        return CanaryEvidenceVerdict(
            "INVALID" if violations else "NOT_EVALUATED",
            tuple(violations),
            0,
            2,
            None,
            False,
            False,
        )
    valid_artifacts = tuple(
        item for item in artifact_items if type(item) is CanaryArtifactV1
    )
    if len(valid_artifacts) != len(artifact_items):
        violations.append("ARTIFACT_SCHEMA_INVALID")
    grouped = _group_attempts(attempt_items, violations)
    accepted = sum(
        _validate_cell(
            cell_id,
            arm,
            manifest.manifest_hash,
            grouped,
            valid_artifacts,
            violations,
        )
        for cell_id, arm, _ in EXPECTED_CELLS
    )
    expected = {(cell_id, arm) for cell_id, arm, _ in EXPECTED_CELLS}
    if any((item.cell_id, item.arm) not in expected for item in valid_artifacts):
        violations.append("ARTIFACT_EXTRA_OR_CROSS_ARM")
    if not _registry_is_terminal(
        registry_items, manifest.manifest_hash, attempt_items, grouped
    ):
        violations.append("REGISTRY_TERMINAL_INVALID")
    status = "INVALID"
    if not violations and accepted == 2:
        status = "NOT_EVALUATED"
        violations.append("PRODUCTION_TRUST_ANCHOR_UNAVAILABLE")
    return CanaryEvidenceVerdict(
        status, tuple(violations), accepted, 2, None, False, False
    )
