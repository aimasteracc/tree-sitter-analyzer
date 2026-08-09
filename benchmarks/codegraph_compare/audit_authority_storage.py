"""Filesystem and plan-mount helpers for the privileged NO1-008A authority."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tarfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.setup_qualification_paths import (
    canonical_relative_path,
)


def _read(path: Path, limit: int = 16 * 1024 * 1024) -> bytes:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("staged input is not regular")
        payload = bytearray()
        while chunk := os.read(descriptor, 1024 * 1024):
            payload.extend(chunk)
            if len(payload) > limit:
                raise ValueError("staged input exceeds bound")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _sha(path: Path, *, limit: int = 16 * 1024 * 1024) -> str:
    """Hash a staged regular file through its retained descriptor."""
    descriptor = os.open(
        path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ValueError("staged input exceeds authorized bound")
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError("staged input exceeds authorized bound")
            digest.update(chunk)
        if size != metadata.st_size:
            raise ValueError("staged input size changed while hashing")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _source_archive_ceiling(inventory_payload: bytes) -> int:
    """Derive a conservative USTAR ceiling from the root-authorized inventory."""
    document = json.loads(inventory_payload)
    eligibility = document.get("eligibility", document)
    files = eligibility.get("tracked_files") if type(eligibility) is dict else None
    if type(files) is not list:
        raise ValueError("authorized inventory lacks tracked files")
    payload_bytes = 0
    for item in files:
        if (
            type(item) is not list
            or len(item) != 5
            or type(item[3]) is not int
            or item[3] < 0
        ):
            raise ValueError("authorized inventory file size is invalid")
        payload_bytes += ((item[3] + 511) // 512) * 512
    # One header per file plus tar end/padding records.  Python's USTAR writer
    # pads to RECORDSIZE, so twenty extra blocks are sufficient and exact.
    ceiling = payload_bytes + (len(files) + 20) * 512
    hard_ceiling = 16 * 1024 * 1024 * 1024
    if ceiling > hard_ceiling:
        raise ValueError("authorized source inventory exceeds hard resource ceiling")
    return ceiling


def _secure_directory(path: Path, *, fresh: bool = False) -> None:
    if fresh:
        path.mkdir(mode=0o700)
    resolved = path.resolve(strict=True)
    metadata = os.stat(resolved)
    if (
        resolved != path
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise ValueError("authority directory is not root-controlled")


def _materialize_source(snapshot: Path, destination: Path, *, ceiling: int) -> None:
    """Stream an authorized USTAR without ever materializing it in memory."""
    destination.mkdir(mode=0o700)
    descriptor = os.open(
        snapshot, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > ceiling
            or metadata.st_size == 0
        ):
            raise ValueError("source snapshot exceeds authorized inventory ceiling")
        seen = 0
        with os.fdopen(os.dup(descriptor), "rb", closefd=True) as stream:
            with tarfile.open(fileobj=stream, mode="r|") as archive:
                for member in archive:
                    seen += 1
                    if not member.isfile():
                        raise ValueError(
                            "source snapshot must contain regular files only"
                        )
                    relative = canonical_relative_path(member.name)
                    if member.uid != 0 or member.gid != 0 or member.mode & 0o022:
                        raise ValueError(
                            "source snapshot metadata is not root-controlled"
                        )
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    member_stream = archive.extractfile(member)
                    if member_stream is None:
                        raise ValueError("source snapshot member absent")
                    output = os.open(
                        target,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o444,
                    )
                    try:
                        remaining = member.size
                        while remaining:
                            chunk = member_stream.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("source snapshot member truncated")
                            written = 0
                            while written < len(chunk):
                                written += os.write(output, chunk[written:])
                            remaining -= len(chunk)
                        if member_stream.read(1):
                            raise ValueError(
                                "source snapshot member exceeds header size"
                            )
                        os.fsync(output)
                    finally:
                        os.close(output)
                    os.chmod(target, 0o444, follow_symlinks=False)
        if seen == 0:
            raise ValueError("source snapshot is empty")
    finally:
        os.close(descriptor)
    for current, directories, _files in os.walk(
        destination, topdown=False, followlinks=False
    ):
        for name in directories:
            os.chmod(Path(current) / name, 0o555, follow_symlinks=False)  # nosec B103
    os.chmod(destination, 0o555)  # nosec B103


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _producer_mount_targets(plan: Mapping[str, Any]) -> tuple[str, str, str]:
    """Derive the only authorized source/tool/config targets from the signed plan."""
    executions = plan.get("executions")
    if type(executions) is not list or not executions:
        raise ValueError("producer plan executions are absent")
    tool_targets = {
        item.get("argv", [None])[0]
        for item in executions
        if type(item) is dict and type(item.get("argv")) is list and item.get("argv")
    }
    config_targets: set[Any] = set()
    source_targets: set[Any] = set()
    for item in executions:
        if type(item) is not dict or type(item.get("argv")) is not list:
            raise ValueError("producer execution argv is invalid")
        argv = item["argv"]
        for option, targets in (
            ("--config", config_targets),
            ("--source", source_targets),
        ):
            positions = [index for index, value in enumerate(argv) if value == option]
            if option == "--config" and len(positions) != 1:
                raise ValueError("producer config target is not exact")
            if any(index + 1 >= len(argv) for index in positions):
                raise ValueError("producer mount target argument is incomplete")
            targets.update(argv[index + 1] for index in positions)
    if len(tool_targets) != 1 or len(config_targets) != 1 or len(source_targets) != 1:
        raise ValueError("producer plan mount targets are not exact")
    mount_targets = tuple(tool_targets | config_targets | source_targets)
    if (
        any(
            type(target) is not str
            or not target.startswith("/")
            or Path(target).resolve().as_posix() != target
            for target in mount_targets
        )
        or len(set(mount_targets)) != 3
    ):
        raise ValueError("producer plan mount targets are not canonical and disjoint")
    return (
        next(iter(source_targets)),
        next(iter(tool_targets)),
        next(iter(config_targets)),
    )
