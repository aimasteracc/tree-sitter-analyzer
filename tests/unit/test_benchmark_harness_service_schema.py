"""Issue #1376：test_benchmark_harness_service_schema 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import json
import os as os
import sys
from functools import partial
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_service_helpers import (
    _qualification_v3_body,
    _qualification_v3_manifest,
    _qualification_v3_public_config,
    _qualification_v3_receipt,
    _sign_qualification_v3_config,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_qualification_v3_signatures_cover_byte_identical_canonical_body():
    from benchmarks.codegraph_compare.receipt_v3 import verify_receipt

    config = _qualification_v3_public_config()
    receipt = _qualification_v3_receipt()
    verify_receipt(
        receipt,
        config["executor"]["key_id"],
        bytes.fromhex(config["executor"]["public_key_hex"]),
        config["approver"]["key_id"],
        bytes.fromhex(config["approver"]["public_key_hex"]),
    )
    assert (
        receipt["body_sha256"]
        == hashlib.sha256(
            json.dumps(
                receipt["body"],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
    )


def test_qualification_v3_approver_verifies_executor_handoff_before_signing():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare.receipt_v3 import (
        approve_executor_attestation,
        create_executor_attestation,
    )

    body = _qualification_v3_body()
    handoff = create_executor_attestation(body, "executor", b"\x11" * 32)
    receipt = approve_executor_attestation(
        handoff,
        "executor",
        Ed25519PrivateKey.from_private_bytes(b"\x11" * 32)
        .public_key()
        .public_bytes_raw(),
        "approver",
        b"\x22" * 32,
    )

    assert receipt["executor_signature"] == handoff["executor_signature"]


def test_qualification_v3_rejects_body_mutation():
    from benchmarks.codegraph_compare.receipt_v3 import verify_receipt

    receipt = _qualification_v3_receipt()
    receipt["body"]["cell"]["repo_id"] = "gin"
    config = _qualification_v3_public_config()
    with pytest.raises(ValueError, match="artifact path|body hash mismatch"):
        verify_receipt(
            receipt,
            "executor",
            bytes.fromhex(config["executor"]["public_key_hex"]),
            "approver",
            bytes.fromhex(config["approver"]["public_key_hex"]),
        )


def test_qualification_v3_rejects_signature_swap():
    from benchmarks.codegraph_compare.receipt_v3 import verify_receipt

    receipt = _qualification_v3_receipt()
    (
        receipt["executor_signature"]["signature"],
        receipt["approver_signature"]["signature"],
    ) = (
        receipt["approver_signature"]["signature"],
        receipt["executor_signature"]["signature"],
    )
    receipt["receipt_hash"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in receipt.items() if k != "receipt_hash"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    config = _qualification_v3_public_config()
    with pytest.raises(ValueError, match="signature mismatch"):
        verify_receipt(
            receipt,
            "executor",
            bytes.fromhex(config["executor"]["public_key_hex"]),
            "approver",
            bytes.fromhex(config["approver"]["public_key_hex"]),
        )


def test_qualification_v3_rejects_duplicate_json_member():
    from benchmarks.codegraph_compare.receipt_v3 import strict_json_loads

    with pytest.raises(ValueError, match="duplicate JSON member"):
        strict_json_loads(b'{"schema_version":3,"schema_version":3}')


def test_qualification_v3_rejects_nan():
    from benchmarks.codegraph_compare.receipt_v3 import strict_json_loads

    with pytest.raises(ValueError, match="non-finite"):
        strict_json_loads(b'{"value":NaN}')


def test_qualification_v3_rejects_extra_nested_field():
    from benchmarks.codegraph_compare.receipt_v3 import validate_body

    body = _qualification_v3_body()
    body["cell"]["unexpected"] = False
    with pytest.raises(ValueError, match="unknown or missing fields"):
        validate_body(body)


def test_qualification_v3_rejects_noncanonical_artifact_path():
    from benchmarks.codegraph_compare.receipt_v3 import validate_body

    body = _qualification_v3_body()
    body["cell"]["artifact_path"] = "cells/../receipt.json"
    with pytest.raises(ValueError, match="artifact path|not canonical"):
        validate_body(body)


def test_qualification_v3_aggregate_requires_public_config_and_full_verification(
    monkeypatch,
):
    from benchmarks.codegraph_compare import verifier_aggregate as verifier

    manifest = _qualification_v3_manifest()
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    plan_hashes = [
        hashlib.sha256(canonical_json_bytes(cell["plan"])).hexdigest()
        for cell in manifest["cells"]
    ]
    plan_set_hash = hashlib.sha256(canonical_json_bytes(plan_hashes)).hexdigest()
    for cell in manifest["cells"]:
        cell["plan"]["plan_set_hash"] = plan_set_hash
    config = _qualification_v3_public_config()
    config["trusted"]["plan_set_hash"] = plan_set_hash
    manifest["run_contract"]["plan_set_hash"] = plan_set_hash
    config["trusted"]["plan_hashes"] = {
        f"{cell['repo_id']}/{cell['arm_id']}": digest
        for cell, digest in zip(manifest["cells"], plan_hashes, strict=True)
    }
    config["trusted"]["plan_document_sha256"] = {
        f"{cell['repo_id']}/{cell['arm_id']}": hashlib.sha256(
            canonical_json_bytes(cell["plan"])
        ).hexdigest()
        for cell in manifest["cells"]
    }
    _sign_qualification_v3_config(config)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import trust_anchor

    monkeypatch.setattr(
        trust_anchor,
        "baked_root_public_key",
        lambda: (
            Ed25519PrivateKey.from_private_bytes(b"\x44" * 32)
            .public_key()
            .public_bytes_raw()
        ),
    )
    monkeypatch.setattr(verifier, "verify_cell", lambda *args, **kwargs: ())
    diagnostic_root = (
        Ed25519PrivateKey.from_private_bytes(b"\x44" * 32)
        .public_key()
        .public_bytes_raw()
    )
    assert (
        verifier.aggregate_verdict(
            manifest,
            public_config=config,
            diagnostic_mode=True,
            diagnostic_root_public_key=diagnostic_root,
        )["status"]
        == "NOT_EVALUATED"
    )
    assert (
        verifier.aggregate_verdict(manifest, public_config=config)["status"]
        == "SETUP_QUALIFIED"
    )


def test_qualification_v3_aggregate_rejects_reordered_cells(monkeypatch):
    from benchmarks.codegraph_compare import verifier

    manifest = _qualification_v3_manifest()
    manifest["cells"][0], manifest["cells"][1] = (
        manifest["cells"][1],
        manifest["cells"][0],
    )
    monkeypatch.setattr(verifier, "verify_cell", lambda *args, **kwargs: ())
    assert (
        verifier.aggregate_verdict(
            manifest, public_config=_qualification_v3_public_config()
        )["status"]
        == "NOT_EVALUATED"
    )


def test_qualification_v3_aggregate_has_no_default_empty_violations():
    from benchmarks.codegraph_compare.verifier import aggregate_verdict

    with pytest.raises(TypeError, match="public_config"):
        aggregate_verdict({})


def test_qualification_v3_aggregate_claims_remain_e0_and_disabled():
    from benchmarks.codegraph_compare.verifier import aggregate_verdict

    verdict = aggregate_verdict({}, public_config=_qualification_v3_public_config())
    assert {
        key: verdict[key]
        for key in (
            "evaluation_stage",
            "status",
            "publishable",
            "winner",
            "dominance_allowed",
            "unlock_allowed",
        )
    } == {
        "evaluation_stage": "E0",
        "status": "NOT_EVALUATED",
        "publishable": False,
        "winner": None,
        "dominance_allowed": False,
        "unlock_allowed": False,
    }


def test_qualification_executor_fails_closed_without_posix_resource(
    tmp_path: Path, monkeypatch
):
    # PR #1249 run 31334854030: Windows 可以导入 validator，但不能执行资格验证。
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    output = tmp_path / "out"
    monkeypatch.setattr(executor, "_resource", None)

    with pytest.raises(RuntimeError, match="requires POSIX resource limits"):
        executor.produce_cell({}, output)
    assert output.exists() is False


def test_qualification_validator_remains_usable_without_posix_resource(monkeypatch):
    # PR #1249 run 31334854030: 缺少 resource 不能破坏模块收集。
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    monkeypatch.setattr(executor, "_resource", None)

    with pytest.raises(ValueError, match="unknown or missing fields"):
        executor.validate_producer_plan({})


def test_qualification_executor_rejects_nonempty_output(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification_executor import produce_cell

    output = tmp_path / "out"
    output.mkdir()
    (output / "preexisting").write_bytes(b"untrusted")
    with pytest.raises(ValueError, match="fresh empty directory"):
        produce_cell({}, output)


def test_qualification_v3_manifest_requires_each_of_fourteen_complete_cells():
    # Audit 2026-08-09 B2: 聚合授权要求完整的外部清单。
    from benchmarks.codegraph_compare.verifier import validate_manifest

    manifest = _qualification_v3_manifest()
    del manifest["cells"][0]["hash_image"]
    with pytest.raises(ValueError, match="manifest cell"):
        validate_manifest(manifest)


def test_qualification_v3_manifest_rejects_thirteen_cells():
    # Audit 2026-08-09 B2: 不完整的矩阵不能进入聚合验证。
    from benchmarks.codegraph_compare.verifier import validate_manifest

    manifest = _qualification_v3_manifest()
    manifest["cells"].pop()
    with pytest.raises(ValueError, match="exact 14"):
        validate_manifest(manifest)


def test_qualification_v3_operator_delegates_privileged_run_cell_authority():
    operator = Path("scripts/no1_008a_operator.sh").read_text(encoding="utf-8")
    pipeline = Path("benchmarks/codegraph_compare/qualification_operator.py").read_text(
        encoding="utf-8"
    )
    assert (
        "from benchmarks.codegraph_compare.audit_authority_client import run_cell"
        in pipeline
    )
    assert "request_receipt" in pipeline
    assert "docker " not in operator
    assert "mkfs.ext4" not in operator
    assert "/var/run/docker.sock" not in operator


def test_qualification_v3_operator_preflight_requires_contracts_and_authority():
    operator = Path("scripts/no1_008a_operator.sh").read_text(encoding="utf-8")
    assert (
        '"$AUTHORITY_SOCKET" "$EXECUTOR_SOCKET" "$APPROVER_SOCKET" "$VERIFIER_SOCKET"'
        in operator
    )
    assert '"$PUBLIC_CONFIG" "$STAGED_ROOT"' in operator


def test_qualification_v3_schema_fragments_stay_below_file_cap():
    # Audit 2026-08-09 P2.2: 外部引用的 schema 片段必须保持可审阅。
    schemas = sorted(Path("rfcs/schemas").glob("no1-008a-cell-receipt-v3*.schema.json"))
    assert [path.name for path in schemas] == [
        "no1-008a-cell-receipt-v3-body.schema.json",
        "no1-008a-cell-receipt-v3-common.schema.json",
        "no1-008a-cell-receipt-v3-fields-a.schema.json",
        "no1-008a-cell-receipt-v3-fields-b.schema.json",
        "no1-008a-cell-receipt-v3.schema.json",
    ]
    assert {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in schemas
    } == {
        "no1-008a-cell-receipt-v3-body.schema.json": 62,
        "no1-008a-cell-receipt-v3-common.schema.json": 261,
        "no1-008a-cell-receipt-v3-fields-a.schema.json": 211,
        "no1-008a-cell-receipt-v3-fields-b.schema.json": 446,
        "no1-008a-cell-receipt-v3.schema.json": 35,
    }


def test_qualification_v3_operator_uses_only_root_authenticated_public_config():
    operator = Path("scripts/no1_008a_operator.sh").read_text(encoding="utf-8")
    assert "parse_public_config" in operator
    assert "--diagnostic-mode" not in operator
    assert "production CLIs authenticate" not in Path(
        "benchmarks/codegraph_compare/README.md"
    ).read_text(encoding="utf-8")


_mark_posix_qualification_section_tests()
