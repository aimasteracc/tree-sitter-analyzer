"""Bounded, process-tree-safe Git subprocess execution."""

from __future__ import annotations

import os
import signal
import subprocess  # nosec B404
import threading
from collections.abc import Callable
from typing import BinaryIO

from .source_oracle import SourceOracleError, _remaining

PopenFactory = Callable[..., subprocess.Popen[bytes]]
_IS_WINDOWS = os.name == "nt"
_TASKKILL = subprocess.run
_KILL_PROCESS_GROUP = os.killpg


def _group_options() -> dict[str, object]:
    if _IS_WINDOWS:
        return {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        }
    return {"start_new_session": True}


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    """Best-effort hard termination of Git and all hook/helper descendants."""
    try:
        if _IS_WINDOWS and getattr(proc, "pid", None) is not None:
            _TASKKILL(  # nosec B603 B607
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        elif getattr(proc, "pid", None) is not None:
            _KILL_PROCESS_GROUP(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except OSError:
            pass


def run_git_bounded(
    root: str,
    args: list[str],
    *,
    deadline: float,
    limit: int,
    env: dict[str, str] | None = None,
    input_: bytes | None = None,
    popen: PopenFactory = subprocess.Popen,
) -> bytes:
    """Run Git with bounded pipes, disabled fsmonitor, and mandatory reaping."""
    if limit < 0:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    child_env = env
    if child_env is None:
        child_env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("GIT_")
        }
        child_env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        proc = popen(  # nosec B603
            ["git", "-c", "core.fsmonitor=false", *args],
            cwd=root,
            stdin=subprocess.PIPE if input_ is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env,
            **_group_options(),
        )
    except OSError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc

    output = bytearray()
    errors = bytearray()
    failures: list[str] = []

    def drain(stream: BinaryIO | None, target: bytearray, cap: int, code: str) -> None:
        try:
            if stream is None:
                failures.append("DIFF_SNAPSHOT_GIT_ERROR")
                return
            while chunk := stream.read(64 * 1024):
                if len(target) + len(chunk) > cap:
                    failures.append(code)
                    _kill_group(proc)
                    return
                target.extend(chunk)
        except OSError:
            failures.append("DIFF_SNAPSHOT_GIT_ERROR")
            _kill_group(proc)

    def feed() -> None:
        if proc.stdin is None or input_ is None:
            return
        try:
            proc.stdin.write(input_)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    threads = [
        threading.Thread(
            target=drain,
            args=(proc.stdout, output, limit, "DIFF_SNAPSHOT_CAPACITY"),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=(proc.stderr, errors, 64 * 1024, "DIFF_SNAPSHOT_GIT_ERROR"),
            daemon=True,
        ),
    ]
    if input_ is not None:
        threads.append(threading.Thread(target=feed, daemon=True))
    for thread in threads:
        thread.start()
    try:
        proc.wait(timeout=_remaining(deadline))
        for thread in threads:
            thread.join(timeout=_remaining(deadline))
        if any(thread.is_alive() for thread in threads):
            raise subprocess.TimeoutExpired("git", 0)
    except subprocess.TimeoutExpired as exc:
        _kill_group(proc)
        proc.wait()
        for thread in threads:
            thread.join()
        raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT") from exc
    if failures:
        _kill_group(proc)
        proc.wait()
        for thread in threads:
            thread.join()
        raise SourceOracleError(failures[0])
    if proc.returncode != 0:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    return bytes(output)
