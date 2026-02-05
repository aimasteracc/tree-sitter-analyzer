"""
MCP Tool for code refactoring operations.

This module provides tools for safe code refactoring including symbol renaming,
code extraction, and code movement.
"""

import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class RefactorRenameTool(BaseTool):
    """
    MCP tool for renaming symbols (functions, classes, variables).

    Supports single-file and cross-file renaming with intelligent symbol detection.
    """

    def get_name(self) -> str:
        """Get tool name."""
        return "refactor_rename"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Rename symbols (functions, classes, variables) across files. "
            "Supports single-file and cross-file renaming with intelligent detection."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Single file to rename symbol in (for single-file rename)",
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to search for cross-file renames",
                },
                "symbol_type": {
                    "type": "string",
                    "enum": ["function", "class", "variable", "method"],
                    "description": "Type of symbol to rename",
                },
                "old_name": {
                    "type": "string",
                    "description": "Current symbol name",
                },
                "new_name": {
                    "type": "string",
                    "description": "New symbol name",
                },
            },
            "required": ["symbol_type", "old_name", "new_name"],
            "oneOf": [
                {"required": ["file_path"]},
                {"required": ["directory"]},
            ],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute refactor_rename tool.

        Args:
            arguments: Dictionary with rename parameters

        Returns:
            Dictionary with success status and statistics
        """
        try:
            symbol_type = arguments["symbol_type"]
            old_name = arguments["old_name"]
            new_name = arguments["new_name"]
            file_path = arguments.get("file_path")
            directory = arguments.get("directory")

            # Validate names
            if not self._is_valid_identifier(old_name):
                return {"success": False, "error": f"Invalid old name: {old_name}"}
            if not self._is_valid_identifier(new_name):
                return {"success": False, "error": f"Invalid new name: {new_name}"}

            # Handle single-file rename
            if file_path:
                return self._rename_in_file(file_path, symbol_type, old_name, new_name)

            # Handle cross-file rename
            if directory:
                return self._rename_in_directory(directory, symbol_type, old_name, new_name)

            return {"success": False, "error": "Must provide either file_path or directory"}

        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def _is_valid_identifier(self, name: str) -> bool:
        """Check if name is a valid Python identifier."""
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))

    def _rename_in_file(
        self, file_path: str, symbol_type: str, old_name: str, new_name: str
    ) -> dict[str, Any]:
        """Rename symbol in a single file."""
        try:
            path = Path(file_path)
            if not path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}

            content = path.read_text(encoding="utf-8")

            # Build regex pattern based on symbol type
            if symbol_type == "function":
                # Match function definitions and calls
                pattern = rf'\b{re.escape(old_name)}\b'
            elif symbol_type == "class":
                # Match class definitions and instantiations
                pattern = rf'\b{re.escape(old_name)}\b'
            elif symbol_type == "variable":
                # Match variable names
                pattern = rf'\b{re.escape(old_name)}\b'
            elif symbol_type == "method":
                # Match method names
                pattern = rf'\b{re.escape(old_name)}\b'
            else:
                return {"success": False, "error": f"Unknown symbol type: {symbol_type}"}

            # Perform replacement
            new_content, count = re.subn(pattern, new_name, content)

            if count == 0:
                return {"success": False, "error": f"Symbol '{old_name}' not found"}

            # Write back
            path.write_text(new_content, encoding="utf-8")

            return {
                "success": True,
                "file": str(path.absolute()),
                "replacements": count,
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to rename: {str(e)}"}

    def _rename_in_directory(
        self, directory: str, symbol_type: str, old_name: str, new_name: str
    ) -> dict[str, Any]:
        """Rename symbol across all files in directory."""
        try:
            dir_path = Path(directory)
            if not dir_path.exists():
                return {"success": False, "error": f"Directory not found: {directory}"}

            # Find all Python files
            py_files = list(dir_path.rglob("*.py"))

            files_modified = 0
            total_replacements = 0
            errors = []

            # Build regex pattern
            pattern = rf'\b{re.escape(old_name)}\b'

            for file_path in py_files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    new_content, count = re.subn(pattern, new_name, content)

                    if count > 0:
                        file_path.write_text(new_content, encoding="utf-8")
                        files_modified += 1
                        total_replacements += count

                except Exception as e:
                    errors.append(f"{file_path.name}: {str(e)}")

            if files_modified == 0:
                return {"success": False, "error": f"Symbol '{old_name}' not found in any file"}

            result = {
                "success": True,
                "files_modified": files_modified,
                "total_replacements": total_replacements,
            }

            if errors:
                result["errors"] = errors

            return result

        except Exception as e:
            return {"success": False, "error": f"Failed to rename: {str(e)}"}
