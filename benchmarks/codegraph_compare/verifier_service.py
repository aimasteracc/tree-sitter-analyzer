"""External exact-14 verifier service and authenticated Unix client."""

from __future__ import annotations

import argparse
import hashlib
import os
import socket
import stat
import struct
import tempfile
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from benchmarks.codegraph_compare.audit_authority_service import verify_contract
from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.receipt_v3_service import _paths, _verify_authority
from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS
from benchmarks.codegraph_compare.verifier import parse_public_config
from benchmarks.codegraph_compare.verifier_aggregate import (
    _validate_verdict_schema,
    aggregate_verdict,
)

MAX_FRAME = 64 * 1024 * 1024
READ_DEADLINE_SECONDS = 10
VERDICT_DOMAIN = b"NO1-008A-EXTERNAL-VERIFIER-VERDICT-V1\0"
_HEX = frozenset("0123456789abcdef")


def _hex64(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in _HEX for c in value):
        raise ValueError(f"{label} is not canonical SHA-256")
    return value


def _frame(connection: socket.socket) -> dict[str, Any]:
    header = connection.recv(4)
    if len(header) != 4:
        raise ValueError("verifier request header absent")
    size = struct.unpack("!I", header)[0]
    if size < 2 or size > MAX_FRAME:
        raise ValueError("verifier request size invalid")
    payload = bytearray()
    while len(payload) < size:
        chunk = connection.recv(min(size - len(payload), 1024 * 1024))
        if not chunk:
            raise ValueError("verifier request truncated")
        payload.extend(chunk)
    return strict_json_loads(bytes(payload))


def _send(connection: socket.socket, value: dict[str, Any]) -> None:
    payload = canonical_json_bytes(value)
    if len(payload) > MAX_FRAME:
        raise ValueError("verifier response exceeds protocol bound")
    connection.sendall(struct.pack("!I", len(payload)) + payload)


def _regular(root: Path, relative: str) -> Path:
    path = root / relative
    if path.resolve(strict=True) != path or root not in path.parents:
        raise ValueError("verifier evidence escapes authority store")
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("verifier evidence must be regular")
    return path


def _load_manifest(
    request: dict[str, Any],
    config: dict[str, Any],
    artifact_root: Path,
    staged_root: Path,
    temporary: Path,
) -> tuple[dict[str, Any], str, str]:
    if set(request) != {"operation", "challenge", "manifest_bytes", "manifest_sha256"}:
        raise ValueError("verifier request is not closed")
    if request["operation"] != "verify-exact-14":
        raise ValueError("verifier operation is not authorized")
    challenge = _hex64(request["challenge"], "verifier challenge")
    text = request["manifest_bytes"]
    if type(text) is not str:
        raise ValueError("manifest canonical bytes must be UTF-8 text")
    raw = text.encode("utf-8", errors="strict")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != _hex64(request["manifest_sha256"], "manifest hash"):
        raise ValueError("manifest hash mismatch")
    manifest = strict_json_loads(raw)
    if canonical_json_bytes(manifest) != raw:
        raise ValueError("manifest bytes are not canonical")
    if (
        type(manifest) is not dict
        or set(manifest) != {"schema_version", "correlation_nonce", "cells"}
        or manifest["schema_version"] != 2
    ):
        raise ValueError("external verifier manifest is not closed")
    correlation = _hex64(manifest["correlation_nonce"], "correlation nonce")
    cells = manifest["cells"]
    if type(cells) is not list or len(cells) != 14:
        raise ValueError("external verifier requires exact fourteen cells")
    loaded_cells = []
    for ordinal, item in enumerate(cells):
        if type(item) is not dict or set(item) != {
            "contract",
            "authority_response",
            "receipt",
        }:
            raise ValueError("external verifier cell is not closed")
        contract = verify_contract(
            {"operation": "run-cell", "contract": item["contract"]}
        )
        identity = EXPECTED_CELLS[ordinal]
        if (contract["cell"]["repo_id"], contract["cell"]["arm_id"]) != identity:
            raise ValueError("external verifier cell order invalid")
        if contract["nonce"] != correlation:
            raise ValueError("root contracts do not share the correlation nonce")
        envelope = item["authority_response"]
        response = _verify_authority(envelope, config)
        if (
            response["contract_digest"]
            != hashlib.sha256(canonical_json_bytes(contract)).hexdigest()
            or response["cell"] != contract["cell"]
            or response["nonce"] != correlation
            or response["job_id"] != contract["job_id"]
        ):
            raise ValueError("authority response does not bind root contract")
        paths = _paths(response, artifact_root, staged_root)
        audit = temporary / f"audit-{ordinal:02d}.json"
        audit.write_bytes(canonical_json_bytes(response["audit"]))
        os.chmod(audit, 0o400)
        loaded_cells.append(
            {
                "repo_id": identity[0],
                "arm_id": identity[1],
                "attempt": 1,
                "plan": strict_json_loads(paths["plan.json"].read_bytes()),
                "inventory": strict_json_loads(paths["inventory.json"].read_bytes()),
                "receipt": item["receipt"],
                "data_image": str(paths["data.img"]),
                "hash_image": str(paths["hash.img"]),
                "process_audit": str(audit),
                "source_snapshot": str(paths["source-snapshot.tar"]),
                "tool": str(paths["tool"]),
                "config": str(paths["config"]),
                "seccomp": str(paths["seccomp"]),
            }
        )
    loaded = {
        "schema_version": 1,
        "verifier_nonce": correlation,
        "verifier_image_digest": config["trusted"]["images"]["verifier"],
        "run_contract": {
            "plan_set_hash": config["trusted"]["plan_set_hash"],
            "run_nonce": correlation,
        },
        "cells": loaded_cells,
    }
    return loaded, digest, challenge


def _verify(
    request: dict[str, Any],
    config: dict[str, Any],
    artifact_root: Path,
    staged_root: Path,
    key: Ed25519PrivateKey,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="no1-008a-verifier-") as directory:
        manifest, digest, challenge = _load_manifest(
            request, config, artifact_root, staged_root, Path(directory)
        )
        verdict = aggregate_verdict(manifest, public_config=config)
    _validate_verdict_schema(verdict)
    identity = {
        "image_digest": config["trusted"]["images"]["verifier"],
        "image_id": config["trusted"]["image_ids"]["verifier"],
        "closure_manifest_sha256": config["verifier"]["service_measurement"],
    }
    signed = {
        "manifest_sha256": digest,
        "challenge": challenge,
        "verdict": verdict,
        "service_identity": identity,
    }
    return {
        **signed,
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": key.sign(VERDICT_DOMAIN + canonical_json_bytes(signed)).hex(),
    }


def serve_once(
    listener: socket.socket,
    *,
    config: dict[str, Any],
    artifact_root: Path,
    staged_root: Path,
    key: Ed25519PrivateKey,
) -> None:
    connection, _ = listener.accept()
    connection.settimeout(READ_DEADLINE_SECONDS)
    try:
        reply = _verify(_frame(connection), config, artifact_root, staged_root, key)
    except Exception as error:
        reply = {"error": type(error).__name__, "reason": str(error)}
    try:
        _send(connection, reply)
    except (TimeoutError, BrokenPipeError, ConnectionError):
        pass
    finally:
        connection.close()


def request_verdict(
    *,
    socket_path: Path,
    manifest: dict[str, Any],
    challenge: str,
    config: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    raw = canonical_json_bytes(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    request = {
        "operation": "verify-exact-14",
        "challenge": challenge,
        "manifest_bytes": raw.decode("utf-8"),
        "manifest_sha256": digest,
    }
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(socket_path))
        option = getattr(socket, "SO_PEERCRED", None)
        if option is None:
            raise ValueError("Unix peer credentials unavailable")
        _pid, uid, _gid = struct.unpack(
            "3i", client.getsockopt(socket.SOL_SOCKET, option, 12)
        )
        if uid != config["verifier"]["peer_uid"]:
            raise ValueError("external verifier peer UID mismatch")
        _send(client, request)
        client.shutdown(socket.SHUT_WR)
        envelope = _frame(client)
    finally:
        client.close()
    if set(envelope) == {"error", "reason"}:
        raise ValueError(f"external verifier rejected manifest: {envelope['reason']}")
    expected = {
        "manifest_sha256",
        "challenge",
        "verdict",
        "service_identity",
        "key_id",
        "algorithm",
        "signature",
    }
    runtime = config["trusted"]["verifier_runtime"]
    identity = {
        "image_digest": runtime["image_digest"],
        "image_id": runtime["image_id"],
        "closure_manifest_sha256": runtime["closure_manifest_sha256"],
    }
    if (
        type(envelope) is not dict
        or set(envelope) != expected
        or envelope["manifest_sha256"] != digest
        or envelope["challenge"] != challenge
        or envelope["service_identity"] != identity
        or envelope["key_id"] != config["verifier"]["key_id"]
        or envelope["algorithm"] != "Ed25519"
    ):
        raise ValueError("external verifier verdict binding mismatch")
    signed = {
        key: envelope[key]
        for key in ("manifest_sha256", "challenge", "verdict", "service_identity")
    }
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(config["verifier"]["public_key_hex"])
    ).verify(
        bytes.fromhex(envelope["signature"]),
        VERDICT_DOMAIN + canonical_json_bytes(signed),
    )
    _validate_verdict_schema(envelope["verdict"])
    return envelope


def _load_key(path: Path) -> Ed25519PrivateKey:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(fd)
        raw = os.read(fd, 33)
    finally:
        os.close(fd)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o400
        or len(raw) != 32
    ):
        raise ValueError("verifier key must be service-owned 0400 raw Ed25519")
    return Ed25519PrivateKey.from_private_bytes(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--public-config", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--staged-root", required=True)
    args = parser.parse_args(argv)
    config = parse_public_config(Path(args.public_config).read_bytes())
    if os.geteuid() != config["verifier"]["peer_uid"]:
        raise SystemExit("verifier service UID does not match root-signed identity")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(args.socket)
    os.chmod(args.socket, 0o660)  # nosec B103
    listener.listen(16)
    while True:
        serve_once(
            listener,
            config=config,
            artifact_root=Path(args.artifact_root).resolve(strict=True),
            staged_root=Path(args.staged_root).resolve(strict=True),
            key=_load_key(Path(args.private_key).resolve(strict=True)),
        )


if __name__ == "__main__":
    raise SystemExit(main())
