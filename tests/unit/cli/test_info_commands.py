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
