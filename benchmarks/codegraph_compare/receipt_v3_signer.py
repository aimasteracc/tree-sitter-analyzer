"""Isolated stdout-only signer CLI for NO1-008A receipt v3."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from benchmarks.codegraph_compare.receipt_v3 import (
    approve_executor_attestation,
    canonical_json_bytes,
    create_executor_attestation,
    strict_json_loads,
)
from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree
from benchmarks.codegraph_compare.verifier import (
    _extract_ext4,
    _sha_file,
    _verify_external_audit,
    _verify_recomputed,
    _verify_trusted_inputs,
    _verify_verity,
    parse_public_config,
)


def _safe_path(raw: str) -> Path:
    if not raw or "," in raw or any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise ValueError("path contains comma or control character")
    path = Path(raw)
    if str(path).startswith("/proc/self/fd/"):
        os.fstat(int(path.name))
        return path
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("path must be an existing canonical absolute path")
    return path


def _read_private_key(raw: str) -> bytes:
    path = _safe_path(raw)
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = (
        os.dup(int(path.name))
        if str(path).startswith("/proc/self/fd/")
        else os.open(path, flags)
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size != 32
            or stat.S_IMODE(metadata.st_mode) != 0o400
            or metadata.st_uid != os.geteuid()
        ):
            raise ValueError(
                "private key must be one service-owned 0400 32-byte regular file"
            )
        payload = os.pread(descriptor, 32, 0)
        if len(payload) != 32:
            raise ValueError("private key must contain exactly 32 raw bytes")
        return payload
    finally:
        os.close(descriptor)


def _build_body(args: argparse.Namespace) -> dict[str, object]:
    plan = strict_json_loads(_safe_path(args.plan).read_bytes())
    inventory = strict_json_loads(_safe_path(args.inventory).read_bytes())
    core = _safe_path(args.core_root)
    result_path = core / "producer-result.json"
    result = strict_json_loads(result_path.read_bytes())
    audit_path = _safe_path(args.process_audit)
    audit_payload = audit_path.read_bytes()
    audit_envelope = strict_json_loads(audit_payload)
    audit_request = audit_envelope["audit"]
    if (
        type(audit_request) is not dict
        or audit_request.get("protocol") != "no1-008a-audit-v1"
        or audit_request.get("phase") != "terminal"
        or type(audit_request.get("audit")) is not dict
    ):
        raise ValueError("external audit authority request invalid")
    audit = audit_request["audit"]
    data = _safe_path(args.data_image)
    hashes = _safe_path(args.hash_image)
    data_size, data_sha = _sha_file(data)
    hash_size, hash_sha = _sha_file(hashes)
    executions = []
    cpu_seconds = 0.0
    for item in result["executions"]:
        cpu_seconds += item.get("cpu_seconds", 0)
        executions.append(
            {
                key: item[key]
                for key in (
                    "id",
                    "argv",
                    "cwd",
                    "environment_digest",
                    "exit_code",
                    "stdout_bytes",
                    "stderr_bytes",
                    "query_bytes",
                    "final_index_observation",
                )
            }
        )
    partition = dict(plan["index_partition"])
    for name in ("indexed_paths", "excluded_paths", "parse_error_paths"):
        partition[f"{name}_hash"] = hashlib.sha256(
            canonical_json_bytes(partition[name])
        ).hexdigest()
    oracle_hashes = [item["stdout_bytes"]["sha256"] for item in executions[3:]]
    index = core / "index"
    resources = {
        "plan_digest": plan["resource_plan_digest"],
        **audit["resource_observations"],
    }
    eligibility = inventory.get("eligibility", inventory)
    audit_blob = {
        "path": "terminal/process-audit.json",
        "size_bytes": len(audit_payload),
        "sha256": hashlib.sha256(audit_payload).hexdigest(),
    }
    return {
        "run_nonce": args.run_nonce,
        "role_images": {
            role: getattr(args, f"{role}_image_digest")
            for role in ("producer", "executor", "approver", "auditor", "verifier")
        },
        "cell": {**plan["cell"], "artifact_path": plan["artifact_path"]},
        "plan": {
            key: plan[key]
            for key in (
                "plan_hash",
                "plan_set_hash",
                "tool_sha256",
                "config_sha256",
                "image_digest",
                "seccomp_sha256",
            )
        },
        "source": {
            "commit": eligibility["commit"],
            "eligibility": eligibility,
            "repo_fingerprint": eligibility["repo_fingerprint"],
            "mount_target": "/source",
            "read_only": True,
        },
        "environment": {
            "environment_digest": executions[0]["environment_digest"],
            "image_digest": plan["image_digest"],
            "docker_security_flags": [
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
            ],
            "network_mode": "none",
            "seccomp_sha256": plan["seccomp_sha256"],
            "credentials_stripped": True,
        },
        "counters": result["counters"],
        "resources": resources,
        "executions": executions,
        "index_partition": partition,
        "snapshot": {
            "format": "dm-verity-v1",
            "data_image_sha256": data_sha,
            "data_image_size": data_size,
            "hash_image_sha256": hash_sha,
            "hash_image_size": hash_size,
            "root_hash": args.root_hash,
            "salt": args.salt,
            "data_block_size": args.data_block_size,
            "hash_block_size": args.hash_block_size,
            "data_blocks": args.data_blocks,
            "tree_hash": _hash_tree(core),
            "index_content_hash": _hash_tree(index),
        },
        "process_audit": {
            **{
                key: audit[key]
                for key in (
                    "producer_container_id",
                    "actual_image_id",
                    "launch_token_sha256",
                    "container_user",
                    "readonly_rootfs",
                    "cap_drop",
                    "mounts",
                    "resource_limits",
                    "tmpfs",
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
                )
            },
            "audit_bytes": audit_blob,
        },
        "oracle_approval": {
            "approved": True,
            "statement": plan["oracle_statement"],
            "oracle_results_hash": hashlib.sha256(
                canonical_json_bytes(oracle_hashes)
            ).hexdigest(),
        },
    }


def _full_semantic_verify(
    args: argparse.Namespace, body: dict[str, object], config: dict[str, object]
) -> None:
    """Recompute all raw evidence semantics before either service signs."""
    plan = strict_json_loads(_safe_path(args.plan).read_bytes())
    inventory = strict_json_loads(_safe_path(args.inventory).read_bytes())
    evidence = {
        name: getattr(args, name)
        for name in (
            "data_image",
            "hash_image",
            "process_audit",
            "source_snapshot",
            "tool",
            "config",
            "seccomp",
        )
    }
    _verify_trusted_inputs(body, plan, inventory, evidence, config)
    image_fds = _verify_verity(
        body,
        evidence,
        __import__(
            "benchmarks.codegraph_compare.verifier", fromlist=["_run_verity"]
        )._run_verity,
    )
    try:
        _verify_external_audit(body, evidence, config)
        with tempfile.TemporaryDirectory(prefix="no1-008a-semantic-") as temporary:
            extracted = Path(temporary)
            _extract_ext4(Path(f"/proc/self/fd/{image_fds[0]}"), extracted)
            _verify_recomputed(body, plan, inventory, extracted)
    finally:
        for descriptor in image_fds:
            os.close(descriptor)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    executor = subparsers.add_parser("sign-executor")
    executor.add_argument("--body")
    executor.add_argument("--run-nonce")
    for role in ("producer", "executor", "approver", "auditor", "verifier"):
        executor.add_argument(f"--{role}-image-digest")
    executor.add_argument("--plan")
    executor.add_argument("--inventory")
    executor.add_argument("--core-root")
    executor.add_argument("--data-image")
    executor.add_argument("--hash-image")
    executor.add_argument("--process-audit")
    executor.add_argument("--root-hash")
    executor.add_argument("--salt")
    executor.add_argument("--data-block-size", type=int, default=4096)
    executor.add_argument("--hash-block-size", type=int, default=4096)
    executor.add_argument("--data-blocks", type=int)
    for option in ("public-config", "source-snapshot", "tool", "config", "seccomp"):
        executor.add_argument(f"--{option}", required=True)
    executor.add_argument("--private-key", required=True)
    executor.add_argument("--key-id", required=True)
    executor.add_argument("--parent-measurement", required=True)
    approver = subparsers.add_parser("sign-approver")
    approver.add_argument("--attestation", required=True)
    approver.add_argument("--run-nonce", required=True)
    for role in ("producer", "executor", "approver", "auditor", "verifier"):
        approver.add_argument(f"--{role}-image-digest", required=True)
    approver.add_argument("--public-config", required=True)
    for option in (
        "plan",
        "inventory",
        "core-root",
        "data-image",
        "hash-image",
        "process-audit",
        "source-snapshot",
        "tool",
        "config",
        "seccomp",
        "root-hash",
        "salt",
    ):
        approver.add_argument(f"--{option}", required=True)
    approver.add_argument("--data-block-size", type=int, required=True)
    approver.add_argument("--hash-block-size", type=int, required=True)
    approver.add_argument("--data-blocks", type=int, required=True)
    approver.add_argument("--private-key", required=True)
    approver.add_argument("--key-id", required=True)
    approver.add_argument("--parent-measurement", required=True)
    args = parser.parse_args(argv)
    pinned: list[int] = []
    try:
        # Pin every non-image document/source/audit/config input before hash/parse/use.
        for name in (
            "body",
            "attestation",
            "public_config",
            "parent_measurement",
            "plan",
            "inventory",
            "process_audit",
            "source_snapshot",
            "tool",
            "config",
            "seccomp",
        ):
            raw = getattr(args, name, None)
            if raw:
                descriptor = os.open(
                    _safe_path(raw),
                    os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
                )
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    os.close(descriptor)
                    raise ValueError(f"{name} must be regular")
                pinned.append(descriptor)
                setattr(args, name, f"/proc/self/fd/{descriptor}")
        key = _read_private_key(args.private_key)
        config = parse_public_config(_safe_path(args.public_config).read_bytes())
        parent_measurement = strict_json_loads(
            _safe_path(args.parent_measurement).read_bytes()
        )
        if (
            parent_measurement
            != config["trusted"][f"{args.command.removeprefix('sign-')}_runtime"][
                "measurement"
            ]
        ):
            raise ValueError("signer subprocess parent runtime measurement mismatch")
        if args.command == "sign-executor":
            evidence_args = (
                args.plan,
                args.inventory,
                args.core_root,
                args.data_image,
                args.hash_image,
                args.process_audit,
                args.root_hash,
                args.salt,
                args.data_blocks,
            )
            if bool(args.body) == all(value is not None for value in evidence_args):
                raise ValueError("provide either one body or the complete evidence set")
            if args.body:
                raise ValueError(
                    "executor signing requires complete independent raw evidence"
                )
            body = _build_body(args)
            if args.key_id != config["executor"]["key_id"]:
                raise ValueError("executor key ID does not match public config")
            _full_semantic_verify(args, body, config)
            result = create_executor_attestation(body, args.key_id, key)
        else:
            attestation = strict_json_loads(_safe_path(args.attestation).read_bytes())
            if args.key_id != config["approver"]["key_id"]:
                raise ValueError("approver key ID does not match public config")
            # Independent semantic approval: consume every raw oracle/snapshot/audit input,
            # rebuild the complete body, and reject before signing unless byte-identical.
            recomputed = _build_body(args)
            if canonical_json_bytes(recomputed) != canonical_json_bytes(
                attestation.get("body")
            ):
                raise ValueError("approver full evidence/oracle verification mismatch")
            _full_semantic_verify(args, recomputed, config)
            result = approve_executor_attestation(
                attestation,
                config["executor"]["key_id"],
                bytes.fromhex(config["executor"]["public_key_hex"]),
                args.key_id,
                key,
            )
        # The only handoff is one canonical document on stdout; never write a directory.
        sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
        return 0
    finally:
        while pinned:
            os.close(pinned.pop())


if __name__ == "__main__":
    raise SystemExit(main())
