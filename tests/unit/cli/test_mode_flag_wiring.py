#!/usr/bin/env python3
"""Systemic contract tests for ``--X-mode`` / ``--X`` flag wiring (#1000).

Many CLI operations use a two-flag pattern: a boolean *trigger* (``--X``) plus
a paired *mode selector* (``--X-mode``). Because every selector carries a
non-None default, passing only ``--X-mode <value>`` used to silently drop the
mode and fall through to default single-file analysis (the confusing "File path
not specified" error, often exit 0).

This generalizes #982 (which fixed only ``--ast-cache-mode``) to every pair in
``_MODE_FLAG_WIRING``: each ``--X-mode`` selector must fail fast (exit 2,
naming the missing ``--X``) when used without its trigger.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.cli_main import (
    _MODE_FLAG_WIRING,
    create_argument_parser,
    main,
)


def _run_main(argv: list[str]) -> pytest.ExceptionInfo[SystemExit]:
    """Run ``main()`` with the given argv, returning the SystemExit info."""
    with patch.object(sys, "argv", ["tree_sitter_analyzer", *argv]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    return exc_info


def _valid_mode_value(mode_flag: str) -> str:
    """Return a valid value for ``mode_flag`` taken from its argparse choices."""
    parser = create_argument_parser()
    for action in parser._actions:
        if mode_flag in action.option_strings:
            choices = getattr(action, "choices", None)
            assert choices, f"{mode_flag} has no choices to pick a valid value"
            return sorted(choices)[0]
    raise AssertionError(f"{mode_flag} not found in parser")


def _trigger_flag(trigger_dest: str) -> str:
    """Map a trigger dest (``ast_cache``) to its flag token (``--ast-cache``)."""
    return "--" + trigger_dest.replace("_", "-")


# (mode_flag, trigger_dest, exemption_dests) — exactly the production table.
_PAIRS = list(_MODE_FLAG_WIRING)
_PAIR_IDS = [pair[0] for pair in _PAIRS]


@pytest.mark.parametrize("mode_flag,trigger_dest,_exempt", _PAIRS, ids=_PAIR_IDS)
def test_mode_flag_alone_errors_naming_trigger(
    mode_flag: str,
    trigger_dest: str,
    _exempt: tuple[str, ...],
    capsys,
) -> None:
    """``--X-mode <val>`` without ``--X`` → parser.error (exit 2) naming ``--X``.

    Must NOT be the generic "File path not specified" fall-through.
    """
    value = _valid_mode_value(mode_flag)
    trigger_flag = _trigger_flag(trigger_dest)

    exc_info = _run_main([mode_flag, value])

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert f"{mode_flag} requires {trigger_flag}" in err
    assert "File path not specified" not in err


def test_table_has_expected_pair_count() -> None:
    """The wiring table covers exactly the 22 discovered ``--X-mode`` pairs."""
    assert len(_MODE_FLAG_WIRING) == 22


def test_every_mode_flag_token_exists_in_parser() -> None:
    """Every table entry's mode flag + derived trigger flag are real options."""
    parser = create_argument_parser()
    known = {
        opt
        for action in parser._actions
        for opt in action.option_strings
        if opt.startswith("--")
    }
    for mode_flag, trigger_dest, _exempt in _MODE_FLAG_WIRING:
        assert mode_flag in known, f"{mode_flag} missing from parser"
        assert _trigger_flag(trigger_dest) in known, (
            f"{_trigger_flag(trigger_dest)} missing from parser"
        )


# --- exemption path (--watch is a shortcut for --ast-cache --ast-cache-mode) ---


def test_watch_exempts_ast_cache_mode() -> None:
    """``--watch --ast-cache-mode <val>`` (no ``--ast-cache``) must NOT error.

    ``--watch`` is a documented shortcut for ``--ast-cache --ast-cache-mode
    watch_start``, so the guard must treat it as satisfying the trigger.
    """
    exc_info = _run_main(["--watch", "--ast-cache-mode", "watch_start"])

    # Guard did not fire (it would have produced exit code 2 with our message).
    assert exc_info.value.code == 0


# --- both-flags happy path: a couple of representative pairs ---


def test_ast_cache_with_mode_still_dispatches() -> None:
    """``--ast-cache --ast-cache-mode stats`` → reaches dispatch, exits 0."""
    exc_info = _run_main(["--ast-cache", "--ast-cache-mode", "stats"])

    assert exc_info.value.code == 0


def test_class_hierarchy_with_mode_does_not_false_error(capsys) -> None:
    """``--class-hierarchy --class-hierarchy-mode summary`` → no wiring error.

    The trigger is present, so ``_validate_mode_flag_wiring`` must not fire.
    The command itself may exit non-zero (no file given), but it must NOT be
    the parser.error naming ``--class-hierarchy``.
    """
    exc_info = _run_main(["--class-hierarchy", "--class-hierarchy-mode", "summary"])

    err = capsys.readouterr().err
    assert "--class-hierarchy-mode requires --class-hierarchy" not in err
    # parser.error (the wiring guard) exits 2; anything else means it did not
    # fire. We assert it did NOT produce the wiring error specifically.
    assert exc_info.value.code != 2 or "requires" not in err
