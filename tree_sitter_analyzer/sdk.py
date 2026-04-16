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
import os
from typing import Any

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer


class Analyzer:
    """Synchronous Python SDK for tree-sitter-analyzer.

    Wraps the MCP tool layer with a clean, synchronous API suitable for
    embedding into any Python application. No MCP server or protocol
    overhead is involved — tool classes are called directly.
    """

    def __init__(self, project_root: str | None = None) -> None:
        self.project_root = project_root or os.getcwd()
        self._server = TreeSitterAnalyzerMCPServer(self.project_root)
        self._loop: asyncio.AbstractEventLoop | None = None

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

    def close(self) -> None:
        """Clean up resources."""
        if self._loop and not self._loop.is_closed():
            self._loop.close()
            self._loop = None

    def __enter__(self) -> Analyzer:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def set_project_path(self, project_path: str) -> None:
        """Change the project root for all tools."""
        self.project_root = project_path
        self._server.set_project_path(project_path)

    def check_code_scale(self, file_path: str, **kwargs: Any) -> dict[str, Any]:
        """Check file size and complexity before reading.

        Args:
            file_path: Path to the source file.

        Returns:
            Dict with file metrics (lines, complexity, etc.).
        """
        args: dict[str, Any] = {"file_path": file_path, **kwargs}
        return self._run_async(
            self._server.analyze_scale_tool.execute(args)
        )

    def analyze_code_structure(
        self, file_path: str, format_type: str = "compact", **kwargs: Any
    ) -> dict[str, Any]:
        """Analyze code structure (classes, methods, fields, annotations).

        Args:
            file_path: Path to the source file.
            format_type: Output format ("compact", "full", "json", "toon").

        Returns:
            Dict with structured code elements.
        """
        args: dict[str, Any] = {
            "file_path": file_path,
            "format_type": format_type,
            **kwargs,
        }
        return self._run_async(
            self._server.analyze_code_structure_tool.execute(args)
        )

    def get_code_outline(self, file_path: str, **kwargs: Any) -> dict[str, Any]:
        """Get hierarchical navigation map (no bodies, just structure).

        Args:
            file_path: Path to the source file.

        Returns:
            Dict with outline tree.
        """
        args: dict[str, Any] = {"file_path": file_path, **kwargs}
        return self._run_async(
            self._server.get_code_outline_tool.execute(args)
        )

    def query_code(
        self, file_path: str, query_key: str = "", query_string: str = "", **kwargs: Any
    ) -> dict[str, Any]:
        """Run a tree-sitter query against a file.

        Args:
            file_path: Path to the source file.
            query_key: Predefined query name (e.g., "methods", "classes").
            query_string: Custom S-expression query.

        Returns:
            Dict with query matches.
        """
        args: dict[str, Any] = {"file_path": file_path, **kwargs}
        if query_key:
            args["query_key"] = query_key
        if query_string:
            args["query_string"] = query_string
        return self._run_async(self._server.query_tool.execute(args))

    def extract_code_section(
        self, file_path: str, start_line: int, end_line: int, **kwargs: Any
    ) -> dict[str, Any]:
        """Extract a specific line range from a file.

        Args:
            file_path: Path to the source file.
            start_line: Start line (1-based).
            end_line: End line (inclusive).

        Returns:
            Dict with extracted code text.
        """
        args: dict[str, Any] = {
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            **kwargs,
        }
        return self._run_async(
            self._server.read_partial_tool.execute(args)
        )

    def trace_impact(
        self, symbol: str, file_path: str = "", **kwargs: Any
    ) -> dict[str, Any]:
        """Find all callers and usage sites of a symbol.

        Args:
            symbol: Symbol name to trace.
            file_path: Optional source file for language detection.

        Returns:
            Dict with usages, call_count, impact_level.
        """
        args: dict[str, Any] = {"symbol": symbol, **kwargs}
        if file_path:
            args["file_path"] = file_path
        return self._run_async(
            self._server.trace_impact_tool.execute(args)
        )

    def modification_guard(
        self, file_path: str, symbol_name: str,
        modification_type: str = "delete", **kwargs: Any
    ) -> dict[str, Any]:
        """Check if modifying a symbol is safe.

        Args:
            file_path: Path to the source file.
            symbol_name: Symbol to check.
            modification_type: Type of modification (rename, signature_change,
                delete, behavior_change, refactor).

        Returns:
            Dict with safety_verdict (SAFE/CAUTION/REVIEW/UNSAFE).
        """
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
        """Search code content using ripgrep.

        Args:
            query: Search pattern.
            roots: Directories to search.

        Returns:
            Dict with search matches.
        """
        args: dict[str, Any] = {"query": query, **kwargs}
        if roots:
            args["roots"] = roots
        return self._run_async(
            self._server.search_content_tool.execute(args)
        )

    def get_project_summary(self, **kwargs: Any) -> dict[str, Any]:
        """Get cached architecture overview of the project.

        Returns:
            Dict with project structure summary.
        """
        args: dict[str, Any] = {**kwargs}
        return self._run_async(
            self._server.get_project_summary_tool.execute(args)
        )
