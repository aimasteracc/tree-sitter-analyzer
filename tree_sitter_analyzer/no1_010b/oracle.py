"""Trusted oracle result protocol for the NO1-010B runner (RFC-0026 §3, C19).

Raw process exit codes cannot distinguish a behavioral assertion failure from
an infrastructure failure: an uncaught ``AssertionError``, ``ImportError``,
or ``SyntaxError`` in a Python oracle all exit with code 1. The runner
therefore never scores raw codes. Every oracle prints a declared result line
as its **final** output; the wrapper maps:

- exit 0 AND the final non-empty output line is ``PASS``  -> ``PASS``;
- exit 0 AND the final non-empty output line is ``FAIL``  -> ``FAIL`` (the
  only path yielding ``ORACLE_FAILED``);
- anything else (non-zero exit, missing/malformed/non-final result line,
  timeout, sandbox denial, undecodable output) -> ``UNKNOWN``.

The oracle author is responsible for catching its own exceptions and printing
exactly one reason line matching the record before the declared result; an
uncaught exception or missing/stale reason is an infrastructure failure, not a
behavioral answer.

Security boundary (RFC-0026 C21): the wrapper never inherits the runner's
environment — the oracle runs with a deliberately constructed minimal
environment (explicit ``env_extra`` entries plus a minimal PATH), so no
secrets or project settings leak. Network isolation and out-of-worktree
write-bounds are enforced by the runner's sandbox around this wrapper (B1).
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO

ORACLE_TIMEOUT_S = 60.0
ORACLE_OUTPUT_MAX_BYTES = 64 * 1024
_RESULT_MARKER = "NO1_010B_ORACLE_RESULT:"
_REASON_MARKER = "NO1_010B_ORACLE_REASON:"
_MINIMAL_PATH = "/usr/bin:/bin"
_IS_WINDOWS = os.name == "nt"
_TASKKILL = subprocess.run
_REAP_TIMEOUT_S = 5.0


class OracleStatus(str, Enum):
    # nosec B105 — the strings are declared-result protocol tokens, not
    # credentials; bandit's hardcoded-password heuristic false-positives on
    # the literal "PASS".
    PASS = "PASS"  # nosec B105
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class OracleOutcome:
    status: OracleStatus
    stdout_tail: str = ""


def _parse_result_line(stdout: str, expected_reason: str) -> OracleStatus:
    """Read the declared result from the oracle's FINAL non-empty line.

    The declared result must be the last output the oracle emits (C19/C43); a
    diagnostic printed after a PASS marker means the marker was not final, so
    the outcome is ``UNKNOWN``, never ``PASS``.
    """
    non_empty = [line for line in stdout.splitlines() if line.strip()]
    if not non_empty:
        return OracleStatus.UNKNOWN
    result_lines = [
        line.strip() for line in non_empty if line.strip().startswith(_RESULT_MARKER)
    ]
    if len(result_lines) != 1 or non_empty[-1].strip() != result_lines[0]:
        return OracleStatus.UNKNOWN
    final = result_lines[0]
    value = final[len(_RESULT_MARKER) :].strip().upper()
    reason_lines = [
        line.strip()[len(_REASON_MARKER) :].strip()
        for line in non_empty
        if line.strip().startswith(_REASON_MARKER)
    ]
    if len(reason_lines) != 1 or reason_lines[0] != expected_reason:
        return OracleStatus.UNKNOWN
    if value == "PASS":
        return OracleStatus.PASS
    if value == "FAIL":
        return OracleStatus.FAIL
    return OracleStatus.UNKNOWN


def _sanitized_env(env_extra: dict[str, str] | None) -> dict[str, str]:
    """Construct a deliberately minimal environment for the oracle (C21).

    Never inherit the runner's environment: no secrets, tokens, or project
    settings reach the oracle. Only explicit ``env_extra`` entries plus a
    minimal PATH (so ``#!/usr/bin/env python3`` shebangs resolve) are passed.
    """
    env = dict(env_extra or {})
    env.setdefault("PATH", _MINIMAL_PATH)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _kill_process_tree(proc: subprocess.Popen[bytes]) -> None:
    """Best-effort hard termination for POSIX and Windows process trees."""
    try:
        if _IS_WINDOWS:
            completed = _TASKKILL(  # nosec B603 B607
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_REAP_TIMEOUT_S,
                check=False,
            )
            if completed.returncode != 0:
                proc.kill()
        else:
            killpg = getattr(os, "killpg", None)
            if killpg is None:
                proc.kill()
            else:
                killpg(proc.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001 - cleanup must preserve the oracle verdict
        try:
            proc.kill()
        except Exception:  # noqa: BLE001 - best-effort cleanup only
            pass


def _reap_process(proc: subprocess.Popen[bytes]) -> None:
    try:
        proc.wait(timeout=_REAP_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        _kill_process_tree(proc)
        try:
            proc.wait(timeout=_REAP_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _drain_bounded(
    stream: BinaryIO | None,
    target: bytearray,
    overflow: threading.Event,
    failed: threading.Event,
    proc: subprocess.Popen[bytes],
) -> None:
    if stream is None:
        failed.set()
        _kill_process_tree(proc)
        return
    try:
        while chunk := stream.read(8192):
            remaining = ORACLE_OUTPUT_MAX_BYTES - len(target)
            if len(chunk) > remaining:
                target.extend(chunk[: max(0, remaining)])
                overflow.set()
                _kill_process_tree(proc)
                return
            target.extend(chunk)
    except OSError:
        failed.set()
        _kill_process_tree(proc)


def run_oracle(
    oracle_path: str,
    cwd: str,
    *,
    expected_reason: str,
    timeout_s: float = ORACLE_TIMEOUT_S,
    env_extra: dict[str, str] | None = None,
) -> OracleOutcome:
    """Run one oracle and classify its outcome via the declared-result line.

    Executes with ``start_new_session`` (its own session/process group) so a
    hung oracle AND its descendants can be killed cleanly on timeout; the
    timeout maps to ``UNKNOWN``. The environment is ``_sanitized_env`` — the
    runner's environment is never inherited (C21).
    """
    cwd_path = Path(cwd).resolve()
    oracle = Path(oracle_path)
    if not oracle.is_absolute():
        oracle = cwd_path / oracle
    if not oracle.is_file():
        return OracleOutcome(OracleStatus.UNKNOWN, "oracle file not found")
    command = [sys.executable, str(oracle)]
    env = _sanitized_env(env_extra)
    try:
        if _IS_WINDOWS:
            proc = subprocess.Popen(  # nosec B603
                command,
                cwd=str(cwd_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=getattr(
                    subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
                ),
            )
        else:
            proc = subprocess.Popen(  # nosec B603
                command,
                cwd=str(cwd_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True,
            )
    except OSError as exc:
        return OracleOutcome(OracleStatus.UNKNOWN, f"oracle could not execute: {exc}")

    stdout_b = bytearray()
    stderr_b = bytearray()
    overflow = threading.Event()
    drain_failed = threading.Event()
    threads = [
        threading.Thread(
            target=_drain_bounded,
            args=(proc.stdout, stdout_b, overflow, drain_failed, proc),
            daemon=True,
        ),
        threading.Thread(
            target=_drain_bounded,
            args=(proc.stderr, stderr_b, overflow, drain_failed, proc),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        _reap_process(proc)
        for thread in threads:
            thread.join(timeout=_REAP_TIMEOUT_S)
        return OracleOutcome(OracleStatus.UNKNOWN, "oracle timed out")

    for thread in threads:
        thread.join(timeout=_REAP_TIMEOUT_S)
    if any(thread.is_alive() for thread in threads):
        _kill_process_tree(proc)
        _reap_process(proc)
        return OracleOutcome(OracleStatus.UNKNOWN, "oracle output did not close")
    if overflow.is_set():
        _reap_process(proc)
        return OracleOutcome(OracleStatus.UNKNOWN, "oracle output exceeded limit")
    if drain_failed.is_set():
        _reap_process(proc)
        return OracleOutcome(OracleStatus.UNKNOWN, "oracle output could not be read")

    # Undecodable bytes from the oracle or its children are an infrastructure
    # failure, never a verdict (C19).
    try:
        stdout = bytes(stdout_b).decode("utf-8")
        stderr = bytes(stderr_b).decode("utf-8")
    except UnicodeDecodeError:
        return OracleOutcome(OracleStatus.UNKNOWN, "oracle output was not UTF-8")
    stderr_tail = stderr[-2000:]
    tail = (stdout[-2000:] + stderr_tail)[-2000:]
    if proc.returncode != 0:
        # Uncaught exception / interpreter error / non-zero exit: never a
        # behavioral FAIL (RFC-0026 C19).
        return OracleOutcome(OracleStatus.UNKNOWN, tail)
    return OracleOutcome(_parse_result_line(stdout, expected_reason), tail)


def oracle_command_line(oracle_path: str) -> str:
    """Render the sandboxed invocation for reporting (no secrets in argv)."""
    return shlex.quote(oracle_path)
