#!/usr/bin/env python3
"""
Partial Read Command

Handles partial file reading functionality, extracting specified line ranges.
"""

from typing import TYPE_CHECKING, Any

from ...file_handler import read_file_partial
from ...output_manager import output_data, output_json, output_section
from .base_command import BaseCommand

if TYPE_CHECKING:
    pass


class PartialReadCommand(BaseCommand):
    """Command for reading partial file content by line range."""

    def __init__(self, args: Any) -> None:
        """Initialize with arguments but skip base class analysis engine setup."""
        self.args = args
        # Don't call super().__init__() to avoid unnecessary analysis engine setup

    def validate_file(self) -> bool:
        """Validate input file exists and is accessible."""
        if not hasattr(self.args, "file_path") or not self.args.file_path:
            from ...output_manager import output_error

            output_error("File path not specified.")
            return False

        from pathlib import Path

        if not Path(self.args.file_path).exists():
            from ...output_manager import output_error

            output_error(f"File not found: {self.args.file_path}")
            return False

        return True

    def execute(self) -> int:
        """
        Execute partial read command.

        Returns:
            int: Exit code (0 for success, 1 for failure)
        """
        # Validate inputs
        if not self.validate_file():
            return 1

        # Validate partial read arguments
        if not self.args.start_line:
            from ...output_manager import output_error

            output_error("--start-line is required")
            return 1

        if self.args.start_line < 1:
            from ...output_manager import output_error

            output_error("--start-line must be 1 or greater")
            return 1

        if self.args.end_line and self.args.end_line < self.args.start_line:
            from ...output_manager import output_error

            output_error("--end-line must be greater than or equal to --start-line")
            return 1

        # Read partial content
        try:
            partial_content = read_file_partial(
                self.args.file_path,
                start_line=self.args.start_line,
                end_line=getattr(self.args, "end_line", None),
                start_column=getattr(self.args, "start_column", None),
                end_column=getattr(self.args, "end_column", None),
            )

            if partial_content is None:
                from ...output_manager import output_error

                output_error("Failed to read file partially")
                return 1

            # Output the result
            self._output_partial_content(partial_content)
            return 0

        except Exception as e:
            from ...output_manager import output_error

            output_error(f"Failed to read file partially: {e}")
            return 1

    def _output_partial_content(self, content: str) -> None:
        """Output the partial content in the specified format."""
        # Build result data
        result_data = {
            "file_path": self.args.file_path,
            "range": {
                "start_line": self.args.start_line,
                "end_line": getattr(self.args, "end_line", None),
                "start_column": getattr(self.args, "start_column", None),
                "end_column": getattr(self.args, "end_column", None),
            },
            "content": content,
            "content_length": len(content),
        }

        # Build range info for header
        range_info = f"Line {self.args.start_line}"
        if hasattr(self.args, "end_line") and self.args.end_line:
            range_info += f"-{self.args.end_line}"

        # Output format selection
        output_format = getattr(self.args, "output_format", "text")

        if output_format == "json":
            # Pure JSON output
            output_json(result_data)
        else:
            # Human-readable format with header
            output_section("Partial Read Result")
            output_data(f"File: {self.args.file_path}")
            output_data(f"Range: {range_info}")
            output_data(f"Characters read: {len(content)}")
            output_data("")  # Empty line for separation

            # Output the actual content
            print(content, end="")  # Use print to avoid extra formatting

    async def execute_async(self, language: str) -> int:
        """Not used for partial read command."""
        return self.execute()
