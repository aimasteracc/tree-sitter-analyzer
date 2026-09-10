"""Issue #1376：_benchmark_harness_qualification_helpers 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
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
