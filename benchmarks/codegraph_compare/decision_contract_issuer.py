"""Offline root decision/run-contract issuer; private keys are read-only inputs."""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import time
from collections.abc import Sequence
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare.audit_authority_service import CONTRACT_DOMAIN
from benchmarks.codegraph_compare.decision_consumer_service import DECISION_DOMAIN
from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    canonical_plan_hash,
    strict_json_loads,
)
from benchmarks.codegraph_compare.service_runtime import secure_key
from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS


def issue(
    plans_dir: Path, key: Ed25519PrivateKey, *, lifetime_seconds: int = 86400
) -> tuple[dict, list[dict]]:
    if lifetime_seconds < 1:
        raise ValueError("decision lifetime must be positive")
    plans = {}
    for path in plans_dir.resolve(strict=True).glob("*.json"):
        plan = strict_json_loads(path.read_bytes())
        cell = plan.get("cell", {})
        identity = (cell.get("repo_id"), cell.get("arm_id"))
        if identity in plans:
            raise ValueError("duplicate decision plan cell")
        plans[identity] = plan
    if set(plans) != set(EXPECTED_CELLS) or len(plans) != 14:
        raise ValueError("offline decision requires exact fourteen plans")
    issued = time.time_ns()
    decision_id, nonce = secrets.token_hex(32), secrets.token_hex(32)
    cells = [
        {
            "repo_id": repo,
            "arm_id": arm,
            "plan_sha256": canonical_plan_hash(plans[(repo, arm)]),
        }
        for repo, arm in EXPECTED_CELLS
    ]
    plan_set_hash = hashlib.sha256(
        canonical_json_bytes([c["plan_sha256"] for c in cells])
    ).hexdigest()
    unsigned = {
        "schema_version": 1,
        "decision_id": decision_id,
        "decision_nonce": nonce,
        "issued_at_ns": issued,
        "expires_at_ns": issued + lifetime_seconds * 1_000_000_000,
        "plan_set_hash": plan_set_hash,
        "cells": cells,
    }
    decision = {
        **unsigned,
        "root_signature": key.sign(
            DECISION_DOMAIN + canonical_json_bytes(unsigned)
        ).hex(),
    }
    decision_digest = hashlib.sha256(canonical_json_bytes(decision)).hexdigest()
    contracts = []
    for ordinal, (repo, arm) in enumerate(EXPECTED_CELLS):
        body = {
            "schema_version": 3,
            "job_id": hashlib.sha256(
                canonical_json_bytes({"decision_id": decision_id, "ordinal": ordinal})
            ).hexdigest(),
            "cell": {"repo_id": repo, "arm_id": arm, "attempt": 1},
            "nonce": nonce,
            "decision_id": decision_id,
            "decision_contract_sha256": decision_digest,
            "expires_at_ns": unsigned["expires_at_ns"],
        }
        contracts.append(
            {
                **body,
                "root_signature": key.sign(
                    CONTRACT_DOMAIN + canonical_json_bytes(body)
                ).hex(),
            }
        )
    return decision, contracts


def _exclusive(path: Path, value: dict) -> None:
    fd = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_CLOEXEC
        | getattr(os, "O_NOFOLLOW", 0),
        0o400,
    )
    try:
        data = canonical_json_bytes(value) + b"\n"
        while data:
            data = data[os.write(fd, data) :]
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans-dir", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--lifetime-seconds", type=int, default=86400)
    args = parser.parse_args(argv)
    fd, raw = secure_key(Path(args.private_key), os.geteuid())
    try:
        decision, contracts = issue(
            Path(args.plans_dir),
            Ed25519PrivateKey.from_private_bytes(raw),
            lifetime_seconds=args.lifetime_seconds,
        )
    finally:
        os.close(fd)
    output = Path(args.output_dir)
    output.mkdir(mode=0o700)
    _exclusive(output / "decision-contract.json", decision)
    run_contracts = output / "run_contracts"
    run_contracts.mkdir(mode=0o700)
    for contract in contracts:
        cell = contract["cell"]
        _exclusive(
            run_contracts / f"{cell['repo_id']}--{cell['arm_id']}.json", contract
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
