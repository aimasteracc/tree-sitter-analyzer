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
            # ".sh"/".bash" and ".scala" graduated 2026-06-10: the
            # tree-sitter grammars are now declared dependencies and the
            # extensions are wired end-to-end (see
            # test_bash_language_wiring.py / test_scala_language_wiring.py
            # + test_core_extensions_still_advertised).
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
        ``--show-supported-extensions`` output. These languages have no
        registered tree-sitter parser, so advertising their extensions
        would promise support the analyzer cannot deliver."""
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
            ".sh",
            ".bash",
            ".zsh",
            ".scala",
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

    def test_show_extensions_cli_advertises_scala(self):
        """End-to-end check: ``--show-supported-extensions`` must mention
        ``.scala``. Inverted 2026-06-10 when scala graduated (tree-sitter-scala
        wired in); the pre-graduation version asserted the opposite."""
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
        assert ".scala" in combined, (
            f"--show-supported-extensions no longer mentions .scala:\n{combined}"
        )

    def test_show_languages_cli_advertises_scala(self):
        """End-to-end check: ``--show-supported-languages`` must list
        ``scala``. Inverted 2026-06-10 when scala graduated."""
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
        assert "scala" in combined, (
            f"--show-supported-languages no longer mentions scala:\n{combined}"
        )


class TestR37adListQueriesJsonEnvelope:
    """r37ad (dogfood): ``--list-queries`` previously ignored
    ``--format json`` and always printed text via ``output_list``.
    Agents that piped output through ``json.loads`` failed with
    ``Expecting value``. This test pins the JSON envelope contract.
    """

    def test_list_queries_json_for_specific_language(self):
        from argparse import Namespace

        args = Namespace(
            language="python",
            file_path=None,
            output_format="json",
            format="json",
        )
        cmd = ListQueriesCommand(args)
        captured: dict = {}
        with patch(
            "tree_sitter_analyzer.cli.info_commands.output_json",
            side_effect=lambda d: captured.update(d) if isinstance(d, dict) else None,
        ):
            rc = cmd.execute()
        assert rc == 0
        assert captured.get("success") is True
        assert captured.get("verdict") == "INFO"
        assert captured.get("language") == "python"
        assert captured.get("scope") == "single_language"
        assert isinstance(captured.get("queries"), list)
        assert isinstance(captured.get("query_count"), int)
        assert captured["query_count"] > 0
        agent_summary = captured.get("agent_summary")
        assert isinstance(agent_summary, dict)
        assert agent_summary["verdict"] == "INFO"
        assert "python" in captured["summary_line"]

    def test_list_queries_json_for_all_languages(self):
        from argparse import Namespace

        args = Namespace(
            language=None,
            file_path=None,
            output_format="json",
            format="json",
        )
        cmd = ListQueriesCommand(args)
        captured: dict = {}
        with patch(
            "tree_sitter_analyzer.cli.info_commands.output_json",
            side_effect=lambda d: captured.update(d) if isinstance(d, dict) else None,
        ):
            rc = cmd.execute()
        assert rc == 0
        assert captured.get("success") is True
        assert captured.get("verdict") == "INFO"
        assert captured.get("scope") == "all_languages"
        assert captured.get("language") is None
        assert isinstance(captured.get("languages"), list)
        assert captured["language_count"] > 0
        assert captured["query_count"] > 0
        assert captured["agent_summary"]["verdict"] == "INFO"

    def test_list_queries_text_path_preserved(self):
        """Text path (default) must still work — regression for backward compat."""
        from argparse import Namespace

        args = Namespace(
            language="python",
            file_path=None,
            output_format="text",
            format=None,
        )
        cmd = ListQueriesCommand(args)
        with (
            patch("tree_sitter_analyzer.cli.info_commands.output_list") as mock_list,
            patch("tree_sitter_analyzer.cli.info_commands.output_json") as mock_json,
        ):
            rc = cmd.execute()
        assert rc == 0
        assert mock_json.call_count == 0, "text mode must not call output_json"
        assert mock_list.call_count > 0


class TestR37aeRemainingInfoCommandsJsonEnvelope:
    """r37ae (dogfood): batch follow-up to r37ad — extend JSON envelope
    support to the other 3 info commands: ``--describe-query``,
    ``--show-supported-languages``, ``--show-supported-extensions``.
    Same drift pattern: all ignored ``--format json``.
    """

    def test_describe_query_json_envelope(self):
        from argparse import Namespace

        from tree_sitter_analyzer.cli.info_commands import DescribeQueryCommand

        args = Namespace(
            language="python",
            describe_query="classes",
            file_path=None,
            output_format="json",
            format="json",
        )
        cmd = DescribeQueryCommand(args)
        captured: dict = {}
        with patch(
            "tree_sitter_analyzer.cli.info_commands.output_json",
            side_effect=lambda d: captured.update(d) if isinstance(d, dict) else None,
        ):
            rc = cmd.execute()
        assert rc == 0
        assert captured.get("success") is True
        assert captured.get("verdict") == "INFO"
        assert captured.get("language") == "python"
        assert captured.get("query_key") == "classes"
        assert isinstance(captured.get("description"), str)
        assert isinstance(captured.get("query_content"), str)
        assert captured["agent_summary"]["verdict"] == "INFO"

    def test_describe_query_not_found_json_envelope(self):
        from argparse import Namespace

        from tree_sitter_analyzer.cli.info_commands import DescribeQueryCommand

        args = Namespace(
            language="python",
            describe_query="this_query_does_not_exist_xyz",
            file_path=None,
            output_format="json",
            format="json",
        )
        cmd = DescribeQueryCommand(args)
        captured: dict = {}
        with patch(
            "tree_sitter_analyzer.cli.info_commands.output_json",
            side_effect=lambda d: captured.update(d) if isinstance(d, dict) else None,
        ):
            rc = cmd.execute()
        assert rc == 1
        assert captured.get("success") is False
        assert captured.get("verdict") == "NOT_FOUND"
        assert captured.get("error_type") == "not_found"
        assert "this_query_does_not_exist_xyz" in captured.get("error", "")

    def test_show_supported_languages_json_envelope(self):
        from argparse import Namespace

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
        assert captured.get("success") is True
        assert captured.get("verdict") == "INFO"
        assert isinstance(captured.get("languages"), list)
        assert captured.get("language_count", 0) > 0
        # Each language entry must have the documented shape.
        sample = captured["languages"][0]
        assert "language" in sample
        assert "extensions" in sample
        assert isinstance(sample["extensions"], list)

    def test_show_supported_extensions_json_envelope(self):
        from argparse import Namespace

        from tree_sitter_analyzer.cli.info_commands import ShowExtensionsCommand

        args = Namespace(output_format="json", format="json")
        cmd = ShowExtensionsCommand(args)
        captured: dict = {}
        with patch(
            "tree_sitter_analyzer.cli.info_commands.output_json",
            side_effect=lambda d: captured.update(d) if isinstance(d, dict) else None,
        ):
            rc = cmd.execute()
        assert rc == 0
        assert captured.get("success") is True
        assert captured.get("verdict") == "INFO"
        assert isinstance(captured.get("extensions"), list)
        assert captured.get("extension_count", 0) > 0

    def test_show_languages_text_path_preserved(self):
        """Text default must still go through output_list (backward compat)."""
        from argparse import Namespace

        from tree_sitter_analyzer.cli.info_commands import ShowLanguagesCommand

        args = Namespace(output_format="text", format=None)
        cmd = ShowLanguagesCommand(args)
        with (
            patch("tree_sitter_analyzer.cli.info_commands.output_list") as mock_list,
            patch("tree_sitter_analyzer.cli.info_commands.output_json") as mock_json,
        ):
            rc = cmd.execute()
        assert rc == 0
        assert mock_json.call_count == 0
        assert mock_list.call_count > 0
