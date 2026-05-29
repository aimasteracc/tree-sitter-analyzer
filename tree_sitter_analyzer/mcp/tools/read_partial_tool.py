#!/usr/bin/env python3
"""
Read Code Partial MCP Tool

This tool provides partial file reading functionality through the MCP protocol,
allowing selective content extraction with line and column range support.
"""

from pathlib import Path
from typing import Any

from ...file_handler import read_file_partial
from ...utils import setup_logger
from ..utils.error_sanitizer import safe_error_message
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool
from .batch_executor import execute_batch
from .read_partial_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .read_partial_helpers import (
    apply_partial_file_output,
    build_agent_summary_for_result,
    count_file_lines,
    format_partial_content,
    format_partial_content_as_json_lines,
    prepare_partial_save_content,
)

logger = setup_logger(__name__)

# ── Module-level helpers (extracted to keep class-method AST depth ≤ 11) ─────

_TOOL_DESCRIPTION: str = (
    "Extract code by exact line (and optional column) ranges. "
    "Supports a ``requests`` array so you can pull many "
    "non-contiguous slices — even from different files — in "
    "ONE call rather than one Read per slice. Returns the raw "
    "text plus line metadata; pair with ``analyze_code_structure`` "
    "or ``query_code`` first to discover the line numbers you "
    "want, then read just those ranges instead of the whole "
    "file.\n\n"
    "WHEN TO USE:\n"
    "- Reading a specific function/class body by known line "
    "range (e.g. lines 120-180)\n"
    "- Batch-extracting several functions across one or many "
    "files in a single MCP round-trip\n"
    "- Loading targeted context for an agent without paying "
    "the token cost of an entire file\n"
    "- Following up an outline / query result (jump straight "
    "to the lines that matter)\n"
    "\n"
    "WHEN NOT TO USE:\n"
    "- Reading an entire small file end-to-end — the built-in "
    "Read tool is simpler\n"
    "- Searching for a pattern when you don't know the line "
    "numbers — use ``search_content`` / ``find_and_grep``\n"
    "- Getting a structural overview (classes, methods, "
    "imports) — use ``get_code_outline`` /"
    " ``analyze_code_structure``"
)


def _check_col_value(col_value: Any, col_field: str) -> None:
    """Raise ValueError if *col_value* is not a valid column index."""
    if not isinstance(col_value, int):
        msg = f"{col_field} must be an integer"
        raise ValueError(msg)
    if col_value < 0:
        msg = f"{col_field} must be >= 0"
        raise ValueError(msg)


def _exc_dict(
    exc: Exception, project_root: str | None, file_path: str
) -> dict[str, Any]:
    """Build a canonical error envelope for an unexpected exception."""
    return {
        "success": False,
        "error": safe_error_message(exc, project_root),
        "file_path": file_path,
    }


def _count_lines(text: str) -> int:
    """Count lines in *text*; returns 0 for falsy input."""
    return len(text.splitlines()) if text else 0


def _range_dict(
    start_line: int,
    end_line: int | None,
    start_column: int | None,
    end_column: int | None,
) -> dict[str, Any]:
    """Build the nested ``range`` sub-dict for the response envelope."""
    return {
        "start_line": start_line,
        "end_line": end_line,
        "start_column": start_column,
        "end_column": end_column,
    }


def _set_clamped_to(result: dict[str, Any], clamped_to: list | None) -> None:
    """Write ``clamped_to`` into *result* only when it is not None."""
    if clamped_to is not None:
        result["clamped_to"] = clamped_to


def _check_requests_exclusivity(
    arguments: dict[str, Any], single_keys: list[str]
) -> None:
    """Raise if batch ``requests`` and single-read keys are mixed."""
    if any(k in arguments for k in single_keys):
        raise ValueError(
            "requests is mutually exclusive with "
            "file_path/start_line/end_line/start_column/end_column"
        )
    if not isinstance(arguments["requests"], list):
        raise ValueError("requests must be a list")


def _log_read_partial_error(file_path: str, exc: Exception) -> None:
    """Emit an error-level log for an unexpected read failure."""
    logger.error("Error reading partial content from %s: %s", file_path, exc)


def _validate_end_line(arguments: dict[str, Any]) -> None:
    """Validate ``end_line`` when present: type + range check."""
    if "end_line" not in arguments:
        return
    _validate_int_field(arguments, "end_line", min_val=1)
    end_val = arguments["end_line"]
    start_default = arguments.get("start_line", 0)
    if end_val < start_default:
        raise ValueError("end_line must be >= start_line")


def _validate_format(arguments: dict[str, Any]) -> None:
    """Validate the ``format`` field when present."""
    if "format" not in arguments:
        return
    val = arguments["format"]
    if not isinstance(val, str):
        raise ValueError("format must be a string")
    if val not in ("text", "json", "raw"):
        raise ValueError("format must be 'text', 'json', or 'raw'")


def _validate_suppress_output(arguments: dict[str, Any]) -> None:
    """Validate ``suppress_output`` is a bool when present."""
    if "suppress_output" not in arguments:
        return
    if not isinstance(arguments["suppress_output"], bool):
        raise ValueError("suppress_output must be a boolean")


def _validate_column_fields(arguments: dict[str, Any]) -> None:
    """Validate start_column and end_column fields."""
    for col_field in ["start_column", "end_column"]:
        if col_field in arguments:
            _check_col_value(arguments[col_field], col_field)


def _require_fields(arguments: dict[str, Any], fields: list[str]) -> None:
    for field in fields:
        if field not in arguments:
            msg = f"Required field '{field}' is missing"
            raise ValueError(msg)


def _validate_string_field(arguments: dict[str, Any], field: str) -> None:
    val = arguments.get(field)
    if val is not None:
        if not isinstance(val, str):
            msg = f"{field} must be a string"
            raise ValueError(msg)
        if not val.strip():
            msg = f"{field} cannot be empty"
            raise ValueError(msg)


def _validate_int_field(
    arguments: dict[str, Any], field: str, min_val: int = 0
) -> None:
    val = arguments.get(field)
    if val is not None:
        if not isinstance(val, int):
            msg = f"{field} must be an integer"
            raise ValueError(msg)
        if val < min_val:
            msg = f"{field} must be >= {min_val}"
            raise ValueError(msg)


def _read_failure_envelope(file_path: str) -> dict[str, Any]:
    """Build the canonical error envelope when ``file_handler`` returned None.

    Distinct from the empty-range / out-of-range responses — this is a
    genuine IO error or validation rejection, so ``success=False``.
    """
    return {
        "success": False,
        "error": f"Failed to read partial content from file: {file_path}",
        "file_path": file_path,
    }


def _compute_range_flags(
    content: str,
    file_lines: int | None,
    start_line: int,
    end_line: int | None,
) -> tuple[bool, bool, list[int] | None]:
    """K8: classify the range as ``out_of_range`` / ``partial_range``.

    Returns ``(out_of_range, partial_range, clamped_to)`` so callers can
    surface structured response flags instead of treating any empty read
    as a generic failure. Agents read these flags and recover with a
    valid range. ``clamped_to=[start_line, file_lines]`` is set only when
    ``partial_range`` is true (caller honours the file boundary).
    """
    has_file_lines = file_lines is not None
    has_end_line = end_line is not None
    file_lines_int: int = file_lines if file_lines is not None else 0
    end_line_int: int = end_line if end_line is not None else 0
    out_of_range = bool(
        content == "" and has_file_lines and start_line > file_lines_int
    )
    partial_range = bool(
        has_file_lines
        and has_end_line
        and start_line <= file_lines_int
        and end_line_int > file_lines_int
    )
    clamped_to: list[int] | None = (
        [start_line, file_lines_int] if partial_range and has_file_lines else None
    )
    return out_of_range, partial_range, clamped_to


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

        proj_root = self.project_root
        resolved_path = self.resolve_and_validate_file_path(file_path)
        log_msg = f"Reading partial content from {file_path}: lines {start_line}-{end_line or 'end'}"
        logger.info(log_msg)

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
            _log_read_partial_error(file_path, e)
            return _exc_dict(e, proj_root, file_path)

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
        """Read partial content and format the response.

        r37ex (dogfood): 87→~25 lines. Range-status math moved to
        ``_compute_range_flags``; the early-return error envelope moved to
        ``_read_failure_envelope``.
        """
        content = self._read_file_partial(
            resolved_path, start_line, end_line, start_column, end_column
        )
        if content is None:
            # file_handler returned None — genuine IO error or validation
            # rejection. Distinct from empty range (handled as out_of_range).
            return _read_failure_envelope(file_path)

        # K8: compute lines_extracted from the ACTUAL content. The old
        # ``end_line - start_line + 1`` formula lied when the requested
        # range was past EOF (content empty but lines_extracted=N).
        lines_extracted = _count_lines(content)
        file_lines = count_file_lines(resolved_path)
        out_of_range, partial_range, clamped_to = _compute_range_flags(
            content, file_lines, start_line, end_line
        )

        n_chars = len(content)
        logger.info(
            "Read %s characters from %s (out_of_range=%s, partial_range=%s)",
            n_chars,
            file_path,
            out_of_range,
            partial_range,
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
            file_lines=file_lines,
            out_of_range=out_of_range,
            partial_range=partial_range,
            clamped_to=clamped_to,
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
        proj_root = self.project_root
        # First check: is the file path valid and resolvable?
        try:
            self.resolve_and_validate_file_path(file_path)
        except ValueError as e:
            return _exc_dict(e, proj_root, file_path)

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
        *,
        file_lines: int | None = None,
        out_of_range: bool = False,
        partial_range: bool = False,
        clamped_to: list | None = None,
    ) -> dict[str, Any]:
        """Build the result dict with range metadata and optional formatted content."""
        result: dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "range": _range_dict(start_line, end_line, start_column, end_column),
            "content_length": len(content),
            "lines_extracted": lines_extracted,
            # Top-level ``content`` exposes the raw extracted slice. The
            # accompanying ``partial_content_result`` field below adds the
            # human-readable metadata header for display; callers that
            # just want the text read this field directly.
            "content": content,
        }
        if file_lines is not None:
            result["file_lines"] = file_lines
        if out_of_range:
            result["out_of_range"] = True
        if partial_range:
            result["partial_range"] = True
            _set_clamped_to(result, clamped_to)
        result["agent_summary"] = build_agent_summary_for_result(
            result, content_format, output_file, suppress_output
        )
        # Mirror ``summary_line`` at the top level so callers that scan
        # for the canonical envelope key see the actionable hint.
        summary_line = result["agent_summary"].get("summary_line")
        if summary_line:
            result["summary_line"] = summary_line
        # r37x (envelope ratchet): top-level verdict mirror (r37u contract).
        verdict = result["agent_summary"].get("verdict")
        if isinstance(verdict, str):
            result["verdict"] = verdict

        if end_line and end_line > start_line and not (out_of_range or partial_range):
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
        """Format extracted content as json or text with metadata header.

        r37dp (dogfood): thin delegation to ``format_partial_content``
        (lifted to ``read_partial_helpers``) so the class drops below the
        500-line god_class threshold.
        """
        return format_partial_content(
            content,
            content_format,
            file_path,
            start_line,
            end_line,
            start_column,
            end_column,
            lines_extracted,
        )

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
        """Format content as a JSON line array with metadata (delegates)."""
        return format_partial_content_as_json_lines(
            content,
            file_path,
            start_line,
            end_line,
            start_column,
            end_column,
            lines_extracted,
        )

    def _apply_file_output(
        self,
        result: dict[str, Any],
        file_path: str,
        content: str,
        content_format: str,
        output_format: str,
        output_file: str | None,
    ) -> None:
        """Write extracted content to a file (delegates to module helper)."""
        apply_partial_file_output(
            result=result,
            file_path=file_path,
            content=content,
            content_format=content_format,
            output_format=output_format,
            output_file=output_file,
            file_output_manager=self.file_output_manager,
            logger=logger,
        )

    def _prepare_save_content(
        self,
        content_format: str,
        content: str,
        result: dict[str, Any],
        file_path: str,
        output_format: str,
    ) -> str:
        """Prepare content for saving to file (delegates to module helper)."""
        return prepare_partial_save_content(
            content_format, content, result, file_path, output_format
        )

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
            _check_requests_exclusivity(arguments, single_keys)
            return True

        _require_fields(arguments, ["file_path", "start_line"])
        _validate_string_field(arguments, "file_path")
        _validate_int_field(arguments, "start_line", min_val=1)
        _validate_end_line(arguments)
        _validate_column_fields(arguments)
        _validate_format(arguments)
        if "output_file" in arguments:
            _validate_string_field(arguments, "output_file")
        _validate_suppress_output(arguments)
        return True

    # MCP tool metadata - name, description, schema
    # Tool name is extract_code_section for clarity in AI agent workflows
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "extract_code_section",
            "description": _TOOL_DESCRIPTION,
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }


# Tool instance for easy module-level access
read_partial_tool = ReadPartialTool()  # Tool instance for easy access
read_partial_tool = ReadPartialTool()
