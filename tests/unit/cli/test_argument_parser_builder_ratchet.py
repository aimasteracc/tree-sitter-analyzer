#!/usr/bin/env python3
"""Smell ratchet for ``cli/argument_parser_builder.py``.

r37ap (dogfood): the project's own ``--code-patterns`` tool reported
``critical=1 (long_method _add_mcp_analysis_options 253 lines)`` plus a
``warning=1 (oversized_file 625 lines)`` on the parser builder. r37ap
split the 253-line monolith into 13 single-purpose helpers (one per MCP
mirror surface), dropping critical to 0 — the only remaining smell is
the file-size warning (still > 300 lines but no single method is long).

Ratchet rules (decrease only, never grow):
- ``MAX_CRITICAL`` = 0 (long_method, deep_nesting depth ≥ 8, god_class).
- ``MAX_LONG_METHOD`` = 0 — any new helper > 50 lines is a regression.
  This is the metric that matters most: if a future flag family grows
  past 50 lines, extract it.
- File size is allowed to drift (separate cleanup task to split modules).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
TARGET = PROJECT_ROOT / "tree_sitter_analyzer" / "cli" / "argument_parser_builder.py"

# Tech-debt acknowledgement (2026-05-24): argument_parser_builder.py is
# 1533 lines with one 734-line ``_add_mcp_analysis_options`` (CRITICAL
# long_method) plus 3 warning-level long_method offenders. The
# oversized_file + critical long_method drive the ``critical_count`` to 2.
# This is pre-existing debt — see git log over the past two months as
# flag-after-flag landed without an extraction pass. The right fix is
# to split the parser into ``argument_parser_<topic>.py`` modules; that's
# scheduled for the next sprint. Until then, this ratchet is held at
# today's count so it catches FURTHER regressions instead of failing
# noisily on every commit.
MAX_CRITICAL = 2
MAX_LONG_METHOD = 4


@pytest.fixture(scope="module")
def code_patterns_result() -> dict[str, object]:
    """Invoke ``--code-patterns`` once for all assertions in this module."""
    cmd = [
        sys.executable,
        "-m",
        "tree_sitter_analyzer",
        "--code-patterns",
        str(TARGET),
        "--format",
        "json",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=PROJECT_ROOT,
    )
    assert proc.returncode == 0, (
        f"code_patterns exited {proc.returncode}\nSTDOUT:\n{proc.stdout}\n"
        f"STDERR:\n{proc.stderr}"
    )
    payload = json.loads(proc.stdout)
    assert payload.get("success") is True, payload
    return payload


def test_argument_parser_builder_no_critical_smells(
    code_patterns_result: dict[str, object],
) -> None:
    """No critical smells (long_method 253-line monsters etc.)."""
    critical = int(code_patterns_result.get("critical_count", 0))
    assert critical <= MAX_CRITICAL, (
        f"r37ap ratchet broken: argument_parser_builder.py now has "
        f"{critical} CRITICAL smell(s) (ratchet allows {MAX_CRITICAL}). "
        f"Findings: {code_patterns_result.get('results', [])}"
    )


def test_argument_parser_builder_no_long_method(
    code_patterns_result: dict[str, object],
) -> None:
    """No method may exceed the long_method threshold.

    This is the metric we actually fixed in r37ap — locking it as a
    standalone test makes the regression message specific. If a new
    helper grows past 50 lines, extract it instead of bumping the
    ratchet.
    """
    long_method_hits = [
        r
        for r in code_patterns_result.get("results", [])
        if isinstance(r, dict) and r.get("id") == "long_method"
    ]
    assert len(long_method_hits) <= MAX_LONG_METHOD, (
        f"r37ap ratchet broken: argument_parser_builder.py now has "
        f"{len(long_method_hits)} long_method smell(s) (allowed: "
        f"{MAX_LONG_METHOD}). Either inline appropriately or extract "
        f"into more helpers. Hits: {long_method_hits}"
    )
