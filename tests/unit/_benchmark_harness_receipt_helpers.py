"""Issue #1376：_benchmark_harness_receipt_helpers 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from tests.unit._benchmark_harness_qualification_helpers import (
    _qualification_verifier_config,
)


def _write_valid_qualification_receipt(cell_root: Path, plan):
    import json
    from dataclasses import asdict

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    import benchmarks.codegraph_compare.setup_qualification as qualification
    from benchmarks.codegraph_compare.integrity import _sha256
    from benchmarks.codegraph_compare.setup_qualification import (
        ZERO_COUNTERS,
        _bytes_hash,
        _hash_tree,
    )

    verifier_config = _qualification_verifier_config()

    def sign(seed: bytes, payload):
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return Ed25519PrivateKey.from_private_bytes(seed * 32).sign(encoded).hex()

    cell_root.mkdir(parents=True, exist_ok=False)
    # 外部封存快照包含已经创建的 receipt inode。
    (cell_root / "cell-receipt.json").touch()
    index = cell_root / "index"
    index.mkdir()
    (index / "index.bin").write_bytes(b"frozen index")

    def blob(relative: str, payload: bytes):
        path = cell_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return {
            "path": relative,
            "size_bytes": len(payload),
            "sha256": _bytes_hash(payload),
        }

    executions = []
    specs = {spec.oracle_id: spec for spec in plan.oracle_specs}
    for number, execution in enumerate(plan.executions):
        identifier = execution.execution_id
        spec = specs.get(identifier)
        stdout = b"{}" if spec is None else spec.expected_result
        query = (
            b"{}"
            if spec is None
            else json.dumps(
                dict(spec.query), sort_keys=True, separators=(",", ":")
            ).encode()
        )
        item = {
            "id": identifier,
            "argv": list(execution.argv),
            "cwd": execution.cwd,
            "exit_code": 0,
            "environment_digest": execution.environment_digest,
            "stdout_bytes": blob(f"raw/{number}-stdout", stdout),
            "stderr_bytes": blob(f"raw/{number}-stderr", b""),
            "query_bytes": blob(f"raw/{number}-query", query),
            "index_bytes": blob(f"raw/{number}-index", b"frozen index"),
        }
        if spec is not None:
            item["oracle_spec_hash"] = spec.digest
        executions.append(item)
    audit_blob = blob("raw/os-audit", b"deny sockets; process tree audited")
    approval_blob = blob("raw/human-approval", b"approved oracle set")
    snapshot_payload = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "snapshot_id": f"snapshot-{plan.repo_id}-{plan.arm_id}",
        "root_identity": list(
            qualification._stable_directory_identity(cell_root.stat())
        ),
        "mount": {"read_only": True},
        "producer_descendants": 0,
        "writes_blocked": True,
    }
    receipt = {
        "schema_version": 2,
        "repo_id": plan.repo_id,
        "arm_id": plan.arm_id,
        "attempt": 1,
        "plan_hash": plan.digest,
        "artifact_path": plan.artifact_path,
        "eligibility": json.loads(json.dumps(asdict(plan.eligibility))),
        "tool": asdict(plan.tool),
        "config": asdict(plan.config),
        "counters": dict(ZERO_COUNTERS),
        "resource_plan_hash": plan.resources.digest,
        "resource_observation": {
            "wall_seconds": 1,
            "cpu_seconds": 1,
            "index_bytes": 12,
            "disk_written_bytes": 128,
            "free_disk_bytes_before": 2,
            "peak_rss_bytes": 512,
            "peak_processes": 1,
            "peak_open_files": 4,
            "peak_concurrency": 1,
        },
        "index_path": plan.index_path,
        "index_content_hash": _hash_tree(index),
        "index_partition": {
            "indexed_paths": sorted(
                set(plan.eligibility.eligible_paths)
                - set(plan.explicit_excluded_allowlist)
                - set(plan.parse_error_allowlist)
            ),
            "excluded_paths": list(plan.explicit_excluded_allowlist),
            "parse_error_paths": list(plan.parse_error_allowlist),
            "parse_error_allowlist": list(plan.parse_error_allowlist),
            "indexed_paths_hash": _sha256(
                sorted(
                    set(plan.eligibility.eligible_paths)
                    - set(plan.explicit_excluded_allowlist)
                    - set(plan.parse_error_allowlist)
                )
            ),
            "excluded_paths_hash": _sha256(list(plan.explicit_excluded_allowlist)),
            "parse_error_paths_hash": _sha256(list(plan.parse_error_allowlist)),
        },
        "raw_executions": executions,
        "snapshot_audit": {
            "payload": snapshot_payload,
            "key_id": verifier_config.executor_key_id,
            "signature": sign(b"\x02", snapshot_payload),
        },
        "index_provenance": {},
        "os_audit": {
            "network_denied": True,
            "credentials_stripped": True,
            "descendants_observed": True,
            "process_audited": True,
            "audit_bytes": audit_blob,
        },
        "human_oracle_approval": {
            "approved": True,
            "approval_bytes": approval_blob,
        },
    }
    core = qualification._evidence_core_payload(
        receipt, plan=plan, actual_index_hash=_hash_tree(index)
    )
    core_digest = _bytes_hash(qualification._canonical_json_bytes(core))
    executor_payload = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "evidence_core_digest": core_digest,
    }
    receipt["index_provenance"] = {
        "payload": executor_payload,
        "key_id": verifier_config.executor_key_id,
        "signature": sign(b"\x02", executor_payload),
    }
    receipt["os_audit"].update(
        {
            "payload": executor_payload,
            "key_id": verifier_config.executor_key_id,
            "signature": sign(b"\x02", executor_payload),
        }
    )
    approval_payload = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "evidence_core_digest": core_digest,
        "approved": True,
        "approval_blob_hash": approval_blob["sha256"],
    }
    receipt["human_oracle_approval"].update(
        {
            "payload": approval_payload,
            "key_id": verifier_config.approver_key_id,
            "signature": sign(b"\x01", approval_payload),
        }
    )
    receipt["receipt_hash"] = _sha256(receipt)
    (cell_root / "cell-receipt.json").write_text(
        json.dumps(receipt, sort_keys=True), encoding="utf-8"
    )
    return receipt


def _validate_qualification_receipt(
    receipt, *, plan, cell_root, verifier_config, sync_retained=True
):
    from benchmarks.codegraph_compare.setup_qualification import (
        _open_root,
        _stable_directory_identity,
        validate_cell_receipt,
    )

    if sync_retained:
        (cell_root / "cell-receipt.json").write_text(
            json.dumps(receipt, sort_keys=True), encoding="utf-8"
        )
    experiment_root = cell_root.parent
    root_fd = _open_root(experiment_root)
    try:
        return validate_cell_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=verifier_config,
            trusted_root_fd=root_fd,
            trusted_root_identity=_stable_directory_identity(os.fstat(root_fd)),
            cell_relative=cell_root.name,
        )
    finally:
        os.close(root_fd)


def _resign_qualification_receipt(receipt):
    from benchmarks.codegraph_compare.integrity import _sha256

    receipt.pop("receipt_hash", None)
    receipt["receipt_hash"] = _sha256(receipt)
    return receipt
