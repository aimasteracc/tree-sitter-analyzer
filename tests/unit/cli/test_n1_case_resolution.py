#!/usr/bin/env python3
"""N1 (round-28): ``--case`` last-wins detection + ``meta.case_sensitive`` echo.

Reproduces the round-28 dogfood bug:

* ``--case sensitive --case insensitive`` silently overrode the first value.
* The response had no ``case_sensitive`` echo, so the caller couldn't tell
  which mode actually won.

The fix:

* CLI helper emits a stderr warning when ``--case`` is passed more than once,
  using last-wins (argparse's default).
* The MCP tool response's ``meta.case_sensitive`` is now a strict ``bool``
  (never ``None``): ``True`` only when the resolved case is ``"sensitive"``.
"""

from __future__ import annotations

import io

import pytest

from tree_sitter_analyzer.cli.commands._case_resolution import (
    case_to_sensitive_bool,
    collect_case_args,
    warn_on_duplicate_case,
)


class TestN1CaseResolutionHelpers:
    """Unit tests for the ``--case`` resolution helper."""

    def test_collect_case_args_space_form(self) -> None:
        argv = ["find-and-grep", "--case", "sensitive", "--query", "foo"]
        assert collect_case_args(argv) == ["sensitive"]

    def test_collect_case_args_equals_form(self) -> None:
        argv = ["find-and-grep", "--case=insensitive", "--query", "foo"]
        assert collect_case_args(argv) == ["insensitive"]

    def test_collect_case_args_duplicates(self) -> None:
        argv = [
            "find-and-grep",
            "--case",
            "sensitive",
            "--query",
            "foo",
            "--case",
            "insensitive",
        ]
        assert collect_case_args(argv) == ["sensitive", "insensitive"]

    def test_case_to_sensitive_bool_returns_bool(self) -> None:
        assert case_to_sensitive_bool("sensitive") is True
        assert case_to_sensitive_bool("insensitive") is False
        assert case_to_sensitive_bool("smart") is False
        assert case_to_sensitive_bool(None) is False
        # Strict bool — never None — even for unrecognized values.
        assert case_to_sensitive_bool("bogus") is False
        assert isinstance(case_to_sensitive_bool(None), bool)

    def test_warn_on_duplicate_case_no_duplicate(self) -> None:
        buf = io.StringIO()
        warned = warn_on_duplicate_case(
            "sensitive",
            argv=["find-and-grep", "--case", "sensitive"],
            stream=buf,
        )
        assert warned is False
        assert buf.getvalue() == ""

    def test_warn_on_duplicate_case_emits_warning(self) -> None:
        buf = io.StringIO()
        warned = warn_on_duplicate_case(
            "insensitive",
            argv=[
                "find-and-grep",
                "--case",
                "sensitive",
                "--case",
                "insensitive",
            ],
            stream=buf,
        )
        assert warned is True
        message = buf.getvalue()
        assert "warning:" in message
        assert "--case" in message
        assert "sensitive" in message
        assert "insensitive" in message
        # The resolved value (last-wins) is echoed so the caller knows
        # which one won.
        assert "insensitive" in message.rsplit("using last value:", 1)[-1]


