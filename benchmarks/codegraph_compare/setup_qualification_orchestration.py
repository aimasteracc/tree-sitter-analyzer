"""Exact, one-attempt, fail-all orchestration for NO1-008A E0 evidence."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from benchmarks.codegraph_compare.integrity import _sha256
from benchmarks.codegraph_compare.setup_qualification import (
    EXPECTED_CELLS,
    CellPlanV1,
    canonical_relative_path,
    validate_cell_receipt,
)
from benchmarks.codegraph_compare.setup_qualification_paths import (
    _manifest_tree_at,
    _open_root,
    _read_regular_at,
    _seal_tree_at,
)

Producer = Callable[[str, str, Path, int], Mapping[str, Any]]


def _trusted_commits(path: Path) -> dict[str, str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        result = {item["id"]: item["commit"] for item in raw["repos"]}
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed trusted repositories manifest") from exc
    if tuple(result) != tuple(repo for repo, _ in EXPECTED_CELLS[::2]):
        raise ValueError("Trusted repositories manifest is not canonical")
    return result


def _validate_plans(
    plans: Sequence[CellPlanV1], trusted_commits: Mapping[str, str]
) -> tuple[CellPlanV1, ...]:
    frozen = tuple(plans)
    identities = tuple((plan.repo_id, plan.arm_id) for plan in frozen)
    artifacts = tuple(plan.artifact_path for plan in frozen)
    if identities != EXPECTED_CELLS:
        raise ValueError("Plans must be the exact ordered canonical 14-cell set")
    if len(set(artifacts)) != len(artifacts):
        raise ValueError("Every cell must have a unique immutable artifact path")
    by_repo: dict[str, CellPlanV1] = {}
    for plan in frozen:
        if plan.eligibility.commit != trusted_commits.get(plan.repo_id):
            raise ValueError("Plan commit does not match trusted repos.yaml")
        previous = by_repo.setdefault(plan.repo_id, plan)
        if asdict(previous.eligibility) != asdict(plan.eligibility):
            raise ValueError("Both arms must use identical source eligibility")
    for artifact in artifacts:
        canonical_relative_path(artifact)
        if not artifact.startswith("cells/") or not artifact.endswith(
            "/cell-receipt.json"
        ):
            raise ValueError(
                "Cell receipt paths must use the canonical cells namespace"
            )
    return frozen


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON member: {key}")
        result[key] = value
    return result


def _parse_receipt(payload: bytes) -> dict[str, Any]:
    parsed = json.loads(payload, object_pairs_hook=_reject_duplicate_members)
    if not isinstance(parsed, dict):
        raise ValueError("Receipt JSON must be an object")
    return parsed


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _write_exclusive_at(root_fd: int, relative: str, payload: bytes) -> None:
    canonical_relative_path(relative)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(relative, flags, 0o600, dir_fd=root_fd)
    try:
        offset = 0
        while offset != len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _stable_manifest(root_fd: int) -> dict[str, str]:
    before, after = _manifest_tree_at(root_fd), _manifest_tree_at(root_fd)
    if before != after:
        raise ValueError("Artifact tree mutated while it was being sealed")
    return before


def orchestrate_qualification(
    *,
    experiment_root: Path,
    plans: Sequence[CellPlanV1],
    producer: Producer,
    trusted_repositories: Path | None = None,
) -> dict[str, Any]:
    """Invoke each planned cell once, strictly validate it, and remain E0."""
    if trusted_repositories is None:
        trusted_repositories = Path(__file__).with_name("repos.yaml")
    plans = _validate_plans(plans, _trusted_commits(trusted_repositories))
    experiment_root.mkdir(parents=True, exist_ok=False)
    # This is the sole trust decision for the experiment directory. Every read,
    # validation and seal below is relative to this retained descriptor.
    experiment_fd = _open_root(experiment_root)
    try:
        plan_document = {
            "schema_version": 2,
            "evaluation_stage": "E0",
            "cells": [asdict(plan) for plan in plans],
            "plan_set_hash": _sha256([asdict(plan) for plan in plans]),
        }
        plan_bytes = _json_bytes(plan_document)
        plan_bytes_digest = hashlib.sha256(plan_bytes).hexdigest()
        _write_exclusive_at(experiment_fd, "plan.json", plan_bytes)

        failures: list[dict[str, Any]] = []
        observed_receipts = 0
        validated: dict[str, tuple[bytes, str, str]] = {}
        for plan in plans:
            cell_relative = PurePosixPath(plan.artifact_path).parent.as_posix()
            cell_root = experiment_root / cell_relative
            try:
                returned = dict(producer(plan.repo_id, plan.arm_id, cell_root, 1))
                raw_bytes = _read_regular_at(experiment_fd, plan.artifact_path)
                on_disk = _parse_receipt(raw_bytes)
                if _sha256(returned) != _sha256(on_disk):
                    raise ValueError(
                        "Producer return does not exactly match immutable receipt bytes"
                    )
                validation = validate_cell_receipt(
                    on_disk,
                    plan=plan,
                    cell_root=cell_root,
                    trusted_root_fd=experiment_fd,
                    cell_relative=cell_relative,
                )
                if validation:
                    raise ValueError(",".join(validation))
                observed_receipts += 1
                validated[plan.artifact_path] = (
                    raw_bytes,
                    plan.digest,
                    on_disk["receipt_hash"],
                )
            except Exception as exc:  # noqa: BLE001 - fail-all records every cell
                failures.append(
                    {
                        "repo_id": plan.repo_id,
                        "arm_id": plan.arm_id,
                        "attempt": 1,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        # Preserve final revalidation and perform it through the pinned root.
        for plan in plans:
            snapshot = validated.get(plan.artifact_path)
            if snapshot is None:
                continue
            try:
                raw_bytes = _read_regular_at(experiment_fd, plan.artifact_path)
                on_disk = _parse_receipt(raw_bytes)
                if (raw_bytes, plan.digest, on_disk.get("receipt_hash")) != snapshot:
                    raise ValueError(
                        "Validated receipt bytes or digest changed before sealing"
                    )
                cell_relative = PurePosixPath(plan.artifact_path).parent.as_posix()
                validation = validate_cell_receipt(
                    on_disk,
                    plan=plan,
                    cell_root=experiment_root / cell_relative,
                    trusted_root_fd=experiment_fd,
                    cell_relative=cell_relative,
                )
                if validation:
                    raise ValueError(",".join(validation))
            except Exception as exc:  # noqa: BLE001 - final seal is fail-closed
                observed_receipts -= 1
                failures.append(
                    {
                        "repo_id": plan.repo_id,
                        "arm_id": plan.arm_id,
                        "attempt": 1,
                        "error": f"FINAL_REVALIDATION: {type(exc).__name__}: {exc}",
                    }
                )

        # A producer may have reached plan.json through writable ancestors.
        # Refuse to seal unless the original bytes and digest are unchanged.
        final_plan_bytes = _read_regular_at(experiment_fd, "plan.json")
        if (
            final_plan_bytes != plan_bytes
            or hashlib.sha256(final_plan_bytes).hexdigest() != plan_bytes_digest
        ):
            raise ValueError("Original plan bytes changed before sealing")

        verdict = {
            "schema_version": 2,
            "evaluation_stage": "E0",
            "status": "NOT_EVALUATED",
            "reason": "HARNESS_SANDBOX_EXECUTOR_AND_INDEPENDENT_APPROVAL_UNAVAILABLE",
            "publishable": False,
            "winner": None,
            "dominance_allowed": False,
            "unlock_allowed": False,
            "expected_cells": len(EXPECTED_CELLS),
            "observed_receipts": observed_receipts,
            "attempts_per_cell": 1,
            "failures": failures,
            "counters": None,
        }
        _write_exclusive_at(experiment_fd, "verdict.json", _json_bytes(verdict))
        manifest = _stable_manifest(experiment_fd)
        _write_exclusive_at(experiment_fd, "checksums.json", _json_bytes(manifest))
        _seal_tree_at(experiment_fd, 0o400)
        return verdict
    finally:
        os.close(experiment_fd)
