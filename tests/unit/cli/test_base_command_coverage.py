#!/usr/bin/env python3
"""Coverage-boosting tests for BaseCommand in cli/commands/base_command.py"""

import asyncio
from argparse import Namespace
from unittest.mock import AsyncMock, Mock, patch

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


class TestErrorEnvelope:
    """Tests for JSON/text error envelopes and error classification."""

    def test_classify_error_type(self):
        """Different exception classes map to stable error_type values."""
        assert _ConcreteCommand._classify_error_type(ValueError("x")) == "validation"
        assert _ConcreteCommand._classify_error_type(TypeError("x")) == "validation"
        assert _ConcreteCommand._classify_error_type(KeyError("x")) == "validation"
        assert _ConcreteCommand._classify_error_type(RuntimeError("x")) == "runtime"

    def test_emit_error_envelope_json(self, cmd):
        """JSON envelope is emitted when explicitly requested."""
        cmd.args.output_format = "json"
        cmd.args.output_format_explicit = True
        cmd._json_error_envelope_enabled = True
        cmd.args.output_format_explicit = True

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_json"
            ) as mock_json,
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_error"
            ) as mock_error,
        ):
            cmd._emit_error_envelope(
                flag_name="analysis",
                message="boom",
                error_type="runtime",
                echo_fields={"file_path": "x"},
            )

        mock_error.assert_not_called()
        payload = mock_json.call_args.args[0]
        assert payload["success"] is False
        assert payload["error_type"] == "runtime"
        assert payload["error"] == "boom"
        assert payload["file_path"] == "x"
        assert payload["agent_summary"]["verdict"] == "ERROR"

    def test_emit_error_envelope_falls_back_to_text_for_toon(self, cmd):
        """Non-json output formats fall back to text error printing."""
        cmd.args.output_format = "toon"
        cmd.args.output_format_explicit = True
        cmd._json_error_envelope_enabled = True

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_error"
            ) as mock_error,
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_json"
            ) as mock_json,
        ):
            cmd._emit_error_envelope(
                flag_name="analysis",
                message="failed",
                error_type="runtime",
            )

        mock_json.assert_not_called()
        mock_error.assert_called_once_with("failed")

    def test_emit_error_envelope_falls_back_for_non_json_with_explicit_envelope_mode(
        self, cmd
    ) -> None:
        cmd.args.output_format = "toon"
        cmd._json_error_envelope_enabled = True
        cmd.args.output_format_explicit = True
        cmd._should_emit_json_error_envelope = lambda: True
        with (
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_error"
            ) as mock_error,
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_json"
            ) as mock_json,
        ):
            cmd._emit_error_envelope(
                flag_name="analysis",
                message="still text",
                error_type="runtime",
            )

        mock_json.assert_not_called()
        mock_error.assert_called_once_with("still text")

    def test_emit_error_envelope_skips_envelope_when_not_explicit(self, cmd):
        """Implicit format arguments use legacy stderr envelope behavior."""
        cmd.args.output_format = "json"
        cmd.args.output_format_explicit = False
        cmd._json_error_envelope_enabled = True

        with patch(
            "tree_sitter_analyzer.cli.commands.base_command.output_error"
        ) as mock_error:
            with patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_json"
            ) as mock_json:
                cmd._emit_error_envelope(
                    flag_name="analysis",
                    message="silent",
                    error_type="runtime",
                )

        mock_error.assert_called_once_with("silent")
        mock_json.assert_not_called()


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

    def test_invalid_path_reports_info_when_non_json(self, cmd):
        """Security validation failure reports legacy info message when JSON envelope is disabled."""
        cmd.args.output_format = "text"
        cmd.args.output_format_explicit = False
        cmd.security_validator.validate_file_path = Mock(
            return_value=(False, "blocked")
        )
        with (
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_info"
            ) as mock_info,
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_error"
            ) as mock_error,
        ):
            result = cmd.validate_file()

        assert result is False
        mock_info.assert_called_once_with(
            "Use --project-root to set the project root directory."
        )
        mock_error.assert_called_once_with("Invalid file path: blocked")

    def test_invalid_path_uses_json_envelope_when_explicit(self, cmd):
        """Invalid path with explicit JSON output stays in envelope mode."""
        cmd.args.output_format = "json"
        cmd.args.output_format_explicit = True
        cmd._json_error_envelope_enabled = True
        cmd.security_validator.validate_file_path = Mock(
            return_value=(False, "blocked")
        )
        with (
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_json"
            ) as mock_json,
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_info"
            ) as mock_info,
        ):
            result = cmd.validate_file()

        assert result is False
        payload = mock_json.call_args.args[0]
        assert payload["success"] is False
        assert payload["error"] == "Invalid file path: blocked"
        assert payload["error_type"] == "validation"
        mock_info.assert_not_called()

    def test_missing_file_reports_info_when_non_json(self, tmp_path, cmd):
        """Missing file path also emits legacy text hints when JSON envelope is disabled."""
        cmd.args.file_path = str(tmp_path / "missing.py")
        cmd.args.output_format = "text"
        cmd.args.output_format_explicit = False
        cmd.security_validator.validate_file_path = Mock(return_value=(True, ""))
        cmd._json_error_envelope_enabled = False
        with (
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_info"
            ) as mock_info,
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_error"
            ) as mock_error,
        ):
            result = cmd.validate_file()

        assert result is False
        mock_info.assert_called_once_with("Check the file path and try again.")
        mock_error.assert_called_once_with(f"File not found: {cmd.args.file_path}")

    def test_missing_file_uses_json_envelope_when_explicit(self, tmp_path, cmd):
        """Explicit json format uses the envelope and skips legacy hints."""
        cmd.args.file_path = str(tmp_path / "missing.json")
        cmd.args.output_format = "json"
        cmd.args.output_format_explicit = True
        cmd._json_error_envelope_enabled = True
        cmd.security_validator.validate_file_path = Mock(return_value=(True, ""))
        with (
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_json"
            ) as mock_json,
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_info"
            ) as mock_info,
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_error"
            ) as mock_error,
        ):
            result = cmd.validate_file()

        assert result is False
        payload = mock_json.call_args.args[0]
        assert payload["success"] is False
        assert payload["error_type"] == "validation"
        assert payload["file_path"] == cmd.args.file_path
        mock_info.assert_not_called()
        mock_error.assert_not_called()


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


class TestPartialRead:
    """Tests for _try_partial_read_precheck."""

    def test_partial_read_precheck_returns_false_when_exception(self, cmd, tmp_path):
        """I/O errors in partial-read path convert to validation envelopes."""
        target = tmp_path / "sample.py"
        target.write_text("x", encoding="utf-8")
        cmd.args = Namespace(
            file_path=str(target),
            partial_read=True,
            start_line=1,
            end_line=1,
            output_format="text",
            output_format_explicit=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.read_file_partial",
                side_effect=ValueError("bad fragment"),
            ),
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_error"
            ) as mock_error,
        ):
            result = cmd._try_partial_read_precheck()

        assert result is False
        mock_error.assert_called_once()

    def test_partial_read_precheck_returns_false_when_content_missing(
        self, cmd, tmp_path
    ):
        """`read_file_partial` returning None fails precheck."""
        target = tmp_path / "sample.py"
        target.write_text("x", encoding="utf-8")
        cmd.args = Namespace(
            file_path=str(target),
            partial_read=True,
            start_line=1,
            end_line=1,
            output_format="text",
            output_format_explicit=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.read_file_partial",
                return_value=None,
            ),
            patch(
                "tree_sitter_analyzer.cli.commands.base_command.output_error"
            ) as mock_error,
        ):
            result = cmd._try_partial_read_precheck()

        assert result is False
        mock_error.assert_called_once()


class TestAnalyzeFile:
    """Tests for BaseCommand.analyze_file precheck, failure and exception paths."""

    def test_analyze_file_precheck_failure_returns_none(self, cmd, tmp_path):
        """Precheck failure should stop before analysis engine call."""
        target = tmp_path / "sample.py"
        target.write_text("x", encoding="utf-8")
        cmd.args = Namespace(
            file_path=str(target),
            partial_read=True,
            start_line=1,
            end_line=1,
            output_format="json",
            output_format_explicit=True,
        )
        cmd._json_error_envelope_enabled = True

        with patch.object(
            cmd,
            "_try_partial_read_precheck",
            return_value=False,
        ):
            result = asyncio.run(cmd.analyze_file("python"))

        assert result is None

    def test_analyze_file_analysis_fails(self, cmd, tmp_path):
        """Engine-level analysis failure gets surfaced as a structured error."""
        target = tmp_path / "sample.py"
        target.write_text("x", encoding="utf-8")
        cmd.args = Namespace(
            file_path=str(target),
            partial_read=False,
            output_format="json",
            output_format_explicit=True,
        )
        cmd._json_error_envelope_enabled = True
        cmd.analysis_engine.analyze = AsyncMock(
            return_value=Mock(success=False, error_message="parse failed")
        )

        with patch(
            "tree_sitter_analyzer.cli.commands.base_command.output_json"
        ) as mock_output_json:
            result = asyncio.run(cmd.analyze_file("python"))

        assert result is None
        payload = mock_output_json.call_args.args[0]
        assert payload["error"] == "Analysis failed: parse failed"

    def test_analyze_file_exception_becomes_validation_error(self, cmd, tmp_path):
        """Engine exceptions map to validation/runtime envelopes."""
        target = tmp_path / "sample.py"
        target.write_text("x", encoding="utf-8")
        cmd.args = Namespace(
            file_path=str(target),
            partial_read=False,
            output_format="json",
            output_format_explicit=True,
        )
        cmd._json_error_envelope_enabled = True
        cmd.analysis_engine.analyze = Mock(side_effect=ValueError("bad input"))

        with patch(
            "tree_sitter_analyzer.cli.commands.base_command.output_json"
        ) as mock_output_json:
            result = asyncio.run(cmd.analyze_file("python"))

        assert result is None
        payload = mock_output_json.call_args.args[0]
        assert payload["error_type"] == "validation"
        assert payload["error"] == "An error occurred during analysis: bad input"


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
