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
    listener: socket.socket, path: Path, request: dict[str, object]
) -> dict[str, object]:
    thread = threading.Thread(
        target=serve_once,
        args=(listener,),
        kwargs={
            "key": Ed25519PrivateKey.from_private_bytes(b"A" * 32),
            "key_id": "authority",
            "runner": lambda _contract: (_ for _ in ()).throw(
                AssertionError("runner called")
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
    assert result["authorization"] == "PRODUCTION_ROOT"
    assert result["top_level_reasons"] == [
        "TOP_LEVEL_INVALID:ValueError:manifest has unknown or missing fields"
    ]
