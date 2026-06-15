#!/usr/bin/env python3
"""
Tests for grammar install hints (Issue #537).

RED-first: these tests define the expected behaviour for Leg 1 (error message)
and Leg 2 (install-state probe). They must fail before the implementation lands.
"""

import importlib.util
from argparse import Namespace
from unittest.mock import patch

from tree_sitter_analyzer.language_loader import (
    LanguageLoader,
    grammar_install_hint,
)


class TestGrammarInstallHint:
    """Leg 1: grammar_install_hint() returns the correct pip-install instruction."""

    def test_swift_hint_contains_extras_name(self):
        hint = grammar_install_hint("swift")
        assert hint is not None
        # Must mention the extras group name
        assert "swift" in hint
        # Must be a pip install instruction
        assert "pip install" in hint

    def test_kotlin_hint_contains_extras_name(self):
        hint = grammar_install_hint("kotlin")
        assert hint is not None
        assert "kotlin" in hint
        assert "pip install" in hint

    def test_python_hint_contains_extras_name(self):
        hint = grammar_install_hint("python")
        assert hint is not None
        assert "python" in hint
        assert "pip install" in hint

    def test_unknown_language_hint_is_none(self):
        """A language not in LANGUAGE_MODULES has no hint."""
        assert grammar_install_hint("unknown_lang_xyz") is None

    def test_hint_format_uses_tree_sitter_analyzer_bracket(self):
        """Hints must use the canonical 'pip install tree-sitter-analyzer[<extra>]' form."""
        hint = grammar_install_hint("swift")
        assert "tree-sitter-analyzer[swift]" in hint

    def test_rust_hint_format(self):
        hint = grammar_install_hint("rust")
        assert "tree-sitter-analyzer[rust]" in hint

    def test_go_hint_format(self):
        hint = grammar_install_hint("go")
        assert "tree-sitter-analyzer[go]" in hint

    def test_csharp_hint_format(self):
        hint = grammar_install_hint("csharp")
        assert hint is not None
        assert "pip install" in hint

    def test_all_loader_languages_have_a_hint(self):
        """Every language in LANGUAGE_MODULES must have a hint (extras or package)."""
        loader = LanguageLoader()
        no_hint = [
            lang
            for lang in loader.LANGUAGE_MODULES
            if grammar_install_hint(lang) is None
        ]
        assert no_hint == [], f"Languages missing install hint: {no_hint}"


class TestGrammarInstalledField:
    """Leg 2: ShowLanguagesCommand adds installed: bool to each language entry."""

    def test_json_output_has_installed_field(self):
        """Each language dict in the JSON envelope must have an 'installed' key."""
        from tree_sitter_analyzer.cli.info_commands import ShowLanguagesCommand

        args = Namespace(output_format="json", format="json")
        cmd = ShowLanguagesCommand(args)
        captured: dict = {}
        with patch(
            "tree_sitter_analyzer.cli.info_commands.output_json",
            side_effect=lambda d: captured.update(d) if isinstance(d, dict) else None,
        ):
            rc = cmd.execute()
        assert rc == 0
        assert "languages" in captured
        for entry in captured["languages"]:
            assert "installed" in entry, (
                f"Entry for {entry.get('language')} missing 'installed' field"
            )
            assert isinstance(entry["installed"], bool)

    def test_installed_true_for_available_grammar(self):
        """Languages whose grammar module is importable must have installed=True."""
        from tree_sitter_analyzer.cli.info_commands import ShowLanguagesCommand

        args = Namespace(output_format="json", format="json")
        cmd = ShowLanguagesCommand(args)
        captured: dict = {}
        with patch(
            "tree_sitter_analyzer.cli.info_commands.output_json",
            side_effect=lambda d: captured.update(d) if isinstance(d, dict) else None,
        ):
            cmd.execute()

        # python grammar IS installed in this test env
        python_entry = next(
            (e for e in captured["languages"] if e["language"] == "python"), None
        )
        assert python_entry is not None
        assert python_entry["installed"] is True

    def test_installed_false_for_missing_grammar(self):
        """Languages whose grammar module is not importable must have installed=False."""
        from tree_sitter_analyzer.cli.info_commands import ShowLanguagesCommand

        args = Namespace(output_format="json", format="json")
        cmd = ShowLanguagesCommand(args)
        captured: dict = {}

        # Patch find_spec to simulate tree_sitter_swift not installed
        original_find_spec = importlib.util.find_spec

        def patched_find_spec(name, *args, **kwargs):
            if name == "tree_sitter_swift":
                return None
            return original_find_spec(name, *args, **kwargs)

        with (
            patch("importlib.util.find_spec", side_effect=patched_find_spec),
            patch(
                "tree_sitter_analyzer.cli.info_commands.output_json",
                side_effect=lambda d: (
                    captured.update(d) if isinstance(d, dict) else None
                ),
            ),
        ):
            cmd.execute()

        swift_entry = next(
            (e for e in captured["languages"] if e["language"] == "swift"), None
        )
        assert swift_entry is not None
        assert swift_entry["installed"] is False

    def test_install_hint_field_present_for_missing_grammar(self):
        """Entries with installed=False must also carry an 'install_hint' key."""
        from tree_sitter_analyzer.cli.info_commands import ShowLanguagesCommand

        args = Namespace(output_format="json", format="json")
        cmd = ShowLanguagesCommand(args)
        captured: dict = {}

        original_find_spec = importlib.util.find_spec

        def patched_find_spec(name, *args, **kwargs):
            if name == "tree_sitter_swift":
                return None
            return original_find_spec(name, *args, **kwargs)

        with (
            patch("importlib.util.find_spec", side_effect=patched_find_spec),
            patch(
                "tree_sitter_analyzer.cli.info_commands.output_json",
                side_effect=lambda d: (
                    captured.update(d) if isinstance(d, dict) else None
                ),
            ),
        ):
            cmd.execute()

        swift_entry = next(
            (e for e in captured["languages"] if e["language"] == "swift"), None
        )
        assert swift_entry is not None
        assert "install_hint" in swift_entry
        assert swift_entry["install_hint"] is not None
        assert "pip install" in swift_entry["install_hint"]

    def test_text_output_marks_not_installed(self):
        """Text output must visually flag languages whose grammar is missing."""
        from tree_sitter_analyzer.cli.info_commands import ShowLanguagesCommand

        args = Namespace(output_format="text", format=None)
        cmd = ShowLanguagesCommand(args)
        text_lines: list[str] = []

        original_find_spec = importlib.util.find_spec

        def patched_find_spec(name, *args, **kwargs):
            if name == "tree_sitter_swift":
                return None
            return original_find_spec(name, *args, **kwargs)

        with (
            patch("importlib.util.find_spec", side_effect=patched_find_spec),
            patch(
                "tree_sitter_analyzer.cli.info_commands.output_list",
                side_effect=lambda msg: text_lines.append(msg),
            ),
        ):
            rc = cmd.execute()

        assert rc == 0
        swift_lines = [line for line in text_lines if "swift" in line.lower()]
        assert len(swift_lines) == 1
        combined = " ".join(swift_lines)
        # Must contain some indicator of not-installed state
        assert any(
            marker in combined.lower()
            for marker in ["not installed", "pip install", "[not installed]"]
        )


class TestParserErrorMessageCarriesHint:
    """Leg 1: parser.parse_code returns an error message with pip install hint
    when the grammar module is not installed."""

    def test_parse_code_error_message_contains_hint_for_grammar_missing(self):
        """When grammar module is absent, error_message must contain install hint."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser.__new__(Parser)

        # Build a minimal mock loader that says swift is unavailable
        class FakeLoader:
            def is_language_available(self, lang):
                return False

            def create_parser_safely(self, lang):
                return None

            LANGUAGE_MODULES = {"swift": "tree_sitter_swift"}

        parser._loader = FakeLoader()
        parser._encoding_manager = None  # won't be reached

        # Patch the parser-module probe: CI environments install the swift
        # grammar, so the real importlib probe would take the bare-error
        # branch there while the hint branch fires locally — pin the seam.
        from unittest.mock import patch

        with patch(
            "tree_sitter_analyzer.core.parser.is_grammar_installed",
            return_value=False,
        ):
            result = parser.parse_code("let x = 1", "swift")
        assert result.success is False
        assert result.error_message is not None
        assert "pip install" in result.error_message, (
            f"Expected pip install hint in: {result.error_message!r}"
        )
        assert "swift" in result.error_message.lower()
