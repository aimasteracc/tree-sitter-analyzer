#!/usr/bin/env python3
"""
Read Code Partial MCP Tool

This tool provides partial file reading functionality through the MCP protocol,
allowing selective content extraction with line and column range support.
"""

import json
from pathlib import Path
from typing import Any

from ...file_handler import read_file_partial
from ...utils import setup_logger
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import apply_toon_format_to_response, format_for_file_output
from .base_tool import BaseMCPTool
from .batch_executor import execute_batch
from .read_partial_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .read_partial_helpers import build_agent_summary_for_result

logger = setup_logger(__name__)


def _validate_column_fields(arguments: dict[str, Any]) -> None:
    """Validate start_column and end_column fields."""
    for col_field in ["start_column", "end_column"]:
        if col_field in arguments:
            col_value = arguments[col_field]
            if not isinstance(col_value, int):
                raise ValueError(f"{col_field} must be an integer")
            if col_value < 0:
                raise ValueError(f"{col_field} must be >= 0")


def _require_fields(arguments: dict[str, Any], fields: list[str]) -> None:
    for field in fields:
        if field not in arguments:
            raise ValueError(f"Required field '{field}' is missing")


def _validate_string_field(arguments: dict[str, Any], field: str) -> None:
    val = arguments.get(field)
    if val is not None:
        if not isinstance(val, str):
            raise ValueError(f"{field} must be a string")
        if not val.strip():
            raise ValueError(f"{field} cannot be empty")


def _validate_int_field(
    arguments: dict[str, Any], field: str, min_val: int = 0
) -> None:
    val = arguments.get(field)
    if val is not None:
        if not isinstance(val, int):
            raise ValueError(f"{field} must be an integer")
        if val < min_val:
            raise ValueError(f"{field} must be >= {min_val}")


class ReadPartialTool(BaseMCPTool):
    """MCP Tool for reading partial content from code files.

    Supports single-range extraction, batch multi-range extraction,
    and multiple output formats (text, json, raw) with file output.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize with optional project root for path resolution."""
        super().__init__(project_root)
        self.file_output_manager = FileOutputManager(project_root)
        logger.info("ReadPartialTool initialized with security validation")

    # JSON schema for input validation
    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return _TOOL_SCHEMA

    # Main entry point - dispatches to mode-specific handler
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute single or batch partial read based on arguments."""
        if "requests" in arguments and arguments["requests"] is not None:
            return await self._execute_batch(arguments)

        if "file_path" not in arguments:
            raise ValueError("file_path is required")
        if "start_line" not in arguments:
            raise ValueError("start_line is required")

        file_path = arguments["file_path"]
        start_line = arguments["start_line"]
        end_line = arguments.get("end_line")
        start_column = arguments.get("start_column")
        end_column = arguments.get("end_column")
        output_file = arguments.get("output_file")
        suppress_output = arguments.get("suppress_output", False)
        content_format = arguments.get("format", "text")
        output_format = arguments.get("output_format", "toon")

        err = self._validate_resolve(
            file_path, start_line, end_line, start_column, end_column
        )
        if err:
            return err

        resolved_path = self.resolve_and_validate_file_path(file_path)
        logger.info(
            f"Reading partial content from {file_path}: lines {start_line}-{end_line or 'end'}"
        )

        try:
            # Delegate to extracted method to reduce nesting depth
            return self._read_and_format(
                file_path,
                resolved_path,
                start_line,
                end_line,
                start_column,
                end_column,
                content_format,
                output_format,
                output_file,
                suppress_output,
            )
        except Exception as e:
            # Return error response for any unexpected failures
            logger.error(f"Error reading partial content from {file_path}: {e}")
            return {"success": False, "error": str(e), "file_path": file_path}

    # Core read + format pipeline extracted to reduce nesting depth
    def _read_and_format(
        self,
        file_path: str,
        resolved_path: str,
        start_line: int,
        end_line: int | None,
        start_column: int | None,
        end_column: int | None,
        content_format: str,
        output_format: str,
        output_file: str | None,
        suppress_output: bool,
    ) -> dict[str, Any]:
        """Read partial content and format the response."""
        # Read the partial content from the resolved file path
        content = self._read_file_partial(
            resolved_path, start_line, end_line, start_column, end_column
        )

        # Handle read failure
        if content is None:
            return {
                "success": False,
                "error": f"Failed to read partial content from file: {file_path}",
                "file_path": file_path,
            }

        # Handle empty content (invalid range)
        if not content or content.strip() == "":
            return {
                "success": False,
                "error": f"Invalid line range or empty content: start_line={start_line}, end_line={end_line}",
                "file_path": file_path,
            }

        logger.info(f"Successfully read {len(content)} characters from {file_path}")

        # Compute lines extracted from range or actual content
        lines_extracted = (
            end_line - start_line + 1 if end_line else len(content.split("\n"))
        )

        result = self._build_result(
            file_path,
            start_line,
            end_line,
            start_column,
            end_column,
            content,
            lines_extracted,
            content_format,
            suppress_output,
            output_file,
        )

        self._apply_file_output(
            result,
            file_path,
            content,
            content_format,
            output_format,
            output_file,
        )

        return apply_toon_format_to_response(result, output_format)

    # Validate file path and range parameters
    # Returns error dict if validation fails, None if OK
    def _validate_resolve(
        self,
        file_path: str,
        start_line: int,
        end_line: int | None,
        start_column: int | None,
        end_column: int | None,
    ) -> dict[str, Any] | None:
        """Validate and resolve file path and range parameters."""
        # First check: is the file path valid and resolvable?
        try:
            self.resolve_and_validate_file_path(file_path)
        except ValueError as e:
            return {"success": False, "error": str(e), "file_path": file_path}

        # Resolve path and check file exists on disk
        resolved = self.resolve_and_validate_file_path(file_path)
        if not Path(resolved).exists():
            return {
                "success": False,
                "error": "Invalid file path: file does not exist",
                "file_path": file_path,
            }
        # Validate start_line is positive
        if start_line < 1:
            return {
                "success": False,
                "error": "start_line must be >= 1",
                "file_path": file_path,
            }
        # Validate end_line >= start_line
        if end_line is not None and end_line < start_line:
            return {
                "success": False,
                "error": "end_line must be >= start_line",
                "file_path": file_path,
            }
        # Validate start_column is non-negative
        if start_column is not None and start_column < 0:
            return {
                "success": False,
                "error": "start_column must be >= 0",
                "file_path": file_path,
            }
        # Validate end_column is non-negative
        if end_column is not None and end_column < 0:
            return {
                "success": False,
                "error": "end_column must be >= 0",
                "file_path": file_path,
            }
        return None

    # Assemble response dict from analysis data
    def _build_result(
        self,
        file_path: str,
        start_line: int,
        end_line: int | None,
        start_column: int | None,
        end_column: int | None,
        content: str,
        lines_extracted: int,
        content_format: str,
        suppress_output: bool,
        output_file: str | None,
    ) -> dict[str, Any]:
        """Build the result dict with range metadata and optional formatted content."""
        result: dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "range": {
                "start_line": start_line,
                "end_line": end_line,
                "start_column": start_column,
                "end_column": end_column,
            },
            "content_length": len(content),
            "lines_extracted": lines_extracted,
        }
        result["agent_summary"] = build_agent_summary_for_result(
            result, content_format, output_file, suppress_output
        )

        if end_line and end_line > start_line:
            result["next_steps"] = [
                "query_code to find related elements in this file",
                "search_content to find callers or usages of this code",
            ]

        if not suppress_output or not output_file:
            result["partial_content_result"] = self._format_content(
                content,
                content_format,
                file_path,
                start_line,
                end_line,
                start_column,
                end_column,
                lines_extracted,
            )

        return result

    # Transform raw content into requested output format
    def _format_content(
        self,
        content: str,
        content_format: str,
        file_path: str,
        start_line: int,
        end_line: int | None,
        start_column: int | None,
        end_column: int | None,
        lines_extracted: int,
    ) -> Any:
        """Format extracted content as json or text with metadata header."""
        # Build human-readable range description
        range_info = f"Line {start_line}"
        if end_line:
            range_info += f"-{end_line}"

        # Build structured result data with range and content
        result_data = {
            "file_path": file_path,
            "range": {
                "start_line": start_line,
                "end_line": end_line,
                "start_column": start_column,
                "end_column": end_column,
            },
            "content": content,
            "content_length": len(content),
        }

        # JSON format: return as line array with metadata
        if content_format == "json":
            return self._format_as_json_lines(
                content,
                file_path,
                start_line,
                end_line,
                start_column,
                end_column,
                lines_extracted,
            )

        # Text format: return JSON dump with metadata header
        json_output = json.dumps(result_data, indent=2, ensure_ascii=False)
        # Build text result with header and content
        return (
            f"--- Partial Read Result ---\n"
            f"File: {file_path}\n"
            f"Range: {range_info}\n"
            f"Characters read: {len(content)}\n"
            f"{json_output}"
        )

    # Format content as JSON line array with metadata
    # Splits content into lines and pads/truncates to match requested range
    def _format_as_json_lines(
        self,
        content: str,
        file_path: str,
        start_line: int,
        end_line: int | None,
        start_column: int | None,
        end_column: int | None,
        lines_extracted: int,
    ) -> dict[str, Any]:
        """Format content as a JSON line array with metadata."""
        lines = content.split("\n")
        if end_line and len(lines) > lines_extracted:
            lines = lines[:lines_extracted]
        elif end_line and len(lines) < lines_extracted:
            pad = lines_extracted - len(lines)
            lines.extend([""] * pad)
        return {
            "lines": lines,
            "metadata": {
                "file_path": file_path,
                "range": {
                    "start_line": start_line,
                    "end_line": end_line,
                    "start_column": start_column,
                    "end_column": end_column,
                },
                "content_length": len(content),
                "lines_count": len(lines),
            },
        }

    # Write extracted content to output file
    def _apply_file_output(
        self,
        result: dict[str, Any],
        file_path: str,
        content: str,
        content_format: str,
        output_format: str,
        output_file: str | None,
    ) -> None:
        """Write extracted content to a file if output_file is specified."""
        # Skip if no output file requested
        if not output_file:
            return

        try:
            # Determine base name for the output file
            base_name = (
                output_file.strip()
                if output_file.strip()
                else Path(file_path).stem + "_extract"
            )

            # Prepare content in appropriate format for saving
            content_to_save = self._prepare_save_content(
                content_format,
                content,
                result,
                file_path,
                output_format,
            )

            # Save to file and record path in result
            saved_file_path = self.file_output_manager.save_to_file(
                content=content_to_save, base_name=base_name
            )
            result["output_file_path"] = saved_file_path
            result["file_saved"] = True
            logger.info(f"Extract output saved to: {saved_file_path}")

        except Exception as e:
            logger.error(f"Failed to save output to file: {e}")
            result["file_save_error"] = str(e)
            result["file_saved"] = False

    # Prepare content for file output based on format
    # Converts raw content to appropriate format (raw, toon, or json)
    def _prepare_save_content(
        self,
        content_format: str,
        content: str,
        result: dict[str, Any],
        file_path: str,
        output_format: str,
    ) -> str:
        """Prepare content for saving to file based on format type."""
        # Raw format: return content as-is
        if content_format == "raw":
            return content
        # JSON format: structure with range metadata
        if content_format == "json":
            result_data = {
                "file_path": file_path,
                "range": result["range"],
                "content": content,
                "content_length": len(content),
            }
            # Use toon format for token efficiency
            if output_format == "toon":
                content_to_save, _ = format_for_file_output(result_data, "toon")
                return content_to_save
            return json.dumps(result_data, indent=2, ensure_ascii=False)
        # Default: use the formatted result content
        return str(result.get("partial_content_result", content))

    # Batch mode: delegate to batch_executor for multi-range extraction
    async def _execute_batch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Batch mode for extracting multiple ranges from multiple files."""
        # Return formatted result
        return await execute_batch(self, arguments, self._read_file_partial)

    # Delegate to file_handler for range extraction
    # Wraps the core read_file_partial with error handling
    def _read_file_partial(
        self,
        file_path: str,
        start_line: int,
        end_line: int | None = None,
        start_column: int | None = None,
        end_column: int | None = None,
    ) -> str | None:
        """Delegate to file_handler for the actual partial read."""
        # Return formatted result
        return read_file_partial(
            file_path, start_line, end_line, start_column, end_column
        )

    # Input validation - fail fast with clear error messages
    # Validates batch vs single mode, types, and range constraints
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments: batch vs single mode, types, ranges."""
        if "requests" in arguments and arguments["requests"] is not None:
            single_keys = [
                "file_path",
                "start_line",
                "end_line",
                "start_column",
                "end_column",
            ]
            if any(k in arguments for k in single_keys):
                raise ValueError(
                    "requests is mutually exclusive with file_path/start_line/end_line/start_column/end_column"
                )
            if not isinstance(arguments["requests"], list):
                raise ValueError("requests must be a list")
            return True

        _require_fields(arguments, ["file_path", "start_line"])
        _validate_string_field(arguments, "file_path")
        _validate_int_field(arguments, "start_line", min_val=1)
        if "end_line" in arguments:
            _validate_int_field(arguments, "end_line", min_val=1)
            if arguments["end_line"] < arguments.get("start_line", 0):
                raise ValueError("end_line must be >= start_line")
        _validate_column_fields(arguments)
        if "format" in arguments:
            val = arguments["format"]
            if not isinstance(val, str):
                raise ValueError("format must be a string")
            if val not in ("text", "json", "raw"):
                raise ValueError("format must be 'text', 'json', or 'raw'")
        if "output_file" in arguments:
            _validate_string_field(arguments, "output_file")
        if "suppress_output" in arguments and not isinstance(
            arguments["suppress_output"], bool
        ):
            raise ValueError("suppress_output must be a boolean")
        return True

    # MCP tool metadata - name, description, schema
    # Tool name is extract_code_section for clarity in AI agent workflows
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "extract_code_section",
            "description": (
                "Read code by exact line ranges. Batch: multiple ranges/files in one call. "
                "Prefer over built-in Read for: extracting specific functions/classes."
            ),
            "inputSchema": self.get_tool_schema(),
        }


# Tool instance for easy module-level access
read_partial_tool = ReadPartialTool()  # Tool instance for easy access
read_partial_tool = ReadPartialTool()
