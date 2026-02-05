"""
MCP Tool for batch file operations.

This module provides a tool for batch file operations including rename,
move, copy, and extension changes.
"""

import re
import shutil
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class BatchOperationsTool(BaseTool):
    """
    MCP tool for batch file operations.

    Supports rename, move, copy, change_extension, add_prefix, and add_suffix operations.
    """

    def get_name(self) -> str:
        """Get tool name."""
        return "batch_operations"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Perform batch operations on multiple files. "
            "Supports rename, move, copy, change_extension, add_prefix, and add_suffix."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["rename", "move", "copy", "change_extension", "add_prefix", "add_suffix"],
                    "description": "Operation to perform",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths to operate on",
                },
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern for rename operation",
                },
                "replacement": {
                    "type": "string",
                    "description": "Replacement pattern for rename operation",
                },
                "target_dir": {
                    "type": "string",
                    "description": "Target directory for move/copy operations",
                },
                "new_extension": {
                    "type": "string",
                    "description": "New file extension (e.g., '.md')",
                },
                "prefix": {
                    "type": "string",
                    "description": "Prefix to add to filenames",
                },
                "suffix": {
                    "type": "string",
                    "description": "Suffix to add to filenames (before extension)",
                },
            },
            "required": ["operation", "files"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute batch operations tool.

        Args:
            arguments: Dictionary with operation parameters

        Returns:
            Dictionary with success status and processed count
        """
        try:
            operation = arguments["operation"]
            files = arguments["files"]

            if operation == "rename":
                return self._batch_rename(files, arguments.get("pattern"), arguments.get("replacement"))
            elif operation == "move":
                return self._batch_move(files, arguments.get("target_dir"))
            elif operation == "copy":
                return self._batch_copy(files, arguments.get("target_dir"))
            elif operation == "change_extension":
                return self._batch_change_extension(files, arguments.get("new_extension"))
            elif operation == "add_prefix":
                return self._batch_add_prefix(files, arguments.get("prefix"))
            elif operation == "add_suffix":
                return self._batch_add_suffix(files, arguments.get("suffix"))
            else:
                return {"success": False, "error": f"Unknown operation: {operation}"}

        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def _batch_rename(self, files: list[str], pattern: str | None, replacement: str | None) -> dict[str, Any]:
        """Batch rename files using regex pattern."""
        if not pattern or not replacement:
            return {"success": False, "error": "pattern and replacement required for rename"}

        processed = 0
        errors = []

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return {"success": False, "error": f"Invalid regex pattern: {str(e)}"}

        for file_str in files:
            try:
                file_path = Path(file_str)
                if not file_path.exists():
                    errors.append(f"{file_str}: file not found")
                    continue

                # Apply regex replacement to filename
                old_name = file_path.name
                new_name = regex.sub(replacement, old_name)

                if new_name != old_name:
                    new_path = file_path.parent / new_name
                    file_path.rename(new_path)
                    processed += 1
                else:
                    errors.append(f"{file_str}: pattern did not match")

            except Exception as e:
                errors.append(f"{file_str}: {str(e)}")

        if errors:
            return {"success": False, "processed": processed, "errors": errors}
        return {"success": True, "processed": processed}

    def _batch_move(self, files: list[str], target_dir: str | None) -> dict[str, Any]:
        """Batch move files to target directory."""
        if not target_dir:
            return {"success": False, "error": "target_dir required for move"}

        target_path = Path(target_dir)
        if not target_path.exists():
            target_path.mkdir(parents=True, exist_ok=True)

        processed = 0
        errors = []

        for file_str in files:
            try:
                file_path = Path(file_str)
                if not file_path.exists():
                    errors.append(f"{file_str}: file not found")
                    continue

                target_file = target_path / file_path.name
                shutil.move(str(file_path), str(target_file))
                processed += 1

            except Exception as e:
                errors.append(f"{file_str}: {str(e)}")

        if errors:
            return {"success": False, "processed": processed, "errors": errors}
        return {"success": True, "processed": processed}

    def _batch_copy(self, files: list[str], target_dir: str | None) -> dict[str, Any]:
        """Batch copy files to target directory."""
        if not target_dir:
            return {"success": False, "error": "target_dir required for copy"}

        target_path = Path(target_dir)
        if not target_path.exists():
            target_path.mkdir(parents=True, exist_ok=True)

        processed = 0
        errors = []

        for file_str in files:
            try:
                file_path = Path(file_str)
                if not file_path.exists():
                    errors.append(f"{file_str}: file not found")
                    continue

                target_file = target_path / file_path.name
                shutil.copy2(str(file_path), str(target_file))
                processed += 1

            except Exception as e:
                errors.append(f"{file_str}: {str(e)}")

        if errors:
            return {"success": False, "processed": processed, "errors": errors}
        return {"success": True, "processed": processed}

    def _batch_change_extension(self, files: list[str], new_extension: str | None) -> dict[str, Any]:
        """Batch change file extensions."""
        if not new_extension:
            return {"success": False, "error": "new_extension required"}

        # Ensure extension starts with dot
        if not new_extension.startswith("."):
            new_extension = "." + new_extension

        processed = 0
        errors = []

        for file_str in files:
            try:
                file_path = Path(file_str)
                if not file_path.exists():
                    errors.append(f"{file_str}: file not found")
                    continue

                new_path = file_path.with_suffix(new_extension)
                file_path.rename(new_path)
                processed += 1

            except Exception as e:
                errors.append(f"{file_str}: {str(e)}")

        if errors:
            return {"success": False, "processed": processed, "errors": errors}
        return {"success": True, "processed": processed}

    def _batch_add_prefix(self, files: list[str], prefix: str | None) -> dict[str, Any]:
        """Batch add prefix to filenames."""
        if not prefix:
            return {"success": False, "error": "prefix required"}

        processed = 0
        errors = []

        for file_str in files:
            try:
                file_path = Path(file_str)
                if not file_path.exists():
                    errors.append(f"{file_str}: file not found")
                    continue

                new_name = prefix + file_path.name
                new_path = file_path.parent / new_name
                file_path.rename(new_path)
                processed += 1

            except Exception as e:
                errors.append(f"{file_str}: {str(e)}")

        if errors:
            return {"success": False, "processed": processed, "errors": errors}
        return {"success": True, "processed": processed}

    def _batch_add_suffix(self, files: list[str], suffix: str | None) -> dict[str, Any]:
        """Batch add suffix to filenames (before extension)."""
        if not suffix:
            return {"success": False, "error": "suffix required"}

        processed = 0
        errors = []

        for file_str in files:
            try:
                file_path = Path(file_str)
                if not file_path.exists():
                    errors.append(f"{file_str}: file not found")
                    continue

                # Add suffix before extension
                stem = file_path.stem
                extension = file_path.suffix
                new_name = stem + suffix + extension
                new_path = file_path.parent / new_name
                file_path.rename(new_path)
                processed += 1

            except Exception as e:
                errors.append(f"{file_str}: {str(e)}")

        if errors:
            return {"success": False, "processed": processed, "errors": errors}
        return {"success": True, "processed": processed}
