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

import asyncio
import hashlib
from collections.abc import Coroutine as CoroutineType
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.dependency_query_tool import DependencyQueryTool
from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool
from tree_sitter_analyzer.mcp.tools.modification_guard_tool import ModificationGuardTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


def _file_hash(path: str) -> str:
    """Compute a fast hash of a file's content for cache invalidation."""
    try:
        content = Path(path).read_bytes()
        return hashlib.md5(content).hexdigest()
    except OSError:
        return ""


class CodeAnalyzer:
    """Programmatic code analyzer backed by MCP tool implementations."""

    def __init__(
        self,
        project_root: str | None = None,
        *,
        cache_enabled: bool = True,
    ) -> None:
        self._project_root = project_root
        self._cache_enabled = cache_enabled
        self._tools = self._init_tools()
        self._cache: dict[str, tuple[str, dict[str, Any]]] = {}

    def _init_tools(self) -> dict[str, Any]:
        return {
            "analyze_code_structure": AnalyzeCodeStructureTool(project_root=self._project_root),
            "check_code_scale": AnalyzeScaleTool(project_root=self._project_root),
            "get_code_outline": GetCodeOutlineTool(project_root=self._project_root),
            "query_code": QueryTool(project_root=self._project_root),
            "extract_code_section": ReadPartialTool(project_root=self._project_root),
            "search_content": SearchContentTool(project_root=self._project_root),
            "trace_impact": TraceImpactTool(project_root=self._project_root),
            "modification_guard": ModificationGuardTool(project_root=self._project_root),
            "dependency_query": DependencyQueryTool(project_root=self._project_root),
        }

    @property
    def project_root(self) -> str | None:
        return self._project_root

    def set_project_root(self, path: str) -> CodeAnalyzer:
        """Return a new analyzer with updated project root (immutable)."""
        return CodeAnalyzer(project_root=path, cache_enabled=self._cache_enabled)

    def clear_cache(self) -> None:
        """Clear the analysis result cache."""
        self._cache.clear()

    def cache_size(self) -> int:
        """Return the number of cached results."""
        return len(self._cache)

    def _cache_key(self, method: str, args: dict[str, Any]) -> str:
        """Build a deterministic cache key from method name and arguments."""
        file_path = args.get("file_path", "")
        args_str = str(sorted(args.items()))
        return f"{method}:{file_path}:{hashlib.md5(args_str.encode()).hexdigest()}"

    async def _cached_execute(
        self, method: str, tool: Any, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a tool with optional caching."""
        if not self._cache_enabled:
            result: dict[str, Any] = await tool.execute(args)
            return result

        cache_key = self._cache_key(method, args)
        file_path = args.get("file_path", "")
        current_hash = _file_hash(file_path) if file_path else ""

        if cache_key in self._cache:
            cached_hash, cached_result = self._cache[cache_key]
            if cached_hash == current_hash and current_hash:
                return cached_result

        new_result: dict[str, Any] = await tool.execute(args)
        if file_path and current_hash:
            self._cache[cache_key] = (current_hash, new_result)
        return new_result

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
        return await self._cached_execute("analyze_structure", tool, args)

    async def check_scale(self, file_path: str) -> dict[str, Any]:
        """Get file size and complexity metrics."""
        tool: AnalyzeScaleTool = self._tools["check_code_scale"]
        return await self._cached_execute(
            "check_scale", tool, {"file_path": file_path, "output_format": "json"}
        )

    async def get_outline(
        self, file_path: str, *, output_format: str = "toon"
    ) -> dict[str, Any]:
        """Get hierarchical code outline."""
        tool: GetCodeOutlineTool = self._tools["get_code_outline"]
        return await self._cached_execute(
            "get_outline", tool, {"file_path": file_path, "output_format": output_format}
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

    async def trace_impact(
        self,
        symbol: str,
        *,
        file_path: str = "",
    ) -> dict[str, Any]:
        """Find all callers and usage sites of a symbol."""
        tool: TraceImpactTool = self._tools["trace_impact"]
        args: dict[str, Any] = {"symbol": symbol}
        if file_path:
            args["file_path"] = file_path
        return await tool.execute(args)  # type: ignore[no-any-return]

    async def modification_guard(
        self,
        file_path: str,
        symbol_name: str,
        *,
        modification_type: str = "delete",
    ) -> dict[str, Any]:
        """Check if modifying a symbol is safe."""
        tool: ModificationGuardTool = self._tools["modification_guard"]
        return await tool.execute({  # type: ignore[no-any-return]
            "file_path": file_path,
            "symbol": symbol_name,
            "modification_type": modification_type,
        })

    async def dependency_query(
        self,
        query_type: str,
        *,
        file_paths: list[str] | None = None,
        node: str = "",
        max_depth: int = 10,
    ) -> dict[str, Any]:
        """Query the project dependency graph."""
        tool: DependencyQueryTool = self._tools["dependency_query"]
        args: dict[str, Any] = {"query_type": query_type, "max_depth": max_depth}
        if file_paths:
            args["file_paths"] = file_paths
        if node:
            args["node"] = node
        return await tool.execute(args)

    async def batch_analyze(
        self,
        file_paths: list[str],
        *,
        analysis_type: str = "structure",
    ) -> dict[str, dict[str, Any]]:
        """Analyze multiple files concurrently.

        Args:
            file_paths: List of file paths to analyze.
            analysis_type: One of "structure", "scale", "outline".

        Returns:
            Dict mapping file_path -> analysis result.
        """
        if not file_paths:
            return {}

        tasks: list[CoroutineType[Any, Any, dict[str, Any]]] = []
        for fp in file_paths:
            if analysis_type == "structure":
                tasks.append(self.analyze_structure(fp))
            elif analysis_type == "scale":
                tasks.append(self.check_scale(fp))
            elif analysis_type == "outline":
                tasks.append(self.get_outline(fp))
            else:
                tasks.append(self.analyze_structure(fp))

        results_list: list[dict[str, Any] | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        results: dict[str, dict[str, Any]] = {}
        for fp, result in zip(file_paths, results_list, strict=True):
            if isinstance(result, BaseException):
                results[fp] = {"success": False, "error": str(result)}
            else:
                results[fp] = result
        return results


def create_analyzer(
    project_root: str | None = None,
    *,
    cache_enabled: bool = True,
) -> CodeAnalyzer:
    """Create a code analyzer instance.

    Args:
        project_root: Optional project root path for security validation.
        cache_enabled: Whether to cache analysis results (default: True).

    Returns:
        CodeAnalyzer instance ready for use.
    """
    if project_root and not Path(project_root).exists():
        raise ValueError(f"Project root does not exist: {project_root}")
    return CodeAnalyzer(project_root=project_root, cache_enabled=cache_enabled)
