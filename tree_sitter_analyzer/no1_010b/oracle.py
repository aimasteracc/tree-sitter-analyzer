"""Trusted oracle result protocol for the NO1-010B runner (RFC-0026 §3, C19).

Raw process exit codes cannot distinguish a behavioral assertion failure from
an infrastructure failure: an uncaught ``AssertionError``, ``ImportError``,
or ``SyntaxError`` in a Python oracle all exit with code 1. The runner
therefore never scores raw codes. Every oracle prints a declared result line
as its final output; the wrapper maps:

- exit 0 AND printed ``PASS``  -> ``PASS``;
- exit 0 AND printed ``FAIL``  -> ``FAIL`` (the only path yielding
  ``ORACLE_FAILED``);
- anything else (non-zero exit, missing/malformed result line, timeout,
  sandbox denial) -> ``UNKNOWN``.

The oracle author is responsible for catching its own exceptions and printing
the declared result; an uncaught exception is an infrastructure failure, not
a behavioral answer.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

ORACLE_TIMEOUT_S = 60.0
_RESULT_MARKER = "NO1_010B_ORACLE_RESULT:"


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
    """Read the declared result line from the oracle's final output."""
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith(_RESULT_MARKER):
            value = stripped[len(_RESULT_MARKER) :].strip().upper()
            if value == "PASS":
                return OracleStatus.PASS
            if value == "FAIL":
                return OracleStatus.FAIL
            return OracleStatus.UNKNOWN
    return OracleStatus.UNKNOWN


def run_oracle(
    oracle_path: str,
    cwd: str,
    *,
    timeout_s: float = ORACLE_TIMEOUT_S,
    env_extra: dict[str, str] | None = None,
) -> OracleOutcome:
    """Run one oracle and classify its outcome via the declared-result line.

    Executes with ``setsid`` (its own process group) so a hung oracle can be
    killed cleanly; the timeout maps to ``UNKNOWN``. No network or secrets
    are available in the sandboxed environment (RFC-0026 C21); only ``cwd``
    is writable.
    """
    oracle = Path(oracle_path)
    if not oracle.is_file():
        return OracleOutcome(OracleStatus.UNKNOWN, "oracle file not found")
    command = [str(oracle)]
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env_extra,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired:
        return OracleOutcome(OracleStatus.UNKNOWN, "oracle timed out")
    except OSError as exc:
        return OracleOutcome(OracleStatus.UNKNOWN, f"oracle could not execute: {exc}")

    tail = (proc.stdout or "")[-2000:]
    if proc.returncode != 0:
        # Uncaught exception / interpreter error / non-zero exit: never a
        # behavioral FAIL (RFC-0026 C19).
        return OracleOutcome(OracleStatus.UNKNOWN, tail)
    return OracleOutcome(_parse_result_line(proc.stdout or ""), tail)


def oracle_command_line(oracle_path: str) -> str:
    """Render the sandboxed invocation for reporting (no secrets in argv)."""
    return shlex.quote(oracle_path)
