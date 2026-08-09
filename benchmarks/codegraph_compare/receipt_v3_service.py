"""External one-shot executor and approver receipt services.

Both roles consume only an authority-signed job response, resolve evidence beneath
fixed read-only stores by job ID, and own exactly one private key.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import socket
import stat
import struct
import subprocess
import sys
import tempfile
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
from benchmarks.codegraph_compare.setup_qualification_paths import (
    _hash_tree_descriptor,
    canonical_relative_path,
)
from benchmarks.codegraph_compare.verifier import parse_public_config

MAX_MESSAGE = 16 * 1024 * 1024
RESPONSE_DOMAIN = b"NO1-008A-RUN-CELL-RESPONSE-V1\0"
SERVICE_RESPONSE_DOMAIN = b"NO1-008A-RECEIPT-SERVICE-RESPONSE-V1\0"
READ_DEADLINE_SECONDS = 10


def _frame(
    connection: socket.socket, seconds: float = READ_DEADLINE_SECONDS
) -> dict[str, Any]:
    value = read_frame(connection, MAX_MESSAGE, seconds, "receipt service request")
    if type(value) is not dict:
        raise ValueError("receipt service frame must be an object")
    return value


def _send(connection: socket.socket, value: dict[str, Any]) -> None:
    payload = canonical_json_bytes(value)
    if len(payload) > MAX_MESSAGE:
        raise ValueError("receipt service response exceeds protocol bound")
    connection.sendall(struct.pack("!I", len(payload)) + payload)


def _verify_authority(envelope: Any, config: dict[str, Any]) -> dict[str, Any]:
    if type(envelope) is not dict or set(envelope) != {
        "response",
        "key_id",
        "algorithm",
        "signature",
    }:
        raise ValueError("authority job envelope is not closed")
    authority = config["auditor"]
    response = envelope["response"]
    if envelope["key_id"] != authority["key_id"] or envelope["algorithm"] != "Ed25519":
        raise ValueError("authority service identity mismatch")
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(authority["public_key_hex"])
    ).verify(
        bytes.fromhex(envelope["signature"]),
        RESPONSE_DOMAIN + canonical_json_bytes(response),
    )
    if type(response) is not dict or set(response) != {
        "contract_digest",
        "job_id",
        "cell",
        "nonce",
        "audit",
        "artifacts",
    }:
        raise ValueError("authority job descriptor is not closed")
    if not re.fullmatch(r"[0-9a-f]{64}", response["job_id"]):
        raise ValueError("authority job id invalid")
    expected = {
        "core",
        "data.img",
        "hash.img",
        "launch-audit.json",
        "verity-format.txt",
    }
    descriptors = response["artifacts"]
    if (
        type(descriptors) is not list
        or {item.get("name") for item in descriptors if type(item) is dict} != expected
    ):
        raise ValueError("authority artifact descriptor set invalid")
    return response


def _regular(root: Path, relative: str) -> Path:
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise ValueError("service evidence path invalid")
    path = root / relative
    if path.resolve(strict=True) != path or root not in path.parents:
        raise ValueError("service evidence escapes fixed store")
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("service evidence must be regular")
    return path


class PinnedPaths(dict[str, Path]):
    """Paths represented only by retained descriptors after identity validation."""

    def __init__(self, values: dict[str, Path]):
        super().__init__()
        self.fds: list[int] = []
        try:
            for name, path in values.items():
                flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
                if name == "core":
                    flags |= getattr(os, "O_DIRECTORY", 0)
                fd = os.open(path, flags)
                metadata = os.fstat(fd)
                if name == "core" and not stat.S_ISDIR(metadata.st_mode):
                    raise ValueError("pinned core changed identity")
                if name != "core" and not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("pinned artifact changed identity")
                self.fds.append(fd)
                self[name] = Path(f"/proc/self/fd/{fd}")
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        while self.fds:
            os.close(self.fds.pop())


def _directory_size(fd: int) -> int:
    total = 0
    for name in os.listdir(fd):
        metadata = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("core evidence contains a symlink")
        if stat.S_ISREG(metadata.st_mode):
            total += metadata.st_size
        elif stat.S_ISDIR(metadata.st_mode):
            child = os.open(
                name,
                os.O_RDONLY
                | os.O_CLOEXEC
                | os.O_DIRECTORY
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=fd,
            )
            try:
                total += _directory_size(child)
            finally:
                os.close(child)
        else:
            raise ValueError("core evidence contains a special file")
    return total


def _paths(
    response: dict[str, Any], artifact_root: Path, staged_root: Path
) -> PinnedPaths:
    """Open every evidence object first, then hash and use only retained FDs."""
    job_id = response["job_id"]
    descriptors = response["artifacts"]
    result: dict[str, Path] = {}
    expected: dict[str, dict[str, Any]] = {}
    for item in descriptors:
        if type(item) is not dict or set(item) != {
            "name",
            "id",
            "sha256",
            "size",
            "path",
        }:
            raise ValueError("authority artifact descriptor is not closed")
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("authority artifact escapes fixed store")
        result[item["name"]] = artifact_root / relative
        expected[item["name"]] = item
    for name in (
        "plan.json",
        "inventory.json",
        "source-snapshot.tar",
        "tool",
        "config",
        "seccomp",
        "public-config.json",
    ):
        staged_relative = canonical_relative_path(f"{job_id}/{name}")
        result[name] = staged_root / staged_relative
    pinned = PinnedPaths(result)
    try:
        for name, item in expected.items():
            path = pinned[name]
            fd = int(path.name)
            if name == "core":
                digest = _hash_tree_descriptor(fd, max_bytes=64 * 1024 * 1024 * 1024)
                size = _directory_size(fd)
            else:
                digest_object = hashlib.sha256()
                size = 0
                offset = 0
                while chunk := os.pread(fd, 1024 * 1024, offset):
                    digest_object.update(chunk)
                    size += len(chunk)
                    offset += len(chunk)
                digest = digest_object.hexdigest()
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
                size != item["size"]
                or digest != item["sha256"]
                or identity != item["id"]
            ):
                raise ValueError("authority artifact changed after signing")
        return pinned
    except BaseException:
        pinned.close()
        raise


def _verity(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="strict")
    labels = {
        "Root hash": "root_hash",
        "Salt": "salt",
        "Data blocks": "data_blocks",
        "Data block size": "data_block_size",
        "Hash block size": "hash_block_size",
    }
    values: dict[str, str] = {}
    for line in text.splitlines():
        for label, key in labels.items():
            if line.startswith(label + ":"):
                values[key] = line.split(":", 1)[1].strip()
    if set(values) != set(labels.values()):
        raise ValueError("verity format evidence incomplete")
    return values


def _sign(
    role: str,
    request: dict[str, Any],
    config: dict[str, Any],
    artifact_root: Path,
    staged_root: Path,
    key: Path,
    measurement: dict[str, Any],
    launch_attestation: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    expected = {"operation", "authority_response"} | (
        {"draft"} if role == "approver" else set()
    )
    if set(request) != expected or request["operation"] != f"{role}-sign":
        raise ValueError("receipt service request is not closed")
    response = _verify_authority(request["authority_response"], config)
    paths = _paths(response, artifact_root, staged_root)
    try:
        verity = _verity(paths["verity-format.txt"])
        with tempfile.TemporaryDirectory(prefix=f"no1-008a-{role}-") as temporary:
            audit = Path(temporary) / "process-audit.json"
            audit.write_bytes(canonical_json_bytes(response["audit"]))
            os.chmod(audit, 0o400)
            parent_measurement = Path(temporary) / "parent-measurement.json"
            parent_measurement.write_bytes(canonical_json_bytes(measurement))
            os.chmod(parent_measurement, 0o400)
            launch_path = Path(temporary) / "launch-attestation.json"
            launch_path.write_bytes(canonical_json_bytes(launch_attestation))
            os.chmod(launch_path, 0o400)
            common = [
                "--launch-attestation",
                str(launch_path),
                "--parent-measurement",
                str(parent_measurement),
                "--run-nonce",
                response["nonce"],
                "--plan",
                str(paths["plan.json"]),
                "--inventory",
                str(paths["inventory.json"]),
                "--core-root",
                str(paths["core"]),
                "--data-image",
                str(paths["data.img"]),
                "--hash-image",
                str(paths["hash.img"]),
                "--process-audit",
                str(audit),
                "--root-hash",
                verity["root_hash"],
                "--salt",
                verity["salt"],
                "--data-block-size",
                verity["data_block_size"],
                "--hash-block-size",
                verity["hash_block_size"],
                "--data-blocks",
                verity["data_blocks"],
            ]
            for image_role in (
                "producer",
                "executor",
                "approver",
                "auditor",
                "verifier",
            ):
                common += [
                    f"--{image_role}-image-digest",
                    config["trusted"]["images"][image_role],
                ]
            independent = [
                "--public-config",
                str(paths["public-config.json"]),
                "--source-snapshot",
                str(paths["source-snapshot.tar"]),
                "--tool",
                str(paths["tool"]),
                "--config",
                str(paths["config"]),
                "--seccomp",
                str(paths["seccomp"]),
            ]
            if role == "executor":
                command = ["sign-executor", *independent, *common]
            else:
                draft = Path(temporary) / "draft.json"
                draft.write_bytes(canonical_json_bytes(request["draft"]))
                os.chmod(draft, 0o400)
                command = [
                    "sign-approver",
                    "--attestation",
                    str(draft),
                    *independent,
                    *common,
                ]
            command += ["--private-key", str(key), "--key-id", config[role]["key_id"]]
            plan_timeout = strict_json_loads(paths["plan.json"].read_bytes()).get(
                "wall_timeout_seconds"
            )
            if type(plan_timeout) is not int or plan_timeout < 1:
                raise ValueError("service plan timeout invalid")
            try:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "benchmarks.codegraph_compare.receipt_v3_signer",
                        *command,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    pass_fds=tuple(paths.fds)
                    + (
                        (int(key.name),)
                        if str(key).startswith("/proc/self/fd/")
                        else ()
                    ),
                )
                try:
                    stdout, stderr = process.communicate(timeout=plan_timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, 9)
                    process.communicate()
                    raise TimeoutError(
                        f"{role} verification cancelled at plan deadline"
                    ) from None
                if process.returncode:
                    raise ValueError(
                        f"{role} independent verification failed: {stderr[:200]!r}"
                    )
                result = strict_json_loads(stdout)
                return response["job_id"], result
            finally:
                paths.close()
    finally:
        paths.close()


def serve_once(
    listener: socket.socket,
    *,
    role: str,
    config: dict[str, Any],
    artifact_root: Path,
    staged_root: Path,
    key: Path,
    signer: Ed25519PrivateKey,
    measurement: dict[str, Any],
    launch_attestation: dict[str, Any],
    allowed_client_uid: int,
) -> None:
    connection, _ = listener.accept()
    try:
        peer_allowed(connection, allowed_client_uid)
        job_id, result = _sign(
            role,
            _frame(connection),
            config,
            artifact_root,
            staged_root,
            key,
            measurement,
            launch_attestation,
        )
        service_identity = measurement
        response = {
            "job_id": job_id,
            "receipt": result,
            "service_identity": service_identity,
        }
        reply = {
            "response": response,
            "key_id": config[role]["key_id"],
            "algorithm": "Ed25519",
            "signature": signer.sign(
                SERVICE_RESPONSE_DOMAIN + canonical_json_bytes(response)
            ).hex(),
        }
    except Exception as error:
        reply = {"error": type(error).__name__, "reason": str(error)}
    try:
        _send(connection, reply)
    except (TimeoutError, BrokenPipeError, ConnectionError):
        pass
    finally:
        connection.close()


def request_receipt(
    *,
    role: str,
    socket_path: Path,
    authority_response: dict[str, Any],
    config: dict[str, Any],
    draft: dict[str, Any] | None = None,
    timeout: float = 360,
) -> dict[str, Any]:
    if timeout <= 0:
        raise TimeoutError(f"{role} overall deadline expired")
    service = config[role]
    request: dict[str, Any] = {
        "operation": f"{role}-sign",
        "authority_response": authority_response,
    }
    if role == "approver":
        if draft is None:
            raise ValueError("approver requires executor draft")
        request["draft"] = draft
    elif draft is not None:
        raise ValueError("executor does not accept a draft")
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
        if uid != service["peer_uid"]:
            raise ValueError(f"{role} service peer UID mismatch")
        payload = canonical_json_bytes(request)
        if len(payload) > MAX_MESSAGE:
            raise ValueError("receipt service request exceeds protocol bound")
        client.sendall(struct.pack("!I", len(payload)) + payload)
        client.shutdown(socket.SHUT_WR)
        reply = _frame(client, timeout)
    finally:
        client.close()
    if set(reply) == {"error", "reason"}:
        raise ValueError(f"{role} service rejected job: {reply['reason']}")
    expected_job = authority_response["response"]["job_id"]
    if type(reply) is not dict or set(reply) != {
        "response",
        "key_id",
        "algorithm",
        "signature",
    }:
        raise ValueError(f"{role} service response binding mismatch")
    response = reply["response"]
    expected_identity = config["trusted"][f"{role}_runtime"]["measurement"]
    if (
        type(response) is not dict
        or set(response) != {"job_id", "receipt", "service_identity"}
        or response["job_id"] != expected_job
        or response["service_identity"] != expected_identity
        or reply["key_id"] != service["key_id"]
        or reply["algorithm"] != "Ed25519"
    ):
        raise ValueError(f"{role} service response binding mismatch")
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(service["public_key_hex"])).verify(
        bytes.fromhex(reply["signature"]),
        SERVICE_RESPONSE_DOMAIN + canonical_json_bytes(response),
    )
    receipt = response["receipt"]
    if type(receipt) is not dict:
        raise ValueError(f"{role} service receipt is not an object")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("executor", "approver"))
    parser.add_argument("--socket", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--public-config", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--staged-root", required=True)
    parser.add_argument("--allowed-client-uid", required=True, type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--launch-attestation")
    args = parser.parse_args(argv)
    config = parse_public_config(Path(args.public_config).read_bytes())
    if os.geteuid() != config[args.role]["peer_uid"]:
        raise SystemExit("receipt service UID does not match root-signed identity")
    # Measure and authenticate the actual launch before the signing key is opened.
    measurement = measure_runtime(
        config["trusted"][f"{args.role}_runtime"]["measurement"]
    )
    if not args.launch_attestation:
        raise SystemExit("root-signed service launch attestation is required")
    launch_attestation = strict_json_loads(Path(args.launch_attestation).read_bytes())
    verify_service_launch_attestation(
        launch_attestation,
        args.role,
        config,
    )
    key_fd, key_raw = secure_key(Path(args.private_key), os.geteuid())
    key_path = Path(f"/proc/self/fd/{key_fd}")
    signer = Ed25519PrivateKey.from_private_bytes(key_raw)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(args.socket)
    os.chmod(args.socket, 0o660)  # nosec B103
    listener.listen(args.workers)

    def worker() -> None:
        while True:
            serve_once(
                listener,
                role=args.role,
                config=config,
                artifact_root=Path(args.artifact_root).resolve(strict=True),
                staged_root=Path(args.staged_root).resolve(strict=True),
                key=key_path,
                signer=signer,
                measurement=measurement,
                launch_attestation=launch_attestation,
                allowed_client_uid=args.allowed_client_uid,
            )

    with ThreadPoolExecutor(
        max_workers=args.workers, thread_name_prefix=args.role
    ) as pool:
        futures = [pool.submit(worker) for _ in range(args.workers)]
        for future in futures:
            future.result()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
