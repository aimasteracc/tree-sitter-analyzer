"""
MCP Tool for extracting code sections by line range.

This module provides the extract_code_section tool that extracts specific
code sections from files using line ranges with automatic encoding detection.

Supports both single-file and batch modes with safety limits.
"""

from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.config import DEFAULT_CONFIG
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

# Backward-compatible alias — reads from centralized config
BATCH_LIMITS = DEFAULT_CONFIG.batch.to_dict()


class ExtractCodeSectionTool(BaseTool):
    """
    MCP tool for extracting code sections by line range.

    Enhanced version matching v1's ReadPartialTool:
    - Single & batch modes
    - Line-based extraction (no columns for simplicity)
    - TOON/Markdown output formats
    - Automatic encoding detection
    - Safety limits for batch operations
    """

    def __init__(self) -> None:
        """Initialize the extract code section tool."""
        self._encoding_detector = EncodingDetector()

    def get_name(self) -> str:
        """Get tool name."""
        return "extract_code_section"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Extract specific code sections by line range with single or batch mode. "
            "Single mode: extract from one file. "
            "Batch mode: extract multiple sections from multiple files in one call. "
            "Automatic encoding detection for multi-language files (Japanese, Chinese, etc.)."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                # Single mode parameters
                "file_path": {
                    "type": "string",
                    "description": "Single mode: Path to the code file to read. Example: 'src/main.py'",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Single mode: Starting line number (1-based). Example: 10",
                    "minimum": 1,
                },
                "end_line": {
                    "type": "integer",
                    "description": "Single mode: Ending line number (1-based, optional - reads to end if not specified). Example: 20",
                    "minimum": 1,
                },
                # Batch mode parameters
                "requests": {
                    "type": "array",
                    "description": "Batch mode: Extract multiple sections from multiple files (mutually exclusive with file_path/start_line)",
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
                                },
                            },
                        },
                        "required": ["file_path", "sections"],
                    },
                },
                # Common parameters
                "output_format": {
                    "type": "string",
                    "enum": ["toon", "markdown"],
                    "description": "Output format: 'toon' (default, token-optimized) or 'markdown' (human-readable)",
                    "default": "toon",
                },
                # Token protection parameters
                "suppress_content": {
                    "type": "boolean",
                    "description": "Return only metadata without content to save tokens (useful for large files)",
                    "default": False,
                },
                "max_content_length": {
                    "type": "integer",
                    "description": "Maximum content length in characters (truncate if exceeded to prevent token explosion)",
                    "minimum": 100,
                },
                # Batch mode control
                "allow_truncate": {
                    "type": "boolean",
                    "description": "Batch mode: allow truncating results to fit limits (default: false)",
                    "default": False,
                },
                "fail_fast": {
                    "type": "boolean",
                    "description": "Batch mode: stop on first error (default: false, partial success)",
                    "default": False,
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute the extract_code_section tool (delegates to single or batch)."""
        if "requests" in arguments and arguments["requests"] is not None:
            return self._execute_batch(arguments)
        return self._execute_single(arguments)

    # ── Single-mode execution ──

    def _execute_single(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute single-file extraction."""
        file_path = arguments.get("file_path", "")
        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")
        output_format = arguments.get("output_format", "toon")
        suppress_content = arguments.get("suppress_content", False)
        max_content_length = arguments.get("max_content_length")

        # Validate required arguments
        if err := self._validate_single_args(file_path, start_line, end_line):
            return err

        # Resolve & validate file
        file_path_obj = Path(file_path).resolve()
        if err := self._validate_file_exists(file_path, file_path_obj):
            return err

        try:
            content = self._extract_lines(file_path_obj, start_line, end_line)
            with open(file_path_obj, encoding="utf-8", errors="replace") as f:
                total_lines = len(f.readlines())

            actual_end_line = end_line if end_line is not None else total_lines
            lines_extracted = (end_line - start_line + 1) if end_line else len(content.splitlines())
            original_length = len(content)

            content, was_truncated = self._apply_truncation(content, max_content_length)

            return self._build_single_result(
                file_path, start_line, actual_end_line, lines_extracted,
                original_length, content, was_truncated, suppress_content,
                output_format, file_path_obj,
            )
        except ValueError as e:
            return self._error(str(e), error_code="INVALID_ARGUMENT")
        except Exception as e:
            return self._error(f"Failed to extract code: {e}", error_code="EXTRACTION_ERROR")

    @staticmethod
    def _validate_single_args(
        file_path: str, start_line: int | None, end_line: int | None,
    ) -> dict[str, Any] | None:
        """Validate single-mode arguments. Returns error dict or None."""
        if not file_path:
            return BaseTool._error("file_path is required", error_code="INVALID_ARGUMENT")
        if start_line is None:
            return BaseTool._error("start_line is required", error_code="INVALID_ARGUMENT")
        if start_line < 1:
            return BaseTool._error("start_line must be >= 1", error_code="INVALID_ARGUMENT")
        if end_line is not None and end_line < start_line:
            return BaseTool._error("end_line must be >= start_line", error_code="INVALID_ARGUMENT")
        return None

    @staticmethod
    def _validate_file_exists(file_path: str, file_path_obj: Path) -> dict[str, Any] | None:
        """Validate file exists and is a regular file. Returns error dict or None."""
        if not file_path_obj.exists():
            return BaseTool._error(f"File not found: {file_path}", error_code="FILE_NOT_FOUND")
        if not file_path_obj.is_file():
            return BaseTool._error(f"Not a file: {file_path}", error_code="INVALID_ARGUMENT")
        return None

    @staticmethod
    def _apply_truncation(
        content: str, max_content_length: int | None,
    ) -> tuple[str, bool]:
        """Apply token-protection truncation. Returns (content, was_truncated)."""
        if max_content_length and len(content) > max_content_length:
            return content[:max_content_length] + "\n... [truncated]", True
        return content, False

    def _build_single_result(
        self, file_path: str, start_line: int, end_line: int,
        lines_extracted: int, original_length: int, content: str,
        was_truncated: bool, suppress_content: bool,
        output_format: str, file_path_obj: Path,
    ) -> dict[str, Any]:
        """Build the result dict for single-mode extraction."""
        if output_format == "markdown":
            lang = self._detect_syntax_lang(file_path_obj)
            md = (
                f"# Code Section Extract\n\n"
                f"**File**: `{file_path}`\n"
                f"**Range**: Line {start_line}-{end_line}\n"
                f"**Lines**: {lines_extracted}\n"
                f"**Size**: {original_length} characters\n\n"
                f"```{lang}\n{content}```\n"
            )
            return {"success": True, "data": md, "output_format": "markdown"}

        # TOON format (default)
        result: dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "range": {"start_line": start_line, "end_line": end_line},
            "lines_extracted": lines_extracted,
            "content_length": original_length,
            "output_format": output_format,
        }
        if not suppress_content:
            result["content"] = content
            if was_truncated:
                result["truncated"] = True
                result["truncated_length"] = len(content)
        else:
            result["content_suppressed"] = True
        return result

    @staticmethod
    def _detect_syntax_lang(file_path_obj: Path) -> str:
        """Detect syntax-highlighting language from file extension."""
        ext = file_path_obj.suffix.lstrip(".")
        lang_map = {
            "py": "python", "js": "javascript", "ts": "typescript",
            "java": "java", "cpp": "cpp", "c": "c", "rs": "rust",
            "go": "go", "rb": "ruby", "php": "php", "cs": "csharp",
        }
        return lang_map.get(ext, ext or "text")

    def _extract_lines(self, file_path: Path, start_line: int, end_line: int | None) -> str:
        """
        Extract lines from file using encoding detection.

        Args:
            file_path: Path to file
            start_line: Starting line (1-based)
            end_line: Ending line (1-based, optional)

        Returns:
            Extracted content as string

        Raises:
            ValueError: If line range is invalid
        """
        # Detect encoding
        encoding = self._encoding_detector.detect_encoding(file_path)

        # Read file with detected encoding
        with open(file_path, encoding=encoding, errors="replace") as f:
            lines = f.readlines()

        # Get total lines
        total_lines = len(lines)

        # Validate start_line
        if start_line > total_lines:
            raise ValueError(f"start_line {start_line} exceeds file length {total_lines}")

        # Convert to 0-indexed
        start_idx = start_line - 1

        # Determine end index
        if end_line is None:
            # Read to end of file
            end_idx = total_lines
        else:
            # Clamp end_line to file length
            end_idx = total_lines if end_line > total_lines else end_line

        # Extract range
        extracted_lines = lines[start_idx:end_idx]

        # Join and return
        return "".join(extracted_lines)

    def _execute_batch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute batch mode for extracting multiple sections from multiple files.

        Args:
            arguments: Contains:
                - requests: List of {file_path, sections: [{start_line, end_line, label}]}
                - output_format: 'toon' or 'markdown'
                - allow_truncate: Allow truncating to fit limits
                - fail_fast: Stop on first error

        Returns:
            Dict containing:
                - success: Whether any sections succeeded
                - count_files: Number of files processed
                - count_sections: Number of successful sections
                - truncated: Whether results were truncated
                - limits: Batch limits used
                - errors_summary: Error count
                - results: List of file results
        """
        output_format = arguments.get("output_format", "toon")
        allow_truncate = arguments.get("allow_truncate", False)
        fail_fast = arguments.get("fail_fast", False)
        requests = arguments.get("requests", [])

        # Phase 1: Validate top-level constraints
        validation_err = self._validate_batch_args(arguments, requests)
        if validation_err is not None:
            return validation_err

        # Enforce max_files limit
        truncated = False
        if len(requests) > BATCH_LIMITS["max_files"]:
            if not allow_truncate:
                return self._error(
                    f"Too many files: {len(requests)} > max_files={BATCH_LIMITS['max_files']}",
                    error_code="LIMIT_EXCEEDED",
                )
            requests = requests[: BATCH_LIMITS["max_files"]]
            truncated = True

        # Phase 2: Process each file request
        results: list[dict[str, Any]] = []
        total_bytes = 0
        total_lines = 0
        ok_sections = 0
        sections_seen_total = 0
        error_count = 0

        for file_req in requests:
            file_result, file_err = self._validate_file_request(
                file_req, fail_fast, allow_truncate
            )
            if file_err is not None:
                if isinstance(file_err, dict) and file_err.get("success") is False:
                    return file_err  # fail_fast early exit
                results.append(file_err)
                error_count += 1
                continue
            if file_result is None:
                continue  # shouldn't happen

            file_path = file_result["file_path"]
            sections = file_result["sections"]
            file_path_obj = file_result["file_path_obj"]
            if file_result.get("truncated"):
                truncated = True

            # Phase 3: Process sections for this file
            out = {"file_path": file_path, "sections": [], "errors": []}
            section_break = False

            for sec in sections:
                sec_result = self._process_section(
                    sec, file_path_obj, fail_fast, allow_truncate,
                    sections_seen_total, total_bytes, total_lines,
                )
                sections_seen_total = sec_result["sections_seen_total"]

                if sec_result.get("early_return"):
                    return sec_result["early_return"]

                if sec_result.get("error"):
                    error_count += 1
                    out["errors"].append(sec_result["error"])
                    if sec_result.get("break"):
                        section_break = True
                        break
                    continue

                if sec_result.get("truncated"):
                    truncated = True
                    section_break = True
                    break

                # Accumulate
                total_bytes = sec_result["total_bytes"]
                total_lines = sec_result["total_lines"]
                ok_sections += 1
                out["sections"].append(sec_result["section"])

            results.append(out)
            if section_break and fail_fast:
                break

        return {
            "success": ok_sections > 0,
            "count_files": len(results),
            "count_sections": ok_sections,
            "truncated": truncated,
            "limits": BATCH_LIMITS,
            "errors_summary": {"errors": error_count},
            "results": results,
            "output_format": output_format,
        }

    # ── Batch helper: validate top-level args ──

    def _validate_batch_args(
        self,
        arguments: dict[str, Any],
        requests: Any,
    ) -> dict[str, Any] | None:
        """Validate batch-level constraints. Returns error dict or None if valid."""
        if any(k in arguments for k in ["file_path", "start_line", "end_line"]):
            return self._error(
                "requests is mutually exclusive with file_path/start_line/end_line",
                error_code="INVALID_ARGUMENT",
            )
        if not isinstance(requests, list):
            return self._error("requests must be a list", error_code="INVALID_ARGUMENT")
        return None

    # ── Batch helper: validate & resolve a single file request ──

    def _validate_file_request(
        self,
        file_req: Any,
        fail_fast: bool,
        allow_truncate: bool,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Validate a single file request entry.

        Returns:
            (parsed_info, error_entry) — one will be None.
            If fail_fast triggers, error_entry is a full _error() response.
        """
        if not isinstance(file_req, dict):
            if fail_fast:
                return None, self._error("Invalid request entry", error_code="INVALID_ARGUMENT")
            return None, {"file_path": "", "sections": [], "errors": [{"error": "Invalid request entry"}]}

        file_path = file_req.get("file_path")
        sections = file_req.get("sections")

        if not file_path or not sections:
            if fail_fast:
                return None, self._error("file_path and sections required", error_code="INVALID_ARGUMENT")
            return None, {"file_path": file_path or "", "sections": [], "errors": [{"error": "file_path and sections required"}]}

        truncated = False
        if len(sections) > BATCH_LIMITS["max_sections_per_file"]:
            if not allow_truncate:
                if fail_fast:
                    return None, self._error(f"Too many sections for file {file_path}", error_code="LIMIT_EXCEEDED")
                return None, {"file_path": file_path, "sections": [], "errors": [{"error": "Too many sections"}]}
            sections = sections[: BATCH_LIMITS["max_sections_per_file"]]
            truncated = True

        file_path_obj = Path(file_path).resolve()
        if not file_path_obj.exists() or not file_path_obj.is_file():
            if fail_fast:
                return None, self._error(f"File not found: {file_path}", error_code="FILE_NOT_FOUND")
            return None, {"file_path": file_path, "sections": [], "errors": [{"error": "File not found"}]}

        file_size = file_path_obj.stat().st_size
        if file_size > BATCH_LIMITS["max_file_size_bytes"]:
            if fail_fast:
                return None, self._error(f"File too large: {file_path}", error_code="LIMIT_EXCEEDED")
            return None, {"file_path": file_path, "sections": [], "errors": [{"error": "File too large"}]}

        return {
            "file_path": file_path,
            "sections": sections,
            "file_path_obj": file_path_obj,
            "truncated": truncated,
        }, None

    # ── Batch helper: process a single section ──

    def _process_section(
        self,
        sec: Any,
        file_path_obj: Path,
        fail_fast: bool,
        allow_truncate: bool,
        sections_seen_total: int,
        total_bytes: int,
        total_lines: int,
    ) -> dict[str, Any]:
        """Process one section entry. Returns a status dict."""
        result: dict[str, Any] = {"sections_seen_total": sections_seen_total}

        if not isinstance(sec, dict):
            result["error"] = {"error": "Invalid section"}
            result["break"] = fail_fast
            return result

        label = sec.get("label")
        start_line = sec.get("start_line")
        end_line = sec.get("end_line")

        if not start_line or start_line < 1:
            result["error"] = {"label": label, "error": "start_line must be >= 1"}
            result["break"] = fail_fast
            return result

        if end_line and end_line < start_line:
            result["error"] = {"label": label, "error": "end_line must be >= start_line"}
            result["break"] = fail_fast
            return result

        result["sections_seen_total"] = sections_seen_total + 1
        if result["sections_seen_total"] > BATCH_LIMITS["max_sections_total"]:
            if not allow_truncate:
                result["early_return"] = self._error(
                    f"Too many sections total: > {BATCH_LIMITS['max_sections_total']}",
                    error_code="LIMIT_EXCEEDED",
                )
                return result
            result["truncated"] = True
            return result

        try:
            content = self._extract_lines(file_path_obj, start_line, end_line)
        except Exception as e:
            result["error"] = {"label": label, "error": str(e)}
            result["break"] = fail_fast
            return result

        if not content or content.strip() == "":
            result["error"] = {"label": label, "error": "Empty content or invalid range"}
            result["break"] = fail_fast
            return result

        content_bytes = len(content.encode("utf-8"))
        content_lines = len(content.splitlines())
        would_bytes = total_bytes + content_bytes
        would_lines = total_lines + content_lines

        if would_bytes > BATCH_LIMITS["max_total_bytes"] or would_lines > BATCH_LIMITS["max_total_lines"]:
            if not allow_truncate:
                result["early_return"] = self._error("Batch extract exceeds total limits", error_code="LIMIT_EXCEEDED")
                return result
            result["truncated"] = True
            return result

        result["total_bytes"] = would_bytes
        result["total_lines"] = would_lines
        result["section"] = {
            "label": label,
            "range": {"start_line": start_line, "end_line": end_line},
            "content_length": len(content),
            "content": content,
        }
        return result
