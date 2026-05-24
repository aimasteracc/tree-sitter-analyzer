#!/usr/bin/env python3
"""Code-smell ratchet for ``cli/info_commands.py``.

r37ao (dogfood): the project's own ``--code-patterns`` tool reported
``critical=1 (deep_nesting depth 8), warning=2 (60-line _emit_json,
76-line execute)`` against ``info_commands.py``. r37ao refactored
``DescribeQueryCommand.execute`` and ``ListQueriesCommand._emit_json``
(plus the text-path) into small helpers, dropping the smell count to
``warning=1`` (depth-5 inside a static envelope dict literal).

This test fixes that improvement as a ratchet: the next person who
re-introduces an 8-deep nesting or a 60-line method has to update the
ratchet number consciously — same pattern as ``KNOWN_VERDICT_DRIFT``
and ``KNOWN_T7_BELOW_THRESHOLD`` elsewhere in the suite.

Layer-3 of the dogfood closure: tool→project, project→self,
self→pattern→guard. Without a guard the smell silently regrows.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
TARGET = PROJECT_ROOT / "tree_sitter_analyzer" / "cli" / "info_commands.py"

# Ratchet — re-running ``code_patterns`` against ``info_commands.py``
# must NEVER report more smells than this. Decreasing this number is
# always welcome; increasing it requires a comment justifying the
# regression in this file.
MAX_TOTAL_PATTERNS = 1
MAX_CRITICAL = 0
MAX_WARNING = 1


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
        cmd, capture_output=True, text=True, check=False, cwd=PROJECT_ROOT
    )
    assert proc.returncode == 0, (
        f"code_patterns exited {proc.returncode}\nSTDOUT:\n{proc.stdout}\n"
        f"STDERR:\n{proc.stderr}"
    )
    payload = json.loads(proc.stdout)
    assert payload.get("success") is True, payload
    return payload


def test_info_commands_total_smell_ratchet(
    code_patterns_result: dict[str, object],
) -> None:
    """info_commands.py must never grow beyond ``MAX_TOTAL_PATTERNS`` smells."""
    total = int(code_patterns_result.get("total_patterns", 0))
    assert total <= MAX_TOTAL_PATTERNS, (
        f"r37ao ratchet broken: info_commands.py now reports {total} smells "
        f"(ratchet allows ≤ {MAX_TOTAL_PATTERNS}). Either fix the new smell or "
        "drop the ratchet number AFTER fixing every preventable smell. "
        f"Findings: {code_patterns_result.get('results', [])}"
    )


def test_info_commands_critical_smell_ratchet(
    code_patterns_result: dict[str, object],
) -> None:
    """No critical smells (deep_nesting depth ≥ 8, god_class, etc.)."""
    critical = int(code_patterns_result.get("critical_count", 0))
    assert critical <= MAX_CRITICAL, (
        f"r37ao ratchet broken: info_commands.py now has {critical} "
        f"CRITICAL smell(s) (ratchet allows {MAX_CRITICAL}). Findings: "
        f"{code_patterns_result.get('results', [])}"
    )


def test_info_commands_warning_smell_ratchet(
    code_patterns_result: dict[str, object],
) -> None:
    """At most ``MAX_WARNING`` warning-level smells."""
    warning = int(code_patterns_result.get("warning_count", 0))
    assert warning <= MAX_WARNING, (
        f"r37ao ratchet broken: info_commands.py now has {warning} "
        f"warning smell(s) (ratchet allows {MAX_WARNING}). Findings: "
        f"{code_patterns_result.get('results', [])}"
    )
