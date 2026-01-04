#!/usr/bin/env python3
"""
Tests for PartialReadCommand
"""

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.partial_read_command import PartialReadCommand


@pytest.fixture
def mock_args():
    """Create mock args for PartialReadCommand."""
    return Namespace(
        file_path="test.py",
        file="test.py",
        start_line=1,
        end_line=10,
        start_column=None,
        end_column=None,
        output_format="text",
        toon_use_tabs=False,
    )


@pytest.fixture
def command(mock_args):
    """Create PartialReadCommand instance for testing."""
    return PartialReadCommand(mock_args)


class TestPartialReadCommandInit:
    """Tests for PartialReadCommand initialization."""

    def test_init(self, command):
        """Test PartialReadCommand initialization."""
        assert command is not None
        assert isinstance(command, PartialReadCommand)
        assert hasattr(command, "args")

    def test_init_with_args(self, mock_args):
        """Test PartialReadCommand initialization with args."""
        command = PartialReadCommand(mock_args)
        assert command.args == mock_args

    def test_init_no_super_call(self, mock_args):
        """Test PartialReadCommand doesn't call super().__init__()."""
        command = PartialReadCommand(mock_args)
        # Should not have analysis_engine attribute from BaseCommand
        assert not hasattr(command, "analysis_engine")


class TestPartialReadCommandValidateFile:
    """Tests for PartialReadCommand.validate_file method."""

    def test_validate_file_success(self, command):
        """Test validate_file with valid file."""
        with patch("pathlib.Path.exists", return_value=True):
            result = command.validate_file()
            assert result is True

    def test_validate_file_no_file_path(self, command):
        """Test validate_file without file_path attribute."""
        delattr(command.args, "file_path")
        with patch("tree_sitter_analyzer.output_manager.output_error"):
            result = command.validate_file()
            assert result is False

    def test_validate_file_empty_file_path(self, command):
        """Test validate_file with empty file_path."""
        command.args.file_path = ""
        with patch("tree_sitter_analyzer.output_manager.output_error"):
            result = command.validate_file()
            assert result is False

    def test_validate_file_not_exists(self, command):
        """Test validate_file with non-existent file."""
        with patch("pathlib.Path.exists", return_value=False):
            with patch("tree_sitter_analyzer.output_manager.output_error"):
                result = command.validate_file()
                assert result is False


class TestPartialReadCommandExecute:
    """Tests for PartialReadCommand.execute method."""

    def test_execute_success(self, command):
        """Test execute returns 0 on success."""
        with patch.object(command, "validate_file", return_value=True):
            with patch(
                "tree_sitter_analyzer.cli.commands.partial_read_command.read_file_partial",
                return_value="test content",
            ):
                with patch.object(command, "_output_partial_content"):
                    result = command.execute()
                    assert result == 0

    def test_execute_validate_file_fails(self, command):
        """Test execute returns 1 when validate_file fails."""
        with patch.object(command, "validate_file", return_value=False):
            result = command.execute()
            assert result == 1

    def test_execute_no_start_line(self, command):
        """Test execute returns 1 when start_line is missing."""
        command.args.start_line = None
        with patch.object(command, "validate_file", return_value=True):
            with patch("tree_sitter_analyzer.output_manager.output_error"):
                result = command.execute()
                assert result == 1

    def test_execute_start_line_less_than_1(self, command):
        """Test execute returns 1 when start_line < 1."""
        command.args.start_line = 0
        with patch.object(command, "validate_file", return_value=True):
            with patch("tree_sitter_analyzer.output_manager.output_error"):
                result = command.execute()
                assert result == 1

    def test_execute_end_line_less_than_start_line(self, command):
        """Test execute returns 1 when end_line < start_line."""
        command.args.start_line = 10
        command.args.end_line = 5
        with patch.object(command, "validate_file", return_value=True):
            with patch("tree_sitter_analyzer.output_manager.output_error"):
                result = command.execute()
                assert result == 1

    def test_execute_read_file_partial_fails(self, command):
        """Test execute returns 1 when read_file_partial fails."""
        with patch.object(command, "validate_file", return_value=True):
            with patch(
                "tree_sitter_analyzer.cli.commands.partial_read_command.read_file_partial",
                return_value=None,
            ):
                with patch("tree_sitter_analyzer.output_manager.output_error"):
                    result = command.execute()
                    assert result == 1

    def test_execute_exception(self, command):
        """Test execute handles exceptions."""
        with patch.object(command, "validate_file", return_value=True):
            with patch(
                "tree_sitter_analyzer.cli.commands.partial_read_command.read_file_partial",
                side_effect=Exception("Test error"),
            ):
                with patch("tree_sitter_analyzer.output_manager.output_error"):
                    result = command.execute()
                    assert result == 1


class TestPartialReadCommandOutputPartialContent:
    """Tests for PartialReadCommand._output_partial_content method."""

    def test_output_partial_content_text(self, command):
        """Test _output_partial_content with text format."""
        command.args.output_format = "text"
        content = "test content"
        with patch(
            "tree_sitter_analyzer.cli.commands.partial_read_command.output_section"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.partial_read_command.output_data"
            ):
                with patch("builtins.print") as mock_print:
                    command._output_partial_content(content)
                    mock_print.assert_called_once_with(content, end="")

    def test_output_partial_content_json(self, command):
        """Test _output_partial_content with JSON format."""
        command.args.output_format = "json"
        content = "test content"
        with patch(
            "tree_sitter_analyzer.cli.commands.partial_read_command.output_json"
        ) as mock_output_json:
            command._output_partial_content(content)
            mock_output_json.assert_called_once()
            # Check the result data structure
            call_args = mock_output_json.call_args[0][0]
            assert call_args["file_path"] == "test.py"
            assert call_args["range"]["start_line"] == 1
            assert call_args["range"]["end_line"] == 10
            assert call_args["content"] == content
            assert call_args["content_length"] == len(content)

    def test_output_partial_content_toon(self, command):
        """Test _output_partial_content with TOON format."""
        command.args.output_format = "toon"
        content = "test content"
        with patch(
            "tree_sitter_analyzer.cli.commands.partial_read_command.ToonFormatter"
        ) as mock_formatter_class:
            mock_formatter = MagicMock()
            mock_formatter.format.return_value = "toon_output"
            mock_formatter_class.return_value = mock_formatter
            with patch("builtins.print") as mock_print:
                command._output_partial_content(content)
                mock_print.assert_called_once_with("toon_output")

    def test_output_partial_content_with_start_column(self, command):
        """Test _output_partial_content with start_column."""
        command.args.start_column = 5
        command.args.output_format = "json"
        content = "test content"
        with patch(
            "tree_sitter_analyzer.cli.commands.partial_read_command.output_json"
        ) as mock_output_json:
            command._output_partial_content(content)
            call_args = mock_output_json.call_args[0][0]
            assert call_args["range"]["start_column"] == 5

    def test_output_partial_content_with_end_column(self, command):
        """Test _output_partial_content with end_column."""
        command.args.end_column = 20
        command.args.output_format = "json"
        content = "test content"
        with patch(
            "tree_sitter_analyzer.cli.commands.partial_read_command.output_json"
        ) as mock_output_json:
            command._output_partial_content(content)
            call_args = mock_output_json.call_args[0][0]
            assert call_args["range"]["end_column"] == 20

    def test_output_partial_content_no_end_line(self, command):
        """Test _output_partial_content without end_line."""
        command.args.end_line = None
        command.args.output_format = "json"
        content = "test content"
        with patch(
            "tree_sitter_analyzer.cli.commands.partial_read_command.output_json"
        ) as mock_output_json:
            command._output_partial_content(content)
            call_args = mock_output_json.call_args[0][0]
            assert call_args["range"]["end_line"] is None

    def test_output_partial_content_toon_use_tabs(self, command):
        """Test _output_partial_content with TOON and use_tabs=True."""
        command.args.output_format = "toon"
        command.args.toon_use_tabs = True
        content = "test content"
        with patch(
            "tree_sitter_analyzer.cli.commands.partial_read_command.ToonFormatter"
        ) as mock_formatter_class:
            mock_formatter = MagicMock()
            mock_formatter.format.return_value = "toon_output"
            mock_formatter_class.return_value = mock_formatter
            command._output_partial_content(content)
            mock_formatter_class.assert_called_once_with(use_tabs=True)


class TestPartialReadCommandExecuteAsync:
    """Tests for PartialReadCommand.execute_async method."""

    @pytest.mark.asyncio
    async def test_execute_async_calls_execute(self, command):
        """Test execute_async calls execute method."""
        with patch.object(command, "execute", return_value=0) as mock_execute:
            result = await command.execute_async("python")
            assert result == 0
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_returns_execute_result(self, command):
        """Test execute_async returns execute result."""
        with patch.object(command, "execute", return_value=1):
            result = await command.execute_async("python")
            assert result == 1


class TestPartialReadCommandIntegration:
    """Integration tests for PartialReadCommand."""

    def test_full_workflow_success(self, command):
        """Test full workflow with successful read."""
        content = "line1\nline2\nline3"
        with patch.object(command, "validate_file", return_value=True):
            with patch(
                "tree_sitter_analyzer.cli.commands.partial_read_command.read_file_partial",
                return_value=content,
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.partial_read_command.output_section"
                ):
                    with patch(
                        "tree_sitter_analyzer.cli.commands.partial_read_command.output_data"
                    ):
                        with patch("builtins.print"):
                            result = command.execute()
                            assert result == 0

    def test_full_workflow_validation_failure(self, command):
        """Test full workflow with validation failure."""
        with patch.object(command, "validate_file", return_value=False):
            result = command.execute()
            assert result == 1

    def test_full_workflow_read_failure(self, command):
        """Test full workflow with read failure."""
        with patch.object(command, "validate_file", return_value=True):
            with patch(
                "tree_sitter_analyzer.cli.commands.partial_read_command.read_file_partial",
                return_value=None,
            ):
                with patch("tree_sitter_analyzer.output_manager.output_error"):
                    result = command.execute()
                    assert result == 1
