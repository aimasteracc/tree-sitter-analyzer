"""Exact, one-attempt, fail-all orchestration for NO1-008A E0 evidence."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.integrity import _sha256
from benchmarks.codegraph_compare.setup_qualification import (
    EXPECTED_CELLS,
    CellPlanV1,
    _bytes_hash,
    _lstat_regular_beneath,
    _write_exclusive,
    canonical_relative_path,
    validate_cell_receipt,
)

Producer = Callable[[str, str, Path, int], Mapping[str, Any]]


def _validate_plans(plans: Sequence[CellPlanV1]) -> tuple[CellPlanV1, ...]:
    frozen = tuple(plans)
    identities = tuple((plan.repo_id, plan.arm_id) for plan in frozen)
    artifacts = tuple(plan.artifact_path for plan in frozen)
    if identities != EXPECTED_CELLS:
        raise ValueError("Plans must be the exact ordered canonical 14-cell set")
    if len(set(artifacts)) != len(artifacts):
        raise ValueError("Every cell must have a unique immutable artifact path")
    for artifact in artifacts:
        canonical_relative_path(artifact)
        if not artifact.startswith("cells/") or not artifact.endswith(
            "/cell-receipt.json"
        ):
            raise ValueError(
                "Cell receipt paths must use the canonical cells namespace"
            )
    return frozen


def _read_regular_json(path: Path) -> tuple[dict[str, Any], bytes]:
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Receipt must be a non-symlink regular file")
    payload = path.read_bytes()
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Receipt JSON must be an object")
    return parsed, payload


def _stable_manifest(root: Path) -> dict[str, str]:
    def snapshot() -> dict[str, str]:
        result = {}
        for path in sorted(root.rglob("*")):
            metadata = os.lstat(path)
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("Artifact tree contains a symlink")
            if stat.S_ISREG(metadata.st_mode):
                result[path.relative_to(root).as_posix()] = _bytes_hash(
                    path.read_bytes()
                )
            elif not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("Artifact tree contains a special file")
        return result

    before, after = snapshot(), snapshot()
    if before != after:
        raise ValueError("Artifact tree mutated while it was being sealed")
    return before


def orchestrate_qualification(
    *,
    experiment_root: Path,
    plans: Sequence[CellPlanV1],
    producer: Producer,
) -> dict[str, Any]:
    """Invoke each planned cell once, strictly validate it, and remain E0."""
    plans = _validate_plans(plans)
    experiment_root.mkdir(parents=True, exist_ok=False)
    if stat.S_ISLNK(os.lstat(experiment_root).st_mode):
        raise ValueError("Experiment root must not be a symlink")
    _write_exclusive(
        experiment_root / "plan.json",
        {
            "schema_version": 2,
            "evaluation_stage": "E0",
            "cells": [asdict(plan) for plan in plans],
            "plan_set_hash": _sha256([asdict(plan) for plan in plans]),
        },
    )
    failures: list[dict[str, Any]] = []
    observed_receipts = 0
    for plan in plans:
        cell_root = experiment_root / Path(plan.artifact_path).parent
        try:
            returned = dict(producer(plan.repo_id, plan.arm_id, cell_root, 1))
            artifact = _lstat_regular_beneath(experiment_root, plan.artifact_path)
            on_disk, raw_bytes = _read_regular_json(artifact)
            if _sha256(returned) != _sha256(on_disk):
                raise ValueError(
                    "Producer return does not exactly match immutable receipt bytes"
                )
            validation = validate_cell_receipt(on_disk, plan=plan, cell_root=cell_root)
            if validation:
                raise ValueError(",".join(validation))
            observed_receipts += 1
            # Detect mutation immediately after validation; the final manifest repeats it.
            if artifact.read_bytes() != raw_bytes:
                raise ValueError("Receipt mutated after validation")
        except Exception as exc:  # noqa: BLE001 - fail-all records every cell
            failures.append(
                {
                    "repo_id": plan.repo_id,
                    "arm_id": plan.arm_id,
                    "attempt": 1,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
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
    _write_exclusive(experiment_root / "verdict.json", verdict)
    manifest = _stable_manifest(experiment_root)
    _write_exclusive(experiment_root / "checksums.json", manifest)
    for path in experiment_root.rglob("*"):
        if path.is_file():
            path.chmod(0o400)
    return verdict
