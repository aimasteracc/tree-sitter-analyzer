"""Non-executing NO1-008A E0 setup-qualification scaffold."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from benchmarks.codegraph_compare.integrity import _sha256
from benchmarks.codegraph_compare.setup_qualification import (
    EXPECTED_CELLS,
    CellPlanV1,
    EligibilityV1,
    canonical_relative_path,
    strict_json_loads,
    validate_receipt_schema_v2,
)


def _trusted_commits(path: Path) -> dict[str, str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        repositories = raw["repos"]
        if not isinstance(repositories, list) or len(repositories) != 7:
            raise ValueError(
                "Trusted repositories manifest must contain exactly seven entries"
            )
        identifiers = tuple(item["id"] for item in repositories)
        commits = tuple(item["commit"] for item in repositories)
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed trusted repositories manifest") from exc
    canonical = tuple(repo for repo, _ in EXPECTED_CELLS[::2])
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Trusted repository IDs must be unique")
    if identifiers != canonical:
        raise ValueError("Trusted repositories manifest is not canonical")
    return dict(zip(identifiers, commits, strict=True))


def _validate_plans(
    plans: Sequence[CellPlanV1],
    trusted_commits: Mapping[str, str],
    trusted_inventories: Mapping[str, EligibilityV1],
) -> tuple[CellPlanV1, ...]:
    """Bind plans to complete inventories obtained outside the E0 scaffold."""
    frozen = tuple(plans)
    identities = tuple((plan.repo_id, plan.arm_id) for plan in frozen)
    artifacts = tuple(plan.artifact_path for plan in frozen)
    if identities != EXPECTED_CELLS:
        raise ValueError("Plans must be the exact ordered canonical 14-cell set")
    if len(set(artifacts)) != len(artifacts):
        raise ValueError("Every cell must have a unique artifact path")
    if set(trusted_inventories) != set(trusted_commits):
        raise ValueError("Trusted inventory map must cover exactly seven repositories")
    by_repo: dict[str, CellPlanV1] = {}
    for plan in frozen:
        trusted = trusted_inventories.get(plan.repo_id)
        if plan.eligibility.commit != trusted_commits.get(plan.repo_id):
            raise ValueError("Plan commit does not match trusted repos.yaml")
        if trusted is None or asdict(plan.eligibility) != asdict(trusted):
            raise ValueError(
                "Plan eligibility does not match the complete trusted inventory"
            )
        previous = by_repo.setdefault(plan.repo_id, plan)
        if asdict(previous.eligibility) != asdict(plan.eligibility):
            raise ValueError("Both arms must use identical source eligibility")
        if tuple(map(asdict, previous.oracle_specs)) != tuple(
            map(asdict, plan.oracle_specs)
        ):
            raise ValueError(
                "Both arms must use exactly identical oracle specifications"
            )
    for artifact in artifacts:
        canonical_relative_path(artifact)
        if not artifact.startswith("cells/") or not artifact.endswith(
            "/cell-receipt.json"
        ):
            raise ValueError(
                "Cell receipt paths must use the canonical cells namespace"
            )
    return frozen


def _parse_receipt(payload: bytes) -> dict[str, Any]:
    """Strict parser retained for a future fresh external verifier artifact."""
    parsed = strict_json_loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Receipt JSON must be an object")
    validate_receipt_schema_v2(parsed)
    unsigned = dict(parsed)
    claimed_hash = unsigned.pop("receipt_hash")
    if claimed_hash != _sha256(unsigned):
        raise ValueError("Receipt hash does not match canonical receipt content")
    return parsed


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def orchestrate_qualification(
    *,
    experiment_root: Path,
    plans: Sequence[CellPlanV1],
    trusted_inventories: Mapping[str, EligibilityV1],
    trusted_repositories: Path | None = None,
) -> dict[str, Any]:
    """Record an E0 stop; never execute a producer, observe receipts, or seal evidence."""
    if trusted_repositories is None:
        trusted_repositories = Path(__file__).with_name("repos.yaml")
    plans = _validate_plans(
        plans, _trusted_commits(trusted_repositories), trusted_inventories
    )
    experiment_root.mkdir(parents=True, exist_ok=False)
    plan_document = {
        "schema_version": 2,
        "evaluation_stage": "E0",
        "cells": [asdict(plan) for plan in plans],
        "plan_set_hash": _sha256([asdict(plan) for plan in plans]),
    }
    verdict = {
        "schema_version": 2,
        "evaluation_stage": "E0",
        "status": "NOT_EVALUATED",
        "reason": "ISOLATED_EXTERNAL_PRODUCER_AND_FRESH_TRUSTED_VERIFIER_ARTIFACT_REQUIRED",
        "publishable": False,
        "winner": None,
        "dominance_allowed": False,
        "unlock_allowed": False,
        "expected_cells": len(EXPECTED_CELLS),
        "observed_receipts": 0,
        "attempts_per_cell": 0,
        "failures": [],
        "counters": None,
    }
    _write_exclusive(experiment_root / "plan.json", _json_bytes(plan_document))
    _write_exclusive(experiment_root / "verdict.json", _json_bytes(verdict))
    return verdict
