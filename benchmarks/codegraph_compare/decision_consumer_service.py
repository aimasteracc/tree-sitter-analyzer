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
from collections.abc import Callable, Mapping, Sequence
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
    wait_for_launch_release,
)
from benchmarks.codegraph_compare.sqlite_ledger_validation import (
    validate_decision_ledger,
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
        "issued_at_ns",
        "expires_at_ns",
        "plan_set_hash",
        "cells",
        "root_signature",
    }
    if type(value) is not dict or set(value) != keys or value["schema_version"] != 1:
        raise ValueError("decision contract is not closed")
    for name in ("decision_id", "decision_nonce", "plan_set_hash"):
        _hex64(value[name], name)
    now = time.time_ns()
    if (
        type(value["issued_at_ns"]) is not int
        or type(value["expires_at_ns"]) is not int
        or value["issued_at_ns"] > now
        or value["expires_at_ns"] <= now
        or value["expires_at_ns"] <= value["issued_at_ns"]
    ):
        raise TimeoutError("decision contract lifetime invalid")
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    cells = value["cells"]
    if type(cells) is not list or len(cells) != 14:
        raise ValueError("decision contract requires exact fourteen cells")
    identities = []
    for cell in cells:
        if type(cell) is not dict or set(cell) != {"repo_id", "arm_id", "plan_sha256"}:
            raise ValueError("decision cell is not closed")
        identities.append((cell["repo_id"], cell["arm_id"]))
        _hex64(cell["plan_sha256"], "decision plan hash")
    if identities != list(EXPECTED_CELLS):
        raise ValueError("decision cells are not exact or ordered")
    unsigned = {k: v for k, v in value.items() if k != "root_signature"}
    signature = value["root_signature"]
    if type(signature) is not str or len(signature) != 128:
        raise ValueError("decision root signature invalid")
    Ed25519PublicKey.from_public_bytes(baked_root_public_key()).verify(
        bytes.fromhex(signature), DECISION_DOMAIN + canonical_json_bytes(unsigned)
    )
    return dict(value)


def verify_configured_plan_set(
    contract: dict[str, Any], config: dict[str, Any]
) -> None:
    """Recompute and bind all ordered decision plan hashes to root config."""
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    trusted = config["trusted"]
    ordered = [cell["plan_sha256"] for cell in contract["cells"]]
    recomputed = hashlib.sha256(canonical_json_bytes(ordered)).hexdigest()
    configured = [
        trusted["plan_hashes"][f"{repo}/{arm}"] for repo, arm in EXPECTED_CELLS
    ]
    if (
        contract["plan_set_hash"] != recomputed
        or recomputed != trusted["plan_set_hash"]
        or ordered != configured
    ):
        raise ValueError("decision plan set is not root-config authorized")


def verify_verdict_envelope(
    envelope: Any, contract: dict[str, Any], config: dict[str, Any]
) -> None:
    contract_digest = hashlib.sha256(canonical_json_bytes(contract)).hexdigest()
    required = {
        "manifest_sha256",
        "decision_id",
        "decision_contract_sha256",
        "challenge",
        "ledger_counter",
        "ledger_prev_hash",
        "issued_at_ns",
        "verdict",
        "service_identity",
        "consumption_record",
        "ledger_head",
        "key_id",
        "algorithm",
        "signature",
    }
    if type(envelope) is not dict or set(envelope) != required:
        raise ValueError("verdict envelope is not closed")
    if (
        envelope["decision_id"] != contract["decision_id"]
        or envelope["decision_contract_sha256"] != contract_digest
    ):
        raise ValueError("verdict does not bind offline decision contract")
    if (
        envelope["key_id"] != config["verifier"]["key_id"]
        or envelope["algorithm"] != "Ed25519"
        or envelope["service_identity"]
        != config["trusted"]["verifier_runtime"]["measurement"]
    ):
        raise ValueError("verifier identity mismatch")
    signed = {
        k: v
        for k, v in envelope.items()
        if k not in {"key_id", "algorithm", "signature"}
    }
    public = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(config["verifier"]["public_key_hex"])
    )
    public.verify(
        bytes.fromhex(envelope["signature"]),
        VERDICT_DOMAIN + canonical_json_bytes(signed),
    )
    verdict = envelope["verdict"]
    if (
        type(verdict) is not dict
        or verdict.get("status") != "SETUP_QUALIFIED"
        or verdict.get("authorization") != "PRODUCTION_VERIFIER"
        or verdict.get("expected_cells") != 14
        or verdict.get("observed_receipts") != 14
        or verdict.get("attempts_per_cell") != 1
        or verdict.get("top_level_reasons") != []
        or type(verdict.get("cell_diagnostics")) is not list
        or len(verdict["cell_diagnostics"]) != 14
        or any(
            type(item) is not dict or item.get("reasons") != []
            for item in verdict["cell_diagnostics"]
        )
    ):
        raise ValueError(
            "decision requires a reason-free exact-14 production qualification"
        )
    consumption = envelope["consumption_record"]
    if (
        type(consumption) is not dict
        or set(consumption) != {"record", "key_id", "algorithm", "signature"}
        or consumption["key_id"] != config["verifier"]["key_id"]
        or consumption["algorithm"] != "Ed25519"
    ):
        raise ValueError("verifier consumption proof envelope invalid")
    public.verify(
        bytes.fromhex(consumption["signature"]),
        LEDGER_DOMAIN + canonical_json_bytes(consumption["record"]),
    )
    record = consumption["record"]
    if (
        type(record) is not dict
        or record.get("event") != "CONSUMED"
        or record.get("manifest_sha256") != envelope["manifest_sha256"]
        or record.get("challenge") != envelope["challenge"]
        or record.get("counter") != envelope["ledger_counter"]
    ):
        raise ValueError("verifier consumption proof is not terminal or bound")


class DecisionLedger:
    """Host-authoritative one-use ledger using a fresh connection per transaction."""

    def __init__(self, path: Path, config: Mapping[str, Any]):
        self._decision_config = config
        role = config.get("decision_consumer")
        trusted = config.get("trusted")
        runtime = (
            trusted.get("decision_consumer_runtime") if type(trusted) is dict else None
        )
        if (
            type(role) is not dict
            or type(runtime) is not dict
            or type(role.get("key_id")) is not str
            or type(role.get("public_key_hex")) is not str
            or len(role["public_key_hex"]) != 64
            or type(runtime.get("measurement")) is not dict
        ):
            raise ValueError("decision ledger verification config invalid")
        parent = path.parent.resolve(strict=True)
        meta = os.stat(parent)
        if (
            parent != path.parent
            or meta.st_uid != 904
            or stat.S_IMODE(meta.st_mode) != 0o700
            or not os.access(parent, os.W_OK | os.X_OK)
        ):
            raise ValueError(
                "decision ledger directory must be UID 904 private 0700 and writable"
            )
        self.path = path
        db = self._connect()
        try:
            db.execute(
                "CREATE TABLE IF NOT EXISTS consumed(decision_id TEXT PRIMARY KEY,decision_nonce TEXT UNIQUE NOT NULL,manifest_sha256 TEXT NOT NULL,consumed_at_ns INTEGER NOT NULL,receipt_json BLOB NOT NULL)"
            )
        finally:
            db.close()
        os.chmod(path, 0o600)
        validate_decision_ledger(self)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def query(self, decision_id: str) -> dict[str, Any]:
        _hex64(decision_id, "decision id")
        db = self._connect()
        try:
            row = db.execute(
                "SELECT receipt_json FROM consumed WHERE decision_id=?", (decision_id,)
            ).fetchone()
        finally:
            db.close()
        if row is None:
            raise ValueError("decision receipt not found")
        return dict(strict_json_loads(bytes(row[0])))

    def consume(
        self,
        contract: dict[str, Any],
        manifest: str,
        build: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM consumed WHERE decision_id=? OR decision_nonce=?",
                (contract["decision_id"], contract["decision_nonce"]),
            ).fetchone():
                raise ValueError("decision already consumed")
            receipt = build()
            db.execute(
                "INSERT INTO consumed VALUES(?,?,?,?,?)",
                (
                    contract["decision_id"],
                    contract["decision_nonce"],
                    manifest,
                    time.time_ns(),
                    canonical_json_bytes(receipt),
                ),
            )
            db.execute("COMMIT")
            return receipt
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()


def consume_request(
    request: Any,
    config: dict[str, Any],
    ledger: DecisionLedger,
    key: Ed25519PrivateKey,
    identity: dict[str, Any],
) -> dict[str, Any]:
    if type(request) is not dict:
        raise ValueError("decision request is not an object")
    if (
        set(request) == {"operation", "decision_id"}
        and request["operation"] == "query-decision"
    ):
        return ledger.query(request["decision_id"])
    if (
        set(request) != {"operation", "decision_contract", "verdict_envelope"}
        or request["operation"] != "consume-decision"
    ):
        raise ValueError("legacy/wrapper decision request rejected")
    contract = verify_decision_contract(request["decision_contract"])
    verify_configured_plan_set(contract, config)
    envelope = request["verdict_envelope"]
    verify_verdict_envelope(envelope, contract, config)

    def build() -> dict[str, Any]:
        body = {
            "schema_version": 1,
            "decision_id": contract["decision_id"],
            "decision_contract_sha256": hashlib.sha256(
                canonical_json_bytes(contract)
            ).hexdigest(),
            "manifest_sha256": envelope["manifest_sha256"],
            "verdict_status": "SETUP_QUALIFIED",
            "consumed_at_ns": time.time_ns(),
            "service_identity": identity,
        }
        return {
            "receipt": body,
            "key_id": config["decision_consumer"]["key_id"],
            "algorithm": "Ed25519",
            "signature": key.sign(RECEIPT_DOMAIN + canonical_json_bytes(body)).hex(),
        }

    return ledger.consume(contract, envelope["manifest_sha256"], build)


def _verify_decision_receipt(
    reply: Any,
    contract: dict[str, Any],
    envelope: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    if type(reply) is not dict or set(reply) != {
        "receipt",
        "key_id",
        "algorithm",
        "signature",
    }:
        raise ValueError("decision receipt envelope invalid")
    body = reply["receipt"]
    digest = hashlib.sha256(canonical_json_bytes(contract)).hexdigest()
    if (
        reply["key_id"] != config["decision_consumer"]["key_id"]
        or reply["algorithm"] != "Ed25519"
        or type(body) is not dict
        or body.get("decision_id") != contract["decision_id"]
        or body.get("decision_contract_sha256") != digest
        or body.get("manifest_sha256") != envelope["manifest_sha256"]
        or body.get("verdict_status") != "SETUP_QUALIFIED"
        or body.get("service_identity")
        != config["trusted"]["decision_consumer_runtime"]["measurement"]
    ):
        raise ValueError(
            "decision receipt is not bound to requested decision and manifest"
        )
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(config["decision_consumer"]["public_key_hex"])
    ).verify(
        bytes.fromhex(reply["signature"]), RECEIPT_DOMAIN + canonical_json_bytes(body)
    )
    return dict(reply)


def request_decision(
    *,
    socket_path: Path,
    contract: dict[str, Any],
    envelope: dict[str, Any],
    config: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout

    def exchange(request: dict[str, Any]) -> Any:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("decision deadline expired")
        payload = canonical_json_bytes(request)
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.settimeout(remaining)
            client.connect(str(socket_path))
            option = getattr(socket, "SO_PEERCRED", None)
            if option is None:
                raise ValueError("Unix peer credentials unavailable")
            pid, uid, _gid = struct.unpack(
                "3i", client.getsockopt(socket.SOL_SOCKET, option, 12)
            )
            if pid <= 0 or uid != config["decision_consumer"]["peer_uid"]:
                raise ValueError("decision consumer peer UID mismatch")
            client.sendall(struct.pack("!I", len(payload)) + payload)
            client.shutdown(socket.SHUT_WR)
            try:
                return read_frame(
                    client,
                    MAX_FRAME,
                    max(0.001, deadline - time.monotonic()),
                    "decision receipt",
                )
            except (EOFError, ValueError, ConnectionError) as exc:
                # The complete request is already on the wire.  A response-side
                # framing failure can therefore follow a durable ledger commit.
                raise ConnectionError(
                    "decision response unavailable after send"
                ) from exc
        finally:
            client.close()

    try:
        reply = exchange(
            {
                "operation": "consume-decision",
                "decision_contract": contract,
                "verdict_envelope": envelope,
            }
        )
    except (TimeoutError, ConnectionError, OSError):
        # The commit may have succeeded before the connection broke. Querying the
        # durable signed receipt makes retry idempotent without consuming twice.
        reply = exchange(
            {"operation": "query-decision", "decision_id": contract["decision_id"]}
        )
    if type(reply) is dict and set(reply) == {"error", "reason"}:
        raise ValueError(f"decision consumer rejected decision: {reply['reason']}")
    return _verify_decision_receipt(reply, contract, envelope, config)


def _serve_connection(
    conn: socket.socket,
    allowed_client_uid: int,
    config: dict[str, Any],
    ledger: DecisionLedger,
    key: Ed25519PrivateKey,
    identity: dict[str, Any],
) -> None:
    """Contain every client failure so malformed peers cannot drain workers."""
    try:
        peer_allowed(conn, allowed_client_uid)
        request = read_frame(conn, MAX_FRAME, 10, "decision request")
        try:
            reply = consume_request(request, config, ledger, key, identity)
        except Exception as exc:
            reply = {"error": type(exc).__name__, "reason": str(exc)}
        payload = canonical_json_bytes(reply)
        conn.sendall(struct.pack("!I", len(payload)) + payload)
    except Exception:
        # Authentication, framing, handler serialization, and response transport
        # errors belong to this connection, never to the long-lived worker future.
        return
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "socket",
        "private-key",
        "public-config",
        "ledger",
        "launch-attestation",
        "launch-release",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--allowed-client-uid", required=True, type=int)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    config = parse_public_config(Path(args.public_config).read_bytes())
    role = "decision_consumer"
    if os.geteuid() != 904 or config[role]["peer_uid"] != 904:
        raise SystemExit("decision consumer UID mismatch")
    launch_bytes = wait_for_launch_release(
        Path(args.launch_attestation), Path(args.launch_release)
    )
    identity = measure_runtime(config["trusted"][f"{role}_runtime"]["measurement"])
    verify_service_launch_attestation(strict_json_loads(launch_bytes), role, config)
    fd, raw = secure_key(Path(args.private_key), os.geteuid())
    key = Ed25519PrivateKey.from_private_bytes(raw)
    if key.public_key().public_bytes_raw().hex() != config[role]["public_key_hex"]:
        os.close(fd)
        raise SystemExit("decision consumer private key does not match public config")
    ledger = DecisionLedger(Path(args.ledger), config)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(args.socket)
    # Filesystem access must not preempt the exact SO_PEERCRED UID authorization.
    os.chmod(args.socket, 0o666)  # nosec B103 - local socket; peer UID is fail-closed
    listener.listen(args.workers)

    def worker() -> None:
        while True:
            conn, _ = listener.accept()
            _serve_connection(
                conn, args.allowed_client_uid, config, ledger, key, identity
            )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in [pool.submit(worker) for _ in range(args.workers)]:
            future.result()
    os.close(fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
