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

This B0 module deliberately exports no production oracle runner. Its private
process helper exists only to contract-test the declared-result protocol; it
sanitizes the environment but does not claim network or filesystem isolation.
RFC-0026 B1 owns the public entry point and may call the private helper only
from inside its kernel-enforced sandbox.
"""

from __future__ import annotations

import os
import secrets
import shlex
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Literal

ORACLE_TIMEOUT_S = 60.0
ORACLE_OUTPUT_MAX_BYTES = 64 * 1024
_RESULT_MARKER = "NO1_010B_ORACLE_RESULT:"
_REASON_MARKER = "NO1_010B_ORACLE_REASON:"
_MINIMAL_PATH = "/usr/bin:/bin"
_IS_WINDOWS = os.name == "nt"
_TASKKILL = subprocess.run
_REAP_TIMEOUT_S = 5.0
_WRAPPER_MARKER = "NO1_010B_TRUSTED_WRAPPER:"


def _oracle_bootstrap(token: str) -> str:
    """Build a per-run capability marker not exposed through argv or env."""
    marker = f"{_WRAPPER_MARKER}{token}:"
    return (
        "import builtins, runpy, sys, traceback\n"
        "_original_import = builtins.__import__\n"
        "_import_failure = None\n"
        "def _tracked_import(*args, **kwargs):\n"
        "    global _import_failure\n"
        "    try:\n"
        "        return _original_import(*args, **kwargs)\n"
        "    except BaseException as exc:\n"
        "        _import_failure = exc\n"
        "        raise\n"
        "builtins.__import__ = _tracked_import\n"
        "try:\n"
        "    runpy.run_path(sys.argv[1], run_name='__main__')\n"
        "except BaseException as exc:\n"
        "    if exc is _import_failure or isinstance(exc, (ImportError, SyntaxError)):\n"
        "        traceback.print_exc()\n"
        f"        print({marker + 'LOAD_ERROR'!r}, flush=True)\n"
        "        raise SystemExit(1)\n"
        "    raise\n"
        f"print({marker + 'COMPLETE'!r}, flush=True)\n"
    )


class OracleStatus(str, Enum):
    # nosec B105 — the strings are declared-result protocol tokens, not
    # credentials; bandit's hardcoded-password heuristic false-positives on
    # the literal "PASS".
    PASS = "PASS"  # nosec B105
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


OracleUnknownReason = Literal[
    "ORACLE_LOAD_ERROR",
    "ORACLE_EXECUTION_ERROR",
    "ORACLE_PROTOCOL_ERROR",
    "ORACLE_TIMEOUT",
]


@dataclass(frozen=True)
class OracleOutcome:
    status: OracleStatus
    unknown_reason: OracleUnknownReason | None = None
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
    value = final[len(_RESULT_MARKER) :].strip()
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


def _extract_wrapper_status(
    stdout: str, token: str
) -> tuple[Literal["COMPLETE", "LOAD_ERROR"] | None, str]:
    """Separate the per-run wrapper capability from oracle-controlled output."""
    prefix = f"{_WRAPPER_MARKER}{token}:"
    lines = stdout.splitlines()
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) != 1:
        return None, stdout
    index = matches[0]
    if any(line.strip() for line in lines[index + 1 :]):
        return None, stdout
    raw_status = lines[index][len(prefix) :]
    if raw_status not in {"COMPLETE", "LOAD_ERROR"}:
        return None, stdout
    status: Literal["COMPLETE", "LOAD_ERROR"] = (
        "COMPLETE" if raw_status == "COMPLETE" else "LOAD_ERROR"
    )
    payload = "\n".join(lines[:index])
    if payload:
        payload += "\n"
    return status, payload


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


def _run_oracle_process_unisolated_for_tests(
    oracle_path: str,
    cwd: str,
    *,
    expected_reason: str,
    timeout_s: float = ORACLE_TIMEOUT_S,
    env_extra: dict[str, str] | None = None,
) -> OracleOutcome:
    """Exercise the oracle protocol without claiming a B1 sandbox.

    The helper is intentionally private and has no production callers. It uses
    a separate process group so timeout cleanup is deterministic and a minimal
    environment so protocol tests do not leak parent secrets. It does *not*
    satisfy RFC-0026 C21 by itself; B1 must establish the read-only candidate,
    scratch redirection, no-network boundary, and write journal first.
    """
    cwd_path = Path(cwd).resolve()
    oracle = Path(oracle_path)
    if not oracle.is_absolute():
        oracle = cwd_path / oracle
    if not oracle.is_file():
        return OracleOutcome(
            OracleStatus.UNKNOWN, "ORACLE_LOAD_ERROR", "oracle file not found"
        )
    wrapper_token = secrets.token_hex(32)
    command = [
        sys.executable,
        "-u",
        "-c",
        _oracle_bootstrap(wrapper_token),
        str(oracle),
    ]
    env = _sanitized_env(env_extra)
    try:
        if _IS_WINDOWS:
            proc = subprocess.Popen(  # nosec B603
                command,
                cwd=str(cwd_path),
                stdout=subprocess.PIPE,
                # One pipe preserves stdout/stderr write order, so a
                # diagnostic emitted after the declared result invalidates
                # the final-output protocol instead of being hidden on a
                # separately parsed stream.
                stderr=subprocess.STDOUT,
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
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
    except OSError as exc:
        return OracleOutcome(
            OracleStatus.UNKNOWN,
            "ORACLE_EXECUTION_ERROR",
            f"oracle could not execute: {exc}",
        )

    stdout_b = bytearray()
    overflow = threading.Event()
    drain_failed = threading.Event()
    threads = [
        threading.Thread(
            target=_drain_bounded,
            args=(proc.stdout, stdout_b, overflow, drain_failed, proc),
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
        return OracleOutcome(OracleStatus.UNKNOWN, "ORACLE_TIMEOUT", "oracle timed out")

    for thread in threads:
        thread.join(timeout=_REAP_TIMEOUT_S)
    if any(thread.is_alive() for thread in threads):
        _kill_process_tree(proc)
        _reap_process(proc)
        return OracleOutcome(
            OracleStatus.UNKNOWN,
            "ORACLE_PROTOCOL_ERROR",
            "oracle output did not close",
        )
    if overflow.is_set():
        _reap_process(proc)
        return OracleOutcome(
            OracleStatus.UNKNOWN,
            "ORACLE_PROTOCOL_ERROR",
            "oracle output exceeded limit",
        )
    if drain_failed.is_set():
        _reap_process(proc)
        return OracleOutcome(
            OracleStatus.UNKNOWN,
            "ORACLE_PROTOCOL_ERROR",
            "oracle output could not be read",
        )

    # Undecodable bytes from the oracle or its children are an infrastructure
    # failure, never a verdict (C19).
    try:
        stdout = bytes(stdout_b).decode("utf-8")
    except UnicodeDecodeError:
        return OracleOutcome(
            OracleStatus.UNKNOWN,
            "ORACLE_PROTOCOL_ERROR",
            "oracle output was not UTF-8",
        )
    wrapper_status, oracle_stdout = _extract_wrapper_status(stdout, wrapper_token)
    tail = oracle_stdout[-2000:]
    if proc.returncode != 0:
        reason: OracleUnknownReason = (
            "ORACLE_LOAD_ERROR"
            if wrapper_status == "LOAD_ERROR"
            else "ORACLE_EXECUTION_ERROR"
        )
        return OracleOutcome(OracleStatus.UNKNOWN, reason, tail)
    if wrapper_status != "COMPLETE":
        return OracleOutcome(OracleStatus.UNKNOWN, "ORACLE_EXECUTION_ERROR", tail)
    status = _parse_result_line(oracle_stdout, expected_reason)
    if status is OracleStatus.UNKNOWN:
        return OracleOutcome(status, "ORACLE_PROTOCOL_ERROR", tail)
    return OracleOutcome(status, stdout_tail=tail)


def oracle_command_line(oracle_path: str) -> str:
    """Render the sandboxed invocation for reporting (no secrets in argv)."""
    return shlex.quote(oracle_path)
