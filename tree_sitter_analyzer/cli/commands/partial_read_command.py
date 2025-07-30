#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Partial Read Command

Handles partial file reading functionality, extracting specified line ranges.
"""
import json
from typing import TYPE_CHECKING

from ...file_handler import read_file_partial
from ...output_manager import output_data, output_json, output_section
from .base_command import BaseCommand

if TYPE_CHECKING:
    pass


class PartialReadCommand(BaseCommand):
    """Command for reading partial file content by line range."""

    def __init__(self, args):
        """Initialize with arguments but skip base class analysis engine setup."""
        self.args = args
        # Don't call super().__init__() to avoid unnecessary analysis engine setup

    def validate_file(self) -> bool:
        """Validate input file exists and is accessible."""
        if not hasattr(self.args, "file_path") or not self.args.file_path:
            from ...output_manager import output_error
            output_error("ERROR: ファイルパスが指定されていません。")
            return False

        import os

        if not os.path.exists(self.args.file_path):
            from ...output_manager import output_error
            output_error(f"ERROR: ファイルが見つかりません: {self.args.file_path}")
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
            output_error("ERROR: --start-lineが必須です")
            return 1

        if self.args.start_line < 1:
            from ...output_manager import output_error
            output_error("ERROR: --start-lineは1以上である必要があります")
            return 1

        if self.args.end_line and self.args.end_line < self.args.start_line:
            from ...output_manager import output_error
            output_error("ERROR: --end-lineは--start-line以上である必要があります")
            return 1

        # Read partial content
        try:
            partial_content = read_file_partial(
                self.args.file_path,
                start_line=self.args.start_line,
                end_line=getattr(self.args, 'end_line', None),
                start_column=getattr(self.args, 'start_column', None),
                end_column=getattr(self.args, 'end_column', None)
            )

            if partial_content is None:
                from ...output_manager import output_error
                output_error("ERROR: ファイルの部分読み込みに失敗しました")
                return 1

            # Output the result
            self._output_partial_content(partial_content)
            return 0

        except Exception as e:
            from ...output_manager import output_error
            output_error(f"ERROR: ファイルの部分読み込みに失敗しました: {e}")
            return 1

    def _output_partial_content(self, content: str) -> None:
        """Output the partial content in the specified format."""
        # Build result data
        result_data = {
            "file_path": self.args.file_path,
            "range": {
                "start_line": self.args.start_line,
                "end_line": getattr(self.args, 'end_line', None),
                "start_column": getattr(self.args, 'start_column', None),
                "end_column": getattr(self.args, 'end_column', None),
            },
            "content": content,
            "content_length": len(content),
        }

        # Build range info for header
        range_info = f"行 {self.args.start_line}"
        if hasattr(self.args, 'end_line') and self.args.end_line:
            range_info += f"-{self.args.end_line}"

        # Output format selection
        output_format = getattr(self.args, 'output_format', 'text')

        if output_format == 'json':
            # Pure JSON output
            output_json(result_data)
        else:
            # Human-readable format with header
            output_section("部分読み込み結果")
            output_data(f"ファイル: {self.args.file_path}")
            output_data(f"範囲: {range_info}")
            output_data(f"読み込み文字数: {len(content)}")
            output_data("")  # Empty line for separation
            
            # Output the actual content
            print(content, end='')  # Use print to avoid extra formatting

    async def execute_async(self, language: str) -> int:
        """Not used for partial read command."""
        return self.execute() 