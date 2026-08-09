"""Manifest aggregation and CLI for the NO1-008A fresh verifier."""

from __future__ import annotations

import argparse
import os
import secrets
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.setup_qualification_paths import (
    canonical_relative_path,
)
from benchmarks.codegraph_compare.setup_qualification_plan import (
    EXPECTED_CELLS,
    ZERO_COUNTERS,
)
from benchmarks.codegraph_compare.verifier import (
    _HEX64,
    _IMAGE,
    CELL_KEYS,
    CLAIMS,
    MANIFEST_KEYS,
    Extractor,
    Runner,
    _exact,
    _extract_ext4,
    _mapping,
    _run_verity,
    _safe_path,
    parse_public_config,
    verify_cell,
)


def validate_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    item = _exact(manifest, MANIFEST_KEYS, "manifest")
    if (
        type(item["schema_version"]) is not int
        or item["schema_version"] != 1
        or _HEX64.fullmatch(item["verifier_nonce"]) is None
        or _IMAGE.fullmatch(item["verifier_image_digest"]) is None
    ):
        raise ValueError("manifest header invalid")
    cells = item["cells"]
    if type(cells) is not list or len(cells) != 14:
        raise ValueError("manifest must contain exact 14 cells")
    identities = []
    for cell in cells:
        exact = _exact(cell, CELL_KEYS, "manifest cell")
        identities.append((exact["repo_id"], exact["arm_id"]))
        if type(exact["attempt"]) is not int or exact["attempt"] != 1:
            raise ValueError("manifest attempt invalid")
        for required in (
            "plan",
            "inventory",
            "receipt",
            "data_image",
            "hash_image",
            "process_audit",
            "source_snapshot",
            "tool",
            "config",
            "seccomp",
        ):
            if exact[required] in (None, "", {}, []):
                raise ValueError("manifest evidence must not be empty")
    if identities != list(EXPECTED_CELLS):
        raise ValueError("manifest cell order invalid")
    return item


def aggregate_verdict(
    manifest: Mapping[str, Any],
    *,
    public_config: Mapping[str, Any],
    runner: Runner = _run_verity,
    extractor: Extractor = _extract_ext4,
    process_identity_factory: Callable[[int], str] | None = None,
) -> dict[str, Any]:
    violations: list[tuple[str, ...]] = []
    observed_receipts = 0
    observed_attempts: list[int] = []
    try:
        exact = validate_manifest(manifest)
        config = parse_public_config(canonical_json_bytes(public_config))
        contract = _mapping(exact["run_contract"], "run contract")
        if contract != {
            "plan_set_hash": config["trusted"]["plan_set_hash"],
            "run_nonce": exact["verifier_nonce"],
        }:
            raise ValueError("fresh run contract mismatch")
        from benchmarks.codegraph_compare.verifier_evidence import _canonical_plan_hash

        plan_hashes = [
            _canonical_plan_hash(_mapping(cell["plan"], "plan"))
            for cell in exact["cells"]
        ]
        import hashlib

        recomputed_plan_set = hashlib.sha256(
            canonical_json_bytes(plan_hashes)
        ).hexdigest()
        if recomputed_plan_set != config["trusted"]["plan_set_hash"] or any(
            cell["plan"].get("plan_set_hash") != recomputed_plan_set
            for cell in exact["cells"]
        ):
            raise ValueError("fourteen-cell canonical plan-set hash mismatch")
        factory = process_identity_factory or (
            lambda number: f"verifier-{os.getpid()}-{number}-{secrets.token_hex(16)}"
        )
        for number, cell in enumerate(exact["cells"]):
            receipt = _mapping(cell["receipt"], "receipt")
            plan = _mapping(cell["plan"], "plan")
            inventory = _mapping(cell["inventory"], "inventory")
            evidence = {
                key: cell[key]
                for key in (
                    "data_image",
                    "hash_image",
                    "process_audit",
                    "source_snapshot",
                    "tool",
                    "config",
                    "seccomp",
                )
            }
            cell_violations = verify_cell(
                receipt,
                public_config=public_config,
                plan=plan,
                inventory=inventory,
                evidence=evidence,
                runner=runner,
                extractor=extractor,
                verifier_nonce=exact["verifier_nonce"],
                verifier_image_digest=exact["verifier_image_digest"],
                process_identity=factory(number),
            )
            violations.append(cell_violations)
            if not cell_violations:
                observed_receipts += 1
                observed_attempts.append(cell["attempt"])
        qualified = len(violations) == 14 and all(item == () for item in violations)
    except (KeyError, TypeError, ValueError):
        qualified = False
    return {
        "schema_version": 1,
        **CLAIMS,
        "status": "SETUP_QUALIFIED" if qualified else "NOT_EVALUATED",
        "expected_cells": 14,
        "observed_receipts": observed_receipts,
        "attempts_per_cell": 1
        if observed_receipts == 14 and observed_attempts == [1] * 14
        else None,
        "counters": dict(ZERO_COUNTERS),
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    raw = strict_json_loads(path.read_bytes())
    root = path.parent.resolve(strict=True)
    validate_manifest(raw)
    contract_relative = canonical_relative_path(raw["run_contract"])
    contract_target = _safe_path(str(root / contract_relative), "run contract")
    if root not in contract_target.parents:
        raise ValueError("run contract escaped controlled root")
    raw["run_contract"] = strict_json_loads(contract_target.read_bytes())
    for cell in raw["cells"]:
        for name in ("plan", "inventory", "receipt"):
            relative = canonical_relative_path(cell[name])
            target = _safe_path(str(root / relative), "manifest document")
            if root not in target.parents:
                raise ValueError("manifest document escaped controlled root")
            cell[name] = strict_json_loads(target.read_bytes())
        for name in (
            "data_image",
            "hash_image",
            "process_audit",
            "source_snapshot",
            "tool",
            "config",
            "seccomp",
        ):
            relative = canonical_relative_path(cell[name])
            target = _safe_path(str(root / relative), "manifest evidence")
            if root not in target.parents:
                raise ValueError("manifest evidence escaped controlled root")
            cell[name] = str(target)
    return raw


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cell = sub.add_parser("cell")
    aggregate = sub.add_parser("aggregate")
    for command in (cell, aggregate):
        command.add_argument("--manifest", required=True)
        command.add_argument("--public-config", required=True)
        command.add_argument("--output", required=True)
        command.add_argument("--verifier-image-digest", required=True)
        command.add_argument("--verifier-nonce", required=True)
    cell.add_argument("--ordinal", required=True, type=int)
    args = parser.parse_args(argv)
    manifest = _load_manifest(_safe_path(args.manifest, "manifest"))
    config = parse_public_config(
        _safe_path(args.public_config, "public config").read_bytes()
    )
    if (
        args.verifier_nonce != manifest["verifier_nonce"]
        or args.verifier_image_digest != manifest["verifier_image_digest"]
    ):
        raise ValueError("verifier binding mismatch")
    if args.command == "aggregate":
        result = aggregate_verdict(manifest, public_config=config)
    else:
        if args.ordinal not in range(14):
            raise ValueError("ordinal must identify one cell")
        item = manifest["cells"][args.ordinal]
        evidence = {
            key: item[key]
            for key in (
                "data_image",
                "hash_image",
                "process_audit",
                "source_snapshot",
                "tool",
                "config",
                "seccomp",
            )
        }
        failures = verify_cell(
            item["receipt"],
            public_config=config,
            plan=item["plan"],
            inventory=item["inventory"],
            evidence=evidence,
            verifier_nonce=args.verifier_nonce,
            verifier_image_digest=args.verifier_image_digest,
            process_identity=f"verifier-{os.getpid()}-{secrets.token_hex(16)}",
        )
        result = {
            "schema_version": 1,
            **CLAIMS,
            "status": "PASS" if not failures else "NOT_EVALUATED",
            "violations": list(failures),
            "verifier_nonce": args.verifier_nonce,
            "verifier_image_digest": args.verifier_image_digest,
        }
    output = Path(args.output)
    if output.exists() or output.parent.resolve(strict=True) != output.parent:
        raise ValueError("output must be fresh beneath canonical parent")
    descriptor = os.open(
        output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.write(descriptor, canonical_json_bytes(result) + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return 0 if result["status"] in {"PASS", "SETUP_QUALIFIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
