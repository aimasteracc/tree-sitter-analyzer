#!/usr/bin/env python3
"""
Error Recovery Tool — MCP Tool

Provides graceful degradation for analyzing problematic files.
Detects encoding, handles binary files, and provides regex fallback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.error_recovery import ErrorRecovery, detect_encoding
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ErrorRecoveryTool(BaseMCPTool):
    """
    MCP tool for analyzing files with error recovery.

    When tree-sitter parsing fails, provides regex-based fallback.
    Detects file encodings including CJK (Chinese, Japanese, Korean).
    Identifies binary files to avoid processing errors.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "error_recovery",
            "description": (
                "Analyze files with graceful error recovery. "
                "Handles encoding issues, binary files, and parsing failures.\n\n"
                "Capabilities:\n"
                "- Encoding detection: UTF-8, GBK, Shift-JIS, EUC-JP, EUC-KR, Big5\n"
                "- Binary file detection: avoids processing non-text files\n"
                "- Regex fallback: extracts structure when tree-sitter fails\n"
                "- Multi-language: Python, Go, C#, Kotlin, Rust regex patterns\n\n"
                "WHEN TO USE:\n"
                "- When files contain encoding errors or mixed encodings\n"
                "- When tree-sitter parsing fails with syntax errors\n"
                "- To detect whether a file is binary before processing\n"
                "- To analyze files with non-UTF-8 encodings (CJK files)\n\n"
                "WHEN NOT TO USE:\n"
                "- For normal file analysis (use query_code or analyze_code_structure)\n"
                "- For dependency queries (use dependency_query)\n"
                "- For syntax highlighting (use language-specific formatters)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to analyze.",
                    },
                    "detect_encoding_only": {
                        "type": "boolean",
                        "description": (
                            "Only detect encoding without full analysis. "
                            "Default: false."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "File content as string. If provided, used instead of reading file_path. "
                            "Useful when file content is already available."
                        ),
                    },
                },
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments."""
        file_path = arguments.get("file_path")
        if file_path is not None and not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

        detect_only = arguments.get("detect_encoding_only")
        if detect_only is not None and not isinstance(detect_only, bool):
            raise ValueError("detect_encoding_only must be a boolean")

        content = arguments.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("content must be a string")

        return True

    @handle_mcp_errors("error_recovery")
    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """Execute error recovery analysis."""
        file_path: str | None = args.get("file_path")
        detect_only: bool = args.get("detect_encoding_only", False)
        content: str | None = args.get("content")

        if not file_path:
            return {
                "success": False,
                "error": "file_path is required",
                "recovery_mode": False,
            }

        path = Path(file_path)
        if not path.is_absolute() and self.project_root:
            path = Path(self.project_root) / path

        # Encoding-only mode
        if detect_only:
            if content:
                bytes_content = content.encode("utf-8")
            else:
                bytes_content = path.read_bytes()

            encoding, had_bom = detect_encoding(bytes_content)
            return {
                "success": True,
                "file_path": str(path),
                "encoding": encoding,
                "had_bom": had_bom,
                "recovery_mode": False,
            }

        # Full recovery analysis
        # Use current directory as project_root if not set
        project_root = self.project_root or str(Path.cwd())
        recovery = ErrorRecovery(project_root=project_root)
        result = recovery.analyze_with_fallback(str(path))

        return result
