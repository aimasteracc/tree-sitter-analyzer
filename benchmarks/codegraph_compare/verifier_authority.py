"""Semantic checks for privileged authority evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

AUTHORITY_AUDIT_KEYS = frozenset(
    {
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
        "cell",
        "plan",
        "source",
        "output",
        "terminal",
        "data_image",
        "hash_image",
        "seccomp_sha256",
        "launch_pid",
        "launch_starttime",
        "launch_pidfd_opened",
        "cgroup_populated",
        "cgroup_subtree_populated",
        "launch_token",
        "core_tree_sha256",
        "source_snapshot_sha256",
        "tool_sha256",
        "config_sha256",
    }
)


def verify_authority_provenance(
    audit: Mapping[str, Any], body: Mapping[str, Any], config: Mapping[str, Any]
) -> None:
    auditor = config["auditor"]
    cell_key = f"{body['cell']['repo_id']}/{body['cell']['arm_id']}"
    if audit["cell"] != body["cell"]:
        raise ValueError("authority audit cell is not receipt-bound")
    if (
        audit["plan"].get("sha256")
        != config["trusted"]["plan_document_sha256"][cell_key]
        or audit["plan"].get("canonical_sha256")
        != config["trusted"]["plan_hashes"][cell_key]
    ):
        raise ValueError("authority audit plan is not root-plan-bound")
    if (
        audit["source_snapshot_sha256"]
        != config["trusted"]["source_snapshot_sha256"][body["cell"]["repo_id"]]
    ):
        raise ValueError("authority audit source snapshot mismatch")
    if (
        audit["core_tree_sha256"] != body["snapshot"]["tree_hash"]
        or audit["tool_sha256"] != config["trusted"]["tool_sha256"]
        or audit["config_sha256"] != config["trusted"]["config_sha256"]
        or audit["seccomp_sha256"] != config["trusted"]["seccomp_sha256"]
    ):
        raise ValueError("authority audit terminal staged provenance mismatch")
    if (
        audit["cgroup_populated"] != 0
        or audit["cgroup_subtree_populated"] != []
        or type(audit["launch_pid"]) is not int
        or audit["launch_pid"] <= 0
        or type(audit["launch_starttime"]) is not str
        or not audit["launch_starttime"]
        or audit["launch_pidfd_opened"] is not True
    ):
        raise ValueError("authority launch identity or cgroup quiescence mismatch")
    launch = audit["launch_token"]
    if type(launch) is not dict or frozenset(launch) != {
        "audit",
        "key_id",
        "algorithm",
        "signature",
    }:
        raise ValueError("authority launch token is not retained")
    request = launch["audit"]
    if (
        launch["key_id"] != auditor["key_id"]
        or launch["algorithm"] != "Ed25519"
        or request.get("phase") != "launch"
        or request.get("service_measurement") != auditor["service_measurement"]
        or request.get("audit", {}).get("cell") != body["cell"]
        or request.get("audit", {}).get("run_nonce") != body["run_nonce"]
        or request.get("audit", {}).get("launch_pid") != audit["launch_pid"]
        or request.get("audit", {}).get("launch_starttime") != audit["launch_starttime"]
        or request.get("audit", {}).get("launch_pidfd_opened") is not True
        or request.get("audit", {}).get("cgroup_id") != audit["cgroup_id"]
    ):
        raise ValueError("authority launch token semantic binding mismatch")
    try:
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(auditor["public_key_hex"])
        ).verify(
            bytes.fromhex(launch["signature"]),
            b"NO1-008A-HOST-LAUNCH-V1\0" + canonical_json_bytes(request),
        )
    except (InvalidSignature, ValueError) as error:
        raise ValueError("authority launch token signature mismatch") from error
    if (
        hashlib.sha256(canonical_json_bytes(launch)).hexdigest()
        != audit["launch_token_sha256"]
    ):
        raise ValueError("authority launch token digest mismatch")
