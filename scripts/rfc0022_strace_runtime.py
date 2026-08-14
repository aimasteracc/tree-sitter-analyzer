#!/usr/bin/env python3
"""Atomic evidence publication for the RFC-0022 strace authority."""

from __future__ import annotations

import json
import os
import signal
import time
import uuid
from pathlib import Path
from typing import Any


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
