"""Keyless closed-14 operator for the external NO1-008A services."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.audit_authority_client import run_cell
from benchmarks.codegraph_compare.decision_consumer_service import (
    request_decision,
    verify_decision_contract,
)
from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.receipt_v3_service import request_receipt
from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS
from benchmarks.codegraph_compare.verifier import parse_public_config
from benchmarks.codegraph_compare.verifier_service import request_verdict


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write(path: Path, value: Any) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        payload = canonical_json_bytes(value) + b"\n"
        while payload:
            written = os.write(descriptor, payload)
            if written == 0:
                raise OSError("operator evidence write made no progress")
            payload = payload[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


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
    decision_contract = verify_decision_contract(
        strict_json_loads(
            Path(args.decision_contract).resolve(strict=True).read_bytes()
        )
    )
    decision_digest = (
        __import__("hashlib")
        .sha256(canonical_json_bytes(decision_contract))
        .hexdigest()
    )
    decision_ids = {contract.get("decision_id") for contract in contracts.values()}
    decision_digests = {
        contract.get("decision_contract_sha256") for contract in contracts.values()
    }
    if decision_ids != {decision_contract["decision_id"]} or decision_digests != {
        decision_digest
    }:
        raise ValueError(
            "all fourteen run contracts must bind the common offline decision"
        )
    if any(
        type(contract.get("expires_at_ns")) is not int
        or contract["expires_at_ns"] <= time.time_ns()
        for contract in contracts.values()
    ):
        raise ValueError("root-signed run contract is expired")
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
        ordinal = list(EXPECTED_CELLS).index(identity)
        from benchmarks.codegraph_compare.receipt_v3 import canonical_plan_hash

        if (
            canonical_plan_hash(plan)
            != decision_contract["cells"][ordinal]["plan_sha256"]
        ):
            raise ValueError("staged plan does not match offline decision cell hash")
    if decision_contract["plan_set_hash"] != config["trusted"]["plan_set_hash"]:
        raise ValueError("offline decision plan set is not root-config authorized")
    deadline = time.monotonic() + sum(value * 4 for value in plan_timeouts.values())
    for identity in EXPECTED_CELLS:
        contract = contracts[identity]
        if contract["expires_at_ns"] <= time.time_ns():
            raise TimeoutError("root-signed decision contract expired before execution")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("exact-14 overall plan deadline expired")
        authority = run_cell(
            contract,
            Path(args.authority_socket),
            {
                **config["auditor"],
                "wall_timeout_seconds": remaining,
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
    # Acceptance uses the verifier-signed CONSUMED record in the envelope.  A
    # subsequent live head query would introduce a TOCTOU race and is unnecessary.
    decision_receipt = request_decision(
        socket_path=Path(args.decision_consumer_socket),
        contract=decision_contract,
        envelope=envelope,
        config=config,
        timeout=deadline - time.monotonic(),
    )
    output = Path(args.experiment_root)
    output.mkdir(mode=0o700, exist_ok=True)
    _write(
        output / "verdict-envelope.json",
        {"envelope": envelope, "decision_receipt": decision_receipt},
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
        _fsync_directory(output)
        raise
    temporary = output / ".operator-state.tmp"
    _write(temporary, {"state": "SUCCESS", "completed_cells": 14})
    os.replace(temporary, state)
    _fsync_directory(output)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "contracts-dir",
        "authority-socket",
        "executor-socket",
        "approver-socket",
        "verifier-socket",
        "decision-consumer-socket",
        "decision-contract",
        "public-config",
        "staged-root",
        "experiment-root",
    ):
        parser.add_argument(f"--{name}", required=True)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
