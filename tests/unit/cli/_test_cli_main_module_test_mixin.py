#!/usr/bin/env python3
"""Private mixins for CLI main module tests."""

import argparse


class TestCLICommandFactoryTestMixin:
    """Tests for CLICommandFactory class."""

    __test__ = False

    def test_create_command_list_queries(self):
        """Test creating ListQueriesCommand."""
        args = argparse.Namespace(
            list_queries=True,
            file_path=None,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "ListQueriesCommand"

    def test_create_command_describe_query(self):
        """Test creating DescribeQueryCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query="class",
            file_path=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "DescribeQueryCommand"

    def test_create_command_show_languages(self):
        """Test creating ShowLanguagesCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=True,
            show_supported_extensions=False,
            filter_help=None,
            file_path=None,
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "ShowLanguagesCommand"

    def test_create_command_show_extensions(self):
        """Test creating ShowExtensionsCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=True,
            file_path=None,
            filter_help=None,
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "ShowExtensionsCommand"

    def test_create_command_filter_help(self):
        """Test creating filter help command."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=True,
            file_path=None,
        )
        command = self._create_command(args)
        # filter_help returns None (exits with code 0)
        assert command is None

    def test_create_command_table(self):
        """Test creating TableCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            table="full",
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "TableCommand"

    def test_create_command_structure(self):
        """Test creating StructureCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            structure=True,
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "StructureCommand"

    def test_create_command_summary(self):
        """Test creating SummaryCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            summary="classes,methods",
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "SummaryCommand"

    def test_create_command_advanced(self):
        """Test creating AdvancedCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            advanced=True,
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "AdvancedCommand"

    def test_create_command_query_key(self):
        """Test creating QueryCommand with query_key."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            query_key="class",
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "QueryCommand"

    def test_create_command_query_string(self):
        """Test creating QueryCommand with query_string."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            query_string="(function_declaration)",
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "QueryCommand"

    def test_create_command_default(self):
        """Test creating DefaultCommand when no specific command is given."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "DefaultCommand"

    def test_create_command_partial_read(self):
        """Test creating PartialReadCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            partial_read=True,
            start_line=1,
            end_line=10,
        )
        command = self._create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "PartialReadCommand"

    def test_create_command_no_file_path(self):
        """Test that command is None when file_path is not provided."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path=None,
        )
        command = self._create_command(args)
        assert command is None

    def _create_command(self, args):
        return self._cli_command_factory.create_command(args)
