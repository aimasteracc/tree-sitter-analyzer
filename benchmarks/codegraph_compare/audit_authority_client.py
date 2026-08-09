"""Fail-closed Unix client for the external NO1-008A audit authority."""

from __future__ import annotations

import socket
import struct
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)

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
        header = client.recv(4)
        if len(header) != 4:
            raise ValueError("external audit authority response absent")
        size = struct.unpack("!I", header)[0]
        if size < 2 or size > MAX_MESSAGE:
            raise ValueError("external audit authority response size invalid")
        chunks = bytearray()
        while len(chunks) < size:
            chunk = client.recv(size - len(chunks))
            if not chunk:
                raise ValueError("external audit authority response truncated")
            chunks.extend(chunk)
    finally:
        client.close()
    envelope = strict_json_loads(bytes(chunks))
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
    """Submit only a root-signed run-cell contract; never submit audit facts."""
    request = {"operation": "run-cell", "contract": contract}
    wire = canonical_json_bytes(request)
    if len(wire) > MAX_MESSAGE:
        raise ValueError("run-cell request exceeds protocol bound")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(120)
    try:
        client.connect(str(socket_path))
        _pid, uid, _gid = _peer_credentials(client)
        if uid != authority["peer_uid"]:
            raise ValueError("external audit authority peer UID mismatch")
        client.sendall(struct.pack("!I", len(wire)) + wire)
        client.shutdown(socket.SHUT_WR)
        header = client.recv(4)
        if len(header) != 4:
            raise ValueError("external authority response absent")
        size = struct.unpack("!I", header)[0]
        if size < 2 or size > MAX_MESSAGE:
            raise ValueError("external authority response size invalid")
        chunks = bytearray()
        while len(chunks) < size:
            chunk = client.recv(size - len(chunks))
            if not chunk:
                raise ValueError("external authority response truncated")
            chunks.extend(chunk)
    finally:
        client.close()
    envelope = strict_json_loads(bytes(chunks))
    if type(envelope) is dict and frozenset(envelope) == {"error", "reason"}:
        raise ValueError(f"authority rejected request: {envelope['reason']}")
    if type(envelope) is not dict or frozenset(envelope) != {
        "audit",
        "artifacts",
        "key_id",
        "algorithm",
        "signature",
    }:
        raise ValueError("run-cell authority envelope invalid")
    if envelope["key_id"] != authority["key_id"] or envelope["algorithm"] != "Ed25519":
        raise ValueError("run-cell authority identity mismatch")
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(authority["public_key_hex"])
    ).verify(
        bytes.fromhex(envelope["signature"]),
        b"NO1-008A-HOST-AUDIT-V1\0" + canonical_json_bytes(envelope["audit"]),
    )
    return envelope
