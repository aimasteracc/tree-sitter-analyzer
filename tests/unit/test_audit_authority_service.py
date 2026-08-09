"""Protocol-policy tests for the privileged NO1-008A authority service."""

from __future__ import annotations

import socket
import struct
import tempfile
import threading
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare.audit_authority_service import serve_once
from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)


def _exchange(
    listener: socket.socket, path: Path, request: dict[str, object], runner=None
) -> dict[str, object]:
    thread = threading.Thread(
        target=serve_once,
        args=(listener,),
        kwargs={
            "key": Ed25519PrivateKey.from_private_bytes(b"A" * 32),
            "key_id": "authority",
            "runner": runner
            or (
                lambda _contract: (_ for _ in ()).throw(AssertionError("runner called"))
            ),
        },
    )
    thread.start()
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(path))
    payload = canonical_json_bytes(request)
    client.sendall(struct.pack("!I", len(payload)) + payload)
    client.shutdown(socket.SHUT_WR)
    size = struct.unpack("!I", client.recv(4))[0]
    response = bytearray()
    while len(response) < size:
        response.extend(client.recv(size - len(response)))
    client.close()
    thread.join(timeout=5)
    return strict_json_loads(bytes(response))


def test_authority_server_rejects_direct_arbitrary_sign_request(tmp_path: Path):
    socket_path = Path(tempfile.mkdtemp(prefix="tsa-a-", dir="/tmp")) / "a.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(1)
    try:
        response = _exchange(
            listener,
            socket_path,
            {"operation": "sign", "contract": {}},
        )
    finally:
        listener.close()
    assert response == {
        "error": "ValueError",
        "reason": "authority policy permits run-cell only",
    }


def test_authority_server_rejects_unsigned_run_cell_before_runner(
    tmp_path: Path, monkeypatch
):
    root = Ed25519PrivateKey.from_private_bytes(b"R" * 32)
    monkeypatch.setattr(
        "benchmarks.codegraph_compare.audit_authority_service.baked_root_public_key",
        lambda: root.public_key().public_bytes_raw(),
    )
    socket_path = Path(tempfile.mkdtemp(prefix="tsa-a-", dir="/tmp")) / "a.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(1)
    contract = {
        "schema_version": 1,
        "job_id": "1" * 64,
        "cell": {"repo_id": "gin", "arm_id": "tsa-warm", "attempt": 1},
        "nonce": "2" * 64,
        "root_signature": "0" * 128,
    }
    try:
        response = _exchange(
            listener, socket_path, {"operation": "run-cell", "contract": contract}
        )
    finally:
        listener.close()
    assert set(response) == {"error", "reason"}
    assert response["error"] == "InvalidSignature"


def test_aggregate_retains_diagnostic_top_level_reason():
    from benchmarks.codegraph_compare.verifier_aggregate import aggregate_verdict

    result = aggregate_verdict({}, public_config={}, diagnostic_mode=True)
    assert result["authorization"] == "DIAGNOSTIC_ONLY"
    assert result["top_level_reasons"] == [
        "DIAGNOSTIC_ONLY",
        "TOP_LEVEL_INVALID:ValueError:manifest has unknown or missing fields",
    ]


def test_aggregate_retains_production_top_level_failure_reason():
    from benchmarks.codegraph_compare.verifier_aggregate import aggregate_verdict

    result = aggregate_verdict({}, public_config={})
    assert result["authorization"] == "PRODUCTION_VERIFIER"
    assert result["top_level_reasons"] == [
        "TOP_LEVEL_INVALID:ValueError:manifest has unknown or missing fields"
    ]


def _signed_contract(root: Ed25519PrivateKey) -> dict[str, object]:
    from benchmarks.codegraph_compare.audit_authority_service import CONTRACT_DOMAIN

    unsigned = {
        "schema_version": 1,
        "job_id": "1" * 64,
        "cell": {"repo_id": "gin", "arm_id": "tsa-warm", "attempt": 1},
        "nonce": "2" * 64,
    }
    return {
        **unsigned,
        "root_signature": root.sign(
            CONTRACT_DOMAIN + canonical_json_bytes(unsigned)
        ).hex(),
    }


def test_authority_response_signs_exact_closed_artifact_descriptors(
    tmp_path: Path, monkeypatch
):
    root = Ed25519PrivateKey.from_private_bytes(b"R" * 32)
    monkeypatch.setattr(
        "benchmarks.codegraph_compare.audit_authority_service.baked_root_public_key",
        lambda: root.public_key().public_bytes_raw(),
    )
    job = tmp_path / ("1" * 64)
    core = job / "producer-output" / "core"
    core.mkdir(parents=True)
    (core / "result").write_bytes(b"core")
    for name in ("data.img", "hash.img", "launch-audit.json", "verity-format.txt"):
        (job / name).write_bytes(name.encode())
    audit = {
        "protocol": "no1-008a-audit-v1",
        "phase": "terminal",
        "service_measurement": "3" * 64,
        "audit": {},
    }
    artifacts = {
        name: str(core if name == "core" else job / name)
        for name in (
            "core",
            "data.img",
            "hash.img",
            "launch-audit.json",
            "verity-format.txt",
        )
    }
    socket_path = Path(tempfile.mkdtemp(prefix="tsa-r-", dir="/tmp")) / "a.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(1)
    try:
        response = _exchange(
            listener,
            socket_path,
            {"operation": "run-cell", "contract": _signed_contract(root)},
            runner=lambda _contract: {"audit": audit, "artifacts": artifacts},
        )
    finally:
        listener.close()
    assert set(response) == {"response", "key_id", "algorithm", "signature"}
    assert [item["name"] for item in response["response"]["artifacts"]] == [
        "core",
        "data.img",
        "hash.img",
        "launch-audit.json",
        "verity-format.txt",
    ]
    assert response["response"]["job_id"] == "1" * 64


def test_authority_response_rejects_symlink_artifact(tmp_path: Path, monkeypatch):
    root = Ed25519PrivateKey.from_private_bytes(b"R" * 32)
    monkeypatch.setattr(
        "benchmarks.codegraph_compare.audit_authority_service.baked_root_public_key",
        lambda: root.public_key().public_bytes_raw(),
    )
    job = tmp_path / ("1" * 64)
    core = job / "producer-output" / "core"
    core.mkdir(parents=True)
    target = job / "target"
    target.write_bytes(b"x")
    for name in ("data.img", "hash.img", "launch-audit.json", "verity-format.txt"):
        (job / name).symlink_to(target)
    artifacts = {
        name: str(core if name == "core" else job / name)
        for name in (
            "core",
            "data.img",
            "hash.img",
            "launch-audit.json",
            "verity-format.txt",
        )
    }
    socket_path = Path(tempfile.mkdtemp(prefix="tsa-r-", dir="/tmp")) / "a.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(1)
    try:
        response = _exchange(
            listener,
            socket_path,
            {"operation": "run-cell", "contract": _signed_contract(root)},
            runner=lambda _contract: {
                "audit": {
                    "protocol": "no1-008a-audit-v1",
                    "phase": "terminal",
                    "service_measurement": "3" * 64,
                    "audit": {},
                },
                "artifacts": artifacts,
            },
        )
    finally:
        listener.close()
    assert response["error"] == "ValueError"
    assert response["reason"] == "artifact path is not authority-owned and canonical"


def test_producer_output_rejects_external_sibling_symlink(tmp_path: Path):
    from benchmarks.codegraph_compare.audit_authority_runner import (
        _validate_producer_output,
    )

    output = tmp_path / "output"
    (output / "core").mkdir(parents=True)
    (output / "external").symlink_to(tmp_path / "host-file")
    try:
        _validate_producer_output(output)
    except ValueError as error:
        assert (
            str(error) == "producer output must contain exactly one real core directory"
        )
    else:
        raise AssertionError("external producer symlink was accepted")


def test_plan_document_digest_is_distinct_from_shared_canonical_plan_hash():
    import hashlib

    from benchmarks.codegraph_compare.receipt_v3 import (
        canonical_json_bytes,
        canonical_plan_hash,
    )

    plan = {
        "cell": {"repo_id": "gin", "arm_id": "tsa-warm", "attempt": 1},
        "wall_timeout_seconds": 60,
    }
    logical = canonical_plan_hash(plan)
    document = {**plan, "plan_hash": logical, "plan_set_hash": "4" * 64}
    document_sha256 = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
    assert canonical_plan_hash(document) == logical
    assert document_sha256 != logical
