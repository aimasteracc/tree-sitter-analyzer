#!/usr/bin/env python3
"""Behavioral oracle for ``no1-010b/0008-test-selection-totals-clamp``.

RFC-0026 §3 declared-result protocol. Red on the unmodified fixture: a negative
quantity is billed as a negative amount instead of being clamped to zero, so the
declared result is ``FAIL`` carrying the registered reason token. The
selected-test criterion is scored separately against the pre-registered
affected-test oracle in the corpus record.

Deliberately self-contained: the registered ``oracle_hash`` must cover the
whole assertion, so this file imports no shared oracle helper.
"""

from __future__ import annotations

import os
import sys

REASON = "negative-quantity-not-clamped"


def check() -> bool:
    """Return whether a negative quantity is clamped to a zero total."""
    sys.path.insert(0, os.getcwd())
    from src.totals import total

    return total(-1, 500) == 0 and total(3, 500) == 1500


def main() -> int:
    try:
        held = check()
    except Exception as exc:
        # A crash is an infrastructure failure, never a behavioral verdict.
        print(f"oracle could not decide: {exc!r}", file=sys.stderr)
        return 1
    print(f"NO1_010B_ORACLE_REASON: {REASON}")
    print(f"NO1_010B_ORACLE_RESULT: {'PASS' if held else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
