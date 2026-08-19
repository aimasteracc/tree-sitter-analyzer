#!/usr/bin/env python3
"""Behavioral oracle for ``no1-010b/0010-migration-coerce-typed-values``.

RFC-0026 §3 declared-result protocol. Red on the unmodified fixture: ``load``
returns ``retries`` as the raw string because ``coerce`` is not wired in, so the
declared result is ``FAIL`` carrying the registered reason token.

Deliberately self-contained: the registered ``oracle_hash`` must cover the
whole assertion, so this file imports no shared oracle helper.
"""

from __future__ import annotations

import os
import sys

REASON = "retries-not-coerced"


def check() -> bool:
    """Return whether ``load`` coerces ``retries`` to a typed integer."""
    sys.path.insert(0, os.getcwd())
    from src.config import load

    settings = load({"host": "db", "retries": "3"})
    retries = settings["retries"]
    return (
        isinstance(retries, int)
        and not isinstance(retries, bool)
        and retries == 3
        and settings["host"] == "db"
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
