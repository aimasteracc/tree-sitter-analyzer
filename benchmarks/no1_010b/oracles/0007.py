#!/usr/bin/env python3
"""Behavioral oracle for ``no1-010b/0007-migration-drop-legacy-total``.

RFC-0026 §3 declared-result protocol. Red on the unmodified fixture: ``place``
still routes through the deprecated ``legacy_total``, so the declared result is
``FAIL`` carrying the registered reason token. The check is behavioral, not
textual: the deprecated callee is replaced with a tripwire and the oracle
observes whether it is reached.

Deliberately self-contained: the registered ``oracle_hash`` must cover the
whole assertion, so this file imports no shared oracle helper.
"""

from __future__ import annotations

import os
import sys

REASON = "legacy-total-still-called"


def check() -> bool:
    """Return whether ``place`` bills without reaching ``legacy_total``."""
    sys.path.insert(0, os.getcwd())
    from src import orders, totals

    def tripwire(quantity: int, unit_price: int) -> int:
        raise AssertionError("legacy_total is still called")

    totals.legacy_total = tripwire
    # ``orders`` binds the name at import time, so both references must trip.
    orders.legacy_total = tripwire
    try:
        return orders.place("oracle-0007", 2, 250) == 500
    except AssertionError:
        return False


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
