"""
MCP Tool for deleting files and directories.

This module provides a tool for safe file and directory deletion with
support for recursive deletion and batch operations.
"""

import shutil
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class DeleteFileTool(BaseTool):
    """
    MCP tool for deleting files and directories.

    Provides safe deletion with options for recursive deletion and
    batch operations.
    """

    def get_name(self) -> str:
        """Get tool name."""
        return "delete_file"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Delete files or directories. Supports recursive deletion and batch operations. "
            "Use with caution as this operation cannot be undone."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file or directory to delete (for single deletion)",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of paths to delete (for batch deletion)",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Delete directories recursively (default: false)",
                    "default": False,
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Confirmation flag (default: true, must be true to delete)",
                    "default": True,
                },
            },
            "oneOf": [
                {"required": ["path"]},
                {"required": ["paths"]},
            ],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute delete_file tool.

        Args:
            arguments: Dictionary with:
                - path: Single file/directory path (or)
                - paths: List of paths for batch deletion
                - recursive: Delete directories recursively (default: False)
                - confirm: Confirmation flag (default: True)

        Returns:
            Dictionary with:
                - success: True if successful, False otherwise
                - path: Path that was deleted (for single deletion)
                - deleted_count: Number of items deleted (for batch deletion)
                - error: Error message (if success=False)
        """
        try:
            # Extract arguments
            single_path = arguments.get("path")
            paths = arguments.get("paths")
            recursive = arguments.get("recursive", False)
            confirm = arguments.get("confirm", True)

            # Require confirmation
            if not confirm:
                return {"success": False, "error": "Deletion requires confirmation (confirm=true)"}

            # Handle batch deletion
            if paths:
                return self._delete_multiple(paths, recursive)

            # Handle single deletion
            if single_path:
                return self._delete_single(single_path, recursive)

            return {"success": False, "error": "Must provide either 'path' or 'paths'"}

        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def _delete_single(self, path_str: str, recursive: bool) -> dict[str, Any]:
        """
        Delete a single file or directory.

        Args:
            path_str: Path to delete
            recursive: Whether to delete directories recursively

        Returns:
            Result dictionary
        """
        try:
            file_path = Path(path_str)

            # Check if path exists
            if not file_path.exists():
                return {"success": False, "error": f"Path does not exist: {path_str}"}

            # Handle directory
            if file_path.is_dir():
                # Check if directory is empty
                if not recursive and any(file_path.iterdir()):
                    return {
                        "success": False,
                        "error": f"Directory not empty. Use recursive=true to delete: {path_str}",
                    }

                # Delete directory
                if recursive:
                    shutil.rmtree(file_path)
                else:
                    file_path.rmdir()
            else:
                # Delete file
                file_path.unlink()

            return {"success": True, "path": str(file_path.absolute())}

        except PermissionError as e:
            return {"success": False, "error": f"Permission denied: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to delete: {str(e)}"}

    def _delete_multiple(self, paths: list[str], recursive: bool) -> dict[str, Any]:
        """
        Delete multiple files or directories.

        Args:
            paths: List of paths to delete
            recursive: Whether to delete directories recursively

        Returns:
            Result dictionary with deleted_count
        """
        deleted_count = 0
        errors = []

        for path_str in paths:
            result = self._delete_single(path_str, recursive)
            if result["success"]:
                deleted_count += 1
            else:
                errors.append(f"{path_str}: {result['error']}")

        if errors:
            return {
                "success": False,
                "deleted_count": deleted_count,
                "errors": errors,
                "error": f"Failed to delete {len(errors)} items",
            }

        return {"success": True, "deleted_count": deleted_count}
