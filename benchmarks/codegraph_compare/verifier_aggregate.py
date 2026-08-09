"""Manifest aggregation and CLI for the NO1-008A fresh verifier."""

from __future__ import annotations

import argparse
import hashlib
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
    diagnostic_mode: bool = False,
    diagnostic_root_public_key: bytes | None = None,
) -> dict[str, Any]:
    violations: list[tuple[str, ...]] = []
    observed_receipts = 0
    observed_attempts: list[int] = []
    top_level_reasons: list[str] = []
    if diagnostic_mode:
        top_level_reasons.append("DIAGNOSTIC_ONLY")
    try:
        exact = validate_manifest(manifest)
        config = parse_public_config(
            canonical_json_bytes(public_config),
            diagnostic_mode=diagnostic_mode,
            diagnostic_root_public_key=diagnostic_root_public_key,
        )
        contract = _mapping(exact["run_contract"], "run contract")
        if contract != {
            "plan_set_hash": config["trusted"]["plan_set_hash"],
            "run_nonce": exact["verifier_nonce"],
        }:
            raise ValueError("run correlation contract mismatch")
        from benchmarks.codegraph_compare.receipt_v3 import canonical_plan_hash

        plan_hashes = [
            canonical_plan_hash(_mapping(cell["plan"], "plan"))
            for cell in exact["cells"]
        ]

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
                diagnostic_mode=diagnostic_mode,
                diagnostic_root_public_key=diagnostic_root_public_key,
            )
            violations.append(cell_violations)
            if not cell_violations:
                observed_receipts += 1
                observed_attempts.append(cell["attempt"])
        qualified = (
            not diagnostic_mode
            and len(violations) == 14
            and all(item == () for item in violations)
        )
    except (KeyError, TypeError, ValueError) as error:
        qualified = False
        top_level_reasons.append(f"TOP_LEVEL_INVALID:{type(error).__name__}:{error}")
    return {
        "schema_version": 1,
        **CLAIMS,
        "status": "SETUP_QUALIFIED" if qualified else "NOT_EVALUATED",
        "authorization": "DIAGNOSTIC_ONLY"
        if diagnostic_mode
        else "PRODUCTION_VERIFIER",
        "top_level_reasons": top_level_reasons,
        "expected_cells": 14,
        "observed_receipts": observed_receipts,
        "attempts_per_cell": 1
        if observed_receipts == 14 and observed_attempts == [1] * 14
        else None,
        "counters": dict(ZERO_COUNTERS),
        "cell_diagnostics": [
            {
                "repo_id": EXPECTED_CELLS[index][0],
                "arm_id": EXPECTED_CELLS[index][1],
                "reasons": list(reasons),
            }
            for index, reasons in enumerate(violations)
        ],
    }


def _validate_verdict_schema(value: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "evaluation_stage",
        "publishable",
        "winner",
        "dominance_allowed",
        "unlock_allowed",
        "status",
        "authorization",
        "top_level_reasons",
        "expected_cells",
        "observed_receipts",
        "attempts_per_cell",
        "counters",
        "cell_diagnostics",
    }
    if type(value) is not dict or set(value) != expected:
        raise ValueError("aggregate verdict does not match the published closed schema")
    if (
        value["schema_version"] != 1
        or any(value[name] != expected_value for name, expected_value in CLAIMS.items())
        or value["status"] not in {"SETUP_QUALIFIED", "NOT_EVALUATED"}
        or value["expected_cells"] != 14
        or type(value["observed_receipts"]) is not int
        or value["observed_receipts"] not in range(15)
        or not (
            value["attempts_per_cell"] is None
            or type(value["attempts_per_cell"]) is int
            and value["attempts_per_cell"] == 1
        )
        or type(value["counters"]) is not dict
        or set(value["counters"]) != set(ZERO_COUNTERS)
        or any(
            type(counter) not in {int, float} or counter != 0
            for counter in value["counters"].values()
        )
    ):
        raise ValueError("aggregate verdict constants or counters are invalid")
    if value["authorization"] not in {"PRODUCTION_VERIFIER", "DIAGNOSTIC_ONLY"}:
        raise ValueError("aggregate authorization invalid")
    if value["status"] == "SETUP_QUALIFIED" and (
        value["authorization"] != "PRODUCTION_VERIFIER"
        or value["top_level_reasons"]
        or value["observed_receipts"] != 14
        or value["attempts_per_cell"] != 1
        or len(value["cell_diagnostics"]) != 14
        or any(
            item.get("reasons") != []
            for item in value["cell_diagnostics"]
            if type(item) is dict
        )
    ):
        raise ValueError("only a reason-free production verifier can qualify")
    if type(value["top_level_reasons"]) is not list or any(
        type(reason) is not str for reason in value["top_level_reasons"]
    ):
        raise ValueError("aggregate top-level reasons invalid")
    if value["authorization"] == "DIAGNOSTIC_ONLY" and (
        value["status"] != "NOT_EVALUATED"
        or "DIAGNOSTIC_ONLY" not in value["top_level_reasons"]
    ):
        raise ValueError("diagnostic verdict requires an explicit diagnostic reason")
    diagnostics = value["cell_diagnostics"]
    if type(diagnostics) is not list or len(diagnostics) > 14:
        raise ValueError("aggregate cell diagnostics invalid")
    if len(diagnostics) == 14 and [
        (item.get("repo_id"), item.get("arm_id"))
        if type(item) is dict
        else (None, None)
        for item in diagnostics
    ] != list(EXPECTED_CELLS):
        raise ValueError("aggregate cell diagnostic order invalid")
    for item in diagnostics:
        if (
            type(item) is not dict
            or set(item) != {"repo_id", "arm_id", "reasons"}
            or type(item["repo_id"]) is not str
            or type(item["arm_id"]) is not str
            or type(item["reasons"]) is not list
            or any(type(reason) is not str for reason in item["reasons"])
        ):
            raise ValueError("aggregate cell diagnostic invalid")


_PINNED_FDS: list[int] = []


def _pin_regular(path: Path, label: str) -> str:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    )
    if not __import__("stat").S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError(f"{label} is not regular")
    _PINNED_FDS.append(descriptor)
    return f"/proc/self/fd/{descriptor}"


def _read_regular(path: Path, label: str) -> bytes:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        if not __import__("stat").S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{label} is not regular")
        chunks = bytearray()
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.extend(chunk)
            if len(chunks) > 16 * 1024 * 1024:
                raise ValueError(f"{label} exceeds size limit")
        return bytes(chunks)
    finally:
        os.close(descriptor)


def _load_manifest(path: Path) -> dict[str, Any]:
    raw = strict_json_loads(_read_regular(path, "manifest"))
    root = path.parent.resolve(strict=True)
    validate_manifest(raw)
    contract_relative = canonical_relative_path(raw["run_contract"])
    contract_target = _safe_path(str(root / contract_relative), "run contract")
    if root not in contract_target.parents:
        raise ValueError("run contract escaped controlled root")
    raw["run_contract"] = strict_json_loads(
        _read_regular(contract_target, "run contract")
    )
    for cell in raw["cells"]:
        for name in ("plan", "inventory", "receipt"):
            relative = canonical_relative_path(cell[name])
            target = _safe_path(str(root / relative), "manifest document")
            if root not in target.parents:
                raise ValueError("manifest document escaped controlled root")
            cell[name] = strict_json_loads(_read_regular(target, "manifest document"))
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
            cell[name] = _pin_regular(target, "manifest evidence")
    return raw


def _write_all(descriptor: int, payload: bytes) -> None:
    while payload:
        written = os.write(descriptor, payload)
        if written == 0:
            raise OSError("aggregate output write made no progress")
        payload = payload[written:]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cell = sub.add_parser("cell")
    aggregate = sub.add_parser("aggregate")
    for command in (cell, aggregate):
        command.add_argument("--manifest", required=True)
        command.add_argument("--public-config", required=True)
        command.add_argument("--diagnostic-mode", action="store_true")
        command.add_argument("--diagnostic-root-public-key-hex")
        command.add_argument("--output", required=True)
        command.add_argument("--verifier-image-digest", required=True)
        command.add_argument("--verifier-nonce", required=True)
    cell.add_argument("--ordinal", required=True, type=int)
    args = parser.parse_args(argv)
    manifest = _load_manifest(_safe_path(args.manifest, "manifest"))
    config_payload = _read_regular(
        _safe_path(args.public_config, "root-signed public config"),
        "root-signed public config",
    )
    diagnostic_root = None
    if args.diagnostic_root_public_key_hex is not None:
        if not args.diagnostic_mode:
            raise ValueError("runtime root selection is diagnostic-only")
        try:
            diagnostic_root = bytes.fromhex(args.diagnostic_root_public_key_hex)
        except ValueError as exc:
            raise ValueError("diagnostic root key is malformed") from exc
    config = parse_public_config(
        config_payload,
        diagnostic_mode=args.diagnostic_mode,
        diagnostic_root_public_key=diagnostic_root,
    )
    if (
        args.verifier_nonce != manifest["verifier_nonce"]
        or args.verifier_image_digest != manifest["verifier_image_digest"]
    ):
        raise ValueError("verifier binding mismatch")
    if args.command == "aggregate":
        result = aggregate_verdict(
            manifest,
            public_config=config,
            diagnostic_mode=args.diagnostic_mode,
            diagnostic_root_public_key=diagnostic_root,
        )
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
            diagnostic_mode=args.diagnostic_mode,
            diagnostic_root_public_key=diagnostic_root,
        )
        diagnostic_reasons = ("DIAGNOSTIC_ONLY",) if args.diagnostic_mode else ()
        result = {
            "schema_version": 1,
            **CLAIMS,
            "status": "NOT_EVALUATED" if args.diagnostic_mode or failures else "PASS",
            "violations": list(failures + diagnostic_reasons),
            "verifier_nonce": args.verifier_nonce,
            "verifier_image_digest": args.verifier_image_digest,
            "authorization": "DIAGNOSTIC_ONLY"
            if args.diagnostic_mode
            else "PRODUCTION",
        }
    if args.command == "aggregate":
        _validate_verdict_schema(result)
    output = Path(args.output)
    if output.exists() or output.parent.resolve(strict=True) != output.parent:
        raise ValueError("output must be fresh beneath canonical parent")
    descriptor = os.open(
        output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        _write_all(descriptor, canonical_json_bytes(result) + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return 0 if result["status"] in {"PASS", "SETUP_QUALIFIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
