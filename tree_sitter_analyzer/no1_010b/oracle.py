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
the declared result; an uncaught exception is an infrastructure failure, not
a behavioral answer.

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
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

ORACLE_TIMEOUT_S = 60.0
_RESULT_MARKER = "NO1_010B_ORACLE_RESULT:"
_MINIMAL_PATH = "/usr/bin:/bin"


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


def _parse_result_line(stdout: str) -> OracleStatus:
    """Read the declared result from the oracle's FINAL non-empty line.

    The declared result must be the last output the oracle emits (C19/C43); a
    diagnostic printed after a PASS marker means the marker was not final, so
    the outcome is ``UNKNOWN``, never ``PASS``.
    """
    non_empty = [line for line in stdout.splitlines() if line.strip()]
    if not non_empty:
        return OracleStatus.UNKNOWN
    final = non_empty[-1].strip()
    if not final.startswith(_RESULT_MARKER):
        return OracleStatus.UNKNOWN
    value = final[len(_RESULT_MARKER) :].strip().upper()
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
    return env


def run_oracle(
    oracle_path: str,
    cwd: str,
    *,
    timeout_s: float = ORACLE_TIMEOUT_S,
    env_extra: dict[str, str] | None = None,
) -> OracleOutcome:
    """Run one oracle and classify its outcome via the declared-result line.

    Executes with ``start_new_session`` (its own session/process group) so a
    hung oracle AND its descendants can be killed cleanly on timeout; the
    timeout maps to ``UNKNOWN``. The environment is ``_sanitized_env`` — the
    runner's environment is never inherited (C21).
    """
    oracle = Path(oracle_path)
    if not oracle.is_file():
        return OracleOutcome(OracleStatus.UNKNOWN, "oracle file not found")
    command = [str(oracle)]
    env = _sanitized_env(env_extra)
    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        return OracleOutcome(OracleStatus.UNKNOWN, f"oracle could not execute: {exc}")

    try:
        stdout_b, stderr_b = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        # Kill the whole process group (start_new_session put the oracle and
        # its descendants in their own session) so no child survives to keep
        # mutating the fixture during later benchmark cases.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        proc.wait()
        return OracleOutcome(OracleStatus.UNKNOWN, "oracle timed out")

    # Undecodable bytes from the oracle or its children are an infrastructure
    # failure, never a verdict (C19): decode with replacement.
    stdout = (stdout_b or b"").decode("utf-8", errors="replace")
    stderr_tail = (stderr_b or b"").decode("utf-8", errors="replace")[-2000:]
    tail = (stdout[-2000:] + stderr_tail)[-2000:]
    if proc.returncode != 0:
        # Uncaught exception / interpreter error / non-zero exit: never a
        # behavioral FAIL (RFC-0026 C19).
        return OracleOutcome(OracleStatus.UNKNOWN, tail)
    return OracleOutcome(_parse_result_line(stdout), tail)


def oracle_command_line(oracle_path: str) -> str:
    """Render the sandboxed invocation for reporting (no secrets in argv)."""
    return shlex.quote(oracle_path)
