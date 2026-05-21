#!/usr/bin/env python3
"""Tests for the shared CLI output-format helper.

r37am (dogfood): consolidated three duplicate ``_wants_json`` /
``_wants_json_output`` helpers into a single module. This test pins:

1. The helper behaves correctly across the format / output_format /
   default cases.
2. No other module in ``tree_sitter_analyzer/cli/`` re-declares the
   same helper (anti-duplication guard).
"""

from __future__ import annotations

import re
from argparse import Namespace
from pathlib import Path

import pytest

from tree_sitter_analyzer.cli.output_format import wants_json_output


class TestWantsJsonOutput:
    """Pin behaviour of :func:`wants_json_output` across input shapes."""

    def test_format_json_explicit(self):
        args = Namespace(format="json", output_format=None)
        assert wants_json_output(args) is True

    def test_output_format_json_fallback(self):
        args = Namespace(format=None, output_format="json")
        assert wants_json_output(args) is True

    def test_format_takes_precedence_over_output_format(self):
        """``--format`` should win over ``--output-format`` when both set."""
        args = Namespace(format="json", output_format="text")
        assert wants_json_output(args) is True

    def test_format_text_explicit(self):
        args = Namespace(format="text", output_format=None)
        assert wants_json_output(args) is False

    def test_output_format_text(self):
        args = Namespace(format=None, output_format="text")
        assert wants_json_output(args) is False

    def test_neither_attribute_set(self):
        args = Namespace()
        assert wants_json_output(args) is False

    def test_format_toon(self):
        """``--format=toon`` is not JSON — return False."""
        args = Namespace(format="toon", output_format=None)
        assert wants_json_output(args) is False

    @pytest.mark.parametrize(
        "value", [None, "", "JSON", "json ", " json", "txt", "yaml"]
    )
    def test_non_json_values_return_false(self, value):
        """Only the exact lowercase string ``"json"`` triggers JSON path."""
        args = Namespace(format=value, output_format=None)
        assert wants_json_output(args) is False


class TestSingleSourceOfTruth:
    """r37am: anti-duplication guard — only one definition allowed."""

    def test_no_duplicate_wants_json_helper(self):
        """Only ``cli/output_format.py`` may define ``_wants_json*`` helpers.

        Catches the case where someone re-adds a local ``_wants_json``
        copy in a different CLI module instead of importing the shared
        one.
        """
        cli_root = (
            Path(__file__).parent.parent.parent.parent / "tree_sitter_analyzer" / "cli"
        )
        # Match standalone ``def _wants_json...`` or ``def wants_json_output``
        # — not ``= wants_json_output`` (re-export alias).
        definition_re = re.compile(r"^def\s+(_?wants_json[a-z_]*)\s*\(", re.MULTILINE)
        violations: list[tuple[Path, list[str]]] = []
        for py_file in cli_root.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            matches = definition_re.findall(text)
            if not matches:
                continue
            relative = py_file.relative_to(cli_root.parent.parent)
            if relative.name == "output_format.py":
                # Source of truth — defining the function is expected.
                continue
            violations.append((relative, matches))
        assert not violations, (
            "r37am: duplicate _wants_json helper found outside "
            "cli/output_format.py — every CLI module must import the "
            "shared ``wants_json_output``. Offenders: "
            + ", ".join(f"{p}: {names}" for p, names in violations)
        )
