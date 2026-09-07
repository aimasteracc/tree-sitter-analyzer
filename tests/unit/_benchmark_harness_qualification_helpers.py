"""Issue #1376：_qualification_helpers 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


def _verifier_recovery_fixture():
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    manifest = {
        "cells": [
            {
                "contract": {
                    "decision_id": "1" * 64,
                    "decision_contract_sha256": "2" * 64,
                }
            }
        ]
    }
    raw = canonical_json_bytes(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    measurement = {"runtime": "trusted"}
    config = {
        "verifier": {"key_id": "verifier", "public_key_hex": "00" * 32},
        "trusted": {"verifier_runtime": {"measurement": measurement}},
    }
    begin_signed = {
        "manifest_sha256": digest,
        "challenge": "3" * 64,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 7,
        "service_identity": measurement,
    }
    begin = {
        **begin_signed,
        "key_id": "verifier",
        "algorithm": "Ed25519",
        "signature": "00" * 64,
    }
    consumed = {
        "counter": 2,
        "event": "CONSUMED",
        "challenge": "3" * 64,
        "manifest_sha256": digest,
    }

    def proof(record):
        return {
            "record": record,
            "key_id": "verifier",
            "algorithm": "Ed25519",
            "signature": "00" * 64,
        }

    envelope = {
        "manifest_sha256": digest,
        "decision_id": "1" * 64,
        "decision_contract_sha256": "2" * 64,
        "challenge": "3" * 64,
        "ledger_counter": 2,
        "ledger_prev_hash": "4" * 64,
        "issued_at_ns": 7,
        "verdict": {},
        "service_identity": measurement,
        "consumption_record": proof(consumed),
        "ledger_head": proof({"counter": 2, "record_hash": "5" * 64}),
        "key_id": "verifier",
        "algorithm": "Ed25519",
        "signature": "00" * 64,
    }
    return manifest, config, begin, envelope


def _disable_verifier_signature_checks(monkeypatch, verifier_service):
    class PublicKey:
        @staticmethod
        def from_public_bytes(_raw):
            return PublicKey()

        def verify(self, _signature, _message):
            return None

    monkeypatch.setattr(verifier_service, "Ed25519PublicKey", PublicKey)
    monkeypatch.setattr(verifier_service, "_validate_verdict_schema", lambda _v: None)


def _qualification_git_repo(path: Path) -> str:
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "main.ts").write_text("export class Main {}\n", encoding="utf-8")
    (path / "generated.ts").write_text("// @generated DO NOT EDIT\n", encoding="utf-8")
    (path / "notes.md").write_text("notes\n", encoding="utf-8")
    (path / "linked.ts").symlink_to("main.ts")
    subprocess.run(
        ["git", "add", "main.ts", "generated.ts", "notes.md", "linked.ts"],
        cwd=path,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=path, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(
        [
            "git",
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{commit},deps/submodule",
        ],
        cwd=path,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "gitlink"], cwd=path, check=True)
    (path / "deps" / "submodule").mkdir(parents=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _qualification_oracles():
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    return (
        OracleSpecV1(
            "main.symbol", "symbol", (("name", "Main"),), {"path": "main.ts", "line": 1}
        ),
        OracleSpecV1(
            "main.call",
            "call",
            (("callee", "Main"), ("caller", "entry")),
            [{"path": "main.ts"}],
        ),
    )


def _qualification_source_inventory(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    return inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def _qualification_verifier_config():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare.setup_qualification_trust import VerifierConfigV1

    return VerifierConfigV1(
        executor_key_id="test-executor",
        executor_public_key=Ed25519PrivateKey.from_private_bytes(b"\x02" * 32)
        .public_key()
        .public_bytes_raw(),
        approver_key_id="test-approver",
        approver_public_key=Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
        .public_key()
        .public_bytes_raw(),
    )


def _qualification_inventories(plans):
    return {plan.repo_id: plan.eligibility for plan in plans}


def _qualification_plans(tmp_path: Path):
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        EXPECTED_CELLS,
        FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
        CellPlanV1,
        EligibilityV1,
        ExecutionSpecV1,
        HarnessArtifactV1,
        ResourcePlanV1,
    )

    tool_path = tmp_path / "tool.bin"
    config_path = tmp_path / "config.json"
    tool_path.write_bytes(b"pinned executable")
    config_path.write_bytes(b'{"offline":true}')
    tool = HarnessArtifactV1.read(tool_path)
    config = HarnessArtifactV1.read(config_path)
    import yaml

    commits = {
        item["id"]: item["commit"]
        for item in yaml.safe_load(
            Path("benchmarks/codegraph_compare/repos.yaml").read_text(encoding="utf-8")
        )["repos"]
    }
    base = EligibilityV1(
        "vscode",
        DEFAULT_SOURCE_RULES.digest,
        commits["vscode"],
        ("main.ts",),
        (("main.ts", "100644", "a" * 40),),
        (("main.ts", "100644", "a" * 40, 1, "e" * 64),),
        ("main.ts",),
        (),
        "b" * 64,
        "c" * 64,
        "d" * 64,
    )
    resources = ResourcePlanV1(30, 20, 1024, 4096, 1, 1024, 2, 8, 1)
    source_checkout = (tmp_path / "source-checkout").resolve()
    source_checkout.mkdir(exist_ok=True)
    return tuple(
        CellPlanV1(
            repo,
            arm,
            1,
            f"cells/{repo}/{arm}/cell-receipt.json",
            f"cells/{repo}/{arm}/index",
            source_checkout.as_posix(),
            replace(base, repo_id=repo, commit=commits[repo]),
            tool,
            config,
            _qualification_oracles(),
            resources,
            (
                ExecutionSpecV1(
                    "delete",
                    (
                        str(tool_path),
                        "delete",
                        "--config",
                        str(config_path),
                        "--index",
                        (tmp_path / "cells" / repo / arm / "index")
                        .resolve()
                        .as_posix(),
                    ),
                    tmp_path.resolve().as_posix(),
                    FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
                ),
                ExecutionSpecV1(
                    "build",
                    (
                        str(tool_path),
                        "build",
                        "--config",
                        str(config_path),
                        "--source",
                        source_checkout.as_posix(),
                        "--index",
                        (tmp_path / "cells" / repo / arm / "index")
                        .resolve()
                        .as_posix(),
                    ),
                    source_checkout.as_posix(),
                    FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
                ),
                ExecutionSpecV1(
                    "health",
                    (
                        str(tool_path),
                        "health",
                        "--config",
                        str(config_path),
                        "--index",
                        (tmp_path / "cells" / repo / arm / "index")
                        .resolve()
                        .as_posix(),
                    ),
                    tmp_path.resolve().as_posix(),
                    FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
                ),
                *(
                    ExecutionSpecV1(
                        spec.oracle_id,
                        (
                            str(tool_path),
                            spec.kind,
                            "--config",
                            str(config_path),
                            *sum(
                                ((f"--{key}", value) for key, value in spec.query),
                                (),
                            ),
                            "--index",
                            (tmp_path / "cells" / repo / arm / "index")
                            .resolve()
                            .as_posix(),
                        ),
                        tmp_path.resolve().as_posix(),
                        FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
                    )
                    for spec in _qualification_oracles()
                ),
            ),
        )
        for repo, arm in EXPECTED_CELLS
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
    # The externally sealed snapshot includes the already-created receipt inode.
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
