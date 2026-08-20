#!/usr/bin/env python3
"""Behavioral oracle for ``no1-010b/0003-refactor-extract-route-registry``.

RFC-0026 §3 declared-result protocol. Red on the unmodified fixture:
``registry.resolve`` still answers ``None`` for every path because the route
table is inlined in ``src/dispatch.py``, so the declared result is ``FAIL``
carrying the registered reason token. The oracle also pins that the refactor
preserves the observable responses.

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

from src.dispatch import dispatch  # noqa: E402
from src.registry import resolve  # noqa: E402

REASON = "route-table-inlined"


def check() -> bool:
    """Return whether the table moved behind ``resolve`` with no behavior change."""
    moved = resolve("/health") == "ok" and resolve("/no-such-route") is None
    preserved = (
        getattr(dispatch("/health"), "body", None) == "ok"
        and getattr(dispatch("/"), "body", None) == "home"
    )
    return moved and preserved


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
