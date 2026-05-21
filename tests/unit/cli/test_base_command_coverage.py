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

    def test_unsupported_language_returns_none_and_emits_envelope(self, cmd, capsys):
        """Q2 (round-33): non-java unsupported language no longer silently
        falls back to Java. ``detect_language`` returns ``None`` and emits
        a canonical error envelope on stdout (when ``output_format=json``)
        so callers can ``json.load`` the result.
        """
        cmd.args.language = "cobol"
        cmd.args.table = False
        cmd.args.quiet = False
        cmd.args.output_format = "json"

        result = cmd.detect_language()
        # No more silent Java fallback.
        assert result is None

        captured = capsys.readouterr()
        # The envelope is the only thing on stdout — must parse as JSON.
        import json as _json

        envelope = _json.loads(captured.out.strip())
        assert envelope["success"] is False
        assert envelope["error_type"] == "validation"
        assert envelope["agent_summary"]["verdict"] == "ERROR"
        assert "cobol" in envelope["error"].lower()
        assert "cobol" in envelope["summary_line"].lower()


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
