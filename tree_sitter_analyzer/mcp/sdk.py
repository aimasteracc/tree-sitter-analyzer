"""
SDK embedding API for tree-sitter-analyzer.

Provides a programmatic interface for embedding code analysis
into existing Python applications without running an MCP server.

Usage:
    from tree_sitter_analyzer.mcp.sdk import create_analyzer

    analyzer = create_analyzer("/path/to/project")
    result = analyzer.analyze_structure("src/main.py")
    methods = analyzer.query("src/main.py", query_key="methods")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


class CodeAnalyzer:
    """Programmatic code analyzer backed by MCP tool implementations."""

    def __init__(self, project_root: str | None = None) -> None:
        self._project_root = project_root
        self._tools = self._init_tools()

    def _init_tools(self) -> dict[str, Any]:
        return {
            "analyze_code_structure": AnalyzeCodeStructureTool(project_root=self._project_root),
            "check_code_scale": AnalyzeScaleTool(project_root=self._project_root),
            "get_code_outline": GetCodeOutlineTool(project_root=self._project_root),
            "query_code": QueryTool(project_root=self._project_root),
            "extract_code_section": ReadPartialTool(project_root=self._project_root),
            "search_content": SearchContentTool(project_root=self._project_root),
        }

    @property
    def project_root(self) -> str | None:
        return self._project_root

    def set_project_root(self, path: str) -> CodeAnalyzer:
        """Return a new analyzer with updated project root (immutable)."""
        return CodeAnalyzer(project_root=path)

    async def analyze_structure(
        self,
        file_path: str,
        *,
        format_type: str = "compact",
        language: str | None = None,
    ) -> dict[str, Any]:
        """Analyze code structure of a file."""
        tool: AnalyzeCodeStructureTool = self._tools["analyze_code_structure"]
        args: dict[str, Any] = {"file_path": file_path, "format_type": format_type}
        if language:
            args["language"] = language
        return await tool.execute(args)

    async def check_scale(self, file_path: str) -> dict[str, Any]:
        """Get file size and complexity metrics."""
        tool: AnalyzeScaleTool = self._tools["check_code_scale"]
        return await tool.execute({"file_path": file_path, "output_format": "json"})

    async def get_outline(
        self, file_path: str, *, output_format: str = "toon"
    ) -> dict[str, Any]:
        """Get hierarchical code outline."""
        tool: GetCodeOutlineTool = self._tools["get_code_outline"]
        return await tool.execute(
            {"file_path": file_path, "output_format": output_format}
        )

    async def query(
        self,
        file_path: str,
        *,
        query_key: str | None = None,
        query_string: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Query code elements using tree-sitter queries."""
        tool: QueryTool = self._tools["query_code"]
        args: dict[str, Any] = {"file_path": file_path}
        if query_key:
            args["query_key"] = query_key
        if query_string:
            args["query_string"] = query_string
        if language:
            args["language"] = language
        return await tool.execute(args)

    async def extract_section(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> dict[str, Any]:
        """Extract a specific code section by line range."""
        tool: ReadPartialTool = self._tools["extract_code_section"]
        return await tool.execute(
            {"file_path": file_path, "start_line": start_line, "end_line": end_line}
        )

    async def search(
        self,
        roots: list[str],
        query: str,
        *,
        extensions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search for content patterns in files."""
        tool: SearchContentTool = self._tools["search_content"]
        args: dict[str, Any] = {"roots": roots, "query": query}
        if extensions:
            args["extensions"] = extensions
        result: dict[str, Any] = await tool.execute(args)
        return result


def create_analyzer(project_root: str | None = None) -> CodeAnalyzer:
    """Create a code analyzer instance.

    Args:
        project_root: Optional project root path for security validation.

    Returns:
        CodeAnalyzer instance ready for use.
    """
    if project_root and not Path(project_root).exists():
        raise ValueError(f"Project root does not exist: {project_root}")
    return CodeAnalyzer(project_root=project_root)
