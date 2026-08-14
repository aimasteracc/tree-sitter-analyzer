#!/usr/bin/env python3
"""Atomic evidence publication for the RFC-0022 strace authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import stat
import time
import uuid
from pathlib import Path
from typing import Any

TRACE_NAME = re.compile(r"trace\.(\d+)")
TERMINAL = re.compile(r"\+\+\+ (?:exited with \d+|killed by .+) \+\+\+")


def raw_trace_metadata(
    trace_dir: Path, *, expected_uid: int = 0
) -> list[dict[str, Any]]:
    metadata: list[dict[str, Any]] = []
    if not trace_dir.is_dir():
        return metadata
    directory_stat = trace_dir.stat()
    if (
        directory_stat.st_uid != expected_uid
        or stat.S_IMODE(directory_stat.st_mode) != 0o700
    ):
        raise OSError("raw trace directory lost root-only ownership")
    for path in sorted(trace_dir.iterdir()):
        match = TRACE_NAME.fullmatch(path.name)
        if match is None or not path.is_file() or path.is_symlink():
            raise OSError(f"unexpected raw trace entry: {path.name}")
        path_stat = path.stat()
        if path_stat.st_uid != expected_uid or stat.S_IMODE(path_stat.st_mode) & 0o022:
            raise OSError(f"raw trace is not root-owned and protected: {path.name}")
        raw = path.read_bytes()
        try:
            lines = raw.decode("utf-8", "strict").splitlines()
        except UnicodeDecodeError as exc:
            raise OSError(f"raw trace is not UTF-8: {path.name}") from exc
        terminal = None
        if lines:
            body = lines[-1].partition(" ")[2]
            terminal = body if TERMINAL.fullmatch(body) else None
        metadata.append(
            {
                "pid": int(match.group(1)),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
                "terminal": terminal,
            }
        )
    return metadata


def seal_trace_directory(trace_dir: Path) -> None:
    for path in trace_dir.iterdir():
        if not path.is_file() or path.is_symlink():
            raise OSError(f"cannot seal unexpected trace entry: {path.name}")
        path.chmod(0o444)
    trace_dir.chmod(0o555)


def record_error_trace_metadata(report: dict[str, Any], trace_dir: Path) -> None:
    try:
        report["raw_trace_files"] = raw_trace_metadata(trace_dir)
        seal_trace_directory(trace_dir)
    except OSError as exc:
        report["errors"].append(f"raw trace finalization failed: {exc}")


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_failure_report(
    path: Path,
    *,
    error: str,
    policy_path: Path,
    target: list[str],
    expected_returncode: int,
) -> None:
    write_report(
        path,
        {
            "schema_version": 1,
            "authority_id": "rfc0022-linux-strace-v1",
            "authority_status": "error",
            "outcome": "indeterminate",
            "errors": [error],
            "policy": {"path": os.fspath(policy_path.resolve())},
            "raw_trace_files": [],
            "target_identity": None,
            "trace_files": [],
            "violations": [],
            "target": {
                "argv": target,
                "expected_returncode": expected_returncode,
                "returncode": None,
            },
        },
    )


def surviving_token_pids(token: str) -> list[int]:
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    needle = f"RFC0022_AUTHORITY_TOKEN={token}".encode()
    survivors: list[int] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            environment = (entry / "environ").read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if needle in environment:
            survivors.append(int(entry.name))
    return sorted(survivors)


def trace_pids(trace_dir: Path) -> list[int]:
    if not trace_dir.is_dir():
        return []
    return sorted(
        int(path.name.removeprefix("trace."))
        for path in trace_dir.glob("trace.*")
        if path.is_file() and path.name.removeprefix("trace.").isdigit()
    )


def cleanup_candidates(token: str, trace_dir: Path) -> tuple[list[int], list[int]]:
    candidates = sorted(
        set(surviving_token_pids(token))
        | {pid for pid in trace_pids(trace_dir) if Path(f"/proc/{pid}").exists()}
    )
    kill_pids(candidates)
    for _ in range(20):
        remaining = [pid for pid in candidates if Path(f"/proc/{pid}").exists()]
        if not remaining:
            return candidates, []
        time.sleep(0.05)
    return candidates, remaining


def kill_pids(pids: list[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue
