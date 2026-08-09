"""Independent one-shot consumer of root-authorized verifier decisions."""

from __future__ import annotations

import argparse
import hashlib
import os
import socket
import sqlite3
import stat
import struct
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.service_runtime import (
    measure_runtime,
    peer_allowed,
    read_frame,
    secure_key,
    verify_service_launch_attestation,
)
from benchmarks.codegraph_compare.trust_anchor import baked_root_public_key
from benchmarks.codegraph_compare.verifier import parse_public_config
from benchmarks.codegraph_compare.verifier_service import LEDGER_DOMAIN, VERDICT_DOMAIN

DECISION_DOMAIN = b"NO1-008A-DECISION-CONTRACT-V1\0"
RECEIPT_DOMAIN = b"NO1-008A-DECISION-RECEIPT-V1\0"
MAX_FRAME = 64 * 1024 * 1024
_HEX = frozenset("0123456789abcdef")


def _hex64(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in _HEX for c in value):
        raise ValueError(f"{label} invalid")
    return value


def verify_decision_contract(value: Any) -> dict[str, Any]:
    keys = {
        "schema_version",
        "decision_id",
        "decision_nonce",
        "expires_at",
        "manifest_sha256",
        "ledger_head",
        "root_signature",
    }
    if type(value) is not dict or set(value) != keys or value["schema_version"] != 1:
        raise ValueError("decision contract is not closed")
    for name in ("decision_id", "decision_nonce", "manifest_sha256"):
        _hex64(value[name], name)
    if type(value["expires_at"]) is not int or value["expires_at"] <= time.time_ns():
        raise TimeoutError("decision contract expired")
    head = value["ledger_head"]
    if (
        type(head) is not dict
        or set(head) != {"counter", "record_hash"}
        or type(head["counter"]) is not int
    ):
        raise ValueError("expected ledger head invalid")
    _hex64(head["record_hash"], "ledger head")
    unsigned = {k: v for k, v in value.items() if k != "root_signature"}
    signature = value["root_signature"]
    if type(signature) is not str or len(signature) != 128:
        raise ValueError("decision root signature invalid")
    Ed25519PublicKey.from_public_bytes(baked_root_public_key()).verify(
        bytes.fromhex(signature), DECISION_DOMAIN + canonical_json_bytes(unsigned)
    )
    return dict(value)


def verify_verdict_envelope(
    envelope: Any, contract: dict[str, Any], config: dict[str, Any]
) -> None:
    if (
        type(envelope) is not dict
        or envelope.get("manifest_sha256") != contract["manifest_sha256"]
    ):
        raise ValueError("verdict manifest does not match decision")
    if (
        envelope.get("key_id") != config["verifier"]["key_id"]
        or envelope.get("algorithm") != "Ed25519"
    ):
        raise ValueError("verifier identity mismatch")
    signed = {
        k: v
        for k, v in envelope.items()
        if k not in {"key_id", "algorithm", "signature"}
    }
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(config["verifier"]["public_key_hex"])
    ).verify(
        bytes.fromhex(envelope["signature"]),
        VERDICT_DOMAIN + canonical_json_bytes(signed),
    )
    retained = envelope.get("ledger_head")
    if (
        type(retained) is not dict
        or retained.get("record") != contract["ledger_head"]
        or retained.get("key_id") != config["verifier"]["key_id"]
    ):
        raise ValueError("verdict ledger head does not match expected root head")
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(config["verifier"]["public_key_hex"])
    ).verify(
        bytes.fromhex(retained["signature"]),
        LEDGER_DOMAIN + canonical_json_bytes(retained["record"]),
    )
    nonce = envelope.get("decision_nonce")
    if nonce != contract["decision_nonce"]:
        raise ValueError("verdict decision nonce mismatch")


class DecisionLedger:
    def __init__(self, path: Path):
        parent = path.parent.resolve(strict=True)
        meta = os.stat(parent)
        if meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) & 0o022:
            raise ValueError("decision ledger directory must be root-controlled")
        self.db = sqlite3.connect(
            path, timeout=30, isolation_level=None, check_same_thread=False
        )
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS consumed(decision_id TEXT PRIMARY KEY,decision_nonce TEXT UNIQUE NOT NULL,manifest_sha256 TEXT NOT NULL,consumed_at_ns INTEGER NOT NULL,receipt_sha256 TEXT NOT NULL)"
        )
        os.chmod(path, 0o600)

    def consume(
        self, contract: dict[str, Any], build: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.db.execute(
                "SELECT 1 FROM consumed WHERE decision_id=? OR decision_nonce=?",
                (contract["decision_id"], contract["decision_nonce"]),
            ).fetchone():
                raise ValueError("decision already consumed")
            receipt = build()
            digest = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
            self.db.execute(
                "INSERT INTO consumed VALUES(?,?,?,?,?)",
                (
                    contract["decision_id"],
                    contract["decision_nonce"],
                    contract["manifest_sha256"],
                    time.time_ns(),
                    digest,
                ),
            )
            self.db.execute("COMMIT")
            return receipt
        except BaseException:
            self.db.execute("ROLLBACK")
            raise


def consume_request(
    request: Any,
    config: dict[str, Any],
    ledger: DecisionLedger,
    key: Ed25519PrivateKey,
    identity: dict[str, Any],
) -> dict[str, Any]:
    if (
        type(request) is not dict
        or set(request) != {"operation", "decision_contract", "verdict_envelope"}
        or request["operation"] != "consume-decision"
    ):
        raise ValueError("legacy/wrapper decision request rejected")
    contract = verify_decision_contract(request["decision_contract"])
    verify_verdict_envelope(request["verdict_envelope"], contract, config)

    def build() -> dict[str, Any]:
        body = {
            "schema_version": 1,
            "decision_id": contract["decision_id"],
            "decision_nonce": contract["decision_nonce"],
            "manifest_sha256": contract["manifest_sha256"],
            "ledger_head": contract["ledger_head"],
            "consumed_at_ns": time.time_ns(),
            "service_identity": identity,
        }
        return {
            "receipt": body,
            "key_id": config["decision_consumer"]["key_id"],
            "algorithm": "Ed25519",
            "signature": key.sign(RECEIPT_DOMAIN + canonical_json_bytes(body)).hex(),
        }

    return ledger.consume(contract, build)


def request_decision(
    *,
    socket_path: Path,
    contract: dict[str, Any],
    envelope: dict[str, Any],
    config: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    if timeout <= 0:
        raise TimeoutError("decision deadline expired")
    request = {
        "operation": "consume-decision",
        "decision_contract": contract,
        "verdict_envelope": envelope,
    }
    payload = canonical_json_bytes(request)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(socket_path))
        peer_allowed_server = getattr(socket, "SO_PEERCRED", None)
        if peer_allowed_server is None:
            raise ValueError("Unix peer credentials unavailable")
        _pid, uid, _gid = struct.unpack(
            "3i", client.getsockopt(socket.SOL_SOCKET, peer_allowed_server, 12)
        )
        if uid != config["decision_consumer"]["peer_uid"]:
            raise ValueError("decision consumer peer UID mismatch")
        client.sendall(struct.pack("!I", len(payload)) + payload)
        client.shutdown(socket.SHUT_WR)
        reply = read_frame(client, MAX_FRAME, timeout, "decision receipt")
    finally:
        client.close()
    if type(reply) is dict and set(reply) == {"error", "reason"}:
        raise ValueError(f"decision consumer rejected decision: {reply['reason']}")
    if type(reply) is not dict:
        raise ValueError("decision receipt is not an object")
    return dict(reply)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "socket",
        "private-key",
        "public-config",
        "ledger",
        "launch-attestation",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--allowed-client-uid", required=True, type=int)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    config = parse_public_config(Path(args.public_config).read_bytes())
    role = "decision_consumer"
    if os.geteuid() != config[role]["peer_uid"]:
        raise SystemExit("decision consumer UID mismatch")
    identity = measure_runtime(config["trusted"][f"{role}_runtime"]["measurement"])
    verify_service_launch_attestation(
        strict_json_loads(Path(args.launch_attestation).read_bytes()), role, config
    )
    fd, raw = secure_key(Path(args.private_key), os.geteuid())
    key = Ed25519PrivateKey.from_private_bytes(raw)
    ledger = DecisionLedger(Path(args.ledger))
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(args.socket)
    os.chmod(args.socket, 0o660)  # nosec B103
    listener.listen(args.workers)

    def worker() -> None:
        while True:
            conn, _ = listener.accept()
            try:
                peer_allowed(conn, args.allowed_client_uid)
                req = read_frame(conn, MAX_FRAME, 10, "decision request")
                try:
                    reply = consume_request(req, config, ledger, key, identity)
                except Exception as exc:
                    reply = {"error": type(exc).__name__, "reason": str(exc)}
                payload = canonical_json_bytes(reply)
                conn.sendall(struct.pack("!I", len(payload)) + payload)
            finally:
                conn.close()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in [pool.submit(worker) for _ in range(args.workers)]:
            future.result()
    os.close(fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
