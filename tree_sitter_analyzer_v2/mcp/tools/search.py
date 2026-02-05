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
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (optional, no limit by default)",
                    "minimum": 0,
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of results to skip (default: 0, for pagination)",
                    "minimum": 0,
                    "default": 0,
                },
                "group_by_directory": {
                    "type": "boolean",
                    "description": "Group results by directory (default: false). Returns dict with by_directory and summary.",
                    "default": False,
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
                - limit: Optional maximum number of results
                - offset: Optional number of results to skip

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
            limit = arguments.get("limit")
            offset = arguments.get("offset", 0)
            group_by_directory = arguments.get("group_by_directory", False)

            # Validate root directory exists
            if not Path(root_dir).exists():
                return {"success": False, "error": f"Directory does not exist: {root_dir}"}

            # Execute search
            result = self._search_engine.find_files(
                root_dir=root_dir,
                pattern=pattern,
                file_type=file_type,
                limit=limit,
                offset=offset,
                group_by_directory=group_by_directory,
            )

            # Format response based on grouping
            if group_by_directory:
                return {"success": True, **result}
            else:
                return {"success": True, "files": result, "count": len(result)}

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
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (optional, no limit by default)",
                    "minimum": 0,
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of results to skip (default: 0, for pagination)",
                    "minimum": 0,
                    "default": 0,
                },
                "context_before": {
                    "type": "integer",
                    "description": "Number of lines to show before each match (like grep -B, default: 0)",
                    "minimum": 0,
                    "default": 0,
                },
                "context_after": {
                    "type": "integer",
                    "description": "Number of lines to show after each match (like grep -A, default: 0)",
                    "minimum": 0,
                    "default": 0,
                },
                "context": {
                    "type": "integer",
                    "description": "Number of lines to show before and after each match (like grep -C, default: 0)",
                    "minimum": 0,
                    "default": 0,
                },
                "multiline": {
                    "type": "boolean",
                    "description": "Enable multiline mode where . matches newlines and patterns can span lines (default: false)",
                    "default": False,
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
                - limit: Optional maximum number of results
                - offset: Optional number of results to skip
                - context_before: Lines before match (default: 0)
                - context_after: Lines after match (default: 0)
                - context: Lines before and after match (default: 0)

        Returns:
            Dictionary with:
                - success: True if successful, False otherwise
                - matches: List of matches with file, line_number, line, context_before, context_after (if success=True)
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
            limit = arguments.get("limit")
            offset = arguments.get("offset", 0)
            context_before = arguments.get("context_before", 0)
            context_after = arguments.get("context_after", 0)
            context = arguments.get("context", 0)
            multiline = arguments.get("multiline", False)

            # If context is set, it overrides context_before and context_after
            if context > 0:
                context_before = context
                context_after = context

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
                limit=limit,
                offset=offset,
                multiline=multiline,
            )

            # Format matches for output with context
            matches = self._add_context_to_matches(raw_matches, context_before, context_after)

            return {"success": True, "matches": matches, "count": len(matches)}

        except RuntimeError as e:
            # Binary not found or command failed
            return {"success": False, "error": str(e)}
        except Exception as e:
            # Unexpected error
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def _add_context_to_matches(
        self, matches: list[dict[str, Any]], context_before: int, context_after: int
    ) -> list[dict[str, Any]]:
        """
        Add context lines to matches.

        Args:
            matches: List of matches from search_engine
            context_before: Number of lines before match
            context_after: Number of lines after match

        Returns:
            List of matches with context_before and context_after fields
        """
        if context_before == 0 and context_after == 0:
            # No context requested, return matches without context fields
            return [
                {
                    "file": match["file"],
                    "line_number": match["line_number"],
                    "line": match["line_content"],
                }
                for match in matches
            ]

        # Group matches by file for efficient context extraction
        matches_by_file: dict[str, list[dict[str, Any]]] = {}
        for match in matches:
            file_path = match["file"]
            if file_path not in matches_by_file:
                matches_by_file[file_path] = []
            matches_by_file[file_path].append(match)

        # Read files and add context
        result_matches = []
        for file_path, file_matches in matches_by_file.items():
            try:
                # Read file content
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()

                # Add context to each match
                for match in file_matches:
                    line_num = match["line_number"]
                    match_dict = {
                        "file": file_path,
                        "line_number": line_num,
                        "line": match["line_content"],
                    }

                    # Add context before
                    if context_before > 0:
                        start_line = max(0, line_num - context_before - 1)
                        end_line = line_num - 1
                        match_dict["context_before"] = [
                            lines[i].rstrip("\n") for i in range(start_line, end_line)
                        ]
                    else:
                        match_dict["context_before"] = []

                    # Add context after
                    if context_after > 0:
                        start_line = line_num
                        end_line = min(len(lines), line_num + context_after)
                        match_dict["context_after"] = [
                            lines[i].rstrip("\n") for i in range(start_line, end_line)
                        ]
                    else:
                        match_dict["context_after"] = []

                    result_matches.append(match_dict)

            except Exception:
                # If we can't read the file, skip context for this file
                for match in file_matches:
                    result_matches.append(
                        {
                            "file": file_path,
                            "line_number": match["line_number"],
                            "line": match["line_content"],
                            "context_before": [],
                            "context_after": [],
                        }
                    )

        return result_matches
