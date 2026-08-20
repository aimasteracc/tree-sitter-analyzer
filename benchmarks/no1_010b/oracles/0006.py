#!/usr/bin/env python3
"""Behavioral oracle for ``no1-010b/0006-bugfix-cancel-unknown-order``.

RFC-0026 §3 declared-result protocol. Red on the unmodified fixture:
``cancel`` raises ``KeyError`` for an order that was never placed instead of
reporting ``False``, so the declared result is ``FAIL`` carrying the registered
reason token.

This is the one seed task whose registered reference patch is deliberately
wrong; its pre-registered terminal pair is ``FAIL / VERIFICATION_FAILED``.

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

from src.orders import cancel  # noqa: E402

REASON = "cancel-raises-keyerror"


def check() -> bool:
    """Return whether cancelling an unplaced order reports ``False``."""
    try:
        return cancel("oracle-0006-never-placed") is False
    except KeyError:
        return False


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
