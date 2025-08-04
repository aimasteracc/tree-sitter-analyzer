#!/usr/bin/env python3
"""
Test Partial Read Command Validation Enhancement

Tests for the enhanced parameter validation logic in PartialReadCommand,
including boundary conditions and error handling.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tree_sitter_analyzer.cli.commands.partial_read_command import PartialReadCommand


class TestPartialReadCommandValidation:
    """Test class for PartialReadCommand validation enhancements."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test.java")

        # Create test file with multiple lines
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(
                """line 1
line 2
line 3
line 4
line 5
line 6
line 7
line 8
line 9
line 10"""
            )

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_start_line_validation(self) -> None:
        """Test validation when start_line is missing."""
        from argparse import Namespace

        args = Namespace(file_path=self.test_file, start_line=None, end_line=5)
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 1  # Should return error code

    def test_start_line_zero_validation(self) -> None:
        """Test validation when start_line is 0."""
        from argparse import Namespace

        args = Namespace(file_path=self.test_file, start_line=0, end_line=5)
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 1  # Should return error code

    def test_start_line_negative_validation(self) -> None:
        """Test validation when start_line is negative."""
        from argparse import Namespace

        args = Namespace(file_path=self.test_file, start_line=-1, end_line=5)
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 1  # Should return error code

    def test_end_line_less_than_start_line_validation(self) -> None:
        """Test validation when end_line is less than start_line."""
        from argparse import Namespace

        args = Namespace(file_path=self.test_file, start_line=5, end_line=3)
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 1  # Should return error code

    def test_end_line_equal_to_start_line_validation(self) -> None:
        """Test validation when end_line equals start_line (should be valid)."""
        from argparse import Namespace

        args = Namespace(
            file_path=self.test_file,
            start_line=3,
            end_line=3,
            start_column=None,
            end_column=None,
            output_format="text",
        )
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 0  # Should succeed

    def test_valid_line_range_validation(self) -> None:
        """Test validation with valid line range."""
        from argparse import Namespace

        args = Namespace(
            file_path=self.test_file,
            start_line=2,
            end_line=4,
            start_column=None,
            end_column=None,
            output_format="text",
        )
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 0  # Should succeed

    def test_start_line_only_validation(self) -> None:
        """Test validation with only start_line specified."""
        from argparse import Namespace

        args = Namespace(
            file_path=self.test_file,
            start_line=3,
            end_line=None,
            start_column=None,
            end_column=None,
            output_format="text",
        )
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 0  # Should succeed

    def test_nonexistent_file_validation(self) -> None:
        """Test validation with nonexistent file."""
        from argparse import Namespace

        nonexistent_file = os.path.join(self.temp_dir, "nonexistent.java")
        args = Namespace(file_path=nonexistent_file, start_line=1, end_line=5)
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 1  # Should return error code

    def test_missing_file_path_validation(self) -> None:
        """Test validation when file_path is missing."""
        from argparse import Namespace

        args = Namespace(file_path=None, start_line=1, end_line=5)
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 1  # Should return error code

    def test_empty_file_path_validation(self) -> None:
        """Test validation when file_path is empty string."""
        from argparse import Namespace

        args = Namespace(file_path="", start_line=1, end_line=5)
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 1  # Should return error code

    def test_large_line_numbers_validation(self) -> None:
        """Test validation with line numbers larger than file."""
        from argparse import Namespace

        args = Namespace(
            file_path=self.test_file,
            start_line=100,
            end_line=200,
            start_column=None,
            end_column=None,
            output_format="text",
        )
        command = PartialReadCommand(args)

        # This should not fail validation but may return empty content
        result = command.execute()
        assert (
            result == 0
        )  # Should succeed (validation passes, but content may be empty)

    def test_boundary_line_numbers(self) -> None:
        """Test with boundary line numbers (first and last lines)."""
        from argparse import Namespace

        # Test first line
        args = Namespace(
            file_path=self.test_file,
            start_line=1,
            end_line=1,
            start_column=None,
            end_column=None,
            output_format="text",
        )
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 0  # Should succeed

    def test_json_output_format_validation(self) -> None:
        """Test validation with JSON output format."""
        from argparse import Namespace

        args = Namespace(
            file_path=self.test_file,
            start_line=2,
            end_line=4,
            start_column=None,
            end_column=None,
            output_format="json",
        )
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 0  # Should succeed

    def test_column_parameters_validation(self) -> None:
        """Test validation with column parameters."""
        from argparse import Namespace

        args = Namespace(
            file_path=self.test_file,
            start_line=2,
            end_line=4,
            start_column=1,
            end_column=5,
            output_format="text",
        )
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 0  # Should succeed

    def test_error_message_content_for_missing_start_line(self) -> None:
        """Test that correct error message is shown for missing start_line."""
        from argparse import Namespace

        args = Namespace(file_path=self.test_file, start_line=None, end_line=5)
        command = PartialReadCommand(args)

        with patch("tree_sitter_analyzer.output_manager.output_error") as mock_error:
            result = command.execute()

            assert result == 1
            mock_error.assert_called_with("--start-line is required")

    def test_error_message_content_for_invalid_start_line(self) -> None:
        """Test that correct error message is shown for invalid start_line."""
        from argparse import Namespace

        # Test with 0 - this is treated as falsy, so shows "required" message
        args = Namespace(file_path=self.test_file, start_line=0, end_line=5)
        command = PartialReadCommand(args)

        with patch("tree_sitter_analyzer.output_manager.output_error") as mock_error:
            result = command.execute()

            assert result == 1
            # 0 is treated as falsy, so it shows "required" message
            mock_error.assert_called_with("--start-line is required")

    def test_error_message_content_for_negative_start_line(self) -> None:
        """Test that correct error message is shown for negative start_line."""
        from argparse import Namespace

        # Test with negative number - this should show "must be 1 or greater"
        args = Namespace(file_path=self.test_file, start_line=-1, end_line=5)
        command = PartialReadCommand(args)

        with patch("tree_sitter_analyzer.output_manager.output_error") as mock_error:
            result = command.execute()

            assert result == 1
            # Negative numbers pass the "not start_line" check but fail the "< 1" check
            mock_error.assert_called_with("--start-line must be 1 or greater")

    def test_error_message_content_for_invalid_end_line(self) -> None:
        """Test that correct error message is shown for invalid end_line."""
        from argparse import Namespace

        args = Namespace(file_path=self.test_file, start_line=5, end_line=3)
        command = PartialReadCommand(args)

        with patch("tree_sitter_analyzer.output_manager.output_error") as mock_error:
            result = command.execute()

            assert result == 1
            mock_error.assert_called_with(
                "--end-line must be greater than or equal to --start-line"
            )

    def test_error_message_content_for_missing_file(self) -> None:
        """Test that correct error message is shown for missing file."""
        from argparse import Namespace

        nonexistent_file = os.path.join(self.temp_dir, "nonexistent.java")
        args = Namespace(file_path=nonexistent_file, start_line=1, end_line=5)
        command = PartialReadCommand(args)

        with patch("tree_sitter_analyzer.output_manager.output_error") as mock_error:
            result = command.execute()

            assert result == 1
            mock_error.assert_called_with(f"File not found: {nonexistent_file}")

    def test_successful_execution_with_valid_parameters(self) -> None:
        """Test successful execution with all valid parameters."""
        from argparse import Namespace

        args = Namespace(
            file_path=self.test_file,
            start_line=2,
            end_line=4,
            start_column=None,
            end_column=None,
            output_format="text",
        )
        command = PartialReadCommand(args)

        result = command.execute()
        assert result == 0  # Should succeed

    def test_validation_order(self) -> None:
        """Test that validations are performed in the correct order."""
        from argparse import Namespace

        # Test that file validation comes before line validation
        args = Namespace(
            file_path=None,  # This should fail first
            start_line=None,  # This would also fail, but file check should come first
            end_line=5,
        )
        command = PartialReadCommand(args)

        with patch("tree_sitter_analyzer.output_manager.output_error") as mock_error:
            result = command.execute()

            assert result == 1
            # Should fail on file path validation first
            mock_error.assert_called_with("File path not specified.")


if __name__ == "__main__":
    pytest.main([__file__])
