#!/usr/bin/env python3
"""Contract tests for ``--ast-cache-mode`` / ``--ast-cache`` flag wiring (#982).

``--ast-cache-mode`` is a *mode selector*; the actual trigger is the boolean
``--ast-cache``. Passing only ``--ast-cache-mode <mode>`` used to silently drop
the mode and fall through to single-file analysis (confusing "File path not
specified" error, sometimes exit 0). It must instead fail fast with a clear
message naming the missing ``--ast-cache`` flag and a non-zero exit.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.cli_main import main


def _run_main(argv: list[str]) -> pytest.ExceptionInfo[SystemExit]:
    """Run ``main()`` with the given argv, returning the SystemExit info."""
    with patch.object(sys, "argv", ["tree_sitter_analyzer", *argv]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    return exc_info


def test_ast_cache_mode_alone_errors_naming_ast_cache(capsys):
    """``--ast-cache-mode stats`` without ``--ast-cache`` → parser.error (exit 2).

    The message must name ``--ast-cache`` and must NOT be the generic
    "File path not specified" fall-through.
    """
    exc_info = _run_main(["--ast-cache-mode", "stats"])

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--ast-cache-mode requires --ast-cache" in err
    assert "File path not specified" not in err


@pytest.mark.slow_ok  # Real CLI dispatch reaches AST cache stats; macOS CI can exceed 5s.
def test_ast_cache_with_mode_still_dispatches():
    """``--ast-cache --ast-cache-mode stats`` → reaches the AST cache dispatch.

    The mode-wiring guard must NOT trip when ``--ast-cache`` is present; the
    command runs to completion and exits (any non-error tool exit is fine).
    """
    exc_info = _run_main(["--ast-cache", "--ast-cache-mode", "stats"])

    # The guard did not fire: we got through to the tool, which exits cleanly.
    # parser.error would have produced code 2 with our specific message.
    assert exc_info.value.code == 0


def test_bare_ast_cache_defaults_to_stats():
    """Bare ``--ast-cache`` (no mode) → still defaults to stats and dispatches.

    The guard only fires on explicit ``--ast-cache-mode`` without
    ``--ast-cache``; the bare ``--ast-cache`` path is unchanged.
    """
    exc_info = _run_main(["--ast-cache"])

    assert exc_info.value.code == 0
