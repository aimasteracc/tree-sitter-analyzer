"""
MCP Tool for combined file finding and content search.

This module provides the find_and_grep tool that combines fd (file search)
and ripgrep (content search) for powerful two-stage search capabilities.
"""

from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
from tree_sitter_analyzer_v2.search import SearchEngine


class FindAndGrepTool(BaseTool):
    """
    MCP tool for two-stage file and content search.

    Combines fd for fast file discovery with ripgrep for efficient content search.
    """

    def __init__(self):
        """Initialize the find_and_grep tool."""
        self._search_engine = SearchEngine()
        # Initialize encoding detector for multi-encoding support
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        self._encoding_detector = EncodingDetector()

    def get_name(self) -> str:
        """Get tool name."""
        return "find_and_grep"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Two-stage search: first use fd to find files matching criteria, "
            "then use ripgrep to search content within those files. "
            "Combines file filtering with content search for precise results."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "roots": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Directory paths to search in. Example: ['.', 'src/', 'tests/']",
                },
                "pattern": {
                    "type": "string",
                    "description": "Filename pattern to match. Example: '*.py', 'test_*', 'main.js'",
                },
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File extensions to include (without dots). Example: ['py', 'js']",
                },
                "query": {
                    "type": "string",
                    "description": "Text pattern to search for in found files. Optional - if not provided, just lists files.",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether content search is case-sensitive (default: True)",
                    "default": True,
                },
                "is_regex": {
                    "type": "boolean",
                    "description": "Whether query is a regex pattern (default: False)",
                    "default": False,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["toon", "markdown"],
                    "description": "Output format: 'toon' (token-optimized, default) or 'markdown' (human-readable)",
                    "default": "toon",
                },
            },
            "required": ["roots"],
        }

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get the MCP tool definition for find_and_grep.

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
        Execute the find_and_grep tool.

        Args:
            arguments: Tool arguments containing:
                - roots: List of root directories to search
                - pattern: Optional filename pattern
                - extensions: Optional list of file extensions
                - query: Optional content search pattern
                - case_sensitive: Whether search is case-sensitive
                - is_regex: Whether query is a regex
                - output_format: 'toon' or 'markdown'

        Returns:
            Dict containing:
                - success: Whether search succeeded
                - files: List of matching file paths (or search results if query provided)
                - output_format: Output format used
                - error: Error message if failed
        """
        roots = arguments.get("roots", [])
        pattern = arguments.get("pattern", "*")
        extensions = arguments.get("extensions")
        query = arguments.get("query")
        case_sensitive = arguments.get("case_sensitive", True)
        is_regex = arguments.get("is_regex", False)
        output_format = arguments.get("output_format", "toon")

        # Validate roots
        if not roots:
            return {"success": False, "error": "At least one root directory must be specified"}

        try:
            # Stage 1: Find files
            all_files = []
            for root in roots:
                root_path = Path(root)
                if not root_path.exists():
                    return {"success": False, "error": f"Directory does not exist: {root}"}

                # Determine file type from extensions
                file_type = None
                if extensions and len(extensions) == 1:
                    file_type = extensions[0]

                # Find files using SearchEngine
                files = self._search_engine.find_files(
                    root_dir=str(root_path), pattern=pattern, file_type=file_type
                )
                all_files.extend(files)

            # Stage 2: Search content (if query provided)
            if query:
                # Search content in found files by reading them directly
                results = []
                import re

                # Compile regex pattern if needed
                if is_regex:
                    flags = 0 if case_sensitive else re.IGNORECASE
                    try:
                        pattern_re = re.compile(query, flags)
                    except re.error:
                        return {"success": False, "error": f"Invalid regex pattern: {query}"}

                for file_path in all_files:
                    try:
                        # Read file content with automatic encoding detection
                        content = self._encoding_detector.read_file_safe(file_path)

                        # Search for pattern
                        if is_regex:
                            if pattern_re.search(content):
                                results.append(file_path)
                        else:
                            # Literal string search
                            search_text = query if case_sensitive else query.lower()
                            content_text = content if case_sensitive else content.lower()
                            if search_text in content_text:
                                results.append(file_path)

                    except Exception:
                        # Skip files that can't be read
                        continue

                all_files = results

            return {"success": True, "files": all_files, "output_format": output_format}

        except Exception as e:
            return {"success": False, "error": f"Search failed: {str(e)}"}
