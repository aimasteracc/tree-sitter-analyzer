"""Fresh, public-key-only verifier for detached NO1-008A receipt v3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
    verify_receipt,
)
from benchmarks.codegraph_compare.setup_qualification_paths import (
    canonical_relative_path,
)
from benchmarks.codegraph_compare.setup_qualification_plan import (
    EXPECTED_CELLS,
    ZERO_COUNTERS,
)

CLAIMS = {
    "evaluation_stage": "E0",
    "publishable": False,
    "winner": None,
    "dominance_allowed": False,
    "unlock_allowed": False,
}
PUBLIC_CONFIG_KEYS = frozenset({"schema_version", "executor", "approver"})
PUBLIC_ROLE_KEYS = frozenset({"key_id", "public_key_hex"})


def _exact(value: Any, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or frozenset(value) != keys:
        raise ValueError(f"{label} has unknown or missing fields")
    return value


def parse_public_config(payload: bytes) -> dict[str, Any]:
    config = _exact(strict_json_loads(payload), PUBLIC_CONFIG_KEYS, "public config")
    if config["schema_version"] != 1 or type(config["schema_version"]) is not int:
        raise ValueError("public config schema must be exact integer 1")
    keys: list[bytes] = []
    ids: list[str] = []
    for role in ("executor", "approver"):
        item = _exact(config[role], PUBLIC_ROLE_KEYS, role)
        if (
            type(item["key_id"]) is not str
            or not item["key_id"]
            or len(item["key_id"].encode()) > 128
        ):
            raise ValueError("public key ID must be bounded and non-empty")
        if type(item["public_key_hex"]) is not str or len(item["public_key_hex"]) != 64:
            raise ValueError("public key must contain 32 hexadecimal bytes")
        try:
            keys.append(bytes.fromhex(item["public_key_hex"]))
        except ValueError as error:
            raise ValueError("public key must be lowercase hexadecimal") from error
        if item["public_key_hex"] != item["public_key_hex"].lower():
            raise ValueError("public key must be lowercase hexadecimal")
        ids.append(item["key_id"])
    if ids[0] == ids[1] or keys[0] == keys[1]:
        raise ValueError("public signer identities must differ")
    return dict(config)


def _read_regular(root: Path, relative: str, expected_size: int) -> bytes:
    relative = canonical_relative_path(relative)
    path = root.joinpath(*relative.split("/"))
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if (
        resolved == resolved_root
        or resolved_root not in resolved.parents
        or path.is_symlink()
        or not path.is_file()
    ):
        raise ValueError("core blob escaped the verified snapshot")
    metadata = path.stat()
    if metadata.st_size != expected_size or expected_size > 512 * 1024 * 1024:
        raise ValueError("core blob size mismatch")
    return path.read_bytes()


def _tree_hash(root: Path) -> str:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("snapshot tree contains a symbolic link")
        relative = path.relative_to(root).as_posix()
        if path.is_file():
            payload = path.read_bytes()
            records.append(
                {
                    "path": relative,
                    "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        elif not path.is_dir():
            raise ValueError("snapshot tree contains a special file")
    return hashlib.sha256(canonical_json_bytes(records)).hexdigest()


def _plan_value(plan: Any, name: str) -> Any:
    return getattr(plan, name) if hasattr(plan, name) else plan[name]


def _item_value(item: Any, attribute: str, key: str) -> Any:
    return getattr(item, attribute) if hasattr(item, attribute) else item[key]


def verify_cell(
    receipt: Mapping[str, Any],
    *,
    public_config: Mapping[str, Any],
    plan: Any | None = None,
    inventory: Mapping[str, Any] | None = None,
    core_root: Path | None = None,
    verifier_pid: int | None = None,
) -> tuple[str, ...]:
    """Return deterministic violations. An empty tuple means setup-qualified cell."""
    violations: list[str] = []
    try:
        parsed_config = parse_public_config(canonical_json_bytes(public_config))
        verify_receipt(
            receipt,
            parsed_config["executor"]["key_id"],
            bytes.fromhex(parsed_config["executor"]["public_key_hex"]),
            parsed_config["approver"]["key_id"],
            bytes.fromhex(parsed_config["approver"]["public_key_hex"]),
        )
    except (KeyError, TypeError, ValueError):
        return ("RECEIPT_OR_SIGNATURE_INVALID",)
    body = receipt["body"]
    cell = body["cell"]
    if (cell["repo_id"], cell["arm_id"]) not in EXPECTED_CELLS or cell["attempt"] != 1:
        violations.append("CELL_IDENTITY_MISMATCH")
    if dict(body["counters"]) != dict(ZERO_COUNTERS):
        violations.append("COUNTERS_NONZERO")
    if body["environment"]["network_mode"] != "none":
        violations.append("NETWORK_MODE_MISMATCH")
    if any(execution["exit_code"] != 0 for execution in body["executions"]):
        violations.append("EXECUTION_FAILED")

    if plan is not None:
        expected = (
            _plan_value(plan, "repo_id"),
            _plan_value(plan, "arm_id"),
            _plan_value(plan, "attempt"),
            _plan_value(plan, "artifact_path"),
        )
        observed = (
            cell["repo_id"],
            cell["arm_id"],
            cell["attempt"],
            cell["artifact_path"],
        )
        if observed != expected:
            violations.append("PLAN_IDENTITY_MISMATCH")
        digest = (
            getattr(plan, "digest", None) or plan.get("digest") or plan.get("plan_hash")
        )
        if body["plan"]["plan_hash"] != digest:
            violations.append("PLAN_HASH_MISMATCH")
        executions = _plan_value(plan, "executions")
        expected_exec = tuple(
            (
                _item_value(item, "execution_id", "id"),
                list(_item_value(item, "argv", "argv")),
                _item_value(item, "cwd", "cwd"),
                _item_value(item, "environment_digest", "environment_digest"),
            )
            for item in executions
        )
        observed_exec = tuple(
            (item["id"], item["argv"], item["cwd"], item["environment_digest"])
            for item in body["executions"]
        )
        if observed_exec != expected_exec:
            violations.append("EXECUTION_PLAN_MISMATCH")

    if inventory is not None:
        expected_inventory = json.loads(canonical_json_bytes(inventory))
        if body["source"]["eligibility"] != expected_inventory:
            violations.append("SOURCE_INVENTORY_MISMATCH")
        if body["source"]["commit"] != expected_inventory.get("commit"):
            violations.append("SOURCE_COMMIT_MISMATCH")
        if body["source"]["repo_fingerprint"] != expected_inventory.get(
            "repo_fingerprint"
        ):
            violations.append("SOURCE_FINGERPRINT_MISMATCH")

    if verifier_pid is not None:
        if type(verifier_pid) is not int or verifier_pid in {
            body["process_audit"].get("pid1_exit"),
            os.getppid(),
        }:
            violations.append("VERIFIER_NOT_FRESH")

    if core_root is not None:
        try:
            if not core_root.is_dir():
                raise ValueError("core root is absent")
            for execution in body["executions"]:
                for field in (
                    "stdout_bytes",
                    "stderr_bytes",
                    "query_bytes",
                    "index_bytes",
                ):
                    blob = execution[field]
                    payload = _read_regular(core_root, blob["path"], blob["size_bytes"])
                    if hashlib.sha256(payload).hexdigest() != blob["sha256"]:
                        raise ValueError("raw hash mismatch")
            for container, field in (
                (body["process_audit"], "audit_bytes"),
                (body["oracle_approval"], "approval_bytes"),
            ):
                blob = container[field]
                payload = _read_regular(core_root, blob["path"], blob["size_bytes"])
                if hashlib.sha256(payload).hexdigest() != blob["sha256"]:
                    raise ValueError("audit hash mismatch")
            if _tree_hash(core_root) != body["snapshot"]["tree_hash"]:
                raise ValueError("tree hash mismatch")
        except (OSError, ValueError):
            violations.append("SNAPSHOT_BYTES_MISMATCH")
    return tuple(dict.fromkeys(violations))


def aggregate_verdict(
    receipts: Sequence[Mapping[str, Any]],
    cell_violations: Sequence[Sequence[str]] | None = None,
) -> dict[str, Any]:
    identities = [
        (
            item.get("body", {}).get("cell", {}).get("repo_id"),
            item.get("body", {}).get("cell", {}).get("arm_id"),
        )
        for item in receipts
    ]
    attempts = [
        item.get("body", {}).get("cell", {}).get("attempt") for item in receipts
    ]
    plan_sets = {
        item.get("body", {}).get("plan", {}).get("plan_set_hash") for item in receipts
    }
    violations = list(cell_violations or [() for _ in receipts])
    qualified = (
        len(receipts) == 14
        and identities == list(EXPECTED_CELLS)
        and len(set(identities)) == 14
        and attempts == [1] * 14
        and len(plan_sets) == 1
        and None not in plan_sets
        and len(violations) == 14
        and all(tuple(item) == () for item in violations)
    )
    return {
        "schema_version": 1,
        **CLAIMS,
        "status": "SETUP_QUALIFIED" if qualified else "NOT_EVALUATED",
        "expected_cells": 14,
        "observed_receipts": len(receipts),
        "attempts_per_cell": 1 if attempts == [1] * len(receipts) else None,
        "counters": dict(ZERO_COUNTERS),
    }


def _load(path: str) -> dict[str, Any]:
    return strict_json_loads(Path(path).read_bytes())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cell = sub.add_parser("cell")
    cell.add_argument("--receipt", required=True)
    cell.add_argument("--public-config", required=True)
    cell.add_argument("--core-root")
    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--receipts", nargs="+", required=True)
    aggregate.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "cell":
        violations = verify_cell(
            _load(args.receipt),
            public_config=_load(args.public_config),
            core_root=Path(args.core_root) if args.core_root else None,
            verifier_pid=os.getpid(),
        )
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    **CLAIMS,
                    "status": "PASS" if not violations else "NOT_EVALUATED",
                    "violations": list(violations),
                },
                sort_keys=True,
            )
        )
        return 0 if not violations else 1
    receipts = [_load(path) for path in args.receipts]
    verdict = aggregate_verdict(receipts)
    output = Path(args.output)
    if output.exists():
        raise ValueError("verdict output must be fresh")
    output.write_bytes(canonical_json_bytes(verdict) + b"\n")
    return 0 if verdict["status"] == "SETUP_QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
