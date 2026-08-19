#!/usr/bin/env python3
"""Behavioral oracle for ``no1-010b/0004-test-selection-dispatch-version``.

RFC-0026 §3 declared-result protocol. Red on the unmodified fixture: there is
no ``/version`` route, so the declared result is ``FAIL`` carrying the
registered reason token. The selected-test criterion is scored separately
against the pre-registered affected-test oracle in the corpus record.

Deliberately self-contained: the registered ``oracle_hash`` must cover the
whole assertion, so this file imports no shared oracle helper.
"""

from __future__ import annotations

import os
import sys

REASON = "version-route-missing"


def check() -> bool:
    """Return whether ``/version`` answers with the pinned version body."""
    sys.path.insert(0, os.getcwd())
    from src.dispatch import dispatch

    response = dispatch("/version")
    return (
        getattr(response, "status", None) == 200
        and getattr(response, "body", None) == "1"
    )


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
