#!/usr/bin/env python3
"""Coverage-boosting tests for BaseCommand in cli/commands/base_command.py"""

from argparse import Namespace
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.cli.commands.base_command import BaseCommand


class _ConcreteCommand(BaseCommand):
    """Minimal concrete subclass for testing BaseCommand"""

    async def execute_async(self, language: str) -> int:
        return 0


@pytest.fixture
def args():
    return Namespace(file_path="test.py", project_root="/tmp")


@pytest.fixture
def cmd(args):
    return _ConcreteCommand(args)


class TestBaseCommandInit:
    """Tests for BaseCommand.__init__"""

    def test_init_sets_project_root(self, args):
        """__init__ should detect and set project_root (lines 46-47)"""
        with patch(
            "tree_sitter_analyzer.cli.commands.base_command.detect_project_root",
            return_value="/detected/root",
        ):
            cmd = _ConcreteCommand(args)
            assert cmd.project_root == "/detected/root"


class TestValidateFile:
    """Tests for BaseCommand.validate_file"""

    def test_no_file_path_returns_false(self):
        """Returns False when args has no file_path (lines 60-61)"""
        args = Namespace()
        cmd = _ConcreteCommand(args)
        result = cmd.validate_file()
        assert result is False

    def test_none_file_path_returns_false(self):
        """Returns False when file_path is None"""
        args = Namespace(file_path=None)
        cmd = _ConcreteCommand(args)
        result = cmd.validate_file()
        assert result is False


class TestDetectLanguage:
    """Tests for BaseCommand.detect_language"""

    def test_unknown_language_returns_none(self, cmd):
        """Returns None when language detection fails (lines 109-110)"""
        cmd.args.language = None
        cmd.args.table = False
        cmd.args.quiet = False

        with patch(
            "tree_sitter_analyzer.cli.commands.base_command.detect_language_from_file",
            return_value="unknown",
        ):
            result = cmd.detect_language()
            assert result is None

    def test_unsupported_language_java_fallback(self, cmd):
        """Non-java unsupported language falls back to java (lines 117-122)"""
        cmd.args.language = "cobol"
        cmd.args.table = False
        cmd.args.quiet = False

        result = cmd.detect_language()
        # COBOL is not a supported language, should fallback to java
        assert result == "java"


class TestExecute:
    """Tests for BaseCommand.execute"""

    def test_execute_async_exception_returns_1(self, cmd):
        """Exception in execute_async returns exit code 1 (lines 166-168)"""
        cmd.validate_file = Mock(return_value=True)
        cmd.detect_language = Mock(return_value="python")

        with patch.object(
            cmd, "execute_async", side_effect=RuntimeError("async failure")
        ):
            result = cmd.execute()
            assert result == 1
