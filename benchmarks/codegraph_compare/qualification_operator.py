"""Keyless closed-14 operator for the external NO1-008A services."""

from __future__ import annotations

import argparse
import os
import time
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
from benchmarks.codegraph_compare.verifier_service import (
    query_ledger_head,
    request_verdict,
)


def _write(path: Path, value: Any) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        os.write(descriptor, canonical_json_bytes(value) + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _run_impl(args: argparse.Namespace) -> int:
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
    staged_root = Path(args.staged_root).resolve(strict=True)
    plan_timeouts: dict[tuple[str, str], int] = {}
    for identity in EXPECTED_CELLS:
        plan = strict_json_loads(
            (staged_root / contracts[identity]["job_id"] / "plan.json").read_bytes()
        )
        value = plan.get("wall_timeout_seconds")
        if type(value) is not int or value < 1:
            raise ValueError("operator plan timeout invalid")
        plan_timeouts[identity] = value
    deadline = time.monotonic() + sum(value * 4 for value in plan_timeouts.values())
    for identity in EXPECTED_CELLS:
        contract = contracts[identity]
        staged = staged_root / contract["job_id"]
        plan = strict_json_loads((staged / "plan.json").read_bytes())
        wall_timeout = plan_timeouts[identity]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("exact-14 overall plan deadline expired")
        authority = run_cell(
            contract,
            Path(args.authority_socket),
            {
                **config["auditor"],
                "wall_timeout_seconds": min(wall_timeout, remaining),
            },
        )
        draft = request_receipt(
            role="executor",
            socket_path=Path(args.executor_socket),
            authority_response=authority,
            config=config,
            timeout=deadline - time.monotonic(),
        )
        receipt = request_receipt(
            role="approver",
            socket_path=Path(args.approver_socket),
            authority_response=authority,
            config=config,
            draft=draft,
            timeout=deadline - time.monotonic(),
        )
        cells.append(
            {"contract": contract, "authority_response": authority, "receipt": receipt}
        )
    if deadline - time.monotonic() <= 0:
        raise TimeoutError("exact-14 overall plan deadline expired")
    manifest = {
        "schema_version": 2,
        "correlation_nonce": correlation_nonce,
        "cells": cells,
    }
    envelope = request_verdict(
        socket_path=Path(args.verifier_socket),
        manifest=manifest,
        config=config,
        timeout=deadline - time.monotonic(),
    )
    verdict = envelope["verdict"]
    if (
        verdict.get("status") != "SETUP_QUALIFIED"
        or verdict.get("authorization") != "PRODUCTION_VERIFIER"
        or verdict.get("observed_receipts") != 14
    ):
        raise ValueError(
            "external fresh verifier did not produce exact-14 qualification"
        )
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("exact-14 overall plan deadline expired")
    live_head = query_ledger_head(
        socket_path=Path(args.verifier_socket), config=config, timeout=remaining
    )
    retained = envelope["ledger_head"]["record"]
    if live_head["record"] != retained:
        raise ValueError(
            "verifier live ledger head no longer matches fresh verdict; retry a new decision"
        )
    output = Path(args.experiment_root)
    output.mkdir(mode=0o700, exist_ok=True)
    _write(
        output / "verdict-envelope.json",
        {
            "envelope": envelope,
            "live_ledger_head": live_head,
            "proof_status": "HISTORICAL_AFTER_ACCEPTANCE",
        },
    )
    return 0


def run(args: argparse.Namespace) -> int:
    """Run with a durable terminal state; a failed exact-14 run is never resumed."""
    output = Path(args.experiment_root)
    output.mkdir(mode=0o700)
    state = output / "operator-state.json"
    _write(state, {"state": "RUNNING", "completed_cells": 0})
    try:
        result = _run_impl(args)
    except BaseException as error:
        temporary = output / ".operator-state.tmp"
        terminal = (
            "CANCELLED"
            if isinstance(error, (TimeoutError, KeyboardInterrupt))
            else "FAILED"
        )
        _write(temporary, {"state": terminal, "error": type(error).__name__})
        os.replace(temporary, state)
        raise
    temporary = output / ".operator-state.tmp"
    _write(temporary, {"state": "SUCCESS", "completed_cells": 14})
    os.replace(temporary, state)
    return result


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
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
