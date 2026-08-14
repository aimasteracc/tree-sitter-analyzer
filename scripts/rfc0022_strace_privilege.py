#!/usr/bin/env python3
"""Privilege separation for RFC-0022 strace evidence."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Any

try:
    import pwd
except ImportError:  # pragma: no cover - Linux-only authority runtime
    pwd = None  # type: ignore[assignment]

from rfc0022_strace_model import AuthorityError

TARGET_LAUNCHER_SHA256 = "95ab811187cf9c0fb510a9b58440127497f0225725d4fc1c3f09e36b1d47912e"  # pragma: allowlist secret


def normalize_target(target: list[str]) -> list[str]:
    if not target or not target[0]:
        raise AuthorityError("target argv is empty")
    executable = Path(target[0])
    if not executable.is_absolute():
        raise AuthorityError("target executable must be absolute")
    executable = executable.resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise AuthorityError("target executable is not an executable file")
    return [os.fspath(executable), *target[1:]]


def build_invocation(
    strace: str,
    policy: dict[str, Any],
    trace_prefix: Path,
    launcher: Path,
    target: list[str],
) -> list[str]:
    return [
        strace,
        "-u",
        policy["target_user"],
        *policy["trace_arguments"],
        "-o",
        os.fspath(trace_prefix),
        "--",
        sys.executable,
        os.fspath(launcher),
        "--",
        *target,
    ]


def prepare_target_identity(
    username: str, isolation_directories: tuple[Path, ...], launcher: Path
) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise AuthorityError("authority requires root privilege separation")
    if pwd is None:
        raise AuthorityError("authority privilege separation requires Linux pwd")
    try:
        record = pwd.getpwnam(username)
    except KeyError as exc:
        raise AuthorityError(f"pinned target user is absent: {username}") from exc
    groups = sorted(set(os.getgrouplist(username, record.pw_gid)))
    if record.pw_uid == 0 or record.pw_gid == 0 or 0 in groups:
        raise AuthorityError("target identity includes root privilege")
    actual_digest = hashlib.sha256(launcher.read_bytes()).hexdigest()
    if actual_digest != TARGET_LAUNCHER_SHA256:
        raise AuthorityError("target launcher digest mismatch")
    for directory in isolation_directories:
        os.chown(directory, record.pw_uid, record.pw_gid)
        directory.chmod(0o700)
    return {
        "gid": record.pw_gid,
        "groups": groups,
        "launcher": {
            "path": os.fspath(launcher.resolve()),
            "sha256": actual_digest,
        },
        "no_new_privs": True,
        "uid": record.pw_uid,
        "user": username,
    }
