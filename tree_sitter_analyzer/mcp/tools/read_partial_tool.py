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

# Set up logging
logger = setup_logger(__name__)

_BATCH_LIMITS = {
    "max_files": 20,
    "max_sections_per_file": 50,
    "max_sections_total": 200,
    "max_total_bytes": 1024 * 1024,  # 1 MiB
    "max_total_lines": 5000,
    "max_file_size_bytes": 5 * 1024 * 1024,  # 5 MiB
}


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
                "requests": {
                    "type": "array",
                    "description": "Batch mode: extract multiple ranges from multiple files in one call (mutually exclusive with file_path/start_line/...)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "sections": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "start_line": {"type": "integer", "minimum": 1},
                                        "end_line": {"type": "integer", "minimum": 1},
                                        "label": {"type": "string"},
                                    },
                                    "required": ["start_line"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["file_path", "sections"],
                        "additionalProperties": False,
                    },
                },
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
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, 50-70% token reduction) or 'json'",
                    "default": "toon",
                },
                "allow_truncate": {
                    "type": "boolean",
                    "description": "Batch mode only: allow truncating results to fit limits (default: false, default behavior is fail on limit exceed)",
                    "default": False,
                },
                "fail_fast": {
                    "type": "boolean",
                    "description": "Batch mode only: stop on first error (default: false, partial success)",
                    "default": False,
                },
            },
            "oneOf": [
                {"required": ["file_path", "start_line"]},
                {"required": ["requests"]},
            ],
            "additionalProperties": False,
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
        # Batch mode: requests[]
        if "requests" in arguments and arguments["requests"] is not None:
            return await self._execute_batch(arguments)

        # Single mode: file_path + start_line
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

        # Resolve + security validation with shared caching to avoid redundant checks
        try:
            resolved_path = self.resolve_and_validate_file_path(file_path)
        except ValueError as e:
            return {"success": False, "error": str(e), "file_path": file_path}

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
                    if content_format == "json":
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
                        if content_format == "raw":
                            # Save only the extracted code content (no metadata)
                            content_to_save = content
                        elif content_format == "json":
                            # Save structured JSON data (optionally in TOON format)
                            if output_format == "toon":
                                content_to_save, _ = format_for_file_output(
                                    result_data, "toon"
                                )
                            else:
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

                # Apply TOON format to direct output if requested
                return apply_toon_format_to_response(result, output_format)

        except Exception as e:
            logger.error(f"Error reading partial content from {file_path}: {e}")
            return {"success": False, "error": str(e), "file_path": file_path}

    async def _execute_batch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Batch mode for extracting multiple ranges from multiple files.

        Notes:
        - Default output is TOON for token reduction.
        - When output_format='toon', the response MUST NOT include detailed JSON fields like results/sections/content.
        """
        output_format = arguments.get("output_format", "toon")
        content_format = arguments.get("format", "text")
        allow_truncate = bool(arguments.get("allow_truncate", False))
        fail_fast = bool(arguments.get("fail_fast", False))
        requests = arguments.get("requests")

        # Mutually exclusive with single-mode args
        single_keys = {
            "file_path",
            "start_line",
            "end_line",
            "start_column",
            "end_column",
        }
        if any(k in arguments for k in single_keys):
            raise ValueError(
                "requests is mutually exclusive with file_path/start_line/end_line/start_column/end_column"
            )

        # Disallow file output options in batch for now (keeps behavior predictable + token goals clear)
        if "output_file" in arguments or "suppress_output" in arguments:
            raise ValueError(
                "output_file/suppress_output are not supported with requests batch mode"
            )

        if not isinstance(requests, list):
            raise ValueError("requests must be a list")

        # Enforce max_files
        truncated = False
        if len(requests) > _BATCH_LIMITS["max_files"]:
            if not allow_truncate:
                raise ValueError(
                    f"Too many files in requests: {len(requests)} > max_files={_BATCH_LIMITS['max_files']}"
                )
            requests = requests[: _BATCH_LIMITS["max_files"]]
            truncated = True

        # Track total section processing; we enforce max_sections_total during processing.

        results: list[dict[str, Any]] = []
        total_bytes = 0
        total_lines = 0
        ok_sections = 0
        sections_seen_total = 0
        error_count = 0

        for file_req in requests:
            if not isinstance(file_req, dict):
                if fail_fast:
                    raise ValueError("Each requests[] entry must be an object")
                results.append(
                    {
                        "file_path": "",
                        "resolved_path": "",
                        "sections": [],
                        "errors": [{"error": "Invalid request entry"}],
                    }
                )
                error_count += 1
                continue

            file_path = file_req.get("file_path")
            sections = file_req.get("sections")
            if not isinstance(file_path, str) or not file_path.strip():
                if fail_fast:
                    raise ValueError("requests[].file_path must be a non-empty string")
                results.append(
                    {
                        "file_path": file_path or "",
                        "resolved_path": "",
                        "sections": [],
                        "errors": [{"error": "Invalid file_path"}],
                    }
                )
                error_count += 1
                continue
            if not isinstance(sections, list):
                if fail_fast:
                    raise ValueError("requests[].sections must be a list")
                results.append(
                    {
                        "file_path": file_path,
                        "resolved_path": "",
                        "sections": [],
                        "errors": [{"error": "Invalid sections"}],
                    }
                )
                error_count += 1
                continue

            if len(sections) > _BATCH_LIMITS["max_sections_per_file"]:
                if not allow_truncate:
                    if fail_fast:
                        raise ValueError(
                            f"Too many sections for file {file_path}: {len(sections)} > max_sections_per_file={_BATCH_LIMITS['max_sections_per_file']}"
                        )
                    results.append(
                        {
                            "file_path": file_path,
                            "resolved_path": "",
                            "sections": [],
                            "errors": [{"error": "Too many sections for file"}],
                        }
                    )
                    error_count += 1
                    continue
                sections = sections[: _BATCH_LIMITS["max_sections_per_file"]]
                truncated = True

            try:
                resolved = self.resolve_and_validate_file_path(file_path)
            except ValueError as e:
                if fail_fast:
                    raise
                results.append(
                    {
                        "file_path": file_path,
                        "resolved_path": "",
                        "sections": [],
                        "errors": [{"error": str(e)}],
                    }
                )
                error_count += 1
                continue

            p = Path(resolved)
            if not p.exists():
                msg = "Invalid file path: file does not exist"
                if fail_fast:
                    raise ValueError(msg)
                results.append(
                    {
                        "file_path": file_path,
                        "resolved_path": resolved,
                        "sections": [],
                        "errors": [{"error": msg}],
                    }
                )
                error_count += 1
                continue

            try:
                if p.stat().st_size > _BATCH_LIMITS["max_file_size_bytes"]:
                    msg = f"File too large: {p.stat().st_size} > max_file_size_bytes={_BATCH_LIMITS['max_file_size_bytes']}"
                    if fail_fast:
                        raise ValueError(msg)
                    results.append(
                        {
                            "file_path": file_path,
                            "resolved_path": resolved,
                            "sections": [],
                            "errors": [{"error": msg}],
                        }
                    )
                    error_count += 1
                    continue
            except OSError as e:
                msg = f"Could not stat file: {e}"
                if fail_fast:
                    raise ValueError(msg) from e
                results.append(
                    {
                        "file_path": file_path,
                        "resolved_path": resolved,
                        "sections": [],
                        "errors": [{"error": msg}],
                    }
                )
                error_count += 1
                continue

            file_result: dict[str, Any] = {
                "file_path": file_path,
                "resolved_path": resolved,
                "sections": [],
                "errors": [],
            }

            for sec in sections:
                if not isinstance(sec, dict):
                    error_count += 1
                    file_result["errors"].append({"error": "Invalid section entry"})
                    if fail_fast:
                        break
                    continue

                label = sec.get("label")
                start_line = sec.get("start_line")
                end_line = sec.get("end_line")
                if not isinstance(start_line, int) or start_line < 1:
                    error_count += 1
                    file_result["errors"].append(
                        {"label": label, "error": "start_line must be an integer >= 1"}
                    )
                    if fail_fast:
                        break
                    continue
                if end_line is not None and (
                    not isinstance(end_line, int) or end_line < start_line
                ):
                    error_count += 1
                    file_result["errors"].append(
                        {
                            "label": label,
                            "error": "end_line must be an integer >= start_line",
                        }
                    )
                    if fail_fast:
                        break
                    continue

                # Enforce global section count limit (based on attempted sections)
                sections_seen_total += 1
                if sections_seen_total > _BATCH_LIMITS["max_sections_total"]:
                    if not allow_truncate:
                        raise ValueError(
                            f"Too many sections in requests: > max_sections_total={_BATCH_LIMITS['max_sections_total']}"
                        )
                    truncated = True
                    break

                content = self._read_file_partial(resolved, start_line, end_line)
                if not content or content.strip() == "":
                    error_count += 1
                    file_result["errors"].append(
                        {
                            "label": label,
                            "error": f"Invalid line range or empty content: start_line={start_line}, end_line={end_line}",
                        }
                    )
                    if fail_fast:
                        break
                    continue

                content_bytes = len(content.encode("utf-8"))
                content_lines = len(content.split("\n")) if content else 0
                if end_line is not None:
                    content_lines = max(0, end_line - start_line + 1)

                # Enforce total limits
                would_bytes = total_bytes + content_bytes
                would_lines = total_lines + content_lines
                if (
                    would_bytes > _BATCH_LIMITS["max_total_bytes"]
                    or would_lines > _BATCH_LIMITS["max_total_lines"]
                ):
                    if not allow_truncate:
                        raise ValueError(
                            "Batch extract exceeds limits: "
                            f"max_total_bytes={_BATCH_LIMITS['max_total_bytes']}, max_total_lines={_BATCH_LIMITS['max_total_lines']}"
                        )
                    truncated = True
                    break

                total_bytes = would_bytes
                total_lines = would_lines
                ok_sections += 1

                # Store detailed section result (will be removed from response in TOON mode by apply_toon_format_to_response)
                section_result: dict[str, Any] = {
                    "label": label,
                    "range": {"start_line": start_line, "end_line": end_line},
                    "content_length": len(content),
                }
                if content_format == "raw":
                    section_result["content"] = content
                else:
                    # text/json both carry the extracted text; JSON output remains structured.
                    section_result["content"] = content

                file_result["sections"].append(section_result)

            results.append(file_result)

        response: dict[str, Any] = {
            "success": ok_sections > 0 and (error_count == 0 or not fail_fast),
            "count_files": len(results),
            "count_sections": ok_sections,
            "truncated": truncated,
            "limits": {
                "max_files": _BATCH_LIMITS["max_files"],
                "max_sections_per_file": _BATCH_LIMITS["max_sections_per_file"],
                "max_sections_total": _BATCH_LIMITS["max_sections_total"],
                "max_total_bytes": _BATCH_LIMITS["max_total_bytes"],
                "max_total_lines": _BATCH_LIMITS["max_total_lines"],
                "max_file_size_bytes": _BATCH_LIMITS["max_file_size_bytes"],
            },
            "errors_summary": {"errors": error_count},
            "results": results,
        }

        return apply_toon_format_to_response(response, output_format)

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
        # Batch mode validation
        if "requests" in arguments and arguments["requests"] is not None:
            if any(
                k in arguments
                for k in [
                    "file_path",
                    "start_line",
                    "end_line",
                    "start_column",
                    "end_column",
                ]
            ):
                raise ValueError(
                    "requests is mutually exclusive with file_path/start_line/end_line/start_column/end_column"
                )
            if not isinstance(arguments["requests"], list):
                raise ValueError("requests must be a list")
            return True

        # Single mode requires file_path + start_line
        for field in ["file_path", "start_line"]:
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
