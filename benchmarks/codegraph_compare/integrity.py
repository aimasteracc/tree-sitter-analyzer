"""Fail-closed experiment integrity primitives for RFC-0021 Slice A1."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.schemas import (
    EvalRecordV1,
    IndexStatsV1,
    RunRecordV1,
)


@dataclass(frozen=True)
class ExpectedCellV1:
    """Exact logical cell declared before an experiment starts."""

    repo: str
    question_id: str
    arm: str
    repeat: int
    agent_backend: str
    run_id: str

    def __post_init__(self) -> None:
        expected = (
            f"{self.question_id}__{self.arm}__{self.agent_backend}__{self.repeat:02d}"
        )
        if self.run_id != expected:
            raise ValueError(f"run_id must equal {expected}")
        if not all((self.repo, self.question_id, self.arm, self.agent_backend)):
            raise ValueError("Expected cell fields must be non-empty")
        if self.repeat < 0:
            raise ValueError("Expected cell repeat must be non-negative")


@dataclass(frozen=True)
class ExperimentManifestV1:
    """Immutable inputs that define one logical experiment."""

    benchmark_version: int
    experiment_id: str
    manifest_hash: str
    benchmark_git_sha: str
    config_hash: str
    question_hash: str
    oracle_hash: str
    seed: int
    timeout_seconds: int
    schedule_hash: str
    agent_backend: str
    model: str
    agent_cli_fingerprint: str
    platform: str
    environment_fingerprint: str
    primary_session_id: str
    retry_session_ids: tuple[str, ...]
    expected_cells: tuple[ExpectedCellV1, ...]
    required_arms: tuple[str, ...]
    indexed_arms: tuple[str, ...]
    tool_fingerprints: tuple[tuple[str, str], ...]
    repo_commits: tuple[tuple[str, str], ...]
    repo_fingerprints: tuple[tuple[str, str], ...]
    eligible_paths: tuple[tuple[str, tuple[str, ...]], ...]
    eligible_paths_hashes: tuple[tuple[str, str], ...]
    parse_error_allowlists: tuple[tuple[str, tuple[str, ...]], ...]
    required_readiness_oracles: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class RegistryEvent:
    """One append-only experiment lifecycle event."""

    experiment_id: str
    manifest_hash: str
    status: str
    outcome: str


@dataclass(frozen=True)
class IntegrityViolation:
    """Machine-readable reason an experiment cannot be published."""

    code: str
    identity: tuple[str, str, str, int] | None = None
    experiment_id: str | None = None
    arm: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class IntegrityVerdict:
    """Complete decision surface for the experiment integrity gate."""

    publishable: bool
    claim_level: str
    violations: tuple[IntegrityViolation, ...]
    canonical_attempts: tuple[RunRecordV1, ...]
    reliability_attempts: tuple[RunRecordV1, ...]
    disclosed_attempts: tuple[RunRecordV1, ...]
    expected_cell_count: int
    observed_cell_count: int
    dominance_allowed: bool
    winner: str | None
    disclosed_experiment_ids: tuple[str, ...]


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _manifest_payload(manifest: ExperimentManifestV1) -> dict[str, Any]:
    return {
        "benchmark_version": 1,
        "benchmark_git_sha": manifest.benchmark_git_sha,
        "config_hash": manifest.config_hash,
        "question_hash": manifest.question_hash,
        "oracle_hash": manifest.oracle_hash,
        "seed": manifest.seed,
        "timeout_seconds": manifest.timeout_seconds,
        "schedule_hash": manifest.schedule_hash,
        "agent_backend": manifest.agent_backend,
        "model": manifest.model,
        "agent_cli_fingerprint": manifest.agent_cli_fingerprint,
        "platform": manifest.platform,
        "environment_fingerprint": manifest.environment_fingerprint,
        "primary_session_id": manifest.primary_session_id,
        "retry_session_ids": list(manifest.retry_session_ids),
        "expected_cells": [asdict(cell) for cell in manifest.expected_cells],
        "required_arms": list(manifest.required_arms),
        "indexed_arms": list(manifest.indexed_arms),
        "tool_fingerprints": dict(manifest.tool_fingerprints),
        "repo_commits": dict(manifest.repo_commits),
        "repo_fingerprints": dict(manifest.repo_fingerprints),
        "eligible_paths": dict(manifest.eligible_paths),
        "eligible_paths_hashes": dict(manifest.eligible_paths_hashes),
        "parse_error_allowlists": dict(manifest.parse_error_allowlists),
        "required_readiness_oracles": dict(manifest.required_readiness_oracles),
    }


def create_manifest(
    *,
    benchmark_git_sha: str,
    config_hash: str,
    question_hash: str,
    oracle_hash: str,
    seed: int,
    timeout_seconds: int,
    schedule_hash: str,
    agent_backend: str,
    model: str,
    agent_cli_fingerprint: str,
    platform: str,
    environment_fingerprint: str,
    primary_session_id: str,
    retry_session_ids: tuple[str, ...],
    expected_cells: tuple[ExpectedCellV1, ...],
    required_arms: tuple[str, ...],
    indexed_arms: tuple[str, ...],
    tool_fingerprints: dict[str, str],
    repo_commits: dict[str, str],
    repo_fingerprints: dict[str, str],
    eligible_paths: dict[str, tuple[str, ...]],
    eligible_paths_hashes: dict[str, str],
    parse_error_allowlists: dict[str, tuple[str, ...]],
    required_readiness_oracles: dict[str, tuple[str, ...]],
) -> ExperimentManifestV1:
    """Create and validate a canonical experiment manifest."""
    strings = (
        benchmark_git_sha,
        config_hash,
        question_hash,
        oracle_hash,
        schedule_hash,
        agent_backend,
        model,
        agent_cli_fingerprint,
        platform,
        environment_fingerprint,
        primary_session_id,
    )
    if not all(strings):
        raise ValueError("Manifest identity and provenance fields must be non-empty")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if len(set(retry_session_ids)) != len(retry_session_ids):
        raise ValueError("retry_session_ids must be unique")
    if primary_session_id in retry_session_ids or any(
        not item for item in retry_session_ids
    ):
        raise ValueError("Primary and retry sessions must be unique and non-empty")
    run_ids = tuple(cell.run_id for cell in expected_cells)
    if not run_ids or len(set(run_ids)) != len(run_ids):
        raise ValueError("Expected cells must be non-empty and unique")
    arm_set = {cell.arm for cell in expected_cells}
    required_set = set(required_arms)
    if arm_set != required_set or len(required_set) != len(required_arms):
        raise ValueError("Required arms must exactly match expected cell arms")
    indexed_set = set(indexed_arms)
    if not indexed_set <= required_set or len(indexed_set) != len(indexed_arms):
        raise ValueError("Indexed arms must be a unique subset of required arms")
    if set(tool_fingerprints) != required_set or any(
        not value for value in tool_fingerprints.values()
    ):
        raise ValueError("Tool fingerprints must exactly cover required arms")
    repo_set = {cell.repo for cell in expected_cells}
    if set(repo_commits) != repo_set or any(
        not value for value in repo_commits.values()
    ):
        raise ValueError("Repo commits must exactly cover expected cell repos")
    for mapping in (repo_fingerprints, eligible_paths_hashes):
        if set(mapping) != repo_set or any(not value for value in mapping.values()):
            raise ValueError("Repo fingerprints must exactly cover expected cell repos")
    if set(eligible_paths) != repo_set or set(parse_error_allowlists) != repo_set:
        raise ValueError("Path policies must exactly cover expected cell repos")
    for repo, paths in eligible_paths.items():
        if (
            tuple(sorted(set(paths))) != paths
            or not paths
            or any(not path for path in paths)
        ):
            raise ValueError("Eligible paths must be sorted, unique, and non-empty")
        if eligible_paths_hashes[repo] != _sha256(list(paths)):
            raise ValueError("Eligible paths hash must match the exact path set")
        allowed_errors = parse_error_allowlists[repo]
        if tuple(sorted(set(allowed_errors))) != allowed_errors:
            raise ValueError("Parse-error allowlists must be sorted and unique")
        if not set(allowed_errors) <= set(paths):
            raise ValueError("Parse-error allowlists must be eligible paths")
    if set(required_readiness_oracles) != indexed_set or any(
        not value for value in required_readiness_oracles.values()
    ):
        raise ValueError("Readiness oracles must exactly cover indexed arms")
    if any(cell.agent_backend != agent_backend for cell in expected_cells):
        raise ValueError("Expected cell backend must match manifest backend")
    blocks: dict[tuple[str, str, int, str], set[str]] = {}
    for cell in expected_cells:
        block = (cell.repo, cell.question_id, cell.repeat, cell.agent_backend)
        blocks.setdefault(block, set()).add(cell.arm)
    if any(arms != required_set for arms in blocks.values()):
        raise ValueError("Every paired block must contain every required arm")

    provisional = ExperimentManifestV1(
        benchmark_version=1,
        experiment_id="",
        manifest_hash="",
        benchmark_git_sha=benchmark_git_sha,
        config_hash=config_hash,
        question_hash=question_hash,
        oracle_hash=oracle_hash,
        seed=seed,
        timeout_seconds=timeout_seconds,
        schedule_hash=schedule_hash,
        agent_backend=agent_backend,
        model=model,
        agent_cli_fingerprint=agent_cli_fingerprint,
        platform=platform,
        environment_fingerprint=environment_fingerprint,
        primary_session_id=primary_session_id,
        retry_session_ids=retry_session_ids,
        expected_cells=expected_cells,
        required_arms=required_arms,
        indexed_arms=indexed_arms,
        tool_fingerprints=tuple(sorted(tool_fingerprints.items())),
        repo_commits=tuple(sorted(repo_commits.items())),
        repo_fingerprints=tuple(sorted(repo_fingerprints.items())),
        eligible_paths=tuple(sorted(eligible_paths.items())),
        eligible_paths_hashes=tuple(sorted(eligible_paths_hashes.items())),
        parse_error_allowlists=tuple(sorted(parse_error_allowlists.items())),
        required_readiness_oracles=tuple(sorted(required_readiness_oracles.items())),
    )
    manifest_hash = _sha256(_manifest_payload(provisional))
    return ExperimentManifestV1(
        **{
            **asdict(provisional),
            "experiment_id": f"sha256:{manifest_hash}",
            "manifest_hash": manifest_hash,
            "expected_cells": expected_cells,
            "tool_fingerprints": provisional.tool_fingerprints,
            "repo_commits": provisional.repo_commits,
        }
    )


def parse_manifest_v1(raw: object) -> ExperimentManifestV1:
    """Decode a persisted JSON manifest and revalidate its nested structures."""
    if not isinstance(raw, dict):
        raise ValueError("Experiment manifest must be an object")
    version = raw.get("benchmark_version")
    if type(version) is not int or version != 1:
        raise ValueError(f"Unsupported benchmark_version: {version}")
    expected_keys = {field.name for field in fields(ExperimentManifestV1)}
    if set(raw) != expected_keys:
        raise ValueError("Manifest fields do not match the V1 schema")
    manifest = ExperimentManifestV1(
        benchmark_version=1,
        experiment_id=raw["experiment_id"],
        manifest_hash=raw["manifest_hash"],
        benchmark_git_sha=raw["benchmark_git_sha"],
        config_hash=raw["config_hash"],
        question_hash=raw["question_hash"],
        oracle_hash=raw["oracle_hash"],
        seed=raw["seed"],
        timeout_seconds=raw["timeout_seconds"],
        schedule_hash=raw["schedule_hash"],
        agent_backend=raw["agent_backend"],
        model=raw["model"],
        agent_cli_fingerprint=raw["agent_cli_fingerprint"],
        platform=raw["platform"],
        environment_fingerprint=raw["environment_fingerprint"],
        primary_session_id=raw["primary_session_id"],
        retry_session_ids=tuple(raw["retry_session_ids"]),
        expected_cells=tuple(ExpectedCellV1(**cell) for cell in raw["expected_cells"]),
        required_arms=tuple(raw["required_arms"]),
        indexed_arms=tuple(raw["indexed_arms"]),
        tool_fingerprints=tuple(tuple(item) for item in raw["tool_fingerprints"]),
        repo_commits=tuple(tuple(item) for item in raw["repo_commits"]),
        repo_fingerprints=tuple(tuple(item) for item in raw["repo_fingerprints"]),
        eligible_paths=tuple(
            (item[0], tuple(item[1])) for item in raw["eligible_paths"]
        ),
        eligible_paths_hashes=tuple(
            tuple(item) for item in raw["eligible_paths_hashes"]
        ),
        parse_error_allowlists=tuple(
            (item[0], tuple(item[1])) for item in raw["parse_error_allowlists"]
        ),
        required_readiness_oracles=tuple(
            (item[0], tuple(item[1])) for item in raw["required_readiness_oracles"]
        ),
    )
    normalized = create_manifest(
        benchmark_git_sha=manifest.benchmark_git_sha,
        config_hash=manifest.config_hash,
        question_hash=manifest.question_hash,
        oracle_hash=manifest.oracle_hash,
        seed=manifest.seed,
        timeout_seconds=manifest.timeout_seconds,
        schedule_hash=manifest.schedule_hash,
        agent_backend=manifest.agent_backend,
        model=manifest.model,
        agent_cli_fingerprint=manifest.agent_cli_fingerprint,
        platform=manifest.platform,
        environment_fingerprint=manifest.environment_fingerprint,
        primary_session_id=manifest.primary_session_id,
        retry_session_ids=manifest.retry_session_ids,
        expected_cells=manifest.expected_cells,
        required_arms=manifest.required_arms,
        indexed_arms=manifest.indexed_arms,
        tool_fingerprints=dict(manifest.tool_fingerprints),
        repo_commits=dict(manifest.repo_commits),
        repo_fingerprints=dict(manifest.repo_fingerprints),
        eligible_paths=dict(manifest.eligible_paths),
        eligible_paths_hashes=dict(manifest.eligible_paths_hashes),
        parse_error_allowlists=dict(manifest.parse_error_allowlists),
        required_readiness_oracles=dict(manifest.required_readiness_oracles),
    )
    if normalized != manifest:
        raise ValueError("Manifest hash or structure is invalid")
    return manifest


def index_partition_is_exact(
    stats: IndexStatsV1,
    manifest: ExperimentManifestV1,
    repo: str,
) -> bool:
    """Return whether index path sets exactly partition the manifest inputs."""

    eligible_paths = set(dict(manifest.eligible_paths)[repo])
    indexed_paths = set(stats.indexed_paths)
    excluded_paths = set(stats.excluded_paths)
    parse_error_paths = set(stats.parse_error_paths)
    path_sets = (indexed_paths, excluded_paths, parse_error_paths)
    partition_is_exact = (
        not (indexed_paths & excluded_paths)
        and not (indexed_paths & parse_error_paths)
        and not (excluded_paths & parse_error_paths)
        and set().union(*path_sets) == eligible_paths
    )
    hashes_match = (
        stats.indexed_paths_hash == _sha256(list(stats.indexed_paths))
        and stats.excluded_paths_hash == _sha256(list(stats.excluded_paths))
        and stats.parse_error_paths_hash == _sha256(list(stats.parse_error_paths))
    )
    counts_match = (
        stats.eligible_source_files == len(eligible_paths)
        and stats.indexed_source_files == len(indexed_paths)
        and stats.excluded_source_files == len(excluded_paths)
        and stats.parse_error_files == len(parse_error_paths)
    )
    allowed_errors = set(dict(manifest.parse_error_allowlists)[repo])
    return (
        partition_is_exact
        and hashes_match
        and counts_match
        and parse_error_paths == allowed_errors
    )


def validate_setup_index_stats(
    stats: object,
    manifest: ExperimentManifestV1,
    repo: str,
    arm: str,
) -> str | None:
    """Validate strict V1 index evidence before any model-backed work."""

    if arm not in manifest.indexed_arms:
        return "UNEXPECTED_INDEX_STATS" if stats is not None else None
    if not isinstance(stats, IndexStatsV1):
        return "INDEX_STATS_V1_REQUIRED"
    if (
        stats.repo_fingerprint != dict(manifest.repo_fingerprints).get(repo)
        or stats.tool_fingerprint != dict(manifest.tool_fingerprints).get(arm)
        or stats.eligible_paths_hash != dict(manifest.eligible_paths_hashes).get(repo)
    ):
        return "MIXED_INDEX_PROVENANCE"
    if stats.eligible_source_files <= 0 or stats.indexed_source_files <= 0:
        return "INDEX_PARTITION_MISMATCH"
    if not index_partition_is_exact(stats, manifest, repo):
        return "INDEX_PARTITION_MISMATCH"
    required_oracles = set(dict(manifest.required_readiness_oracles)[arm])
    if not required_oracles <= set(stats.readiness_oracles):
        return "READINESS_ORACLE_MISMATCH"
    return None


def append_registry_event(path: Path, event: RegistryEvent) -> None:
    """Atomically bind an experiment ID to one hash, then append its event."""
    if event.status not in {"PLANNED", "RUNNING", "BLOCKED", "COMPLETE", "INVALID"}:
        raise ValueError(f"Unsupported registry status: {event.status}")
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = path.parent / f"{event.experiment_id.replace(':', '_')}.manifest-hash"
    try:
        with owner.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(event.manifest_hash + "\n")
    except FileExistsError:
        bound_hash = owner.read_text(encoding="utf-8").strip()
        if bound_hash != event.manifest_hash:
            raise ValueError(
                f"Experiment {event.experiment_id} already has manifest hash {bound_hash}"
            ) from None
    encoded = _canonical_json_bytes(asdict(event)).decode("utf-8")
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded + "\n")


def validate_publishable_experiment(
    manifest: ExperimentManifestV1,
    *,
    registry: Iterable[RegistryEvent],
    runs: Iterable[RunRecordV1],
    evals: Iterable[EvalRecordV1],
    reported_experiment_ids: tuple[str, ...],
) -> IntegrityVerdict:
    """Validate one experiment through the focused fail-closed gate."""
    from benchmarks.codegraph_compare._integrity_gate import validate_experiment

    return validate_experiment(
        manifest,
        registry=registry,
        runs=runs,
        evals=evals,
        reported_experiment_ids=reported_experiment_ids,
    )
