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

    def test_no_inline_format_getattr_duplication(self):
        """r37an: catch the INLINE pattern that r37am's guard missed.

        ``fmt = getattr(args, "format", None) or getattr(args,
        "output_format", ...)`` followed by ``if fmt == "json"`` is
        functionally identical to ``wants_json_output(args)`` but the
        guard above only checks function definitions. r37an caught
        ``sql_platform_helpers.py`` re-inlining the same pattern.
        This test extends the guard to flag any new inline copy.

        Allowlist: ``output_format.py`` (the definition) and
        ``_effective_output_format`` in ``special_commands.py`` which
        returns the format *string* (with a "json" default), not a
        boolean — different semantics so an explicit allowlist entry.
        """
        cli_root = (
            Path(__file__).parent.parent.parent.parent / "tree_sitter_analyzer" / "cli"
        )
        # Match the two-call getattr pattern that drove r37am consolidation.
        inline_re = re.compile(
            r'getattr\s*\(\s*args\s*,\s*["\']format["\'].*?\s*'
            r'or\s+getattr\s*\(\s*args\s*,\s*["\']output_format["\']',
            re.DOTALL,
        )
        # Files that legitimately use this idiom for a *different* purpose.
        allowlist = {
            "output_format.py",  # the canonical definition
            # _effective_output_format returns the *string* (with default),
            # not a bool — different semantics.
            "special_commands.py",
        }
        violations: list[Path] = []
        for py_file in cli_root.rglob("*.py"):
            if py_file.name in allowlist:
                continue
            text = py_file.read_text(encoding="utf-8")
            if inline_re.search(text):
                violations.append(py_file.relative_to(cli_root.parent.parent))
        assert not violations, (
            "r37an: inline `getattr(args, 'format', ...) or getattr(args, "
            "'output_format', ...)` pattern found outside "
            "cli/output_format.py. Use ``wants_json_output(args)`` instead. "
            f"Offenders: {violations}"
        )
