"""Root-authorized run-cell-only audit authority protocol server."""

from __future__ import annotations

import argparse
import os
import platform
import socket
import stat
import struct
from collections.abc import Callable, Mapping
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
from benchmarks.codegraph_compare.trust_anchor import baked_root_public_key

MAX_MESSAGE = 4 * 1024 * 1024
CONTRACT_DOMAIN = b"NO1-008A-RUN-CELL-CONTRACT-V1\0"
AUDIT_DOMAIN = b"NO1-008A-HOST-AUDIT-V1\0"
_HEX = frozenset("0123456789abcdef")


def _exact(value: Any, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or frozenset(value) != keys:
        raise ValueError(f"{label} is not closed")
    return value


def _hex64(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in _HEX for c in value):
        raise ValueError(f"{label} is not canonical SHA-256")
    return value


def verify_contract(request: Any) -> Mapping[str, Any]:
    request = _exact(request, frozenset({"operation", "contract"}), "request")
    if request["operation"] != "run-cell":
        raise ValueError("authority policy permits run-cell only")
    contract = _exact(
        request["contract"],
        frozenset({"schema_version", "job_id", "cell", "nonce", "root_signature"}),
        "run-cell contract",
    )
    cell = _exact(
        contract["cell"], frozenset({"repo_id", "arm_id", "attempt"}), "contract cell"
    )
    if (
        contract["schema_version"] != 1
        or type(cell["attempt"]) is not int
        or cell["attempt"] != 1
    ):
        raise ValueError("run-cell contract version or attempt invalid")
    for name in ("repo_id", "arm_id"):
        if type(cell[name]) is not str or not cell[name] or len(cell[name]) > 64:
            raise ValueError("contract cell identity invalid")
    _hex64(contract["job_id"], "job id")
    _hex64(contract["nonce"], "nonce")
    unsigned = {
        key: value for key, value in contract.items() if key != "root_signature"
    }
    signature = contract["root_signature"]
    if type(signature) is not str or len(signature) != 128:
        raise ValueError("contract root signature invalid")
    Ed25519PublicKey.from_public_bytes(baked_root_public_key()).verify(
        bytes.fromhex(signature), CONTRACT_DOMAIN + canonical_json_bytes(unsigned)
    )
    return contract


def _read_frame(connection: socket.socket) -> Any:
    header = connection.recv(4)
    if len(header) != 4:
        raise ValueError("authority request header absent")
    size = struct.unpack("!I", header)[0]
    if size < 2 or size > MAX_MESSAGE:
        raise ValueError("authority request size invalid")
    payload = bytearray()
    while len(payload) < size:
        chunk = connection.recv(size - len(payload))
        if not chunk:
            raise ValueError("authority request truncated")
        payload.extend(chunk)
    return strict_json_loads(bytes(payload))


def _write_frame(connection: socket.socket, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(value)
    connection.sendall(struct.pack("!I", len(payload)) + payload)


def _load_key(path: Path) -> Ed25519PrivateKey:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        metadata = os.fstat(descriptor)
        raw = os.read(descriptor, 33)
    finally:
        os.close(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o400
        or len(raw) != 32
    ):
        raise ValueError("authority key must be root-owned 0400 raw Ed25519")
    return Ed25519PrivateKey.from_private_bytes(raw)


def serve_once(
    listener: socket.socket,
    *,
    key: Ed25519PrivateKey,
    key_id: str,
    runner: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> None:
    connection, _ = listener.accept()
    try:
        contract = verify_contract(_read_frame(connection))
        result = runner(contract)
        result = _exact(result, frozenset({"audit", "artifacts"}), "runner result")
        audit = _exact(
            result["audit"],
            frozenset({"protocol", "phase", "service_measurement", "audit"}),
            "canonical terminal audit",
        )
        signed = {
            "audit": audit,
            "key_id": key_id,
            "algorithm": "Ed25519",
            "signature": key.sign(AUDIT_DOMAIN + canonical_json_bytes(audit)).hex(),
        }
        artifacts = dict(result["artifacts"])
        artifact_parent = Path(next(iter(artifacts.values()))).parent
        os.chmod(artifact_parent, 0o700)
        audit_path = artifact_parent / "process-audit.json"
        descriptor = os.open(
            audit_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444
        )
        try:
            os.write(descriptor, canonical_json_bytes(signed))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        artifacts["process_audit"] = str(audit_path)
        os.chmod(artifact_parent, 0o500)
        _write_frame(connection, {**signed, "artifacts": artifacts})
    except Exception as error:
        _write_frame(connection, {"error": type(error).__name__, "reason": str(error)})
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--staged-root", required=True)
    parser.add_argument("--artifact-root", required=True)
    args = parser.parse_args(argv)
    if os.geteuid() != 0 or platform.system() != "Linux":
        raise SystemExit("authority service requires Linux root")
    from benchmarks.codegraph_compare.audit_authority_runner import AuthorityRunner

    key = _load_key(Path(args.private_key))
    runner = AuthorityRunner(Path(args.staged_root), Path(args.artifact_root), key)
    path = Path(args.socket)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)
    listener.listen(16)
    while True:
        serve_once(listener, key=key, key_id=args.key_id, runner=runner)


if __name__ == "__main__":
    raise SystemExit(main())
