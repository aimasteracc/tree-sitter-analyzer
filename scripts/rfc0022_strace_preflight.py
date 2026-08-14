#!/usr/bin/env python3
"""Pinned binary and package provenance for the RFC-0022 Linux authority."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from rfc0022_strace_model import AuthorityError

PINNED_STRACE_EXECUTABLE = "/usr/bin/strace"
PINNED_DPKG_QUERY = "/usr/bin/dpkg-query"
PINNED_AUTHORITY_PYTHON = "/usr/bin/python3"
PREFLIGHT_TIMEOUT_SECONDS = 15
VERSION_RE = re.compile(r"strace -- version (\d+(?:\.\d+){1,2})")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_root_owned_executable(path: Path, label: str) -> None:
    details = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(details.st_mode)
        or details.st_uid != 0
        or stat.S_IMODE(details.st_mode) & 0o022
    ):
        raise AuthorityError(f"{label} is not a protected root-owned executable")


def require_isolated_root_runtime() -> None:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0:
        return
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise AuthorityError(
            "root authority requires Python flags -I -S -B before project code"
        )
    expected = Path(PINNED_AUTHORITY_PYTHON).resolve(strict=True)
    actual = Path(sys.executable).resolve(strict=True)
    if actual != expected:
        raise AuthorityError("root authority Python is not the pinned system runtime")
    _require_root_owned_executable(actual, "pinned authority Python")


def strace_preflight(minimum: str, executable: str = "strace") -> dict[str, str | None]:
    resolved = shutil.which(executable)
    if resolved is None:
        raise AuthorityError("strace is absent")
    resolved_path = Path(resolved).resolve()
    try:
        result = subprocess.run(
            [os.fspath(resolved_path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            close_fds=True,
            timeout=PREFLIGHT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise AuthorityError("strace version preflight timed out") from exc
    match = VERSION_RE.search(result.stdout)
    if result.returncode != 0 or match is None:
        raise AuthorityError("strace version preflight failed")
    actual = match.group(1)
    actual_tuple = tuple(int(part) for part in actual.split("."))
    minimum_tuple = tuple(int(part) for part in minimum.split("."))
    width = max(len(actual_tuple), len(minimum_tuple))
    if actual_tuple + (0,) * (width - len(actual_tuple)) < minimum_tuple + (0,) * (
        width - len(minimum_tuple)
    ):
        raise AuthorityError(f"strace {actual} is older than required {minimum}")
    package: str | None = None
    pinned_path = Path(PINNED_STRACE_EXECUTABLE)
    if executable == PINNED_STRACE_EXECUTABLE:
        if resolved_path != pinned_path:
            raise AuthorityError("pinned strace resolved to an unexpected path")
        _require_root_owned_executable(pinned_path, "pinned strace")
        dpkg_query = Path(PINNED_DPKG_QUERY)
        if not dpkg_query.exists():
            raise AuthorityError("pinned dpkg-query is absent")
        _require_root_owned_executable(dpkg_query, "pinned dpkg-query")
        try:
            package_result = subprocess.run(
                [
                    os.fspath(dpkg_query),
                    "-W",
                    "-f=${Package}=${Version}",
                    "strace",
                ],
                check=False,
                capture_output=True,
                text=True,
                close_fds=True,
                timeout=PREFLIGHT_TIMEOUT_SECONDS,
            )
            files_result = subprocess.run(
                [os.fspath(dpkg_query), "-L", "strace"],
                check=False,
                capture_output=True,
                text=True,
                close_fds=True,
                timeout=PREFLIGHT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise AuthorityError("strace package provenance query timed out") from exc
        package = package_result.stdout.strip()
        package_files = set(files_result.stdout.splitlines())
        if (
            package_result.returncode != 0
            or not package
            or files_result.returncode != 0
            or PINNED_STRACE_EXECUTABLE not in package_files
        ):
            raise AuthorityError("strace package provenance query failed")
    return {
        "version": actual,
        "executable": os.fspath(resolved_path),
        "sha256": _sha256(resolved_path),
        "package": package,
    }
