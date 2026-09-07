"""Issue #1376：_benchmark_harness_service_helpers 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


def _qualification_v3_body(repo_id="vscode", arm_id="tsa-warm"):
    blob = {
        "path": "raw/empty",
        "size_bytes": 0,
        "sha256": hashlib.sha256(b"").hexdigest(),
    }
    executions = []
    for execution_id in ("delete", "build", "health", "symbol", "call"):
        executions.append(
            {
                "id": execution_id,
                "argv": [
                    "/tool/bin",
                    execution_id,
                    "--source",
                    "/source",
                    "--config",
                    "/config.json",
                ],
                "cwd": "/source",
                "environment_digest": "1" * 64,
                "exit_code": 0,
                "stdout_bytes": dict(blob),
                "stderr_bytes": dict(blob),
                "query_bytes": dict(blob),
                "final_index_observation": dict(blob),
            }
        )
    return {
        "run_nonce": "a" * 64,
        "role_images": {
            "producer": "sha256:" + "6" * 64,
            "executor": "sha256:" + "7" * 64,
            "approver": "sha256:" + "8" * 64,
            "auditor": "sha256:" + "a" * 64,
            "verifier": "sha256:" + "9" * 64,
        },
        "cell": {
            "repo_id": repo_id,
            "arm_id": arm_id,
            "attempt": 1,
            "artifact_path": f"cells/{repo_id}/{arm_id}/cell-receipt.json",
        },
        "plan": {
            "plan_hash": "2" * 64,
            "plan_set_hash": "3" * 64,
            "tool_sha256": "4" * 64,
            "config_sha256": "5" * 64,
            "image_digest": "sha256:" + "6" * 64,
            "seccomp_sha256": "7" * 64,
        },
        "source": {
            "commit": "8" * 40,
            "eligibility": {
                "repo_id": repo_id,
                "source_rules_hash": "4" * 64,
                "commit": "8" * 40,
                "tracked_regular_paths": ["main.ts"],
                "tracked_entries": [["main.ts", "100644", "a" * 40]],
                "root_tree_id": "c" * 40,
                "tracked_files": [["main.ts", "100644", "a" * 40, 1, "b" * 64]],
                "eligible_paths": ["main.ts"],
                "prefilter_exclusions": [],
                "tracked_inventory_hash": "5" * 64,
                "eligible_paths_hash": "6" * 64,
                "repo_fingerprint": "9" * 64,
            },
            "repo_fingerprint": "9" * 64,
            "mount_target": "/source",
            "read_only": True,
        },
        "environment": {
            "environment_digest": "1" * 64,
            "image_digest": "sha256:" + "6" * 64,
            "docker_security_flags": [
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
            ],
            "network_mode": "none",
            "seccomp_sha256": "7" * 64,
            "credentials_stripped": True,
        },
        "counters": {
            "api_cost_usd": 0,
            "input_tokens": 0,
            "model_calls": 0,
            "network_requests": 0,
            "output_tokens": 0,
            "provider_requests": 0,
        },
        "resources": {
            "plan_digest": "a" * 64,
            "wall_ns": 1,
            "cpu_usec": 1,
            "io_bytes": 1,
            "memory_peak_bytes": 1,
            "pids_peak": 1,
        },
        "executions": executions,
        "index_partition": {
            "indexed_paths": ["main.ts"],
            "excluded_paths": [],
            "parse_error_paths": [],
            "indexed_paths_hash": "b" * 64,
            "excluded_paths_hash": "c" * 64,
            "parse_error_paths_hash": "d" * 64,
        },
        "snapshot": {
            "format": "dm-verity-v1",
            "data_image_sha256": "e" * 64,
            "data_image_size": 1,
            "hash_image_sha256": "f" * 64,
            "hash_image_size": 1,
            "root_hash": "0" * 64,
            "salt": "1" * 64,
            "data_block_size": 4096,
            "hash_block_size": 4096,
            "data_blocks": 1,
            "tree_hash": "2" * 64,
            "index_content_hash": "3" * 64,
        },
        "process_audit": {
            "producer_container_id": "producer-1",
            "actual_image_id": "sha256:" + "a" * 64,
            "launch_token_sha256": "b" * 64,
            "container_user": "65532:65532",
            "readonly_rootfs": True,
            "cap_drop": ["ALL"],
            "mounts": [
                ["/host/config", "/config.json", True],
                ["/host/out", "/out", False],
                ["/host/plan", "/plan/cell-plan.json", True],
                ["/host/inventory", "/plan/inventory.json", True],
                ["/host/gate", "/run/no1-008a-launch-gate", True],
                ["/host/seccomp", "/plan/seccomp.json", True],
                ["/host/source", "/source", True],
                ["/host/tool", "/tool/bin", True],
            ],
            "resource_limits": {
                "pids_limit": 64,
                "memory": 4294967296,
                "nano_cpus": 1000000000,
            },
            "tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
            "image_digest": "sha256:" + "6" * 64,
            "cgroup_id": "cg-1",
            "network_mode": "none",
            "security_opt": ["no-new-privileges", "seccomp=" + "7" * 64],
            "restart_count": 0,
            "terminal_pid": 0,
            "launch_count": 1,
            "cgroup_processes_after_stop": [],
            "pid1_exit": 0,
            "run_nonce": "a" * 64,
            "resource_observations": {
                "wall_ns": 1,
                "cpu_usec": 1,
                "io_bytes": 1,
                "memory_peak_bytes": 1,
                "pids_peak": 1,
            },
            "audit_bytes": dict(blob),
        },
        "oracle_approval": {
            "approved": True,
            "statement": "approver authorizes the exact oracle results",
            "oracle_results_hash": hashlib.sha256(
                json.dumps(
                    [blob["sha256"], blob["sha256"]], separators=(",", ":")
                ).encode()
            ).hexdigest(),
        },
    }


def _qualification_v3_receipt(repo_id="vscode", arm_id="tsa-warm"):
    from benchmarks.codegraph_compare.receipt_v3 import (
        assemble_receipt,
        sign_body,
        signature_record,
    )

    body = _qualification_v3_body(repo_id, arm_id)
    executor = signature_record("executor", sign_body(body, b"\x11" * 32))
    approver = signature_record("approver", sign_body(body, b"\x22" * 32))
    return assemble_receipt(body, executor, approver)


def _qualification_v3_public_config():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    role_specs = {
        "executor": (b"\x11" * 32, 901, "a"),
        "approver": (b"\x22" * 32, 902, "b"),
        "auditor": (b"\x33" * 32, 900, "d"),
        "verifier": (b"\x55" * 32, 903, "e"),
        "decision_consumer": (b"\x66" * 32, 904, "f"),
    }
    image_suffixes = {
        "producer": "6",
        "executor": "7",
        "approver": "8",
        "auditor": "a",
        "verifier": "9",
        "decision_consumer": "f",
    }
    image_id_suffixes = dict(zip(image_suffixes, "abcdef", strict=True))

    config = {
        "schema_version": 6,
        **{
            role: {
                "key_id": "verifier-service" if role == "verifier" else role,
                "public_key_hex": Ed25519PrivateKey.from_private_bytes(private)
                .public_key()
                .public_bytes_raw()
                .hex(),
                "protocol": (
                    "no1-008a-audit-v1"
                    if role == "auditor"
                    else f"no1-008a-{role.replace('_', '-')}-service-v1"
                ),
                "peer_uid": uid,
                "service_measurement": measurement * 64,
            }
            for role, (private, uid, measurement) in role_specs.items()
        },
        "trusted": {
            "plan_set_hash": "3" * 64,
            "plan_hashes": {
                f"{repo}/{arm}": "2" * 64
                for repo in (
                    "vscode",
                    "excalidraw",
                    "django",
                    "tokio",
                    "okhttp",
                    "gin",
                    "alamofire",
                )
                for arm in ("tsa-warm", "codegraph-warm")
            },
            "plan_document_sha256": {
                f"{repo}/{arm}": "1" * 64
                for repo in (
                    "vscode",
                    "excalidraw",
                    "django",
                    "tokio",
                    "okhttp",
                    "gin",
                    "alamofire",
                )
                for arm in ("tsa-warm", "codegraph-warm")
            },
            "inventory_sha256": dict.fromkeys(
                (
                    "vscode",
                    "excalidraw",
                    "django",
                    "tokio",
                    "okhttp",
                    "gin",
                    "alamofire",
                ),
                "4" * 64,
            ),
            "source_snapshot_sha256": dict.fromkeys(
                (
                    "vscode",
                    "excalidraw",
                    "django",
                    "tokio",
                    "okhttp",
                    "gin",
                    "alamofire",
                ),
                "5" * 64,
            ),
            "tool_sha256": "4" * 64,
            "config_sha256": "5" * 64,
            "seccomp_sha256": "7" * 64,
            "images": {
                role: "sha256:" + suffix * 64 for role, suffix in image_suffixes.items()
            },
            "image_ids": {
                role: "sha256:" + suffix * 64
                for role, suffix in image_id_suffixes.items()
            },
        },
    }
    trusted = config["trusted"]
    for role, (_private, uid, measurement) in role_specs.items():
        trusted[f"{role}_runtime"] = {
            "image_digest": trusted["images"][role],
            "image_id": trusted["image_ids"][role],
            "closure_manifest_sha256": measurement * 64,
            "measurement": {
                "interpreter_sha256": "1" * 64,
                "closure_manifest": {},
                "closure_manifest_sha256": measurement * 64,
                "uid": uid,
                "gid": uid,
                "rootfs_readonly": True,
                "allowed_writable_mounts": [],
            },
        }
    trusted["service_launch"] = {
        role: {
            "image_id": trusted["image_ids"][role],
            "cmd": ["python", "-m", f"benchmarks.codegraph_compare.{role}_service"],
            "entrypoint": None,
            "user": str(uid),
            "readonly_rootfs": True,
            "mounts": [],
            "network_mode": "none",
            "security_opt": ["no-new-privileges:true"],
        }
        for role, (_private, uid, _measurement) in role_specs.items()
    }
    return _sign_qualification_v3_config(config)


def _sign_qualification_v3_config(config):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.verifier import ROOT_SIGNATURE_DOMAIN

    unsigned = {key: value for key, value in config.items() if key != "root_signature"}
    config["root_signature"] = (
        Ed25519PrivateKey.from_private_bytes(b"\x44" * 32)
        .sign(ROOT_SIGNATURE_DOMAIN + canonical_json_bytes(unsigned))
        .hex()
    )
    return config


def _qualification_v3_manifest():
    from benchmarks.codegraph_compare.setup_qualification import EXPECTED_CELLS

    return {
        "schema_version": 1,
        "verifier_nonce": "a" * 64,
        "verifier_image_digest": "sha256:" + "b" * 64,
        "run_contract": {"plan_set_hash": "3" * 64, "run_nonce": "a" * 64},
        "cells": [
            {
                "repo_id": repo,
                "arm_id": arm,
                "attempt": 1,
                "plan": {"identity": f"{repo}/{arm}"},
                "inventory": {"repo_id": repo},
                "receipt": _qualification_v3_receipt(repo, arm),
                "data_image": "/evidence/data.img",
                "hash_image": "/evidence/hash.img",
                "process_audit": "/evidence/process-audit.json",
                "source_snapshot": "/evidence/source.tar",
                "tool": "/evidence/tool",
                "config": "/evidence/config",
                "seccomp": "/evidence/seccomp",
            }
            for repo, arm in EXPECTED_CELLS
        ],
    }


def _diagnostic_authority_server(socket_path: Path, key: bytes):
    import socket
    import threading

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare.host_auditor import DOMAIN
    from benchmarks.codegraph_compare.receipt_v3 import (
        canonical_json_bytes,
        strict_json_loads,
    )

    ready = threading.Event()

    def serve():
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        ready.set()
        connection, _ = listener.accept()
        header = connection.recv(4)
        size = struct.unpack("!I", header)[0]
        wire = bytearray()
        while len(wire) < size:
            wire.extend(connection.recv(size - len(wire)))
        request = strict_json_loads(bytes(wire))
        envelope = {
            "audit": request,
            "key_id": "auditor",
            "algorithm": "Ed25519",
            "signature": Ed25519PrivateKey.from_private_bytes(key)
            .sign(DOMAIN + canonical_json_bytes(request))
            .hex(),
        }
        response = canonical_json_bytes(envelope)
        connection.sendall(struct.pack("!I", len(response)) + response)
        connection.close()
        listener.close()
        socket_path.unlink(missing_ok=True)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    ready.wait(timeout=5)
    return thread


def _authority_runner_for_test(tmp_path: Path):
    import threading

    from benchmarks.codegraph_compare.audit_authority_runner import AuthorityRunner

    runner = AuthorityRunner.__new__(AuthorityRunner)
    runner._artifacts = tmp_path
    runner._semaphore = threading.BoundedSemaphore(1)
    runner._lock_path = tmp_path / ".authority.lock"
    runner._lock_path.write_bytes(b"")
    return runner


def _mock_authority_cgroup_host(tmp_path: Path, monkeypatch):
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    cgroup = tmp_path / "cgroup"
    cgroup.mkdir()
    (cgroup / "cgroup.controllers").write_text("cpu memory io pids", encoding="utf-8")
    (cgroup / "cgroup.subtree_control").write_text(
        "cpu memory io pids", encoding="utf-8"
    )
    monkeypatch.setattr(authority, "_CGROUP_ROOT", cgroup)
    monkeypatch.setattr(
        authority,
        "_run",
        lambda *_args: b'{"CgroupVersion":"2","CgroupDriver":"cgroupfs"}',
    )
    monkeypatch.setattr(authority.os, "access", lambda *_args: True)
    return authority, cgroup
