#!/usr/bin/env python3
"""Behavioral oracle for ``no1-010b/0009-refactor-split-load``.

RFC-0026 §3 declared-result protocol. Red on the unmodified fixture: ``load``
parses and validates in one body, so ``parse`` and ``validate`` do not exist and
the declared result is ``FAIL`` carrying the registered reason token. The oracle
also pins that the refactor accepts and rejects exactly the same inputs.

Deliberately self-contained: the registered ``oracle_hash`` must cover the
whole assertion, so this file imports no shared oracle helper.
"""

from __future__ import annotations

import os
import sys

REASON = "load-not-split"


def check() -> bool:
    """Return whether ``load`` composes ``parse`` and ``validate`` unchanged."""
    sys.path.insert(0, os.getcwd())
    from src import config

    parse = getattr(config, "parse", None)
    validate = getattr(config, "validate", None)
    if parse is None or validate is None:
        return False
    raw = {"host": "db", "retries": "3"}
    if validate(parse(raw)) != config.load(raw):
        return False
    try:
        config.load({"host": "db"})
    except ValueError:
        return True
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
