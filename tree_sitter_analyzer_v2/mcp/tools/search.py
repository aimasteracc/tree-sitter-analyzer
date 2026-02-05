"""
MCP Tools for file and content search using fd and ripgrep.

This module provides two MCP tools:
- find_files: Fast file search using fd
- search_content: Fast content search using ripgrep
"""

from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
from tree_sitter_analyzer_v2.search import SearchEngine


class FindFilesTool(BaseTool):
    """
    MCP tool for finding files using fd.

    Fast file search tool that wraps the fd command-line utility to find
    files matching glob patterns.
    """

    def __init__(self):
        """Initialize the find_files tool."""
        self._search_engine = SearchEngine()

    def get_name(self) -> str:
        """Get tool name."""
        return "find_files"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Find files matching a glob pattern using fd (fast file search). "
            "Returns a list of file paths matching the pattern. "
            "Supports glob patterns like '*.py', 'sample*', etc. "
            "Optionally filter by file type (e.g., 'py', 'ts', 'java')."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {"type": "string", "description": "Root directory to search in"},
                "pattern": {
                    "type": "string",
                    "description": "File pattern to match (e.g., '*.py', 'sample*', '*')",
                },
                "file_type": {
                    "type": "string",
                    "description": "Optional file type filter (e.g., 'py', 'ts', 'java')",
                },
            },
            "required": ["root_dir", "pattern"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute find_files tool.

        Args:
            arguments: Dictionary with:
                - root_dir: Root directory to search
                - pattern: Glob pattern (e.g., "*.py")
                - file_type: Optional file type filter (e.g., "py")

        Returns:
            Dictionary with:
                - success: True if successful, False otherwise
                - files: List of file paths (if success=True)
                - count: Number of files found
                - error: Error message (if success=False)
        """
        try:
            # Extract arguments
            root_dir = arguments["root_dir"]
            pattern = arguments["pattern"]
            file_type = arguments.get("file_type")

            # Validate root directory exists
            if not Path(root_dir).exists():
                return {"success": False, "error": f"Directory does not exist: {root_dir}"}

            # Execute search
            files = self._search_engine.find_files(
                root_dir=root_dir, pattern=pattern, file_type=file_type
            )

            return {"success": True, "files": files, "count": len(files)}

        except RuntimeError as e:
            # Binary not found or command failed
            return {"success": False, "error": str(e)}
        except Exception as e:
            # Unexpected error
            return {"success": False, "error": f"Unexpected error: {str(e)}"}


class SearchContentTool(BaseTool):
    """
    MCP tool for searching file content using ripgrep.

    Fast content search tool that wraps the ripgrep command-line utility to
    search for patterns in file contents.
    """

    def __init__(self):
        """Initialize the search_content tool."""
        self._search_engine = SearchEngine()

    def get_name(self) -> str:
        """Get tool name."""
        return "search_content"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Search file contents for a pattern using ripgrep (fast content search). "
            "Returns matching lines with file path, line number, and line content. "
            "Supports literal strings (default) and regex patterns. "
            "Optionally filter by file type and case sensitivity."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {"type": "string", "description": "Root directory to search in"},
                "pattern": {
                    "type": "string",
                    "description": "Pattern to search for (literal string or regex)",
                },
                "file_type": {
                    "type": "string",
                    "description": "Optional file type filter (e.g., 'py', 'ts', 'java')",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether search is case-sensitive (default: true)",
                },
                "use_regex": {
                    "type": "boolean",
                    "description": "Whether pattern is a regex (default: false)",
                },
            },
            "required": ["root_dir", "pattern"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute search_content tool.

        Args:
            arguments: Dictionary with:
                - root_dir: Root directory to search
                - pattern: Search pattern
                - file_type: Optional file type filter (e.g., "py")
                - case_sensitive: Case-sensitive search (default: True)
                - use_regex: Use regex pattern (default: False)

        Returns:
            Dictionary with:
                - success: True if successful, False otherwise
                - matches: List of matches with file, line_number, line (if success=True)
                - count: Number of matches found
                - error: Error message (if success=False)
        """
        try:
            # Extract arguments
            root_dir = arguments["root_dir"]
            pattern = arguments["pattern"]
            file_type = arguments.get("file_type")
            case_sensitive = arguments.get("case_sensitive", True)
            use_regex = arguments.get("use_regex", False)

            # Validate root directory exists
            if not Path(root_dir).exists():
                return {"success": False, "error": f"Directory does not exist: {root_dir}"}

            # Execute search
            raw_matches = self._search_engine.search_content(
                root_dir=root_dir,
                pattern=pattern,
                file_type=file_type,
                case_sensitive=case_sensitive,
                is_regex=use_regex,
            )

            # Format matches for output
            matches = []
            for match in raw_matches:
                matches.append(
                    {
                        "file": match["file"],
                        "line_number": match["line_number"],
                        "line": match["line_content"],
                    }
                )

            return {"success": True, "matches": matches, "count": len(matches)}

        except RuntimeError as e:
            # Binary not found or command failed
            return {"success": False, "error": str(e)}
        except Exception as e:
            # Unexpected error
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
