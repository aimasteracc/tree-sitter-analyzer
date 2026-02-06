"""
MCP Tool for writing files.

This module provides a tool for writing content to files with safety checks.
"""

from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class WriteFileTool(BaseTool):
    """
    MCP tool for writing content to files.

    Provides safe file writing with automatic directory creation and
    proper error handling.
    """

    def get_name(self) -> str:
        """Get tool name."""
        return "write_file"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Write contents to a file. Creates parent directories if needed. "
            "Overwrites existing files. Use with caution."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write (absolute or relative)",
                },
                "contents": {
                    "type": "string",
                    "description": "Contents to write to the file",
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding (default: utf-8)",
                    "default": "utf-8",
                },
            },
            "required": ["path", "contents"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute write_file tool.

        Args:
            arguments: Dictionary with:
                - path: File path to write
                - contents: Content to write
                - encoding: File encoding (default: utf-8)

        Returns:
            Dictionary with:
                - success: True if successful, False otherwise
                - path: Path to the written file (if success=True)
                - error: Error message (if success=False)
        """
        try:
            # Extract arguments
            path_str = arguments["path"]
            contents = arguments["contents"]
            encoding = arguments.get("encoding", "utf-8")

            # Convert to Path object
            file_path = Path(path_str)

            # Create parent directories if they don't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            file_path.write_text(contents, encoding=encoding)

            return {"success": True, "path": str(file_path.absolute())}

        except OSError as e:
            # File system errors (permission denied, disk full, etc.)
            return {"success": False, "error": f"Failed to write file: {str(e)}"}
        except Exception as e:
            # Unexpected errors
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
