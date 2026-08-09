"""Keyless closed-14 operator for the external NO1-008A services."""

from __future__ import annotations

import argparse
import os
import secrets
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.audit_authority_client import run_cell
from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.receipt_v3_service import request_receipt
from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS
from benchmarks.codegraph_compare.verifier import parse_public_config


def _write(path: Path, value: Any) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        os.write(descriptor, canonical_json_bytes(value) + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_regular(source: Path, destination: Path) -> None:
    source_fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    destination_fd = os.open(
        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400
    )
    try:
        if not stat.S_ISREG(os.fstat(source_fd).st_mode):
            raise ValueError("pipeline evidence source is not regular")
        while chunk := os.read(source_fd, 1024 * 1024):
            os.write(destination_fd, chunk)
        os.fsync(destination_fd)
    finally:
        os.close(source_fd)
        os.close(destination_fd)


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.public_config).resolve(strict=True)
    config = parse_public_config(config_path.read_bytes())
    contracts: dict[tuple[str, str], dict[str, Any]] = {}
    for path in Path(args.contracts_dir).resolve(strict=True).glob("*.json"):
        contract = strict_json_loads(path.read_bytes())
        cell = contract.get("cell", {})
        identity = (cell.get("repo_id"), cell.get("arm_id"))
        if identity in contracts:
            raise ValueError("duplicate run-cell contract")
        contracts[identity] = contract
    if tuple(contracts) != EXPECTED_CELLS and set(contracts) != set(EXPECTED_CELLS):
        raise ValueError("contracts must cover the exact fourteen ordered cells")
    output = Path(args.experiment_root)
    output.mkdir(mode=0o700)
    artifact_root = Path(args.artifact_root).resolve(strict=True)
    staged_root = Path(args.staged_root).resolve(strict=True)
    cells = []
    maximum_plan_timeout = 0
    verifier_nonce = secrets.token_hex(32)
    for ordinal, identity in enumerate(EXPECTED_CELLS):
        contract = contracts[identity]
        job_id = contract["job_id"]
        staged = staged_root / job_id
        plan_preview = strict_json_loads((staged / "plan.json").read_bytes())
        wall_timeout = plan_preview.get("wall_timeout_seconds")
        if type(wall_timeout) is not int or wall_timeout < 1:
            raise ValueError("operator plan timeout invalid")
        maximum_plan_timeout = max(maximum_plan_timeout, wall_timeout)
        authority_config = {**config["auditor"], "wall_timeout_seconds": wall_timeout}
        authority = run_cell(contract, Path(args.authority_socket), authority_config)
        draft = request_receipt(
            role="executor",
            socket_path=Path(args.executor_socket),
            authority_response=authority,
            config=config,
            timeout=wall_timeout + 180,
        )
        receipt = request_receipt(
            role="approver",
            socket_path=Path(args.approver_socket),
            authority_response=authority,
            config=config,
            draft=draft,
            timeout=wall_timeout + 180,
        )
        cell_dir = output / f"cell-{ordinal:02d}"
        cell_dir.mkdir(mode=0o700)
        receipt_path = cell_dir / "receipt.json"
        audit_path = cell_dir / "process-audit.json"
        plan_path = cell_dir / "plan.json"
        inventory_path = cell_dir / "inventory.json"
        _write(receipt_path, receipt)
        _write(audit_path, authority["response"]["audit"])
        descriptors = {
            item["name"]: item for item in authority["response"]["artifacts"]
        }
        _copy_regular(staged / "plan.json", plan_path)
        _copy_regular(staged / "inventory.json", inventory_path)
        evidence_names = {
            "data_image": artifact_root / descriptors["data.img"]["path"],
            "hash_image": artifact_root / descriptors["hash.img"]["path"],
            "source_snapshot": staged / "source-snapshot.tar",
            "tool": staged / "tool",
            "config": staged / "config",
            "seccomp": staged / "seccomp",
        }
        relative_evidence = {}
        for evidence_name, source in evidence_names.items():
            target = cell_dir / evidence_name
            _copy_regular(source, target)
            relative_evidence[evidence_name] = target.relative_to(output).as_posix()
        cells.append(
            {
                "repo_id": identity[0],
                "arm_id": identity[1],
                "attempt": 1,
                "plan": plan_path.relative_to(output).as_posix(),
                "inventory": inventory_path.relative_to(output).as_posix(),
                "receipt": receipt_path.relative_to(output).as_posix(),
                "process_audit": audit_path.relative_to(output).as_posix(),
                **relative_evidence,
            }
        )
    run_contract = output / "run-contract.json"
    _write(
        run_contract,
        {
            "plan_set_hash": config["trusted"]["plan_set_hash"],
            "run_nonce": verifier_nonce,
        },
    )
    manifest = {
        "schema_version": 1,
        "verifier_nonce": verifier_nonce,
        "verifier_image_digest": config["trusted"]["images"]["verifier"],
        "run_contract": run_contract.relative_to(output).as_posix(),
        "cells": cells,
    }
    manifest_path = output / "manifest.json"
    _write(manifest_path, manifest)
    verdict_path = output / "verdict.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.codegraph_compare.verifier_aggregate",
            "aggregate",
            "--manifest",
            str(manifest_path),
            "--public-config",
            str(config_path),
            "--verifier-nonce",
            verifier_nonce,
            "--verifier-image-digest",
            config["trusted"]["images"]["verifier"],
            "--output",
            str(verdict_path),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=args.verifier_timeout,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"fresh production verifier rejected run: {completed.stderr[:200]!r}"
        )
    verdict = strict_json_loads(verdict_path.read_bytes())
    if (
        verdict.get("status") != "SETUP_QUALIFIED"
        or verdict.get("authorization") != "PRODUCTION_ROOT"
        or verdict.get("observed_receipts") != 14
    ):
        raise ValueError(
            "fresh verifier did not produce production-root exact-14 qualification"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "contracts-dir",
        "authority-socket",
        "executor-socket",
        "approver-socket",
        "public-config",
        "artifact-root",
        "staged-root",
        "experiment-root",
    ):
        parser.add_argument(f"--{name}", required=True)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
