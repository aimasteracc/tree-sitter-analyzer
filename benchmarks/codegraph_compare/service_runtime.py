"""Root-authorized runtime measurement and hardened Unix framing helpers."""

from __future__ import annotations

import hashlib
import os
import socket
import stat
import struct
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

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
    metadata = os.fstat(fd)
    raw = os.read(fd, 33)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != expected_uid
        or stat.S_IMODE(metadata.st_mode) != 0o400
        or metadata.st_size != 32
        or len(raw) != 32
    ):
        os.close(fd)
        raise ValueError("private key must be service-owned 0400 regular 32-byte file")
    os.lseek(fd, 0, os.SEEK_SET)
    return fd, raw


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
    actual: dict[str, str] = {}
    loaded: dict[str, Path] = {}
    for module in tuple(sys.modules.values()):
        path = (
            getattr(module, "__file__", None)
            if isinstance(module, ModuleType)
            else None
        )
        if not path:
            continue
        candidate = Path(path).resolve(strict=True)
        try:
            relative = candidate.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            continue
        if relative.endswith((".pyc", ".pyo")):
            source = Path(str(candidate)[:-1])
            if source.is_file():
                candidate = source
                relative = candidate.relative_to(PROJECT_ROOT).as_posix()
        loaded[relative] = candidate
    if set(loaded) != set(expected):
        raise ValueError("loaded project module closure differs from root manifest")
    for relative, path in sorted(loaded.items()):
        digest = _sha256_file(path)
        if expected[relative] != digest:
            raise ValueError(f"loaded project module changed: {relative}")
        actual[relative] = digest
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
