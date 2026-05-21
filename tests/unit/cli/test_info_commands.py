#!/usr/bin/env python3
"""Tests for cli/info_commands.py"""

from argparse import Namespace
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.cli.info_commands import (
    DescribeQueryCommand,
    InfoCommand,
    ListQueriesCommand,
    ShowExtensionsCommand,
    ShowLanguagesCommand,
)


@pytest.fixture
def args_with_language():
    return Namespace(language="python", describe_query="classes")


@pytest.fixture
def args_no_language():
    return Namespace(language=None, file_path=None, describe_query="classes")


@pytest.fixture
def args_with_file():
    return Namespace(language=None, file_path="test.py", describe_query="classes")


class TestInfoCommandAbstract:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            InfoCommand(Namespace())


class TestListQueriesCommand:
    def test_with_explicit_language(self, args_with_language):
        with patch("tree_sitter_analyzer.cli.info_commands.query_loader") as mock_ql:
            mock_ql.list_queries_for_language.return_value = ["classes", "methods"]
            mock_ql.get_query_description.side_effect = ["List classes", "List methods"]
            cmd = ListQueriesCommand(args_with_language)
            result = cmd.execute()
            assert result == 0
            mock_ql.list_queries_for_language.assert_called_once_with("python")

    def test_with_file_path_language_detection(self, args_with_file):
        with (
            patch("tree_sitter_analyzer.cli.info_commands.query_loader") as mock_ql,
            patch(
                "tree_sitter_analyzer.cli.info_commands.detect_language_from_file",
                return_value="java",
            ),
        ):
            mock_ql.list_queries_for_language.return_value = ["classes"]
            mock_ql.get_query_description.return_value = "List classes"
            cmd = ListQueriesCommand(args_with_file)
            result = cmd.execute()
            assert result == 0
            mock_ql.list_queries_for_language.assert_called_once_with("java")

    def test_no_language_no_file_lists_all(self, args_no_language):
        with (
            patch("tree_sitter_analyzer.cli.info_commands.query_loader") as mock_ql,
            patch("tree_sitter_analyzer.cli.info_commands.output_list"),
        ):
            mock_ql.list_supported_languages.return_value = ["python"]
            mock_ql.list_queries_for_language.return_value = ["classes"]
            mock_ql.get_query_description.return_value = "List classes"
            cmd = ListQueriesCommand(args_no_language)
            result = cmd.execute()
            assert result == 0
            mock_ql.list_supported_languages.assert_called_once()


class TestDescribeQueryCommand:
    def test_describe_with_explicit_language(self, args_with_language):
        with (
            patch("tree_sitter_analyzer.cli.info_commands.query_loader") as mock_ql,
            patch("tree_sitter_analyzer.cli.info_commands.output_info"),
            patch("tree_sitter_analyzer.cli.info_commands.output_data"),
        ):
            mock_ql.get_query_description.return_value = "List classes"
            mock_ql.get_query.return_value = "SELECT * FROM classes"
            cmd = DescribeQueryCommand(args_with_language)
            result = cmd.execute()
            assert result == 0

    def test_describe_no_language_no_file(self, args_no_language):
        with patch("tree_sitter_analyzer.cli.info_commands.output_error") as mock_err:
            cmd = DescribeQueryCommand(args_no_language)
            result = cmd.execute()
            assert result == 1
            mock_err.assert_called_once()

    def test_describe_query_not_found(self, args_with_language):
        with (
            patch("tree_sitter_analyzer.cli.info_commands.query_loader") as mock_ql,
            patch("tree_sitter_analyzer.cli.info_commands.output_error"),
        ):
            mock_ql.get_query_description.return_value = None
            mock_ql.get_query.return_value = None
            cmd = DescribeQueryCommand(args_with_language)
            result = cmd.execute()
            assert result == 1

    def test_describe_query_value_error(self, args_with_language):
        with (
            patch("tree_sitter_analyzer.cli.info_commands.query_loader") as mock_ql,
            patch("tree_sitter_analyzer.cli.info_commands.output_error"),
        ):
            mock_ql.get_query_description.side_effect = ValueError("bad query")
            cmd = DescribeQueryCommand(args_with_language)
            result = cmd.execute()
            assert result == 1


class TestShowLanguagesCommand:
    def test_show_languages(self):
        args = Namespace()
        with (
            patch("tree_sitter_analyzer.cli.info_commands.detector") as mock_det,
            patch("tree_sitter_analyzer.cli.info_commands.output_list"),
        ):
            mock_det.get_supported_languages.return_value = ["python", "java"]
            mock_det.get_language_info.side_effect = [
                {"extensions": [".py", ".pyw"]},
                {"extensions": [".java"]},
            ]
            cmd = ShowLanguagesCommand(args)
            result = cmd.execute()
            assert result == 0
            mock_det.get_supported_languages.assert_called_once()
            assert mock_det.get_language_info.call_count == 2


class TestShowExtensionsCommand:
    def test_show_extensions(self):
        args = Namespace()
        with (
            patch("tree_sitter_analyzer.cli.info_commands.detector") as mock_det,
            patch("tree_sitter_analyzer.cli.info_commands.output_list"),
            patch("tree_sitter_analyzer.cli.info_commands.output_info"),
        ):
            mock_det.get_supported_extensions.return_value = [
                ".py",
                ".java",
                ".js",
                ".ts",
                ".go",
                ".rs",
                ".rb",
                ".c",
                ".cpp",
            ]
            cmd = ShowExtensionsCommand(args)
            result = cmd.execute()
            assert result == 0
            mock_det.get_supported_extensions.assert_called_once()


class TestQ3SupportedExtensionsParity:
    """Q3 regression: --show-supported-extensions must only list extensions
    whose language has a real tree-sitter parser registered.

    The orphan ``scala_plugin.py`` / ``bash_plugin.py`` modules promised
    support that the analyzer cannot deliver, because there is no underlying
    ``tree-sitter-scala`` / ``tree-sitter-bash`` dependency wired up. The
    canonical source of truth is :attr:`LanguageDetector.SUPPORTED_LANGUAGES`
    (the same set that backs ``--show-supported-languages``). Every extension
    advertised by ``get_supported_extensions()`` must map to a language in
    that set; otherwise the documentation is lying.
    """

    @pytest.fixture
    def detector_instance(self):
        from tree_sitter_analyzer.language_detector import LanguageDetector

        return LanguageDetector()

    def test_every_supported_extension_maps_to_supported_language(
        self, detector_instance
    ):
        """Every extension reported as supported must resolve to a language
        in ``SUPPORTED_LANGUAGES`` — otherwise we're advertising a parser we
        don't have."""
        supported_extensions = detector_instance.get_supported_extensions()
        supported_languages = set(detector_instance.get_supported_languages())

        offenders: list[tuple[str, str]] = []
        for ext in supported_extensions:
            lang = detector_instance.EXTENSION_MAPPING.get(ext)
            assert lang is not None, (
                f"Extension {ext!r} reported as supported but has no mapping"
            )
            if lang not in supported_languages:
                offenders.append((ext, lang))

        assert not offenders, (
            "Extensions advertised as supported but mapped to unregistered "
            f"languages: {offenders}"
        )

    @pytest.mark.parametrize(
        "extension",
        [
            ".scala",
            ".sh",
            ".bash",
            ".lua",
            ".hs",
            ".dart",
            ".elm",
            ".fs",
            ".m",
            ".ml",
            ".pl",
            ".r",
            ".vb",
            ".clj",
            ".jsp",
            ".jspx",
        ],
    )
    def test_orphan_extensions_not_advertised(self, detector_instance, extension):
        """Orphan-plugin / no-parser extensions must NOT appear in the
        ``--show-supported-extensions`` output. ``scala_plugin.py`` and
        ``bash_plugin.py`` ship in the source tree as work-in-progress, but
        until the underlying tree-sitter dependency is wired in we must not
        advertise their extensions to users."""
        extensions = detector_instance.get_supported_extensions()
        assert extension not in extensions, (
            f"Extension {extension!r} is still advertised as supported but "
            "its language has no registered tree-sitter parser. See Q3."
        )

    def test_core_extensions_still_advertised(self, detector_instance):
        """Make sure the trim didn't accidentally hide real, working
        extensions. These are languages we *do* support."""
        extensions = detector_instance.get_supported_extensions()
        expected_present = {
            ".py",
            ".java",
            ".js",
            ".ts",
            ".tsx",
            ".c",
            ".cpp",
            ".rs",
            ".go",
            ".rb",
            ".php",
            ".kt",
            ".swift",
            ".cs",
            ".html",
            ".css",
            ".json",
            ".sql",
            ".yaml",
            ".md",
        }
        missing = expected_present - set(extensions)
        assert not missing, (
            f"Core working extensions disappeared from supported list: {missing}"
        )

    def test_all_known_extensions_still_includes_orphans(self, detector_instance):
        """The raw mapping (``get_all_known_extensions``) must still expose
        orphan extensions for diagnostics — only the user-facing
        ``get_supported_extensions`` should hide them."""
        all_known = detector_instance.get_all_known_extensions()
        # Orphan extensions still appear in the raw mapping (the WIP plugins
        # are intentionally kept around for future work).
        assert ".scala" in all_known
        assert ".lua" in all_known

    def test_show_extensions_cli_does_not_advertise_scala(self):
        """End-to-end check: ``--show-supported-extensions`` output must not
        mention ``.scala``."""
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--show-supported-extensions",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Combined stdout+stderr because output_list/output_info may route
        # to different streams depending on env.
        combined = result.stdout + result.stderr
        assert ".scala" not in combined, (
            f"--show-supported-extensions still mentions .scala:\n{combined}"
        )

    def test_show_languages_cli_does_not_advertise_scala(self):
        """End-to-end check: ``--show-supported-languages`` output must not
        list ``scala`` as a top-level language."""
        import re
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--show-supported-languages",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = result.stdout + result.stderr
        # Match scala as a language label (start-of-line indented entry),
        # ignoring incidental occurrences in extensions or descriptions.
        assert not re.search(r"^\s+scala\s", combined, re.MULTILINE), (
            f"--show-supported-languages still mentions scala:\n{combined}"
        )
