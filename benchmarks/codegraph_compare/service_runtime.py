"""Root-authorized runtime measurement and hardened Unix framing helpers."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import struct
import subprocess
import sys
import sysconfig
import time
from importlib import metadata as importlib_metadata
from pathlib import Path
from types import ModuleType
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HEX = frozenset("0123456789abcdef")


def recv_exact(connection: socket.socket, count: int, deadline: float) -> bytes:
    """Receive exactly count bytes under one monotonic deadline."""
    out = bytearray()
    while len(out) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("frame read deadline expired")
        connection.settimeout(remaining)
        chunk = connection.recv(count - len(out))
        if not chunk:
            raise ValueError("frame truncated")
        out.extend(chunk)
    return bytes(out)


def read_frame(
    connection: socket.socket, maximum: int, seconds: float, label: str
) -> Any:
    deadline = time.monotonic() + seconds
    header = recv_exact(connection, 4, deadline)
    size = struct.unpack("!I", header)[0]
    if size < 2 or size > maximum:
        raise ValueError(f"{label} size invalid")
    from benchmarks.codegraph_compare.receipt_v3 import strict_json_loads

    return strict_json_loads(recv_exact(connection, size, deadline))


def peer_allowed(connection: socket.socket, allowed_uid: int) -> None:
    option = getattr(socket, "SO_PEERCRED", None)
    if option is None:
        raise ValueError("Unix peer credentials unavailable")
    pid, uid, _gid = struct.unpack(
        "3i", connection.getsockopt(socket.SOL_SOCKET, option, 12)
    )
    if pid <= 0 or uid != allowed_uid:
        raise PermissionError("Unix client UID is not authorized")


def secure_key(path: Path, expected_uid: int) -> tuple[int, bytes]:
    """Open a key once, validate the open object, and return its retained FD."""
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(fd)
        raw = os.pread(fd, 32, 0)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or stat.S_IMODE(metadata.st_mode) != 0o400
            or metadata.st_size != 32
            or len(raw) != 32
        ):
            raise ValueError(
                "private key must be service-owned 0400 regular 32-byte file"
            )
        return fd, raw
    except BaseException:
        os.close(fd)
        raise


def _unescape_mount(value: str) -> str:
    for encoded, plain in (
        ("\\040", " "),
        ("\\011", "\t"),
        ("\\012", "\n"),
        ("\\134", "\\"),
    ):
        value = value.replace(encoded, plain)
    return value


def _mount_measurement() -> tuple[bool, list[str]]:
    rows = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    writable: list[str] = []
    root_ro: bool | None = None
    for row in rows:
        fields = row.split()
        if len(fields) < 7 or "-" not in fields:
            raise ValueError("mountinfo row invalid")
        target = _unescape_mount(fields[4])
        options = fields[5].split(",")
        if target == "/":
            root_ro = "ro" in options and "rw" not in options
        if "rw" in options:
            writable.append(target)
    if root_ro is None:
        raise ValueError("root mount absent from mountinfo")
    return root_ro, sorted(set(writable))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _module_manifest(expected: dict[str, str]) -> dict[str, str]:
    """Measure every loaded non-stdlib module and its installed RECORD."""
    loaded: dict[str, Path] = {}
    stdlib = Path(sysconfig.get_path("stdlib")).resolve(strict=True)
    purelib = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    distributions = importlib_metadata.packages_distributions()
    record_paths: set[Path] = set()
    for name, module in tuple(sys.modules.items()):
        raw = (
            getattr(module, "__file__", None)
            if isinstance(module, ModuleType)
            else None
        )
        if not raw:
            continue
        candidate = Path(raw).resolve(strict=True)
        if candidate.suffix in {".pyc", ".pyo"}:
            source = Path(str(candidate)[:-1])
            if source.is_file():
                candidate = source
        try:
            relative = candidate.relative_to(PROJECT_ROOT).as_posix()
            key = relative  # preserve the public manifest's project naming.
        except ValueError:
            try:
                candidate.relative_to(stdlib)
                in_site = candidate.is_relative_to(purelib)
            except ValueError:
                in_site = False
            if not in_site:
                # A non-stdlib module outside both roots is still first-party/package code.
                key = "external:" + candidate.as_posix()
            else:
                key = "package:" + candidate.relative_to(purelib).as_posix()
                top = name.split(".", 1)[0]
                for distribution_name in distributions.get(top, []):
                    distribution = importlib_metadata.distribution(distribution_name)
                    record = (
                        Path(str(distribution.locate_file("")))
                        / f"{distribution.metadata['Name'].replace('-', '_')}-{distribution.version}.dist-info"
                        / "RECORD"
                    )
                    if not record.is_file():
                        matches = list(
                            Path(str(distribution.locate_file(""))).glob(
                                "*.dist-info/RECORD"
                            )
                        )
                        if len(matches) == 1:
                            record = matches[0]
                    if record.is_file():
                        record_paths.add(record.resolve(strict=True))
        loaded[key] = candidate
    for record in record_paths:
        try:
            key = "package:" + record.relative_to(purelib).as_posix()
        except ValueError:
            key = "external:" + record.as_posix()
        loaded[key] = record
    if set(loaded) != set(expected):
        raise ValueError("loaded non-stdlib module closure differs from root manifest")
    actual = {key: _sha256_file(path) for key, path in sorted(loaded.items())}
    changed = [key for key in actual if actual[key] != expected[key]]
    if changed:
        raise ValueError(f"loaded module changed: {changed[0]}")
    return actual


def measure_runtime(expected: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "interpreter_sha256",
        "closure_manifest",
        "closure_manifest_sha256",
        "uid",
        "gid",
        "rootfs_readonly",
        "allowed_writable_mounts",
    }
    if type(expected) is not dict or set(expected) != keys:
        raise ValueError("root runtime measurement contract is not closed")
    interpreter = _sha256_file(Path(sys.executable).resolve(strict=True))
    manifest_expected = expected["closure_manifest"]
    if type(manifest_expected) is not dict or any(
        type(k) is not str
        or type(v) is not str
        or len(v) != 64
        or any(c not in _HEX for c in v)
        for k, v in manifest_expected.items()
    ):
        raise ValueError("root closure manifest invalid")
    manifest = _module_manifest(manifest_expected)
    root_ro, writable = _mount_measurement()
    actual = {
        "interpreter_sha256": interpreter,
        "closure_manifest": manifest,
        "closure_manifest_sha256": hashlib.sha256(
            canonical_json_bytes(manifest)
        ).hexdigest(),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "rootfs_readonly": root_ro,
        "allowed_writable_mounts": writable,
    }
    if actual != expected:
        raise ValueError(
            "actual service runtime does not match root-signed expected measurement"
        )
    return actual


SERVICE_LAUNCH_DOMAIN = b"NO1-008A-SERVICE-LAUNCH-V1\0"


def _proc_identity(pid: int | str = "self") -> dict[str, Any]:
    stat_fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()
    cgroup = Path(f"/proc/{pid}/cgroup").read_text(encoding="ascii").strip()
    status = Path(f"/proc/{pid}/status").read_text(encoding="ascii").splitlines()
    nspid_rows = [row for row in status if row.startswith("NSpid:")]
    nspids = (
        [int(value) for value in nspid_rows[0].split()[1:]]
        if len(nspid_rows) == 1
        else [int(stat_fields[0])]
    )
    if len(stat_fields) < 22 or not cgroup:
        raise ValueError("service process identity unavailable")
    return {
        "host_pid": nspids[0],
        "container_pid": nspids[-1],
        "starttime": stat_fields[21],
        "cgroup": cgroup,
    }


def create_service_launch_attestation(
    container: str,
    role: str,
    config: dict[str, Any],
    key: Ed25519PrivateKey,
    key_id: str,
) -> dict[str, Any]:
    """Authority-side Docker observation; no service self-report is trusted."""
    result = subprocess.run(
        ["docker", "inspect", container],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ValueError("authority Docker inspect failed")
    rows = json.loads(result.stdout)
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        raise ValueError("authority Docker inspect result invalid")
    item = rows[0]
    state = item.get("State", {})
    host = item.get("HostConfig", {})
    docker_config = item.get("Config", {})
    pid = state.get("Pid")
    if state.get("Running") is not True or type(pid) is not int or pid <= 0:
        raise ValueError("service container is not running")
    actual = {
        "container_id": item.get("Id"),
        "role": role,
        "image_id": item.get("Image"),
        "cmd": docker_config.get("Cmd"),
        "entrypoint": docker_config.get("Entrypoint"),
        "user": docker_config.get("User"),
        "readonly_rootfs": host.get("ReadonlyRootfs"),
        "mounts": item.get("Mounts"),
        "network_mode": host.get("NetworkMode"),
        "security_opt": host.get("SecurityOpt"),
        "process": _proc_identity(pid),
    }
    expected = config["trusted"]["service_launch"][role]
    checked = {
        name: actual[name]
        for name in (
            "image_id",
            "cmd",
            "entrypoint",
            "user",
            "readonly_rootfs",
            "mounts",
            "network_mode",
            "security_opt",
        )
    }
    if checked != expected:
        raise ValueError("actual service container launch differs from root config")
    envelope = {"attestation": actual, "key_id": key_id, "algorithm": "Ed25519"}
    envelope["signature"] = key.sign(
        SERVICE_LAUNCH_DOMAIN + canonical_json_bytes(actual)
    ).hex()
    return envelope


def verify_service_launch_attestation(
    envelope: dict[str, Any],
    role: str,
    config: dict[str, Any],
    *,
    local: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Service startup gate binding the signed Docker observation to /proc/self."""
    if type(envelope) is not dict or set(envelope) != {
        "attestation",
        "key_id",
        "algorithm",
        "signature",
    }:
        raise ValueError("service launch attestation envelope is not closed")
    authority = config["auditor"]
    if envelope["key_id"] != authority["key_id"] or envelope["algorithm"] != "Ed25519":
        raise ValueError("service launch authority identity mismatch")
    claim = envelope["attestation"]
    if type(claim) is not dict:
        raise ValueError("service launch attestation is not an object")
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(authority["public_key_hex"])
    ).verify(
        bytes.fromhex(envelope["signature"]),
        SERVICE_LAUNCH_DOMAIN + canonical_json_bytes(claim),
    )
    expected = config["trusted"]["service_launch"][role]
    checked = {name: claim[name] for name in expected}
    if claim.get("role") != role or checked != expected:
        raise ValueError("service launch root-config binding mismatch")
    actual = _proc_identity() if local is None else local
    process = claim.get("process")
    if (
        type(process) is not dict
        or type(process.get("host_pid")) is not int
        or process["host_pid"] <= 0
        or any(
            process.get(name) != actual.get(name)
            for name in ("container_pid", "starttime", "cgroup")
        )
    ):
        raise ValueError("service launch process/cgroup binding mismatch")
    return dict(claim)
