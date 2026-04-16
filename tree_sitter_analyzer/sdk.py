"""
Public SDK facade for tree-sitter-analyzer.

Provides a synchronous Python API for code analysis without MCP protocol
overhead. Designed for embedding into applications, scripts, and other
Python libraries.

Usage:
    from tree_sitter_analyzer.sdk import Analyzer

    analyzer = Analyzer(project_root="/path/to/project")
    result = analyzer.check_code_scale(file_path="src/main.py")
    analyzer.close()

Or as a context manager:
    with Analyzer(project_root="/path/to/project") as analyzer:
        result = analyzer.analyze_code_structure(file_path="src/main.py")
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.dependency_query_tool import DependencyQueryTool
from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool


def _file_hash(path: str) -> str:
    """Compute a fast hash of a file's content for cache invalidation."""
    try:
        content = Path(path).read_bytes()
        return hashlib.md5(content).hexdigest()
    except OSError:
        return ""


class Analyzer:
    """Synchronous Python SDK for tree-sitter-analyzer.

    Wraps the MCP tool layer with a clean, synchronous API suitable for
    embedding into any Python application. No MCP server or protocol
    overhead is involved — tool classes are called directly.
    """

    def __init__(
        self,
        project_root: str | None = None,
        *,
        cache_enabled: bool = True,
    ) -> None:
        self.project_root = project_root or os.getcwd()
        self._server = TreeSitterAnalyzerMCPServer(self.project_root)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cache_enabled = cache_enabled
        self._cache: dict[str, tuple[str, dict[str, Any]]] = {}

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create an event loop for async tool calls."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
        return self._loop

    def _run_async(self, coro: Any) -> dict[str, Any]:
        """Run an async coroutine synchronously."""
        try:
            asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result: dict[str, Any] = pool.submit(asyncio.run, coro).result()
                return result
        except RuntimeError:
            result2: dict[str, Any] = asyncio.run(coro)
            return result2

    def _cache_key(self, method: str, args: dict[str, Any]) -> str:
        """Build a deterministic cache key."""
        file_path = args.get("file_path", "")
        args_str = str(sorted(args.items()))
        return f"{method}:{file_path}:{hashlib.md5(args_str.encode()).hexdigest()}"

    def _cached_execute(
        self, method: str, tool: Any, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a tool with optional caching."""
        if not self._cache_enabled:
            return self._run_async(tool.execute(args))

        cache_key = self._cache_key(method, args)
        file_path = args.get("file_path", "")
        current_hash = _file_hash(file_path) if file_path else ""

        if cache_key in self._cache:
            cached_hash, cached_result = self._cache[cache_key]
            if cached_hash == current_hash and current_hash:
                return cached_result

        new_result: dict[str, Any] = self._run_async(tool.execute(args))
        if file_path and current_hash:
            self._cache[cache_key] = (current_hash, new_result)
        return new_result

    def close(self) -> None:
        """Clean up resources."""
        if self._loop and not self._loop.is_closed():
            self._loop.close()
            self._loop = None
        self._cache.clear()

    def __enter__(self) -> Analyzer:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def clear_cache(self) -> None:
        """Clear the analysis result cache."""
        self._cache.clear()

    def cache_size(self) -> int:
        """Return the number of cached results."""
        return len(self._cache)

    def set_project_path(self, project_path: str) -> None:
        """Change the project root for all tools."""
        self.project_root = project_path
        self._server.set_project_path(project_path)
        self._cache.clear()

    def check_code_scale(self, file_path: str, **kwargs: Any) -> dict[str, Any]:
        """Check file size and complexity before reading."""
        args: dict[str, Any] = {"file_path": file_path, **kwargs}
        return self._cached_execute(
            "check_code_scale", self._server.analyze_scale_tool, args
        )

    def analyze_code_structure(
        self, file_path: str, format_type: str = "compact", **kwargs: Any
    ) -> dict[str, Any]:
        """Analyze code structure (classes, methods, fields, annotations)."""
        args: dict[str, Any] = {
            "file_path": file_path,
            "format_type": format_type,
            **kwargs,
        }
        return self._cached_execute(
            "analyze_code_structure", self._server.analyze_code_structure_tool, args
        )

    def get_code_outline(self, file_path: str, **kwargs: Any) -> dict[str, Any]:
        """Get hierarchical navigation map (no bodies, just structure)."""
        args: dict[str, Any] = {"file_path": file_path, **kwargs}
        return self._cached_execute(
            "get_code_outline", self._server.get_code_outline_tool, args
        )

    def query_code(
        self, file_path: str, query_key: str = "", query_string: str = "", **kwargs: Any
    ) -> dict[str, Any]:
        """Run a tree-sitter query against a file."""
        args: dict[str, Any] = {"file_path": file_path, **kwargs}
        if query_key:
            args["query_key"] = query_key
        if query_string:
            args["query_string"] = query_string
        return self._run_async(self._server.query_tool.execute(args))

    def extract_code_section(
        self, file_path: str, start_line: int, end_line: int, **kwargs: Any
    ) -> dict[str, Any]:
        """Extract a specific line range from a file."""
        args: dict[str, Any] = {
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            **kwargs,
        }
        return self._run_async(self._server.read_partial_tool.execute(args))

    def trace_impact(
        self, symbol: str, file_path: str = "", **kwargs: Any
    ) -> dict[str, Any]:
        """Find all callers and usage sites of a symbol."""
        tool: TraceImpactTool = self._server.trace_impact_tool
        args: dict[str, Any] = {"symbol": symbol, **kwargs}
        if file_path:
            args["file_path"] = file_path
        return self._run_async(tool.execute(args))

    def modification_guard(
        self, file_path: str, symbol_name: str,
        modification_type: str = "delete", **kwargs: Any
    ) -> dict[str, Any]:
        """Check if modifying a symbol is safe."""
        args: dict[str, Any] = {
            "file_path": file_path,
            "symbol": symbol_name,
            "modification_type": modification_type,
            **kwargs,
        }
        return self._run_async(
            self._server.modification_guard_tool.execute(args)
        )

    def search_content(
        self, query: str, roots: list[str] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """Search code content using ripgrep."""
        args: dict[str, Any] = {"query": query, **kwargs}
        if roots:
            args["roots"] = roots
        return self._run_async(
            self._server.search_content_tool.execute(args)
        )

    def get_project_summary(self, **kwargs: Any) -> dict[str, Any]:
        """Get cached architecture overview of the project."""
        args: dict[str, Any] = {**kwargs}
        return self._run_async(
            self._server.get_project_summary_tool.execute(args)
        )

    def dependency_query(
        self,
        query_type: str,
        *,
        file_paths: list[str] | None = None,
        node: str = "",
        max_depth: int = 10,
    ) -> dict[str, Any]:
        """Query the project dependency graph."""
        tool: DependencyQueryTool = self._server.dependency_query_tool
        args: dict[str, Any] = {"query_type": query_type, "max_depth": max_depth}
        if file_paths:
            args["file_paths"] = file_paths
        if node:
            args["node"] = node
        return self._run_async(tool.execute(args))

    def batch_analyze(
        self,
        file_paths: list[str],
        *,
        analysis_type: str = "structure",
    ) -> dict[str, dict[str, Any]]:
        """Analyze multiple files sequentially with caching.

        Args:
            file_paths: List of file paths to analyze.
            analysis_type: One of "structure", "scale", "outline".

        Returns:
            Dict mapping file_path -> analysis result.
        """
        if not file_paths:
            return {}

        results: dict[str, dict[str, Any]] = {}
        for fp in file_paths:
            try:
                if analysis_type == "scale":
                    results[fp] = self.check_code_scale(fp)
                elif analysis_type == "outline":
                    results[fp] = self.get_code_outline(fp)
                else:
                    results[fp] = self.analyze_code_structure(fp)
            except Exception as exc:
                results[fp] = {"success": False, "error": str(exc)}
        return results
