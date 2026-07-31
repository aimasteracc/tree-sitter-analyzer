"""Immutable bundle, digest, and replay machinery for NO1-001B."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from benchmarks.codegraph_compare._integrity_gate import validate_experiment
from benchmarks.codegraph_compare.integrity import (
    RegistryEvent,
    parse_manifest_v1,
)
from benchmarks.codegraph_compare.schemas import RunRecordV1, parse_run_record
from benchmarks.codegraph_compare.smoke_policy import audit_codex_transcript
from benchmarks.codegraph_compare.smoke_preflight import validate_model_preflight

_PLAN_FILES = (
    "eligibility.json",
    "experiment-manifest.json",
    "index-evidence.json",
    "model-preflight.json",
    "workspace-evidence.json",
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _runs(path: Path) -> tuple[RunRecordV1, ...]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_run_record(json.loads(line))
        if not isinstance(parsed, RunRecordV1):
            raise ValueError("Smoke bundle contains a legacy run record")
        records.append(parsed)
    return tuple(records)


def _registry(path: Path, experiment_id: str) -> tuple[RegistryEvent, ...]:
    return tuple(
        RegistryEvent(**raw)
        for raw in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        )
        if raw["experiment_id"] == experiment_id
    )


def _copy_tree_files(source: Path, destination: Path) -> None:
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())


def _validate_policy_evidence(
    bundle_root: Path,
    runs: tuple[RunRecordV1, ...],
) -> None:
    evidence = bundle_root / "evidence"
    expected_policy_files = {
        f"policy_{run.run_id}.json" for run in runs
    }
    actual_policy_files = {
        path.name for path in evidence.glob("policy_*.json")
    }
    if actual_policy_files != expected_policy_files:
        raise ValueError("policy evidence inventory mismatch")
    for run in runs:
        stored = _json(evidence / f"policy_{run.run_id}.json")
        if stored.get("transcript_path") != run.transcript_path:
            raise ValueError(f"policy transcript binding mismatch: {run.run_id}")
        transcript = (
            bundle_root
            / "artifacts"
            / run.arm
            / "raw"
            / Path(run.transcript_path).name
        )
        recomputed = cast(
            dict[str, Any],
            json.loads(
                json.dumps(asdict(audit_codex_transcript(transcript, run.arm)))
            ),
        )
        recomputed["transcript_path"] = run.transcript_path
        if recomputed != stored:
            raise ValueError(f"policy audit mismatch: {run.run_id}")
        if recomputed["violations"] and run.status.value != "INVALID":
            raise ValueError(f"policy-invalid run has wrong status: {run.run_id}")


def create_smoke_bundle(
    destination: Path,
    *,
    plan_dir: Path,
    experiment_dir: Path,
    registry_path: Path,
) -> str:
    """Create one immutable complete bundle and return its external digest."""

    destination.mkdir(parents=True, exist_ok=False)
    plan_target = destination / "plan"
    plan_target.mkdir()
    for name in _PLAN_FILES:
        (plan_target / name).write_bytes((plan_dir / name).read_bytes())
    manifest = parse_manifest_v1(_json(plan_target / "experiment-manifest.json"))
    validate_model_preflight(
        plan_target / "model-preflight.json",
        expected_model=manifest.model,
        expected_cli_fingerprint=manifest.agent_cli_fingerprint,
    )
    evidence_target = destination / "evidence"
    _copy_tree_files(experiment_dir, evidence_target)
    artifact_target = destination / "artifacts"
    _copy_tree_files(plan_dir / "artifacts", artifact_target)

    events = _registry(registry_path, manifest.experiment_id)
    registry_target = destination / "registry.jsonl"
    registry_target.write_text(
        "".join(
            json.dumps(
                asdict(event),
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
            for event in events
        ),
        encoding="utf-8",
    )
    runs = _runs(evidence_target / "runs.jsonl")
    _validate_policy_evidence(destination, runs)
    verdict = validate_experiment(
        manifest,
        registry=events,
        runs=runs,
        evals=(),
        reported_experiment_ids=(manifest.experiment_id,),
    )
    verdict_payload = asdict(verdict)
    (destination / "verdict.json").write_text(
        json.dumps(
            verdict_payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    files = sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    )
    checksums = {
        relative: _sha256_bytes((destination / relative).read_bytes())
        for relative in files
    }
    checksums_path = destination / "checksums.json"
    checksums_path.write_text(
        json.dumps(
            {"schema_version": 1, "sha256": checksums},
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return _sha256_bytes(checksums_path.read_bytes())


def validate_smoke_bundle(bundle: Path, *, external_digest: str) -> dict[str, Any]:
    """Validate every byte and recompute the claim-bounded final verdict."""

    checksums_path = bundle / "checksums.json"
    if _sha256_bytes(checksums_path.read_bytes()) != external_digest:
        raise ValueError("external bundle digest mismatch")
    checksums = _json(checksums_path)
    if set(checksums) != {"schema_version", "sha256"}:
        raise ValueError("checksum schema mismatch")
    expected = checksums["sha256"]
    actual_files = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and path != checksums_path
    }
    if actual_files != set(expected):
        raise ValueError("bundle file inventory mismatch")
    for relative, digest in expected.items():
        if _sha256_bytes((bundle / relative).read_bytes()) != digest:
            raise ValueError(f"bundle checksum mismatch: {relative}")

    manifest = parse_manifest_v1(_json(bundle / "plan/experiment-manifest.json"))
    validate_model_preflight(
        bundle / "plan/model-preflight.json",
        expected_model=manifest.model,
        expected_cli_fingerprint=manifest.agent_cli_fingerprint,
    )
    events = _registry(bundle / "registry.jsonl", manifest.experiment_id)
    runs = _runs(bundle / "evidence/runs.jsonl")
    _validate_policy_evidence(bundle, runs)
    verdict = validate_experiment(
        manifest,
        registry=events,
        runs=runs,
        evals=(),
        reported_experiment_ids=(manifest.experiment_id,),
    )
    recomputed = cast(dict[str, Any], json.loads(json.dumps(asdict(verdict))))
    if recomputed != _json(bundle / "verdict.json"):
        raise ValueError("bundle verdict mismatch")
    if verdict.dominance_allowed or verdict.winner is not None:
        raise ValueError("Smoke bundle exceeds the E1 claim boundary")
    return recomputed


def replay_smoke_bundle(
    bundle: Path, destination: Path, *, external_digest: str
) -> dict[str, Any]:
    """Replay an immutable bundle byte-for-byte into a fresh destination."""

    verdict = validate_smoke_bundle(bundle, external_digest=external_digest)
    destination.mkdir(parents=True, exist_ok=False)
    _copy_tree_files(bundle, destination)
    replay_files = {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    }
    source_files = {
        path.relative_to(bundle).as_posix(): path.read_bytes()
        for path in bundle.rglob("*")
        if path.is_file()
    }
    if replay_files != source_files:
        raise ValueError("bundle replay is not byte-identical")
    validate_smoke_bundle(destination, external_digest=external_digest)
    return verdict
