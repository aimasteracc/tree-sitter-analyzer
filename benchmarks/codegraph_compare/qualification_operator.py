"""Keyless closed-14 operator for the external NO1-008A services."""

from __future__ import annotations

import argparse
import os
import secrets
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
from benchmarks.codegraph_compare.verifier_service import request_verdict


def _write(path: Path, value: Any) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        os.write(descriptor, canonical_json_bytes(value) + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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
    if set(contracts) != set(EXPECTED_CELLS) or len(contracts) != 14:
        raise ValueError("contracts must cover the exact fourteen cells")
    nonces = {contract.get("nonce") for contract in contracts.values()}
    if len(nonces) != 1:
        raise ValueError("root-signed run contracts must share one correlation nonce")
    correlation_nonce = nonces.pop()
    if type(correlation_nonce) is not str or len(correlation_nonce) != 64:
        raise ValueError("root-signed correlation nonce invalid")
    cells = []
    maximum_plan_timeout = 0
    staged_root = Path(args.staged_root).resolve(strict=True)
    for identity in EXPECTED_CELLS:
        contract = contracts[identity]
        staged = staged_root / contract["job_id"]
        plan = strict_json_loads((staged / "plan.json").read_bytes())
        wall_timeout = plan.get("wall_timeout_seconds")
        if type(wall_timeout) is not int or wall_timeout < 1:
            raise ValueError("operator plan timeout invalid")
        maximum_plan_timeout = max(maximum_plan_timeout, wall_timeout)
        authority = run_cell(
            contract,
            Path(args.authority_socket),
            {**config["auditor"], "wall_timeout_seconds": wall_timeout},
        )
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
        cells.append(
            {"contract": contract, "authority_response": authority, "receipt": receipt}
        )
    challenge = secrets.token_hex(32)
    while challenge == correlation_nonce:
        challenge = secrets.token_hex(32)
    plan_margin = maximum_plan_timeout + 180
    verifier_timeout = args.verifier_timeout or plan_margin
    if type(verifier_timeout) is not int or verifier_timeout < plan_margin:
        raise ValueError(
            "verifier timeout must include the maximum plan verification margin"
        )
    manifest = {
        "schema_version": 2,
        "correlation_nonce": correlation_nonce,
        "cells": cells,
    }
    envelope = request_verdict(
        socket_path=Path(args.verifier_socket),
        manifest=manifest,
        challenge=challenge,
        config=config,
        timeout=verifier_timeout,
    )
    verdict = envelope["verdict"]
    if (
        verdict.get("status") != "SETUP_QUALIFIED"
        or verdict.get("authorization") != "PRODUCTION_ROOT"
        or verdict.get("observed_receipts") != 14
    ):
        raise ValueError(
            "external fresh verifier did not produce exact-14 qualification"
        )
    output = Path(args.experiment_root)
    output.mkdir(mode=0o700)
    _write(output / "verdict-envelope.json", envelope)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "contracts-dir",
        "authority-socket",
        "executor-socket",
        "approver-socket",
        "verifier-socket",
        "public-config",
        "staged-root",
        "experiment-root",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--verifier-timeout", type=int)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
