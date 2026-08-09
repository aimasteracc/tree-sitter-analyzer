"""Root-authorized run-cell-only audit authority protocol server."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import socket
import stat
import struct
import time
from collections.abc import Callable, Mapping
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
    create_service_launch_attestation,
    measure_runtime,
    peer_allowed,
    read_frame,
    secure_key,
    verify_service_launch_attestation,
)
from benchmarks.codegraph_compare.trust_anchor import baked_root_public_key

MAX_MESSAGE = 4 * 1024 * 1024
READ_DEADLINE_SECONDS = 10
CONTRACT_DOMAIN = b"NO1-008A-RUN-CELL-CONTRACT-V1\0"
AUDIT_DOMAIN = b"NO1-008A-HOST-AUDIT-V1\0"
RESPONSE_DOMAIN = b"NO1-008A-RUN-CELL-RESPONSE-V1\0"
ARTIFACT_NAMES = frozenset(
    {"data.img", "hash.img", "launch-audit.json", "verity-format.txt"}
)
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
        frozenset(
            {
                "schema_version",
                "job_id",
                "cell",
                "nonce",
                "decision_id",
                "decision_contract_sha256",
                "expires_at_ns",
                "root_signature",
            }
        ),
        "run-cell decision contract",
    )
    cell = _exact(
        contract["cell"], frozenset({"repo_id", "arm_id", "attempt"}), "contract cell"
    )
    if (
        contract["schema_version"] != 3
        or type(cell["attempt"]) is not int
        or cell["attempt"] != 1
        or type(contract["expires_at_ns"]) is not int
        or contract["expires_at_ns"] <= time.time_ns()
    ):
        raise ValueError(
            "run-cell decision contract version, attempt, or expiry invalid"
        )
    for name in ("repo_id", "arm_id"):
        if type(cell[name]) is not str or not cell[name] or len(cell[name]) > 64:
            raise ValueError("contract cell identity invalid")
    _hex64(contract["job_id"], "job id")
    _hex64(contract["nonce"], "nonce")
    _hex64(contract["decision_id"], "decision id")
    _hex64(contract["decision_contract_sha256"], "decision contract digest")
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
    return read_frame(
        connection, MAX_MESSAGE, READ_DEADLINE_SECONDS, "authority request"
    )


def _write_frame(connection: socket.socket, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(value)
    if len(payload) > MAX_MESSAGE:
        raise ValueError("authority response exceeds protocol bound")
    connection.sendall(struct.pack("!I", len(payload)) + payload)


_KEY_FDS: list[int] = []


def _load_key(path: Path) -> Ed25519PrivateKey:
    descriptor, raw = secure_key(path, 0)
    _KEY_FDS.append(descriptor)
    return Ed25519PrivateKey.from_private_bytes(raw)


def _artifact_descriptor(
    name: str, raw_path: Any, contract: Mapping[str, Any], artifact_root: Path | None
) -> dict[str, Any]:
    if name not in ARTIFACT_NAMES or type(raw_path) is not str:
        raise ValueError("runner artifact set is not closed")
    path = Path(raw_path)
    job_id = contract["job_id"]
    expected_tail = (
        (job_id, "producer-output", "core") if name == "core" else (job_id, name)
    )
    if (
        not path.is_absolute()
        or tuple(path.parts[-len(expected_tail) :]) != expected_tail
        or path.resolve(strict=True) != path
        or (
            artifact_root is not None
            and (
                artifact_root not in path.parents
                or path.relative_to(artifact_root).parts[:1] != (job_id,)
            )
        )
    ):
        raise ValueError("artifact path is not authority-owned and canonical")
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError("artifact must not be a symbolic link")
    if name == "core":
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("core artifact must be a directory")
        from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree

        digest = _hash_tree(path)
        size = sum(
            os.lstat(child).st_size
            for child in path.rglob("*")
            if stat.S_ISREG(os.lstat(child).st_mode)
        )
    else:
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("artifact must be a regular file")
        descriptor = os.open(
            path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (
                metadata.st_dev,
                metadata.st_ino,
            ) or not stat.S_ISREG(opened.st_mode):
                raise ValueError("artifact identity changed while opening")
            sha = hashlib.sha256()
            size = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                sha.update(chunk)
                size += len(chunk)
            digest = sha.hexdigest()
        finally:
            os.close(descriptor)
    relative = f"{job_id}/" + "/".join(path.parts[path.parts.index(job_id) + 1 :])
    identity = hashlib.sha256(
        canonical_json_bytes(
            {"name": name, "sha256": digest, "size": size, "path": relative}
        )
    ).hexdigest()
    return {
        "name": name,
        "id": identity,
        "sha256": digest,
        "size": size,
        "path": relative,
    }


def attest_service_launch(
    container: str,
    role: str,
    config: dict[str, Any],
    key: Ed25519PrivateKey,
    key_id: str,
) -> dict[str, Any]:
    """Authority-supervisor launch attestation entrypoint."""
    if role not in {"executor", "approver", "auditor", "verifier", "decision_consumer"}:
        raise ValueError("service launch role is not authorized")
    return create_service_launch_attestation(container, role, config, key, key_id)


def serve_once(
    listener: socket.socket,
    *,
    key: Ed25519PrivateKey,
    key_id: str,
    runner: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    artifact_root: Path | None = None,
    allowed_client_uid: int | None = None,
) -> None:
    connection, _ = listener.accept()
    reply: Mapping[str, Any] | None = None
    try:
        if allowed_client_uid is not None:
            peer_allowed(connection, allowed_client_uid)
        contract = verify_contract(_read_frame(connection))
        result = _exact(
            runner(contract), frozenset({"audit", "artifacts"}), "runner result"
        )
        audit = _exact(
            result["audit"],
            frozenset({"protocol", "phase", "service_measurement", "audit"}),
            "canonical terminal audit",
        )
        artifacts = result["artifacts"]
        if type(artifacts) is not dict or frozenset(artifacts) != ARTIFACT_NAMES:
            raise ValueError("runner artifact set is not closed")
        descriptors = [
            _artifact_descriptor(name, artifacts[name], contract, artifact_root)
            for name in sorted(ARTIFACT_NAMES)
        ]
        audit_envelope = {
            "audit": audit,
            "key_id": key_id,
            "algorithm": "Ed25519",
            "signature": key.sign(AUDIT_DOMAIN + canonical_json_bytes(audit)).hex(),
        }
        response = {
            "contract_digest": hashlib.sha256(
                canonical_json_bytes(contract)
            ).hexdigest(),
            "job_id": contract["job_id"],
            "cell": contract["cell"],
            "nonce": contract["nonce"],
            "audit": audit_envelope,
            "artifacts": descriptors,
        }
        reply = {
            "response": response,
            "key_id": key_id,
            "algorithm": "Ed25519",
            "signature": key.sign(
                RESPONSE_DOMAIN + canonical_json_bytes(response)
            ).hex(),
        }
    except Exception as error:
        reply = {"error": type(error).__name__, "reason": str(error)}
    try:
        _write_frame(connection, reply)
    except (TimeoutError, BrokenPipeError, ConnectionError):
        # A client disconnect never terminates the long-lived authority service.
        pass
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--staged-root", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--allowed-client-uid", required=True, type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--public-config", required=True)
    parser.add_argument("--launch-attestation", required=True)
    args = parser.parse_args(argv)
    if os.geteuid() != 0 or platform.system() != "Linux":
        raise SystemExit("authority service requires Linux root")
    from benchmarks.codegraph_compare.audit_authority_runner import AuthorityRunner
    from benchmarks.codegraph_compare.verifier import parse_public_config

    config = parse_public_config(Path(args.public_config).read_bytes())
    measure_runtime(config["trusted"]["auditor_runtime"]["measurement"])
    verify_service_launch_attestation(
        strict_json_loads(Path(args.launch_attestation).read_bytes()), "auditor", config
    )
    key = _load_key(Path(args.private_key))
    runner = AuthorityRunner(Path(args.staged_root), Path(args.artifact_root), key)
    path = Path(args.socket)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)
    listener.listen(args.workers)

    def worker() -> None:
        while True:
            serve_once(
                listener,
                key=key,
                key_id=args.key_id,
                runner=runner,
                artifact_root=Path(args.artifact_root).resolve(strict=True),
                allowed_client_uid=args.allowed_client_uid,
            )

    with ThreadPoolExecutor(
        max_workers=args.workers, thread_name_prefix="authority"
    ) as pool:
        futures = [pool.submit(worker) for _ in range(args.workers)]
        for future in futures:
            future.result()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
