"""
MCP Tool for replacing strings in files.

This module provides a tool for precise string replacement in files with safety checks.
"""

from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class ReplaceInFileTool(BaseTool):
    """
    MCP tool for replacing strings in files.

    Provides safe string replacement with options for single or multiple replacements.
    """

    def get_name(self) -> str:
        """Get tool name."""
        return "replace_in_file"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Replace string in a file. Can replace first occurrence or all occurrences. "
            "Use with caution as this modifies files."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to modify (absolute or relative)",
                },
                "old_string": {
                    "type": "string",
                    "description": "String to replace (must match exactly)",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement string",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false, replaces only first)",
                    "default": False,
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding (default: utf-8)",
                    "default": "utf-8",
                },
            },
            "required": ["path", "old_string", "new_string"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute replace_in_file tool.

        Args:
            arguments: Dictionary with:
                - path: File path to modify
                - old_string: String to replace
                - new_string: Replacement string
                - replace_all: Replace all occurrences (default: False)
                - encoding: File encoding (default: utf-8)

        Returns:
            Dictionary with:
                - success: True if successful, False otherwise
                - path: Path to the modified file (if success=True)
                - replacements: Number of replacements made (if success=True)
                - error: Error message (if success=False)
        """
        try:
            # Extract arguments
            path_str = arguments["path"]
            old_string = arguments["old_string"]
            new_string = arguments["new_string"]
            replace_all = arguments.get("replace_all", False)
            encoding = arguments.get("encoding", "utf-8")

            # Validate old_string is not empty
            if not old_string:
                return {"success": False, "error": "old_string cannot be empty"}

            # Convert to Path object
            file_path = Path(path_str)

            # Check if file exists
            if not file_path.exists():
                return {"success": False, "error": f"File does not exist: {path_str}"}

            # Read file content
            try:
                content = file_path.read_text(encoding=encoding)
            except Exception as e:
                return {"success": False, "error": f"Failed to read file: {str(e)}"}

            # Check if old_string exists in content
            if old_string not in content:
                return {"success": False, "error": f"String not found in file: {old_string}"}

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
                count = content.count(old_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
                count = 1

            # Write back to file
            try:
                file_path.write_text(new_content, encoding=encoding)
            except Exception as e:
                return {"success": False, "error": f"Failed to write file: {str(e)}"}

            return {
                "success": True,
                "path": str(file_path.absolute()),
                "replacements": count,
            }

        except Exception as e:
            # Unexpected errors
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
