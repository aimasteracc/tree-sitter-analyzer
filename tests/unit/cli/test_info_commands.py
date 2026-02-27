#!/usr/bin/env python3
"""
Tests for info_commands module.

Tests for ListQueriesCommand, DescribeQueryCommand,
ShowLanguagesCommand, and ShowExtensionsCommand.
"""

from argparse import Namespace
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.cli.info_commands import (
    DescribeQueryCommand,
    ListQueriesCommand,
    ShowExtensionsCommand,
    ShowLanguagesCommand,
)

MODULE = "tree_sitter_analyzer.cli.info_commands"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_output():
    """Patch all output functions used by info_commands."""
    with (
        patch(f"{MODULE}.output_list") as m_list,
        patch(f"{MODULE}.output_info") as m_info,
        patch(f"{MODULE}.output_error") as m_error,
        patch(f"{MODULE}.output_data") as m_data,
    ):
        yield {
            "output_list": m_list,
            "output_info": m_info,
            "output_error": m_error,
            "output_data": m_data,
        }


@pytest.fixture
def mock_query_loader():
    """Patch the query_loader singleton used by info_commands."""
    with patch(f"{MODULE}.query_loader") as m:
        yield m


@pytest.fixture
def mock_detector():
    """Patch the detector singleton used by info_commands."""
    with patch(f"{MODULE}.detector") as m:
        yield m


@pytest.fixture
def mock_detect_language():
    """Patch detect_language_from_file function."""
    with patch(f"{MODULE}.detect_language_from_file") as m:
        yield m


# ---------------------------------------------------------------------------
# ListQueriesCommand tests
# ---------------------------------------------------------------------------


class TestListQueriesCommand:
    """Tests for ListQueriesCommand.execute()."""

    def test_execute_with_language(self, mock_output, mock_query_loader):
        """When args.language is set, list queries for that language and return 0."""
        args = Namespace(language="python", file_path=None)
        mock_query_loader.list_queries_for_language.return_value = ["methods", "classes"]
        mock_query_loader.get_query_description.side_effect = lambda _lang, key: {
            "methods": "Extract method declarations",
            "classes": "Extract class declarations",
        }.get(key)

        cmd = ListQueriesCommand(args)
        result = cmd.execute()

        assert result == 0
        mock_query_loader.list_queries_for_language.assert_called_once_with("python")
        assert mock_output["output_list"].call_count >= 3  # header + 2 queries

    def test_execute_with_file_path(
        self, mock_output, mock_query_loader, mock_detect_language
    ):
        """When args.file_path is set (and language is not), detect language from file."""
        args = Namespace(language=None, file_path="example.py")
        mock_detect_language.return_value = "python"
        mock_query_loader.list_queries_for_language.return_value = ["methods"]
        mock_query_loader.get_query_description.return_value = "Extract methods"

        cmd = ListQueriesCommand(args)
        result = cmd.execute()

        assert result == 0
        mock_detect_language.assert_called_once_with("example.py")
        mock_query_loader.list_queries_for_language.assert_called_once_with("python")

    def test_execute_no_language_no_file_lists_all(self, mock_output, mock_query_loader):
        """When neither language nor file_path is provided, list all languages."""
        args = Namespace(language=None, file_path=None)
        mock_query_loader.list_supported_languages.return_value = ["python", "java"]
        mock_query_loader.list_queries_for_language.side_effect = lambda lang: {
            "python": ["methods"],
            "java": ["class"],
        }[lang]
        mock_query_loader.get_query_description.return_value = "A description"

        cmd = ListQueriesCommand(args)
        result = cmd.execute()

        assert result == 0
        mock_query_loader.list_supported_languages.assert_called_once()
        # Should list both languages
        assert mock_query_loader.list_queries_for_language.call_count == 2


# ---------------------------------------------------------------------------
# DescribeQueryCommand tests
# ---------------------------------------------------------------------------


class TestDescribeQueryCommand:
    """Tests for DescribeQueryCommand.execute()."""

    def test_execute_with_language(self, mock_output, mock_query_loader):
        """When args.language is set, describe the specified query and return 0."""
        args = Namespace(language="python", file_path=None, describe_query="methods")
        mock_query_loader.get_query_description.return_value = "Extract method declarations"
        mock_query_loader.get_query.return_value = "(method_declaration) @method"

        cmd = DescribeQueryCommand(args)
        result = cmd.execute()

        assert result == 0
        mock_query_loader.get_query_description.assert_called_once_with(
            "python", "methods"
        )
        mock_query_loader.get_query.assert_called_once_with("python", "methods")
        mock_output["output_info"].assert_called_once()
        mock_output["output_data"].assert_called_once()

    def test_execute_with_file_path(
        self, mock_output, mock_query_loader, mock_detect_language
    ):
        """When file_path is set (and language is not), detect language from file."""
        args = Namespace(language=None, file_path="app.java", describe_query="class")
        mock_detect_language.return_value = "java"
        mock_query_loader.get_query_description.return_value = "Extract class declarations"
        mock_query_loader.get_query.return_value = "(class_declaration) @class"

        cmd = DescribeQueryCommand(args)
        result = cmd.execute()

        assert result == 0
        mock_detect_language.assert_called_once_with("app.java")
        mock_output["output_info"].assert_called_once()
        mock_output["output_data"].assert_called_once()

    def test_execute_no_language_no_file_returns_error(self, mock_output):
        """When neither language nor file_path is provided, output error and return 1."""
        args = Namespace(language=None, file_path=None, describe_query="methods")

        cmd = DescribeQueryCommand(args)
        result = cmd.execute()

        assert result == 1
        mock_output["output_error"].assert_called_once()
        assert "requires" in mock_output["output_error"].call_args[0][0]

    def test_execute_nonexistent_query(self, mock_output, mock_query_loader):
        """When the query does not exist, output error and return 1."""
        args = Namespace(
            language="python", file_path=None, describe_query="nonexistent_query"
        )
        mock_query_loader.get_query_description.return_value = None
        mock_query_loader.get_query.return_value = None

        cmd = DescribeQueryCommand(args)
        result = cmd.execute()

        assert result == 1
        mock_output["output_error"].assert_called_once()
        assert "not found" in mock_output["output_error"].call_args[0][0]

    def test_execute_value_error_returns_1(self, mock_output, mock_query_loader):
        """When query_loader raises ValueError, output error and return 1."""
        args = Namespace(language="python", file_path=None, describe_query="bad_query")
        mock_query_loader.get_query_description.side_effect = ValueError(
            "Unsupported language"
        )

        cmd = DescribeQueryCommand(args)
        result = cmd.execute()

        assert result == 1
        mock_output["output_error"].assert_called_once_with("Unsupported language")


# ---------------------------------------------------------------------------
# ShowLanguagesCommand tests
# ---------------------------------------------------------------------------


class TestShowLanguagesCommand:
    """Tests for ShowLanguagesCommand.execute()."""

    def test_execute_shows_languages(self, mock_output, mock_detector):
        """Should list each supported language with its extensions and return 0."""
        mock_detector.get_supported_languages.return_value = ["python", "java"]
        mock_detector.get_language_info.side_effect = lambda lang: {
            "python": {"extensions": [".py", ".pyx", ".pyi"]},
            "java": {"extensions": [".java"]},
        }[lang]

        args = Namespace(language=None)
        cmd = ShowLanguagesCommand(args)
        result = cmd.execute()

        assert result == 0
        mock_detector.get_supported_languages.assert_called_once()
        assert mock_detector.get_language_info.call_count == 2
        # header + 2 language lines
        assert mock_output["output_list"].call_count == 3

    def test_execute_truncates_long_extension_list(self, mock_output, mock_detector):
        """When a language has more than 5 extensions, display is truncated."""
        many_exts = [".a", ".b", ".c", ".d", ".e", ".f", ".g"]
        mock_detector.get_supported_languages.return_value = ["multi"]
        mock_detector.get_language_info.return_value = {"extensions": many_exts}

        args = Namespace(language=None)
        cmd = ShowLanguagesCommand(args)
        result = cmd.execute()

        assert result == 0
        # The second call (index 1) should be the language line with truncation
        lang_line = mock_output["output_list"].call_args_list[1][0][0]
        assert "2 more" in lang_line


# ---------------------------------------------------------------------------
# ShowExtensionsCommand tests
# ---------------------------------------------------------------------------


class TestShowExtensionsCommand:
    """Tests for ShowExtensionsCommand.execute()."""

    def test_execute_shows_extensions(self, mock_output, mock_detector):
        """Should list extensions in chunks and report the total count."""
        extensions = [".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".rb"]
        mock_detector.get_supported_extensions.return_value = extensions

        args = Namespace(language=None)
        cmd = ShowExtensionsCommand(args)
        result = cmd.execute()

        assert result == 0
        mock_detector.get_supported_extensions.assert_called_once()
        # 1 header + ceil(9/8)=2 chunk lines via output_list, plus 1 output_info
        assert mock_output["output_list"].call_count == 3  # header + 2 chunks
        mock_output["output_info"].assert_called_once()
        assert "9" in mock_output["output_info"].call_args[0][0]
