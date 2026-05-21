#!/usr/bin/env python3
"""
Partial Read Command

Handles partial file reading functionality, extracting specified line ranges.
"""

from typing import TYPE_CHECKING, Any

from ...file_handler import read_file_partial
from ...mcp.tools.read_partial_helpers import (
    build_agent_summary,
    count_file_lines,
)
from ...output_manager import output_data, output_json, output_section
from .base_command import BaseCommand

# TOON formatter for CLI output
try:
    from ...formatters.toon_formatter import ToonFormatter

    _toon_available = True
except ImportError:
    _toon_available = False

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
        end_line = getattr(self.args, "end_line", None)
        start_column = getattr(self.args, "start_column", None)
        end_column = getattr(self.args, "end_column", None)
        # K8: count lines from the ACTUAL content. The old formula
        # ``end_line - start_line + 1`` lied when the range was past
        # EOF — an agent saw ``lines_extracted=N`` while ``content``
        # was empty.
        lines_extracted = len(content.splitlines()) if content else 0

        # Detect out-of-range / partial-overlap so we can surface
        # actionable flags instead of pretending the read succeeded.
        file_lines = count_file_lines(self.args.file_path)
        out_of_range = bool(
            content == ""
            and file_lines is not None
            and self.args.start_line > file_lines
        )
        partial_range = bool(
            file_lines is not None
            and end_line is not None
            and self.args.start_line <= file_lines
            and end_line > file_lines
        )
        clamped_to: list[int] | None = (
            [self.args.start_line, file_lines]
            if partial_range and file_lines is not None
            else None
        )

        # Build result data
        result_data: dict[str, Any] = {
            "file_path": self.args.file_path,
            "range": {
                "start_line": self.args.start_line,
                "end_line": end_line,
                "start_column": start_column,
                "end_column": end_column,
            },
            "content": content,
            "content_length": len(content),
            "lines_extracted": lines_extracted,
        }
        if file_lines is not None:
            result_data["file_lines"] = file_lines
        if out_of_range:
            result_data["out_of_range"] = True
        if partial_range:
            result_data["partial_range"] = True
            if clamped_to is not None:
                result_data["clamped_to"] = clamped_to
        result_data["agent_summary"] = build_agent_summary(
            file_path=self.args.file_path,
            start_line=self.args.start_line,
            end_line=end_line,
            start_column=start_column,
            end_column=end_column,
            content_length=len(content),
            lines_extracted=lines_extracted,
            content_format="text",
            file_lines=file_lines,
            out_of_range=out_of_range,
            partial_range=partial_range,
            clamped_to=clamped_to,
        )
        # Mirror ``summary_line`` at top level for callers that scan
        # for the canonical envelope key.
        summary_line = result_data["agent_summary"].get("summary_line")
        if summary_line:
            result_data["summary_line"] = summary_line
        # r37ag (dogfood): mirror ``agent_summary.verdict`` to top-level
        # (r37u envelope contract). Without this the CLI envelope gate
        # caught ``--partial-read`` returning ``verdict: None``.
        verdict = result_data["agent_summary"].get("verdict")
        if isinstance(verdict, str) and verdict:
            result_data["verdict"] = verdict
        result_data.setdefault("success", True)

        # Build range info for header
        range_info = f"Line {self.args.start_line}"
        if hasattr(self.args, "end_line") and self.args.end_line:
            range_info += f"-{self.args.end_line}"

        # Output format selection
        output_format = getattr(self.args, "output_format", "text")

        if output_format == "json":
            # Pure JSON output
            output_json(result_data)
        elif output_format == "toon" and _toon_available:
            # TOON output
            use_tabs = getattr(self.args, "toon_use_tabs", False)
            formatter = ToonFormatter(use_tabs=use_tabs)
            print(formatter.format(result_data))
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
