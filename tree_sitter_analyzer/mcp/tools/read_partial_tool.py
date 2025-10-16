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
from .base_tool import BaseMCPTool

# Set up logging
logger = setup_logger(__name__)


class ReadPartialTool(BaseMCPTool):
    """
    MCP Tool for reading partial content from code files.

    This tool integrates with existing file_handler functionality to provide
    selective file content reading through the MCP protocol.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the read partial tool."""
        super().__init__(project_root)
        self.file_output_manager = FileOutputManager(project_root)
        logger.info("ReadPartialTool initialized with security validation")

    def get_tool_schema(self) -> dict[str, Any]:
        """
        Get the MCP tool schema for read_code_partial.

        Returns:
            Dictionary containing the tool schema
        """
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the code file to read",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Starting line number (1-based)",
                    "minimum": 1,
                },
                "end_line": {
                    "type": "integer",
                    "description": "Ending line number (1-based, optional - reads to end if not specified)",
                    "minimum": 1,
                },
                "start_column": {
                    "type": "integer",
                    "description": "Starting column number (0-based, optional)",
                    "minimum": 0,
                },
                "end_column": {
                    "type": "integer",
                    "description": "Ending column number (0-based, optional)",
                    "minimum": 0,
                },
                "format": {
                    "type": "string",
                    "description": "Output format for the content",
                    "enum": ["text", "json", "raw"],
                    "default": "text",
                },
                "output_file": {
                    "type": "string",
                    "description": "Optional filename to save output to file (extension auto-detected based on content)",
                },
                "suppress_output": {
                    "type": "boolean",
                    "description": "When true and output_file is specified, suppress partial_content_result in response to save tokens",
                    "default": False,
                },
            },
            "required": ["file_path", "start_line"],
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the read_code_partial tool.

        Args:
            arguments: Tool arguments containing file_path, line/column ranges, and format

        Returns:
            Dictionary containing the partial file content and metadata (CLI --partial-read compatible format)

        Raises:
            ValueError: If required arguments are missing or invalid
            FileNotFoundError: If the specified file doesn't exist
        """
        # Validate required arguments
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
        output_format = arguments.get("format", "text")

        # Security validation BEFORE path resolution to catch symlinks
        is_valid, error_msg = self.security_validator.validate_file_path(
            file_path, self.project_root
        )
        if not is_valid:
            logger.warning(
                f"Security validation failed for file path: {file_path} - {error_msg}"
            )
            return {
                "success": False,
                "error": f"Security validation failed: {error_msg}",
                "file_path": file_path,
            }

        # Resolve file path using common path resolver
        resolved_path = self.path_resolver.resolve(file_path)

        # Additional security validation on resolved path
        is_valid, error_msg = self.security_validator.validate_file_path(
            resolved_path, self.project_root
        )
        if not is_valid:
            logger.warning(
                f"Security validation failed for resolved path: {resolved_path} - {error_msg}"
            )
            return {
                "success": False,
                "error": f"Security validation failed for resolved path: {error_msg}",
                "file_path": file_path,
            }

        # Validate file exists
        if not Path(resolved_path).exists():
            return {
                "success": False,
                "error": "Invalid file path: file does not exist",
                "file_path": file_path,
            }

        # Validate line numbers
        if start_line < 1:
            return {
                "success": False,
                "error": "start_line must be >= 1",
                "file_path": file_path,
            }

        if end_line is not None and end_line < start_line:
            return {
                "success": False,
                "error": "end_line must be >= start_line",
                "file_path": file_path,
            }

        # Validate column numbers
        if start_column is not None and start_column < 0:
            return {
                "success": False,
                "error": "start_column must be >= 0",
                "file_path": file_path,
            }

        if end_column is not None and end_column < 0:
            return {
                "success": False,
                "error": "end_column must be >= 0",
                "file_path": file_path,
            }

        logger.info(
            f"Reading partial content from {file_path}: lines {start_line}-{end_line or 'end'}"
        )

        try:
            # Use existing file_handler functionality
            # Use performance monitoring with proper context manager
            from ...mcp.utils import get_performance_monitor

            with get_performance_monitor().measure_operation("read_code_partial"):
                content = self._read_file_partial(
                    resolved_path, start_line, end_line, start_column, end_column
                )

                if content is None:
                    return {
                        "success": False,
                        "error": f"Failed to read partial content from file: {file_path}",
                        "file_path": file_path,
                    }

                # Check if content is empty or invalid range
                if not content or content.strip() == "":
                    return {
                        "success": False,
                        "error": f"Invalid line range or empty content: start_line={start_line}, end_line={end_line}",
                        "file_path": file_path,
                    }

                # Build result structure compatible with CLI --partial-read format
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

                # Format as JSON string like CLI does
                json_output = json.dumps(result_data, indent=2, ensure_ascii=False)

                # Build range info for header
                range_info = f"Line {start_line}"
                if end_line:
                    range_info += f"-{end_line}"

                # Build CLI-compatible output with header and JSON (without log message)
                cli_output = (
                    f"--- Partial Read Result ---\n"
                    f"File: {file_path}\n"
                    f"Range: {range_info}\n"
                    f"Characters read: {len(content)}\n"
                    f"{json_output}"
                )

                logger.info(
                    f"Successfully read {len(content)} characters from {file_path}"
                )

                # Calculate lines extracted
                lines_extracted = len(content.split("\n")) if content else 0
                if end_line:
                    lines_extracted = end_line - start_line + 1

                # Build result - conditionally include partial_content_result based on suppress_output
                result = {
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

                # Only include partial_content_result if not suppressed or no output file specified
                if not suppress_output or not output_file:
                    if output_format == "json":
                        # For JSON format, return structured data with exact line count
                        lines = content.split("\n") if content else []

                        # If end_line is specified, ensure we return exactly the requested number of lines
                        if end_line and len(lines) > lines_extracted:
                            lines = lines[:lines_extracted]
                        elif end_line and len(lines) < lines_extracted:
                            # Pad with empty lines if needed (shouldn't normally happen)
                            lines.extend([""] * (lines_extracted - len(lines)))

                        result["partial_content_result"] = {
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
                    else:
                        # For text/raw format, return CLI-compatible string
                        result["partial_content_result"] = cli_output

                # Handle file output if requested
                if output_file:
                    try:
                        # Generate base name from original file path if not provided
                        if not output_file or output_file.strip() == "":
                            base_name = Path(file_path).stem + "_extract"
                        else:
                            base_name = output_file

                        # Determine what content to save based on format preference
                        if output_format == "raw":
                            # Save only the extracted code content (no metadata)
                            content_to_save = content
                        elif output_format == "json":
                            # Save structured JSON data
                            content_to_save = json_output
                        else:  # format == "text" (default)
                            # Save CLI-compatible format with headers
                            content_to_save = cli_output

                        # Save to file with automatic extension detection
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

                return result

        except Exception as e:
            logger.error(f"Error reading partial content from {file_path}: {e}")
            return {"success": False, "error": str(e), "file_path": file_path}

    def _read_file_partial(
        self,
        file_path: str,
        start_line: int,
        end_line: int | None = None,
        start_column: int | None = None,
        end_column: int | None = None,
    ) -> str | None:
        """
        Internal method to read partial file content.

        This method wraps the existing read_file_partial function from file_handler.

        Args:
            file_path: Path to the file to read
            start_line: Starting line number (1-based)
            end_line: Ending line number (1-based, optional)
            start_column: Starting column number (0-based, optional)
            end_column: Ending column number (0-based, optional)

        Returns:
            Partial file content as string, or None if error
        """
        return read_file_partial(
            file_path, start_line, end_line, start_column, end_column
        )

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments against the schema.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        schema = self.get_tool_schema()
        required_fields = schema.get("required", [])

        # Check required fields
        for field in required_fields:
            if field not in arguments:
                raise ValueError(f"Required field '{field}' is missing")

        # Validate file_path
        if "file_path" in arguments:
            file_path = arguments["file_path"]
            if not isinstance(file_path, str):
                raise ValueError("file_path must be a string")
            if not file_path.strip():
                raise ValueError("file_path cannot be empty")

        # Validate start_line
        if "start_line" in arguments:
            start_line = arguments["start_line"]
            if not isinstance(start_line, int):
                raise ValueError("start_line must be an integer")
            if start_line < 1:
                raise ValueError("start_line must be >= 1")

        # Validate end_line
        if "end_line" in arguments:
            end_line = arguments["end_line"]
            if not isinstance(end_line, int):
                raise ValueError("end_line must be an integer")
            if end_line < 1:
                raise ValueError("end_line must be >= 1")
            if "start_line" in arguments and end_line < arguments["start_line"]:
                raise ValueError("end_line must be >= start_line")

        # Validate column numbers
        for col_field in ["start_column", "end_column"]:
            if col_field in arguments:
                col_value = arguments[col_field]
                if not isinstance(col_value, int):
                    raise ValueError(f"{col_field} must be an integer")
                if col_value < 0:
                    raise ValueError(f"{col_field} must be >= 0")

        # Validate format
        if "format" in arguments:
            format_value = arguments["format"]
            if not isinstance(format_value, str):
                raise ValueError("format must be a string")
            if format_value not in ["text", "json", "raw"]:
                raise ValueError("format must be 'text', 'json', or 'raw'")

        # Validate output_file if provided
        if "output_file" in arguments:
            output_file = arguments["output_file"]
            if not isinstance(output_file, str):
                raise ValueError("output_file must be a string")
            if not output_file.strip():
                raise ValueError("output_file cannot be empty")

        # Validate suppress_output if provided
        if "suppress_output" in arguments:
            suppress_output = arguments["suppress_output"]
            if not isinstance(suppress_output, bool):
                raise ValueError("suppress_output must be a boolean")

        return True

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get the MCP tool definition for read_code_partial.

        Returns:
            Tool definition dictionary compatible with MCP server
        """
        return {
            "name": "extract_code_section",
            "description": "Extract specific code sections by line/column range with multiple output formats (text/json/raw), optionally save to file with token optimization",
            "inputSchema": self.get_tool_schema(),
        }


# Tool instance for easy access
read_partial_tool = ReadPartialTool()
