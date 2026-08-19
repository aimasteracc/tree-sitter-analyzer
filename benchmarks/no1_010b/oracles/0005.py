#!/usr/bin/env python3
"""Behavioral oracle for ``no1-010b/0005-bugfix-discount-ignored``.

RFC-0026 §3 declared-result protocol. Red on the unmodified fixture: ``total``
drops its ``discount`` argument and bills full price, so the declared result is
``FAIL`` carrying the registered reason token.

Deliberately self-contained: the registered ``oracle_hash`` must cover the
whole assertion, so this file imports no shared oracle helper.
"""

from __future__ import annotations

import os
import sys

REASON = "discount-not-applied"


def check() -> bool:
    """Return whether a discount reduces the billed amount."""
    sys.path.insert(0, os.getcwd())
    from src.totals import total

    return total(3, 500, 100) == 1400 and total(3, 500) == 1500


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
