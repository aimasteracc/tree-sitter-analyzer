"""Immutable bundle, digest, and replay machinery for NO1-001B."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from benchmarks.codegraph_compare._integrity_gate import validate_experiment
from benchmarks.codegraph_compare.integrity import (
    ExperimentManifestV1,
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
_TERMINAL_EVIDENCE_MARKER = re.compile(
    r"^(?:(?:EXECUTION|EVIDENCE)_EXCEPTION|"
    r"(?:RUNTIME_POST_AUDIT|FROZEN_POSTCHECK|RUNTIME_CLEANUP)_FAILED):"
    r"[A-Za-z_][A-Za-z0-9_]*$|^(?:INDEX_CONTENT|RUNTIME_SEMANTIC)_DRIFT$"
)
_RUNTIME_EVIDENCE_MARKER = re.compile(
    r"^(?:(?:RUNTIME_POST_AUDIT|FROZEN_POSTCHECK|RUNTIME_CLEANUP)_FAILED:"
    r"[A-Za-z_][A-Za-z0-9_]*|(?:INDEX_CONTENT|RUNTIME_SEMANTIC)_DRIFT)$"
)
_EXECUTION_EVIDENCE_MARKER = re.compile(
    r"^(?:EXECUTION_EXCEPTION:[A-Za-z_][A-Za-z0-9_]*|INDEX_CONTENT_DRIFT)$"
)
_EVIDENCE_EXCEPTION_MARKER = re.compile(
    r"^EVIDENCE_EXCEPTION:[A-Za-z_][A-Za-z0-9_]*$"
)
_ARM_TOOL_SERVERS = {
    "tsa-warm": "tree-sitter-analyzer",
    "codegraph-warm": "codegraph",
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_runtime_marker_sequence(markers: list[str]) -> bool:
    index = 0
    if index < len(markers) and (
        markers[index] == "RUNTIME_SEMANTIC_DRIFT"
        or markers[index].startswith("RUNTIME_POST_AUDIT_FAILED:")
    ):
        index += 1
    if index < len(markers) and (
        markers[index] == "INDEX_CONTENT_DRIFT"
        or markers[index].startswith("FROZEN_POSTCHECK_FAILED:")
    ):
        index += 1
    if index < len(markers) and markers[index].startswith(
        "RUNTIME_CLEANUP_FAILED:"
    ):
        index += 1
    return index == len(markers)


def _runtime_measurements_match(runtime: dict[str, Any], markers: list[str]) -> bool:
    for marker in markers:
        if marker.startswith("RUNTIME_POST_AUDIT_FAILED:") and (
            runtime.get("semantic_digest_after") is not None
            or runtime.get("post_paths") is not None
        ):
            return False
        if marker == "RUNTIME_SEMANTIC_DRIFT" and (
            not isinstance(runtime.get("semantic_digest_before"), str)
            or not isinstance(runtime.get("semantic_digest_after"), str)
            or runtime["semantic_digest_before"] == runtime["semantic_digest_after"]
        ):
            return False
        if marker == "INDEX_CONTENT_DRIFT" and (
            not isinstance(runtime.get("expected_hash"), str)
            or not isinstance(runtime.get("frozen_hash_after"), str)
            or runtime["expected_hash"] == runtime["frozen_hash_after"]
        ):
            return False
        if marker.startswith("FROZEN_POSTCHECK_FAILED:") and runtime.get(
            "frozen_hash_after"
        ) is not None:
            return False
        if marker.startswith("RUNTIME_CLEANUP_FAILED:") and runtime.get(
            "cleanup_status"
        ) != "FAILED":
            return False
    required = {
        "runtime_post": runtime.get("materialized") is True
        and runtime.get("semantic_digest_after") is None,
        "semantic_drift": isinstance(runtime.get("semantic_digest_before"), str)
        and isinstance(runtime.get("semantic_digest_after"), str)
        and runtime["semantic_digest_before"] != runtime["semantic_digest_after"],
        "index_drift": isinstance(runtime.get("expected_hash"), str)
        and isinstance(runtime.get("frozen_hash_after"), str)
        and runtime["expected_hash"] != runtime["frozen_hash_after"],
        "frozen_postcheck": runtime.get("frozen_hash_after") is None,
        "cleanup": runtime.get("cleanup_status") == "FAILED",
    }
    represented = {
        "runtime_post": any(
            marker.startswith("RUNTIME_POST_AUDIT_FAILED:") for marker in markers
        ),
        "semantic_drift": "RUNTIME_SEMANTIC_DRIFT" in markers,
        "index_drift": "INDEX_CONTENT_DRIFT" in markers,
        "frozen_postcheck": any(
            marker.startswith("FROZEN_POSTCHECK_FAILED:") for marker in markers
        ),
        "cleanup": any(
            marker.startswith("RUNTIME_CLEANUP_FAILED:") for marker in markers
        ),
    }
    return represented == required


def _validate_arm_tool_preflight(path: Path, *, require_executables: bool) -> None:
    raw = _json(path)
    if not isinstance(raw, dict) or set(raw) != set(_ARM_TOOL_SERVERS):
        raise ValueError("arm-tool preflight must contain both indexed arms")
    expected_fields = {"server", "enabled", "command", "args"}
    for arm, server in _ARM_TOOL_SERVERS.items():
        record = raw[arm]
        if not isinstance(record, dict) or set(record) != expected_fields:
            raise ValueError(f"arm-tool preflight fields are invalid for {arm}")
        if record["server"] != server or record["enabled"] is not True:
            raise ValueError(f"arm-tool preflight server is invalid for {arm}")
        command = Path(str(record["command"]))
        if not command.is_absolute() or not isinstance(record["args"], list):
            raise ValueError(f"arm-tool preflight transport is invalid for {arm}")
        if require_executables and not command.is_file():
            raise ValueError(f"arm-tool preflight executable is unavailable for {arm}")


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
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        )
        if raw["experiment_id"] == experiment_id
    )


def _copy_tree_files(source: Path, destination: Path) -> None:
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())


def _without_terminal_exception(
    stored: dict[str, Any],
    run: RunRecordV1,
    evidence: Path,
    manifest: ExperimentManifestV1,
) -> dict[str, Any]:
    """Validate and remove terminal markers before transcript comparison."""

    violations = stored.get("violations")
    if not isinstance(violations, list) or not violations:
        return stored
    evidence_fallback = isinstance(violations[0], str) and bool(
        _EVIDENCE_EXCEPTION_MARKER.fullmatch(violations[0])
    )
    runtime_path = evidence / f"runtime_index_{run.run_id}.json"
    runtime_markers: list[str] = []
    if runtime_path.is_file() and not evidence_fallback:
        runtime = _json(runtime_path)
        failure_codes = runtime.get("failure_codes")
        if not isinstance(failure_codes, list) or not all(
            isinstance(marker, str)
            and _RUNTIME_EVIDENCE_MARKER.fullmatch(marker)
            for marker in failure_codes
        ) or not _valid_runtime_marker_sequence(failure_codes):
            raise ValueError(f"runtime evidence marker mismatch: {run.run_id}")
        runtime_markers = failure_codes
        if runtime_markers:
            if run.arm not in manifest.indexed_arms:
                raise ValueError(f"runtime evidence on non-indexed arm: {run.run_id}")
            expected_identity = {
                "schema_version": 1,
                "experiment_id": run.experiment_id,
                "manifest_hash": manifest.manifest_hash,
                "session_id": run.session_id,
                "run_id": run.run_id,
                "repo": run.repo,
                "arm": run.arm,
                "repeat": run.repeat,
                "expected_hash": dict(manifest.index_content_hashes)[run.arm],
                "failure_codes": runtime_markers,
            }
            if any(
                runtime.get(key) != value for key, value in expected_identity.items()
            ):
                raise ValueError(f"runtime evidence binding mismatch: {run.run_id}")
            if not _runtime_measurements_match(runtime, runtime_markers):
                raise ValueError(f"runtime evidence measurement mismatch: {run.run_id}")
            if violations[: len(runtime_markers)] != runtime_markers:
                raise ValueError(f"runtime evidence ordering mismatch: {run.run_id}")
    marker_count = 1 if evidence_fallback else len(runtime_markers)
    remaining = violations[marker_count:]
    if not evidence_fallback and remaining and isinstance(remaining[0], str):
        marker = remaining[0]
        if _EXECUTION_EVIDENCE_MARKER.fullmatch(marker):
            if marker == "INDEX_CONTENT_DRIFT" and marker not in runtime_markers:
                raise ValueError(f"runtime evidence missing for drift: {run.run_id}")
            marker_count += 1
    if marker_count == 0:
        return stored
    if marker_count < len(violations):
        next_violation = violations[marker_count]
        if isinstance(next_violation, str) and _TERMINAL_EVIDENCE_MARKER.fullmatch(
            next_violation
        ):
            raise ValueError(f"terminal evidence ordering mismatch: {run.run_id}")
    expected_blocker = "POLICY_AUDIT:" + ",".join(violations)
    blocker = run.blocker_reason or ""
    product_prefix = expected_blocker + ";PRODUCT_FAILURE:"
    has_product_failure = blocker.startswith(product_prefix) and bool(
        blocker[len(product_prefix) :]
    )
    if (
        run.status.value != "INVALID"
        or (blocker != expected_blocker and not has_product_failure)
        or (not run.transcript_path and run.answer != "ERROR")
    ):
        raise ValueError(f"terminal exception binding mismatch: {run.run_id}")
    comparable = dict(stored)
    comparable["violations"] = violations[marker_count:]
    return comparable


def _validate_policy_evidence(
    bundle_root: Path,
    runs: tuple[RunRecordV1, ...],
    manifest: ExperimentManifestV1,
) -> None:
    evidence = bundle_root / "evidence"
    expected_policy_files = {f"policy_{run.run_id}.json" for run in runs}
    actual_policy_files = {path.name for path in evidence.glob("policy_*.json")}
    if actual_policy_files != expected_policy_files:
        raise ValueError("policy evidence inventory mismatch")
    for run in runs:
        stored = _json(evidence / f"policy_{run.run_id}.json")
        if stored.get("transcript_path") != run.transcript_path:
            raise ValueError(f"policy transcript binding mismatch: {run.run_id}")
        transcript = (
            bundle_root / "artifacts" / run.arm / "raw" / Path(run.transcript_path).name
        )
        recomputed = cast(
            dict[str, Any],
            json.loads(json.dumps(asdict(audit_codex_transcript(transcript, run.arm)))),
        )
        recomputed["transcript_path"] = run.transcript_path
        stored_violations = stored.get("violations")
        comparable = _without_terminal_exception(stored, run, evidence, manifest)
        if recomputed != comparable:
            raise ValueError(f"policy audit mismatch: {run.run_id}")
        if stored_violations and run.status.value != "INVALID":
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
    arm_tool_preflight = plan_dir / "arm-tool-preflight.json"
    _validate_arm_tool_preflight(arm_tool_preflight, require_executables=True)
    (plan_target / "arm-tool-preflight.json").write_bytes(
        arm_tool_preflight.read_bytes()
    )
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
    _validate_policy_evidence(destination, runs, manifest)
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
    arm_tool_preflight = bundle / "plan/arm-tool-preflight.json"
    if arm_tool_preflight.is_file():
        _validate_arm_tool_preflight(arm_tool_preflight, require_executables=False)
    events = _registry(bundle / "registry.jsonl", manifest.experiment_id)
    runs = _runs(bundle / "evidence/runs.jsonl")
    _validate_policy_evidence(bundle, runs, manifest)
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
