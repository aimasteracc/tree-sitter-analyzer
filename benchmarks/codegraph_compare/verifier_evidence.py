"""Immutable trust-root, dm-verity, and signed host-audit verification."""

from __future__ import annotations

import hashlib
import os
import stat
import tarfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)

Runner = Callable[[Sequence[str]], Any]


def _safe_path(raw: Any, label: str) -> Path:
    if (
        type(raw) is not str
        or not raw
        or "," in raw
        or any(ord(c) < 32 or ord(c) == 127 for c in raw)
    ):
        raise ValueError(f"{label} contains a comma or control character")
    path = Path(raw)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError(f"{label} must be canonical, absolute, and existing")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        if stat.S_ISLNK(os.lstat(current).st_mode):
            raise ValueError(f"{label} parent components must not be symbolic links")
    return path


def _sha_file(path: Path) -> tuple[int, str]:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    )
    digest = hashlib.sha256()
    size = 0
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("evidence image is not regular")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return size, digest.hexdigest()


def _canonical_plan_hash(plan: Mapping[str, Any]) -> str:
    unsigned = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_hash", "plan_set_hash"}
    }
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def _sha_evidence(path: Any, label: str) -> str:
    return _sha_file(_safe_path(path, label))[1]


def _verify_trusted_inputs(
    body: Mapping[str, Any],
    plan: Mapping[str, Any],
    inventory: Mapping[str, Any],
    evidence: Mapping[str, Any],
    config: Mapping[str, Any],
) -> None:
    trusted = config["trusted"]
    identity = f"{body['cell']['repo_id']}/{body['cell']['arm_id']}"
    repo = body["cell"]["repo_id"]
    canonical_plan_hash = _canonical_plan_hash(plan)
    if (
        plan.get("plan_hash") != canonical_plan_hash
        or canonical_plan_hash != trusted["plan_hashes"][identity]
    ):
        raise ValueError("canonical plan hash mismatch")
    if (
        plan.get("plan_set_hash") != trusted["plan_set_hash"]
        or body["plan"]["plan_set_hash"] != trusted["plan_set_hash"]
    ):
        raise ValueError("common plan-set hash mismatch")
    if (
        hashlib.sha256(canonical_json_bytes(inventory)).hexdigest()
        != trusted["inventory_sha256"][repo]
    ):
        raise ValueError("canonical inventory hash mismatch")
    if (
        _sha_evidence(evidence["source_snapshot"], "source snapshot")
        != trusted["source_snapshot_sha256"][repo]
    ):
        raise ValueError("immutable source snapshot hash mismatch")
    with tarfile.open(
        _safe_path(evidence["source_snapshot"], "source snapshot"), "r:"
    ) as archive:
        members = archive.getmembers()
        if any(
            member.issym() or member.islnk() or not (member.isfile() or member.isdir())
            for member in members
        ):
            raise ValueError("source snapshot contains unsafe member")
        regular = {member.name for member in members if member.isfile()}
    eligibility = inventory.get("eligibility", inventory)
    if eligibility.get("repo_id") != repo or not set(
        eligibility.get("tracked_regular_paths", ())
    ).issubset(regular):
        raise ValueError("source snapshot does not contain trusted inventory")
    for name in ("tool", "config", "seccomp"):
        if _sha_evidence(evidence[name], name) != trusted[f"{name}_sha256"]:
            raise ValueError(f"trusted {name} bytes mismatch")
    if (
        body["plan"]["tool_sha256"] != trusted["tool_sha256"]
        or body["plan"]["config_sha256"] != trusted["config_sha256"]
        or body["plan"]["seccomp_sha256"] != trusted["seccomp_sha256"]
    ):
        raise ValueError("receipt trust-root digest mismatch")
    images = trusted["images"]
    if body["role_images"] != images:
        raise ValueError("signed role image provenance mismatch")
    if body["environment"]["image_digest"] != images["producer"]:
        raise ValueError("unauthorized producer image")


def _verify_verity(
    body: Mapping[str, Any], evidence: Mapping[str, Any], runner: Runner
) -> tuple[int, int]:
    snapshot = body["snapshot"]
    paths = (
        _safe_path(evidence["data_image"], "data image"),
        _safe_path(evidence["hash_image"], "hash image"),
    )
    descriptors = tuple(
        os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
        for path in paths
    )
    try:
        observed: list[int | str] = []
        for descriptor in descriptors:
            digest = hashlib.sha256()
            size = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
            os.lseek(descriptor, 0, os.SEEK_SET)
            observed.extend((size, digest.hexdigest()))
        if tuple(observed) != (
            snapshot["data_image_size"],
            snapshot["data_image_sha256"],
            snapshot["hash_image_size"],
            snapshot["hash_image_sha256"],
        ):
            raise ValueError("image digest or size mismatch")
        expected_blocks = (
            snapshot["data_image_size"] + snapshot["data_block_size"] - 1
        ) // snapshot["data_block_size"]
        if snapshot["data_blocks"] != expected_blocks:
            raise ValueError("dm-verity data_blocks mismatch")
        result = runner(
            [
                "veritysetup",
                "verify",
                f"/proc/self/fd/{descriptors[0]}",
                f"/proc/self/fd/{descriptors[1]}",
                snapshot["root_hash"],
                "--hash",
                "sha256",
                "--salt",
                snapshot["salt"],
                "--data-block-size",
                str(snapshot["data_block_size"]),
                "--hash-block-size",
                str(snapshot["hash_block_size"]),
                "--data-blocks",
                str(snapshot["data_blocks"]),
            ]
        )
        if result.returncode != 0:
            raise ValueError("veritysetup verification failed")
        return descriptors[0], descriptors[1]
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise


def _verify_external_audit(
    body: Mapping[str, Any], evidence: Mapping[str, Any], config: Mapping[str, Any]
) -> Mapping[str, Any]:
    audit_path = _safe_path(evidence["process_audit"], "signed host audit")
    envelope = strict_json_loads(audit_path.read_bytes())
    if frozenset(envelope) != frozenset({"audit", "key_id", "algorithm", "signature"}):
        raise ValueError("host audit envelope is not closed")
    audit = envelope["audit"]
    required = frozenset(
        {
            "producer_container_id",
            "image_digest",
            "cgroup_id",
            "network_mode",
            "security_opt",
            "restart_count",
            "terminal_pid",
            "launch_count",
            "cgroup_processes_after_stop",
            "pid1_exit",
            "run_nonce",
            "resource_observations",
        }
    )
    if type(audit) is not dict or frozenset(audit) != required:
        raise ValueError("host audit ledger is not closed")
    auditor = config["auditor"]
    if envelope["key_id"] != auditor["key_id"] or envelope["algorithm"] != "Ed25519":
        raise ValueError("host audit authority mismatch")
    try:
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(auditor["public_key_hex"])
        ).verify(
            bytes.fromhex(envelope["signature"]),
            b"NO1-008A-HOST-AUDIT-V1\0" + canonical_json_bytes(audit),
        )
    except (InvalidSignature, ValueError) as error:
        raise ValueError("host audit signature mismatch") from error
    if (
        audit["network_mode"] != "none"
        or audit["restart_count"] != 0
        or audit["terminal_pid"] != 0
        or audit["launch_count"] != 1
        or audit["cgroup_processes_after_stop"] != []
    ):
        raise ValueError(
            "host audit does not prove terminal isolated one-launch execution"
        )
    expected_security = [
        "no-new-privileges",
        f"seccomp={config['trusted']['seccomp_sha256']}",
    ]
    if audit["security_opt"] != expected_security:
        raise ValueError("host audit security options mismatch")
    if audit["run_nonce"] != body["run_nonce"]:
        raise ValueError("signed host audit nonce mismatch")
    if audit["resource_observations"] != {
        key: value for key, value in body["resources"].items() if key != "plan_digest"
    }:
        raise ValueError("resource observations are not host-audit derived")
    expected = {
        key: value
        for key, value in body["process_audit"].items()
        if key != "audit_bytes"
    }
    # Receipt carries only facts that the independently signed audit measures.
    if expected != audit:
        raise ValueError("receipt host audit facts mismatch")
    blob = body["process_audit"]["audit_bytes"]
    payload = audit_path.read_bytes()
    if (
        len(payload) != blob["size_bytes"]
        or hashlib.sha256(payload).hexdigest() != blob["sha256"]
    ):
        raise ValueError("signed host audit bytes mismatch")
    return audit
