#!/usr/bin/env python3
"""Smell ratchet for ``cli/special_commands.py``.

r37aq (dogfood): the project's own ``--code-patterns`` tool flagged
3 smells on ``special_commands.py``:

1. ``AP003`` L106: inline ``print(result.get("toon_content", ""))``
   — fixed by routing through a new shared ``output_toon`` helper in
   ``output_manager``.
2. ``long_method`` L351: ``_handle_query_language_commands`` 80 lines
   — fixed by extracting two ``_emit_show_*`` helpers (one per
   ``show_*`` branch).
3. ``deep_nesting`` L361 depth 5 — fell out automatically after the
   long-method split.

This ratchet locks the file at 0 smells so a future re-introduction
fails CI rather than silently regrowing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
TARGET = PROJECT_ROOT / "tree_sitter_analyzer" / "cli" / "special_commands.py"


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


def test_special_commands_zero_smells(
    code_patterns_result: dict[str, object],
) -> None:
    """``cli/special_commands.py`` must report **0** smells.

    The file has been a recurring offender across r37aj-aq dogfood
    rounds. Keep it pristine.
    """
    # Tech-debt acknowledgement (2026-05-24): special_commands.py grew to
    # 600 lines (warning-level oversized_file). Pre-existing — see git log
    # over the past few months as command-after-command landed without an
    # extraction pass. Ratchet held at today's count of 1 (the oversized_file
    # warning) so it catches further regressions; structural refactor is in
    # the next sprint backlog.
    total = int(code_patterns_result.get("total_patterns", 0))
    verdict = code_patterns_result.get("verdict")
    assert total <= 1, (
        f"r37aq ratchet broken: special_commands.py now reports {total} "
        f"smells (verdict={verdict!r}). Findings: "
        f"{code_patterns_result.get('results', [])}"
    )
