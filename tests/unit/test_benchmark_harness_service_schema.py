"""Issue #1376：service schema 行为组，保留测试逻辑，文本 I/O 显式使用 UTF-8。"""

from __future__ import annotations

import hashlib
import json
import os as os
import struct
import subprocess
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
    # PR #1249 run 31334854030: Windows may import validators but cannot execute.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    output = tmp_path / "out"
    monkeypatch.setattr(executor, "_resource", None)

    with pytest.raises(RuntimeError, match="requires POSIX resource limits"):
        executor.produce_cell({}, output)
    assert output.exists() is False


def test_qualification_validator_remains_usable_without_posix_resource(monkeypatch):
    # PR #1249 run 31334854030: missing resource must not break module collection.
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
    # Audit 2026-08-09 B2: aggregate authority requires a complete external manifest.
    from benchmarks.codegraph_compare.verifier import validate_manifest

    manifest = _qualification_v3_manifest()
    del manifest["cells"][0]["hash_image"]
    with pytest.raises(ValueError, match="manifest cell"):
        validate_manifest(manifest)


def test_qualification_v3_manifest_rejects_thirteen_cells():
    # Audit 2026-08-09 B2: no partial matrix can enter aggregate verification.
    from benchmarks.codegraph_compare.verifier import validate_manifest

    manifest = _qualification_v3_manifest()
    manifest["cells"].pop()
    with pytest.raises(ValueError, match="exact 14"):
        validate_manifest(manifest)


def test_qualification_v3_verity_command_binds_both_image_hashes(tmp_path: Path):
    # Audit 2026-08-09 B3: fresh verifier authenticates data/hash images itself.
    from benchmarks.codegraph_compare.verifier import _verify_verity

    data = tmp_path / "data.img"
    hashes = tmp_path / "hash.img"
    data.write_bytes(b"data")
    hashes.write_bytes(b"hash")
    body = _qualification_v3_body()
    snapshot = body["snapshot"]
    snapshot.update(
        {
            "data_image_size": 4,
            "data_image_sha256": hashlib.sha256(b"data").hexdigest(),
            "hash_image_size": 4,
            "hash_image_sha256": hashlib.sha256(b"hash").hexdigest(),
        }
    )
    commands = []

    def runner(command):
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    _verify_verity(
        body,
        {"data_image": str(data.resolve()), "hash_image": str(hashes.resolve())},
        runner,
    )
    normalized = [
        [
            "/proc/self/fd/<open>" if part.startswith("/proc/self/fd/") else part
            for part in command
        ]
        for command in commands
    ]
    assert normalized == [
        [
            "veritysetup",
            "verify",
            "/proc/self/fd/<open>",
            "/proc/self/fd/<open>",
            "0" * 64,
            "--hash",
            "sha256",
            "--salt",
            "1" * 64,
            "--data-block-size",
            "4096",
            "--hash-block-size",
            "4096",
            "--data-blocks",
            "1",
        ]
    ]


def test_qualification_v3_verity_rejects_mutated_hash_image(tmp_path: Path):
    # Audit 2026-08-09 B3: mutation of either image fails before extraction.
    from benchmarks.codegraph_compare.verifier import _verify_verity

    data = tmp_path / "data.img"
    hashes = tmp_path / "hash.img"
    data.write_bytes(b"data")
    hashes.write_bytes(b"mutated")
    body = _qualification_v3_body()
    body["snapshot"].update(
        {
            "data_image_size": 4,
            "data_image_sha256": hashlib.sha256(b"data").hexdigest(),
            "hash_image_size": 4,
            "hash_image_sha256": hashlib.sha256(b"hash").hexdigest(),
        }
    )
    with pytest.raises(ValueError, match="image digest"):
        _verify_verity(
            body,
            {"data_image": str(data.resolve()), "hash_image": str(hashes.resolve())},
            lambda command: subprocess.CompletedProcess(command, 0, b"", b""),
        )


def test_qualification_v3_run_correlation_requires_process_isolation():
    # Audit 2026-08-09 P1.3: exit codes are never accepted as process identity.
    from benchmarks.codegraph_compare.verifier import verify_cell

    receipt = _qualification_v3_receipt()
    body = receipt["body"]
    failures = verify_cell(
        receipt,
        public_config=_qualification_v3_public_config(),
        plan={},
        inventory={},
        evidence={},
        verifier_nonce="a" * 64,
        verifier_image_digest=body["process_audit"]["image_digest"],
        process_identity="fresh-process",
        diagnostic_mode=True,
        diagnostic_root_public_key=__import__(
            "cryptography.hazmat.primitives.asymmetric.ed25519",
            fromlist=["Ed25519PrivateKey"],
        )
        .Ed25519PrivateKey.from_private_bytes(b"\x44" * 32)
        .public_key()
        .public_bytes_raw(),
    )
    assert failures == (
        "CELL_EVIDENCE_INVALID:verifier process is not isolated from producer",
    )


def test_qualification_v3_runtime_requires_exact_five_execution_order():
    # Audit 2026-08-09 P2.1: runtime and schema pin identical execution cardinality.
    from benchmarks.codegraph_compare.receipt_v3 import validate_body

    body = _qualification_v3_body()
    body["executions"].pop()
    with pytest.raises(ValueError, match="exact delete"):
        validate_body(body)


def test_qualification_v3_decision_commit_disconnect_queries_original_receipt(
    monkeypatch,
):
    # Audit 2026-08-09 B2: an EOF after commit must use the idempotent query path.
    import json

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import decision_consumer_service as consumer
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    config = _qualification_v3_public_config()
    contract = {"decision_id": "d" * 64, "issued_at_ns": 0, "expires_at_ns": 2}
    envelope = {"manifest_sha256": "e" * 64}
    body = {
        "schema_version": 1,
        "decision_id": contract["decision_id"],
        "decision_contract_sha256": hashlib.sha256(
            canonical_json_bytes(contract)
        ).hexdigest(),
        "manifest_sha256": envelope["manifest_sha256"],
        "verdict_status": "SETUP_QUALIFIED",
        "consumed_at_ns": 1,
        "service_identity": config["trusted"]["decision_consumer_runtime"][
            "measurement"
        ],
    }
    receipt = {
        "receipt": body,
        "key_id": config["decision_consumer"]["key_id"],
        "algorithm": "Ed25519",
        "signature": Ed25519PrivateKey.from_private_bytes(b"\x66" * 32)
        .sign(consumer.RECEIPT_DOMAIN + canonical_json_bytes(body))
        .hex(),
    }
    requests = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["decision_consumer"]["peer_uid"], 123)

        def send(self, framed):
            requests.append(json.loads(framed[4:]))
            return len(framed)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    replies = iter(
        (ValueError("frame truncated"), {"status": "consumed", "receipt": receipt})
    )

    def read_reply(*_args):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", read_reply)

    assert (
        consumer.request_decision(
            socket_path=Path("/unused"),
            contract=contract,
            envelope=envelope,
            config=config,
            timeout=1,
        )
        == receipt
    )
    assert [request["operation"] for request in requests] == [
        "consume-decision",
        "query-decision",
    ]
    assert requests[1]["decision_id"] == contract["decision_id"]


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


def test_qualification_v3_runtime_schema_acceptance_parity():
    # Audit 2026-08-09 P2.1: published schema and runtime accept the same emitted receipt.
    from benchmarks.codegraph_compare.receipt_v3 import validate_receipt_shape

    receipt = _qualification_v3_receipt()
    validate_receipt_shape(receipt)


def test_qualification_v3_runtime_schema_mutation_contract():
    # Audit 2026-08-09 P2.1: representative shape mutations have exact parser parity.
    import copy

    from jsonschema import Draft202012Validator

    from benchmarks.codegraph_compare.receipt_v3 import (
        _published_schema,
        validate_receipt_shape,
    )

    schema, registry = _published_schema()
    validator = Draft202012Validator(schema, registry=registry)
    mutations = []
    missing = copy.deepcopy(_qualification_v3_receipt())
    del missing["body"]["run_nonce"]
    mutations.append(missing)
    extra = copy.deepcopy(_qualification_v3_receipt())
    extra["body"]["snapshot"]["mount_flags"] = ["ro"]
    mutations.append(extra)
    order = copy.deepcopy(_qualification_v3_receipt())
    order["body"]["executions"][0]["id"] = "health"
    mutations.append(order)
    duplicate = copy.deepcopy(_qualification_v3_receipt())
    duplicate["body"]["index_partition"]["indexed_paths"] *= 2
    mutations.append(duplicate)
    outcomes = []
    for receipt in mutations:
        try:
            validate_receipt_shape(receipt)
            runtime = True
        except ValueError:
            runtime = False
        schema_valid = not tuple(validator.iter_errors(receipt))
        outcomes.append((runtime, schema_valid))
    assert outcomes == [(False, False), (False, False), (False, False), (False, False)]


def test_receipt_v3_rejects_an_eighth_mount_with_wrong_target():
    # PR #1249 review 3744439666: the launch gate makes exactly eight targets.
    from benchmarks.codegraph_compare.receipt_v3 import validate_receipt_shape

    receipt = _qualification_v3_receipt()
    receipt["body"]["process_audit"]["mounts"][6][1] = "/unexpected"

    with pytest.raises(ValueError, match="mount"):
        validate_receipt_shape(receipt)


def test_receipt_v3_rejects_writable_non_output_mount():
    # PR #1249 review 3744302996: only the producer output mount is writable.
    from benchmarks.codegraph_compare.receipt_v3 import validate_receipt_shape

    receipt = _qualification_v3_receipt()
    receipt["body"]["process_audit"]["mounts"][0][2] = False

    with pytest.raises(ValueError, match="mount"):
        validate_receipt_shape(receipt)


def test_receipt_v3_docker_context_allows_only_five_schema_refs():
    # PR #1249 review 3744303008: the runtime schema COPY needs its exact closure.
    negations = [
        line
        for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.startswith("!rfcs")
    ]

    assert negations == [
        "!rfcs/",
        "!rfcs/schemas/",
        "!rfcs/schemas/no1-008a-cell-receipt-v3.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-body.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-common.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-fields-a.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-fields-b.schema.json",
    ]


def test_qualification_v3_schema_fragments_stay_below_file_cap():
    # Audit 2026-08-09 P2.2: externally referenced schema fragments remain reviewable.
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


def test_public_config_v6_published_schema_accepts_runtime_config():
    # PR #1249 review 3744482399: trusted is the same closed object on both surfaces.
    from jsonschema import Draft202012Validator

    schema = json.loads(
        Path(
            "benchmarks/codegraph_compare/published_schemas/public-config-v6.schema.json"
        ).read_bytes()
    )
    config = _qualification_v3_public_config()

    assert list(Draft202012Validator(schema).iter_errors(config)) == []


def test_public_config_v6_schema_and_runtime_reject_extra_trusted_field():
    # PR #1249 review 3744482399: neither schema nor parser permits trusted extensions.
    import copy

    from jsonschema import Draft202012Validator

    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.verifier import parse_public_config

    schema = json.loads(
        Path(
            "benchmarks/codegraph_compare/published_schemas/public-config-v6.schema.json"
        ).read_bytes()
    )
    config = copy.deepcopy(_qualification_v3_public_config())
    config["trusted"]["untrusted_extension"] = "0" * 64
    diagnostic = copy.deepcopy(config)
    diagnostic.pop("root_signature")

    with pytest.raises(
        ValueError, match="trusted config has unknown or missing fields"
    ):
        parse_public_config(canonical_json_bytes(diagnostic), diagnostic_mode=True)
    assert len(list(Draft202012Validator(schema).iter_errors(config))) == 1


def test_service_launch_schema_matches_process_identity_shape():
    # PR #1249 review 3744516431: published process fields match _proc_identity().
    from jsonschema import Draft202012Validator

    schema = json.loads(
        Path(
            "benchmarks/codegraph_compare/published_schemas/service-launch-v1.schema.json"
        ).read_bytes()
    )
    process = {
        "host_pid": 123,
        "container_pid": 1,
        "starttime": "456",
        "cgroup": "0::/container",
        "executable": "/usr/bin/python3",
        "executable_sha256": "a" * 64,
        "cmdline": ["python", "-m", "service"],
        "namespaces": {
            name: f"{name}:[1]"
            for name in ("mnt", "pid", "net", "user", "uts", "ipc", "cgroup")
        },
        "capabilities": dict.fromkeys(
            ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"),
            "0000000000000000",
        ),
        "no_new_privs": "1",
        "seccomp": "2",
        "seccomp_filters": "1",
    }
    attestation = {
        "container_id": "b" * 64,
        "role": "verifier",
        "image_id": "sha256:" + "c" * 64,
        "cmd": ["python"],
        "entrypoint": None,
        "user": "903",
        "readonly_rootfs": True,
        "mounts": [],
        "network_mode": "none",
        "security_opt": [],
        "process": process,
    }
    envelope = {
        "attestation": attestation,
        "key_id": "auditor",
        "algorithm": "Ed25519",
        "signature": "d" * 128,
    }

    assert list(Draft202012Validator(schema).iter_errors(envelope)) == []


_mark_posix_qualification_section_tests()
