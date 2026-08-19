#!/usr/bin/env python3
"""Behavioral oracle for ``no1-010b/0001-bugfix-dispatch-unknown-route``.

RFC-0026 §3 declared-result protocol. Red on the unmodified fixture:
``dispatch`` returns ``None`` for an unknown route instead of a 404 response,
so the declared result is ``FAIL`` carrying the registered reason token.

Deliberately self-contained: the registered ``oracle_hash`` must cover the
whole assertion, so this file imports no shared oracle helper.
"""

from __future__ import annotations

import os
import sys

REASON = "dispatch-returns-none"


def check() -> bool:
    """Return whether an unknown route answers with a 404 response."""
    sys.path.insert(0, os.getcwd())
    from src.dispatch import dispatch

    response = dispatch("/no-such-route")
    return getattr(response, "status", None) == 404


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
