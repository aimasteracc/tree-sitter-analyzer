#!/usr/bin/env python3
"""
Unit tests for cli/commands/base_command.py

Covers: BaseCommand.__init__, validate_file, detect_language, analyze_file,
execute, and execute_async dispatch.
"""

import asyncio
from argparse import Namespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.base_command import BaseCommand


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing ABC
# ---------------------------------------------------------------------------


class _TestCommand(BaseCommand):
    """Concrete subclass for testing the abstract BaseCommand."""

    def __init__(self, args: Namespace, return_code: int = 0):
        self._return_code = return_code
        super().__init__(args)

    async def execute_async(self, language: str) -> int:
        return self._return_code


def _make_args(**kwargs):
    """Create a Namespace with sensible defaults."""
    defaults = {
        "file_path": None,
        "project_root": None,
        "language": None,
        "table": False,
        "quiet": False,
        "partial_read": False,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


@pytest.fixture
def mock_security_validator():
    with patch("tree_sitter_analyzer.cli.commands.base_command.SecurityValidator") as cls:
        instance = MagicMock()
        instance.validate_file_path.return_value = (True, None)
        instance.sanitize_input.side_effect = lambda x, **kw: x
        cls.return_value = instance
        yield instance


@pytest.fixture
def mock_engine():
    with patch("tree_sitter_analyzer.cli.commands.base_command.get_analysis_engine") as factory:
        engine = MagicMock()
        factory.return_value = engine
        yield engine


@pytest.fixture
def mock_detect_project_root():
    with patch(
        "tree_sitter_analyzer.cli.commands.base_command.detect_project_root",
        return_value=None,
    ) as m:
        yield m


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestBaseCommandInit:
    def test_init_sets_args(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args(file_path="/some/file.py")
        cmd = _TestCommand(args)
        assert cmd.args is args

    def test_init_creates_analysis_engine(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args()
        cmd = _TestCommand(args)
        assert cmd.analysis_engine is mock_engine

    def test_init_creates_security_validator(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args()
        cmd = _TestCommand(args)
        assert cmd.security_validator is mock_security_validator


# ---------------------------------------------------------------------------
# validate_file tests
# ---------------------------------------------------------------------------


class TestValidateFile:
    def test_returns_false_when_no_file_path(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args(file_path=None)
        cmd = _TestCommand(args)
        with patch("tree_sitter_analyzer.cli.commands.base_command.output_error"):
            assert cmd.validate_file() is False

    def test_returns_false_when_security_validation_fails(self, mock_engine, mock_security_validator, mock_detect_project_root):
        mock_security_validator.validate_file_path.return_value = (False, "path traversal")
        args = _make_args(file_path="/etc/passwd")
        cmd = _TestCommand(args)
        with patch("tree_sitter_analyzer.cli.commands.base_command.output_error"):
            assert cmd.validate_file() is False

    def test_returns_false_when_file_does_not_exist(self, mock_engine, mock_security_validator, mock_detect_project_root, tmp_path):
        args = _make_args(file_path=str(tmp_path / "nonexistent.py"))
        cmd = _TestCommand(args)
        with patch("tree_sitter_analyzer.cli.commands.base_command.output_error"):
            assert cmd.validate_file() is False

    def test_returns_true_for_valid_existing_file(self, mock_engine, mock_security_validator, mock_detect_project_root, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        args = _make_args(file_path=str(f))
        cmd = _TestCommand(args)
        assert cmd.validate_file() is True


# ---------------------------------------------------------------------------
# detect_language tests
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    def test_uses_explicit_language_from_args(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args(language="python", file_path="/f.py", table=True)
        cmd = _TestCommand(args)
        with patch("tree_sitter_analyzer.cli.commands.base_command.is_language_supported", return_value=True):
            lang = cmd.detect_language()
        assert lang == "python"

    def test_explicit_language_outputs_info_in_verbose_mode(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args(language="java", file_path="/f.java", table=False, quiet=False)
        cmd = _TestCommand(args)
        with (
            patch("tree_sitter_analyzer.cli.commands.base_command.is_language_supported", return_value=True),
            patch("tree_sitter_analyzer.cli.commands.base_command.output_info") as mock_info,
        ):
            lang = cmd.detect_language()
        assert lang == "java"
        mock_info.assert_called_once()

    def test_auto_detect_from_file(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args(file_path="/code.rs")
        cmd = _TestCommand(args)
        with (
            patch("tree_sitter_analyzer.cli.commands.base_command.detect_language_from_file", return_value="rust"),
            patch("tree_sitter_analyzer.cli.commands.base_command.is_language_supported", return_value=True),
        ):
            lang = cmd.detect_language()
        assert lang == "rust"

    def test_unknown_language_returns_none(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args(file_path="/unknown.xyz")
        cmd = _TestCommand(args)
        with (
            patch("tree_sitter_analyzer.cli.commands.base_command.detect_language_from_file", return_value="unknown"),
            patch("tree_sitter_analyzer.cli.commands.base_command.output_error"),
        ):
            lang = cmd.detect_language()
        assert lang is None

    def test_unsupported_language_falls_back_to_java(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args(language="cobol", file_path="/f.cob", table=True)
        cmd = _TestCommand(args)
        with patch("tree_sitter_analyzer.cli.commands.base_command.is_language_supported", return_value=False):
            lang = cmd.detect_language()
        assert lang == "java"


# ---------------------------------------------------------------------------
# analyze_file tests
# ---------------------------------------------------------------------------


class TestAnalyzeFile:
    @pytest.mark.asyncio
    async def test_success_returns_analysis_result(self, mock_engine, mock_security_validator, mock_detect_project_root):
        mock_result = MagicMock()
        mock_result.success = True
        mock_engine.analyze = AsyncMock(return_value=mock_result)

        args = _make_args(file_path="/f.py")
        cmd = _TestCommand(args)
        result = await cmd.analyze_file("python")
        assert result is mock_result

    @pytest.mark.asyncio
    async def test_failed_analysis_returns_none(self, mock_engine, mock_security_validator, mock_detect_project_root):
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "parse error"
        mock_engine.analyze = AsyncMock(return_value=mock_result)

        args = _make_args(file_path="/f.py")
        cmd = _TestCommand(args)
        with patch("tree_sitter_analyzer.cli.commands.base_command.output_error"):
            result = await cmd.analyze_file("python")
        assert result is None

    @pytest.mark.asyncio
    async def test_none_result_returns_none(self, mock_engine, mock_security_validator, mock_detect_project_root):
        mock_engine.analyze = AsyncMock(return_value=None)

        args = _make_args(file_path="/f.py")
        cmd = _TestCommand(args)
        with patch("tree_sitter_analyzer.cli.commands.base_command.output_error"):
            result = await cmd.analyze_file("python")
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self, mock_engine, mock_security_validator, mock_detect_project_root):
        mock_engine.analyze = AsyncMock(side_effect=RuntimeError("engine failure"))

        args = _make_args(file_path="/f.py")
        cmd = _TestCommand(args)
        with patch("tree_sitter_analyzer.cli.commands.base_command.output_error"):
            result = await cmd.analyze_file("python")
        assert result is None

    @pytest.mark.asyncio
    async def test_partial_read_failure_returns_none(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args(file_path="/f.py", partial_read=True, start_line=1)

        cmd = _TestCommand(args)
        with (
            patch("tree_sitter_analyzer.cli.commands.base_command.read_file_partial", return_value=None),
            patch("tree_sitter_analyzer.cli.commands.base_command.output_error"),
        ):
            result = await cmd.analyze_file("python")
        assert result is None

    @pytest.mark.asyncio
    async def test_partial_read_exception_returns_none(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args(file_path="/f.py", partial_read=True, start_line=1)
        cmd = _TestCommand(args)
        with (
            patch("tree_sitter_analyzer.cli.commands.base_command.read_file_partial", side_effect=IOError("disk error")),
            patch("tree_sitter_analyzer.cli.commands.base_command.output_error"),
        ):
            result = await cmd.analyze_file("python")
        assert result is None


# ---------------------------------------------------------------------------
# execute tests
# ---------------------------------------------------------------------------


class TestExecute:
    def test_returns_1_when_file_invalid(self, mock_engine, mock_security_validator, mock_detect_project_root):
        args = _make_args(file_path=None)
        cmd = _TestCommand(args)
        with patch("tree_sitter_analyzer.cli.commands.base_command.output_error"):
            assert cmd.execute() == 1

    def test_returns_1_when_language_detection_fails(self, mock_engine, mock_security_validator, mock_detect_project_root, tmp_path):
        f = tmp_path / "test.xyz"
        f.write_text("data")
        args = _make_args(file_path=str(f))
        cmd = _TestCommand(args)
        with (
            patch("tree_sitter_analyzer.cli.commands.base_command.detect_language_from_file", return_value="unknown"),
            patch("tree_sitter_analyzer.cli.commands.base_command.output_error"),
        ):
            assert cmd.execute() == 1

    def test_returns_execute_async_return_code(self, mock_engine, mock_security_validator, mock_detect_project_root, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        args = _make_args(file_path=str(f), language="python", table=True)
        cmd = _TestCommand(args, return_code=0)
        with patch("tree_sitter_analyzer.cli.commands.base_command.is_language_supported", return_value=True):
            assert cmd.execute() == 0

    def test_returns_1_when_execute_async_raises(self, mock_engine, mock_security_validator, mock_detect_project_root, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        args = _make_args(file_path=str(f), language="python", table=True)

        class _ErrorCommand(_TestCommand):
            async def execute_async(self, language):
                raise RuntimeError("async crash")

        cmd = _ErrorCommand(args)
        with (
            patch("tree_sitter_analyzer.cli.commands.base_command.is_language_supported", return_value=True),
            patch("tree_sitter_analyzer.cli.commands.base_command.output_error"),
        ):
            assert cmd.execute() == 1
