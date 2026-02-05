"""
MCP Tool for extracting code sections by line range.

This module provides the extract_code_section tool that extracts specific
code sections from files using line ranges with automatic encoding detection.

Supports both single-file and batch modes with safety limits.
"""

from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

# Safety limits for batch mode
BATCH_LIMITS = {
    "max_files": 20,  # Maximum files per batch
    "max_sections_per_file": 50,  # Maximum sections per file
    "max_sections_total": 200,  # Total sections across all files
    "max_total_bytes": 1024 * 1024,  # 1 MiB total content
    "max_total_lines": 5000,  # Total lines across all sections
    "max_file_size_bytes": 5 * 1024 * 1024,  # 5 MiB per file
}


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

    def __init__(self):
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

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get the MCP tool definition for extract_code_section.

        Returns:
            Tool definition dictionary compatible with MCP server
        """
        return {
            "name": self.get_name(),
            "description": self.get_description(),
            "inputSchema": self.get_schema(),
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the extract_code_section tool.

        Args:
            arguments: Tool arguments containing:
                Single mode:
                - file_path: Path to file
                - start_line: Starting line (1-based)
                - end_line: Ending line (1-based, optional)

                Batch mode:
                - requests: List of {file_path, sections: [{start_line, end_line, label}]}

                Common:
                - output_format: 'toon' or 'markdown'
                - suppress_content: Only return metadata (token protection)
                - max_content_length: Truncate content (token protection)
                - allow_truncate: Allow result truncation (batch)
                - fail_fast: Stop on first error (batch)

        Returns:
            Single mode:
                - success, file_path, range, lines_extracted, content_length, content, output_format

            Batch mode:
                - success, count_files, count_sections, truncated, limits, results
        """
        # Check for batch mode
        if "requests" in arguments and arguments["requests"] is not None:
            return self._execute_batch(arguments)

        # Single mode
        file_path = arguments.get("file_path", "")
        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")
        output_format = arguments.get("output_format", "toon")
        suppress_content = arguments.get("suppress_content", False)
        max_content_length = arguments.get("max_content_length")

        # Validate required arguments
        if not file_path:
            return {"success": False, "error": "file_path is required"}

        if start_line is None:
            return {"success": False, "error": "start_line is required"}

        # Validate start_line
        if start_line < 1:
            return {"success": False, "error": "start_line must be >= 1"}

        # Validate end_line if provided
        if end_line is not None and end_line < start_line:
            return {"success": False, "error": "end_line must be >= start_line"}

        # Resolve file path
        file_path_obj = Path(file_path).resolve()

        # Check file exists
        if not file_path_obj.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        # Check it's a file
        if not file_path_obj.is_file():
            return {"success": False, "error": f"Not a file: {file_path}"}

        try:
            # Extract content
            content = self._extract_lines(file_path_obj, start_line, end_line)

            # Get total lines to determine actual end_line
            with open(file_path_obj, encoding="utf-8", errors="replace") as f:
                total_lines = len(f.readlines())

            # Calculate actual end_line if not specified
            actual_end_line = end_line if end_line is not None else total_lines

            # Calculate metadata
            lines_extracted = len(content.splitlines())
            if end_line:
                lines_extracted = end_line - start_line + 1

            original_length = len(content)
            was_truncated = False

            # Token protection: truncate if needed
            if max_content_length and len(content) > max_content_length:
                content = content[:max_content_length] + "\n... [truncated]"
                was_truncated = True

            # Build result based on output format
            if output_format == "markdown":
                # Format as markdown
                # Detect language from file extension for syntax highlighting
                ext = file_path_obj.suffix.lstrip(".")
                lang_map = {
                    "py": "python",
                    "js": "javascript",
                    "ts": "typescript",
                    "java": "java",
                    "cpp": "cpp",
                    "c": "c",
                    "rs": "rust",
                    "go": "go",
                    "rb": "ruby",
                    "php": "php",
                    "cs": "csharp",
                }
                lang = lang_map.get(ext, ext or "text")

                markdown_content = f"""# Code Section Extract

**File**: `{file_path}`
**Range**: Line {start_line}-{actual_end_line}
**Lines**: {lines_extracted}
**Size**: {original_length} characters

```{lang}
{content}```
"""
                result = {"success": True, "data": markdown_content, "output_format": "markdown"}
            else:
                # TOON format (default)
                result = {
                    "success": True,
                    "file_path": file_path,
                    "range": {"start_line": start_line, "end_line": actual_end_line},
                    "lines_extracted": lines_extracted,
                    "content_length": original_length,
                    "output_format": output_format,
                }

                # Token protection: suppress content if requested
                if not suppress_content:
                    result["content"] = content
                    if was_truncated:
                        result["truncated"] = True
                        result["truncated_length"] = len(content)
                else:
                    result["content_suppressed"] = True

            return result

        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Failed to extract code: {str(e)}"}

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
            # Validate end_line doesn't exceed file length
            if end_line > total_lines:
                # Clamp to file length
                end_idx = total_lines
            else:
                end_idx = end_line  # 1-indexed end_line becomes exclusive upper bound

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

        # Validate mutually exclusive with single mode
        if any(k in arguments for k in ["file_path", "start_line", "end_line"]):
            return {
                "success": False,
                "error": "requests is mutually exclusive with file_path/start_line/end_line",
            }

        if not isinstance(requests, list):
            return {"success": False, "error": "requests must be a list"}

        # Enforce max_files limit
        truncated = False
        if len(requests) > BATCH_LIMITS["max_files"]:
            if not allow_truncate:
                return {
                    "success": False,
                    "error": f"Too many files: {len(requests)} > max_files={BATCH_LIMITS['max_files']}",
                }
            requests = requests[: BATCH_LIMITS["max_files"]]
            truncated = True

        results = []
        total_bytes = 0
        total_lines = 0
        ok_sections = 0
        sections_seen_total = 0
        error_count = 0

        for file_req in requests:
            if not isinstance(file_req, dict):
                if fail_fast:
                    return {"success": False, "error": "Invalid request entry"}
                results.append(
                    {
                        "file_path": "",
                        "sections": [],
                        "errors": [{"error": "Invalid request entry"}],
                    }
                )
                error_count += 1
                continue

            file_path = file_req.get("file_path")
            sections = file_req.get("sections")

            if not file_path or not sections:
                if fail_fast:
                    return {"success": False, "error": "file_path and sections required"}
                results.append(
                    {
                        "file_path": file_path or "",
                        "sections": [],
                        "errors": [{"error": "file_path and sections required"}],
                    }
                )
                error_count += 1
                continue

            # Enforce max_sections_per_file
            if len(sections) > BATCH_LIMITS["max_sections_per_file"]:
                if not allow_truncate:
                    if fail_fast:
                        return {
                            "success": False,
                            "error": f"Too many sections for file {file_path}",
                        }
                    results.append(
                        {
                            "file_path": file_path,
                            "sections": [],
                            "errors": [{"error": "Too many sections"}],
                        }
                    )
                    error_count += 1
                    continue
                sections = sections[: BATCH_LIMITS["max_sections_per_file"]]
                truncated = True

            # Resolve and validate file
            file_path_obj = Path(file_path).resolve()
            if not file_path_obj.exists() or not file_path_obj.is_file():
                if fail_fast:
                    return {"success": False, "error": f"File not found: {file_path}"}
                results.append(
                    {
                        "file_path": file_path,
                        "sections": [],
                        "errors": [{"error": "File not found"}],
                    }
                )
                error_count += 1
                continue

            # Check file size
            file_size = file_path_obj.stat().st_size
            if file_size > BATCH_LIMITS["max_file_size_bytes"]:
                if fail_fast:
                    return {"success": False, "error": f"File too large: {file_path}"}
                results.append(
                    {
                        "file_path": file_path,
                        "sections": [],
                        "errors": [{"error": "File too large"}],
                    }
                )
                error_count += 1
                continue

            file_result = {"file_path": file_path, "sections": [], "errors": []}

            for sec in sections:
                if not isinstance(sec, dict):
                    error_count += 1
                    file_result["errors"].append({"error": "Invalid section"})
                    if fail_fast:
                        break
                    continue

                label = sec.get("label")
                start_line = sec.get("start_line")
                end_line = sec.get("end_line")

                if not start_line or start_line < 1:
                    error_count += 1
                    file_result["errors"].append(
                        {"label": label, "error": "start_line must be >= 1"}
                    )
                    if fail_fast:
                        break
                    continue

                if end_line and end_line < start_line:
                    error_count += 1
                    file_result["errors"].append(
                        {"label": label, "error": "end_line must be >= start_line"}
                    )
                    if fail_fast:
                        break
                    continue

                # Enforce global section count
                sections_seen_total += 1
                if sections_seen_total > BATCH_LIMITS["max_sections_total"]:
                    if not allow_truncate:
                        return {
                            "success": False,
                            "error": f"Too many sections total: > {BATCH_LIMITS['max_sections_total']}",
                        }
                    truncated = True
                    break

                # Extract content
                try:
                    content = self._extract_lines(file_path_obj, start_line, end_line)
                except Exception as e:
                    error_count += 1
                    file_result["errors"].append({"label": label, "error": str(e)})
                    if fail_fast:
                        break
                    continue

                if not content or content.strip() == "":
                    error_count += 1
                    file_result["errors"].append(
                        {"label": label, "error": "Empty content or invalid range"}
                    )
                    if fail_fast:
                        break
                    continue

                content_bytes = len(content.encode("utf-8"))
                content_lines = len(content.splitlines())

                # Enforce total limits
                would_bytes = total_bytes + content_bytes
                would_lines = total_lines + content_lines

                if (
                    would_bytes > BATCH_LIMITS["max_total_bytes"]
                    or would_lines > BATCH_LIMITS["max_total_lines"]
                ):
                    if not allow_truncate:
                        return {"success": False, "error": "Batch extract exceeds total limits"}
                    truncated = True
                    break

                total_bytes = would_bytes
                total_lines = would_lines
                ok_sections += 1

                # Store section result
                section_result = {
                    "label": label,
                    "range": {"start_line": start_line, "end_line": end_line},
                    "content_length": len(content),
                    "content": content,
                }

                file_result["sections"].append(section_result)

            results.append(file_result)

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
