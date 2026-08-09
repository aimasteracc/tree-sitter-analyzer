"""Filesystem and plan-mount helpers for the privileged NO1-008A authority."""

from __future__ import annotations

import hashlib
import io
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


def _sha(path: Path) -> str:
    return hashlib.sha256(_read(path)).hexdigest()


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


def _materialize_source(snapshot: Path, destination: Path) -> None:
    destination.mkdir(mode=0o700)
    payload = _read(snapshot)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        members = archive.getmembers()
        if not members or any(not member.isfile() for member in members):
            raise ValueError("source snapshot must contain regular files only")
        for member in members:
            relative = canonical_relative_path(member.name)
            if member.uid != 0 or member.gid != 0 or member.mode & 0o022:
                raise ValueError("source snapshot metadata is not root-controlled")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("source snapshot member absent")
            descriptor = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444
            )
            try:
                while chunk := stream.read(1024 * 1024):
                    os.write(descriptor, chunk)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.chmod(target, 0o444, follow_symlinks=False)
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
