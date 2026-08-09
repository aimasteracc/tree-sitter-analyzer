"""Fail-closed Unix client for the external NO1-008A audit authority."""

from __future__ import annotations

import hashlib
import socket
import struct
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
)
from benchmarks.codegraph_compare.service_runtime import read_frame

MAX_MESSAGE = 4 * 1024 * 1024


def _peer_credentials(client: socket.socket) -> tuple[int, int, int]:
    option = getattr(socket, "SO_PEERCRED", None)
    if option is None:
        raise ValueError("Unix peer credentials unavailable")
    return struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, option, 12))


def exchange(
    request: dict[str, Any], socket_path: Path, authority: dict[str, Any], domain: bytes
) -> dict[str, Any]:
    wire = canonical_json_bytes(request)
    if len(wire) > MAX_MESSAGE:
        raise ValueError("audit request exceeds protocol bound")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(10)
    try:
        client.connect(str(socket_path))
        peer_pid, peer_uid, _peer_gid = _peer_credentials(client)
        if peer_pid <= 0 or peer_uid != authority["peer_uid"]:
            raise ValueError("external audit authority peer UID mismatch")
        client.sendall(struct.pack("!I", len(wire)) + wire)
        client.shutdown(socket.SHUT_WR)
        envelope = read_frame(
            client, MAX_MESSAGE, 10, "external audit authority response"
        )
    finally:
        client.close()
    if type(envelope) is not dict or frozenset(envelope) != {
        "audit",
        "key_id",
        "algorithm",
        "signature",
    }:
        raise ValueError("external audit authority envelope invalid")
    if (
        envelope["audit"] != request
        or envelope["key_id"] != authority["key_id"]
        or envelope["algorithm"] != "Ed25519"
    ):
        raise ValueError("external audit authority response binding mismatch")
    try:
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(authority["public_key_hex"])
        ).verify(
            bytes.fromhex(envelope["signature"]), domain + canonical_json_bytes(request)
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("external audit authority signature mismatch") from exc
    return envelope


def run_cell(
    contract: dict[str, Any], socket_path: Path, authority: dict[str, Any]
) -> dict[str, Any]:
    """Submit a root-signed job and verify its exact signed response."""
    request = {"operation": "run-cell", "contract": contract}
    wire = canonical_json_bytes(request)
    if len(wire) > MAX_MESSAGE:
        raise ValueError("run-cell request exceeds protocol bound")
    timeout = authority.get("wall_timeout_seconds", 120)
    if type(timeout) not in {int, float} or timeout <= 0:
        raise ValueError("authority timeout contract invalid")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(socket_path))
        _pid, uid, _gid = _peer_credentials(client)
        if uid != authority["peer_uid"]:
            raise ValueError("external audit authority peer UID mismatch")
        client.sendall(struct.pack("!I", len(wire)) + wire)
        client.shutdown(socket.SHUT_WR)
        envelope = read_frame(
            client, MAX_MESSAGE, timeout, "external authority response"
        )
    finally:
        client.close()
    if type(envelope) is dict and frozenset(envelope) == {"error", "reason"}:
        raise ValueError(f"authority rejected request: {envelope['reason']}")
    if type(envelope) is not dict or frozenset(envelope) != {
        "response",
        "key_id",
        "algorithm",
        "signature",
    }:
        raise ValueError("run-cell authority envelope invalid")
    response = envelope["response"]
    expected_response_keys = {
        "contract_digest",
        "job_id",
        "cell",
        "nonce",
        "audit",
        "artifacts",
    }
    if type(response) is not dict or set(response) != expected_response_keys:
        raise ValueError("run-cell authority response is not closed")
    if (
        response["contract_digest"]
        != hashlib.sha256(canonical_json_bytes(contract)).hexdigest()
        or response["job_id"] != contract["job_id"]
        or response["cell"] != contract["cell"]
        or response["nonce"] != contract["nonce"]
        or envelope["key_id"] != authority["key_id"]
        or envelope["algorithm"] != "Ed25519"
    ):
        raise ValueError("run-cell authority response binding mismatch")
    audit_envelope = response["audit"]
    if type(audit_envelope) is not dict or set(audit_envelope) != {
        "audit",
        "key_id",
        "algorithm",
        "signature",
    }:
        raise ValueError("run-cell terminal audit envelope invalid")
    if (
        audit_envelope["key_id"] != authority["key_id"]
        or audit_envelope["algorithm"] != "Ed25519"
    ):
        raise ValueError("run-cell terminal audit identity mismatch")
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(authority["public_key_hex"])
    ).verify(
        bytes.fromhex(audit_envelope["signature"]),
        b"NO1-008A-HOST-AUDIT-V1\0" + canonical_json_bytes(audit_envelope["audit"]),
    )
    artifacts = response["artifacts"]
    expected_names = {
        "data.img",
        "hash.img",
        "launch-audit.json",
        "verity-format.txt",
    }
    if (
        type(artifacts) is not list
        or {item.get("name") for item in artifacts if type(item) is dict}
        != expected_names
    ):
        raise ValueError("run-cell artifact set is not exact")
    for item in artifacts:
        if type(item) is not dict or set(item) != {
            "name",
            "id",
            "sha256",
            "size",
            "path",
        }:
            raise ValueError("run-cell artifact descriptor is not closed")
        name = item["name"]
        expected_path = f"{contract['job_id']}/{name}"
        identity = hashlib.sha256(
            canonical_json_bytes(
                {
                    "name": name,
                    "sha256": item["sha256"],
                    "size": item["size"],
                    "path": item["path"],
                }
            )
        ).hexdigest()
        if (
            item["path"] != expected_path
            or item["id"] != identity
            or type(item["size"]) is not int
            or item["size"] < 0
            or type(item["sha256"]) is not str
            or len(item["sha256"]) != 64
        ):
            raise ValueError("run-cell artifact descriptor binding mismatch")
    try:
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(authority["public_key_hex"])
        ).verify(
            bytes.fromhex(envelope["signature"]),
            b"NO1-008A-RUN-CELL-RESPONSE-V1\0" + canonical_json_bytes(response),
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("run-cell authority signature mismatch") from exc
    return envelope
