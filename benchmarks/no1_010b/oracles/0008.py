#!/usr/bin/env python3
"""Behavioral oracle for ``no1-010b/0008-test-selection-totals-clamp``.

RFC-0026 §3 declared-result protocol. Red on the unmodified fixture: a negative
quantity is billed as a negative amount instead of being clamped to zero, so the
declared result is ``FAIL`` carrying the registered reason token. The
selected-test criterion is scored separately against the pre-registered
affected-test oracle in the corpus record.

Deliberately self-contained: the registered oracle digest must cover the whole
assertion, so this file imports no shared oracle helper.
"""

from __future__ import annotations

import os
import sys

# The fixture import is at module scope and uncaught on purpose: §3 keeps
# ORACLE_LOAD_ERROR and ORACLE_EXECUTION_ERROR distinct, and §5 requires each
# to be forced independently, so a broken fixture must fail during load.
sys.path.insert(0, os.getcwd())

from src.totals import total  # noqa: E402

REASON = "negative-quantity-not-clamped"


def check() -> bool:
    """Return whether a negative quantity is clamped to a zero total."""
    return bool(total(-1, 500) == 0 and total(3, 500) == 1500)


def main() -> int:
    try:
        held = check()
    except Exception as exc:
        # A runtime crash after load is an execution error, never a verdict.
        print(f"oracle could not decide: {exc!r}", file=sys.stderr)
        return 1
    print(f"NO1_010B_ORACLE_REASON: {REASON}")
    print(f"NO1_010B_ORACLE_RESULT: {'PASS' if held else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
