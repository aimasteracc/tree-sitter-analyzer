"""Keyless closed-14 operator for the external NO1-008A services."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.audit_authority_client import run_cell
from benchmarks.codegraph_compare.audit_authority_service import (
    MAX_MESSAGE as AUTHORITY_MAX_MESSAGE,
)
from benchmarks.codegraph_compare.audit_authority_service import (
    verify_contract,
)
from benchmarks.codegraph_compare.decision_consumer_service import (
    request_decision,
    verify_configured_plan_set,
    verify_decision_contract,
)
from benchmarks.codegraph_compare.execution_budget import (
    CONTRACT_EXPIRY_MARGIN_SECONDS,
    authority_cell_budget_seconds,
    exact14_execution_budget_seconds,
)
from benchmarks.codegraph_compare.receipt_inventory import validate_receipt_inventory
from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.receipt_v3_service import (
    MAX_MESSAGE as RECEIPT_MAX_MESSAGE,
)
from benchmarks.codegraph_compare.receipt_v3_service import (
    request_receipt,
)
from benchmarks.codegraph_compare.setup_qualification_executor import (
    validate_producer_plan,
)
from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS
from benchmarks.codegraph_compare.verifier import parse_public_config
from benchmarks.codegraph_compare.verifier_service import (
    preflight_exact14_manifest,
    request_verdict,
)

RECEIPT_CANONICAL_SCHEMA_OVERHEAD = 2 * 1024 * 1024
RECEIPT_FRAME_WRAPPER_OVERHEAD = 4096


def preflight_receipt_service_frames(
    plan: dict[str, Any], inventory: dict[str, Any]
) -> dict[str, int]:
    """Bound every per-cell receipt frame before authority is consumed.

    The authority envelope is charged at its complete protocol ceiling.  The
    receipt body retains the inventory eligibility tree and selected plan/audit
    trees, so canonical escaping and a closed schema allowance are charged too.
    """
    canonical = canonical_json_bytes(plan) + canonical_json_bytes(inventory)
    staged = len(canonical) + canonical.count(b'"') + canonical.count(b"\\")
    executor_request = AUTHORITY_MAX_MESSAGE + RECEIPT_FRAME_WRAPPER_OVERHEAD
    executor_response = (
        AUTHORITY_MAX_MESSAGE
        + staged
        + RECEIPT_CANONICAL_SCHEMA_OVERHEAD
        + RECEIPT_FRAME_WRAPPER_OVERHEAD
    )
    approver_request = (
        AUTHORITY_MAX_MESSAGE + executor_response + RECEIPT_FRAME_WRAPPER_OVERHEAD
    )
    approver_response = executor_response + RECEIPT_FRAME_WRAPPER_OVERHEAD
    bounds = {
        "executor_request": executor_request,
        "executor_response": executor_response,
        "approver_request": approver_request,
        "approver_response": approver_response,
    }
    if any(size > RECEIPT_MAX_MESSAGE for size in bounds.values()):
        raise ValueError("per-cell receipt frame upper bound exceeds protocol ceiling")
    return bounds


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
        raw_contract = strict_json_loads(path.read_bytes())
        contract = dict(
            verify_contract({"operation": "run-cell", "contract": raw_contract})
        )
        cell = contract["cell"]
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
    expiries = {contract.get("expires_at_ns") for contract in contracts.values()}
    if len(expiries) != 1 or any(type(value) is not int for value in expiries):
        raise ValueError("all fourteen run contracts must have one exact expiry")
    common_expiry = expiries.pop()
    if common_expiry != decision_contract["expires_at_ns"]:
        raise ValueError("run contracts and offline decision must share one expiry")
    correlation_nonce = nonces.pop()
    if type(correlation_nonce) is not str or len(correlation_nonce) != 64:
        raise ValueError("root-signed correlation nonce invalid")
    cells = []
    staged_root = Path(args.staged_root).resolve(strict=True)
    plans: dict[tuple[str, str], dict[str, Any]] = {}
    inventories: dict[tuple[str, str], dict[str, Any]] = {}
    for identity in EXPECTED_CELLS:
        plan = strict_json_loads(
            (staged_root / contracts[identity]["job_id"] / "plan.json").read_bytes()
        )
        inventory = strict_json_loads(
            (
                staged_root / contracts[identity]["job_id"] / "inventory.json"
            ).read_bytes()
        )
        eligibility = validate_receipt_inventory(inventory)
        if eligibility["repo_id"] != identity[0]:
            raise ValueError("staged inventory does not match contract repository")
        inventories[identity] = inventory
        preflight_receipt_service_frames(plan, inventory)
        plan = validate_producer_plan(plan)
        if plan["cell"] != contracts[identity]["cell"]:
            raise ValueError("staged plan cell does not exactly match its contract")
        authority_cell_budget_seconds(plan)
        plans[identity] = plan
        ordinal = list(EXPECTED_CELLS).index(identity)
        from benchmarks.codegraph_compare.receipt_v3 import canonical_plan_hash

        logical_hash = canonical_plan_hash(plan)
        if (
            plan["plan_hash"] != logical_hash
            or logical_hash != decision_contract["cells"][ordinal]["plan_sha256"]
        ):
            raise ValueError("staged plan does not match offline decision cell hash")
    verify_configured_plan_set(decision_contract, config)
    # This bound uses only root-staged inputs and runs before the first authority
    # reservation, so an oversized exact-14 frame consumes no cell.
    preflight_exact14_manifest(
        [
            (plans[identity], inventories[identity], contracts[identity])
            for identity in EXPECTED_CELLS
        ]
    )
    serial_budget_seconds = exact14_execution_budget_seconds(plans)
    required_lifetime_ns = (
        serial_budget_seconds + CONTRACT_EXPIRY_MARGIN_SECONDS
    ) * 1_000_000_000
    if common_expiry - time.time_ns() < required_lifetime_ns:
        raise TimeoutError(
            "common exact-14 contract lifetime is below closed serial budget"
        )
    # Stop service work before the separately reserved expiry safety margin.
    deadline = time.monotonic() + serial_budget_seconds
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
                "wall_timeout_seconds": min(
                    remaining, authority_cell_budget_seconds(plans[identity])
                ),
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
