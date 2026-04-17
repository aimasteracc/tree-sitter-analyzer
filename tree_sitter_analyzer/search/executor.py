"""
Fast Path Executor Module

Executes simple queries using deterministic tools (grep, ripgrep, ast-grep)
and existing MCP tools. Provides fast (<1s) results for common query patterns.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

# Set up logging
logger = setup_logger(__name__)

# Set up logging
logger = setup_logger(__name__)


@dataclass
class ExecutionResult:
    """Result of query execution."""
    success: bool
    results: list[dict[str, Any]]
    error: str | None = None
    execution_time: float = 0.0
    tool_used: str = ""


class FastPathExecutor:
    """
    Executes simple queries using fast deterministic tools.

    Handles grep, ripgrep, and delegates to existing MCP tools (dependency_query,
    trace_impact, etc.) for specialized queries.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize the fast path executor.

        Args:
            project_root: Root directory of the project to search
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self._ripgrep_available = self._check_ripgrep()

    def _extract_by_position(self, params: dict[str, Any], position: int) -> Any:
        """
        Extract a value from params by numeric position.

        This is a fallback for when regex groups aren't named.

        Args:
            params: Parameters dictionary
            position: Numeric position to extract (1-indexed)

        Returns:
            The value at that position, or None
        """
        # Try integer key first (for backward compatibility with tests)
        if position in params:  # type: ignore[comparison-overlap]
            return params[position]  # type: ignore[index]

        # Try string key representation
        pos_key = str(position)
        if pos_key in params:
            return params[pos_key]

        # Also check for keys with named groups that might match
        for key, value in params.items():
            # Handle both string keys and potential legacy integer keys
            key_str = str(key) if not isinstance(key, str) else key
            if "group" in key_str.lower():
                return value

        return None

    def _check_ripgrep(self) -> bool:
        """Check if ripgrep is available."""
        try:
            subprocess.run(
                ["rg", "--version"],
                capture_output=True,
                check=True,
                timeout=2,
            )
            return True
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            return False

    def execute(self, handler: str, params: dict[str, Any]) -> ExecutionResult:
        """
        Execute a query using the appropriate fast path tool.

        Args:
            handler: Name of the handler method to call
            params: Extracted parameters from the query

        Returns:
            ExecutionResult with search results
        """
        import time

        start_time = time.time()

        try:
            if handler == "grep_by_name":
                result = self._grep_by_name(params)
            elif handler == "grep_in_files":
                result = self._grep_in_files(params)
            elif handler == "dependency_of":
                result = self._dependency_of(params)
            elif handler == "what_calls":
                result = self._what_calls(params)
            else:
                result = ExecutionResult(
                    success=False,
                    results=[],
                    error=f"Unknown handler: {handler}",
                )

            result.execution_time = time.time() - start_time
            return result

        except Exception as e:
            logger.exception(f"Fast path execution failed: {e}")
            return ExecutionResult(
                success=False,
                results=[],
                error=str(e),
                execution_time=time.time() - start_time,
            )

    def _grep_by_name(self, params: dict[str, Any]) -> ExecutionResult:
        """
        Find functions/classes by name using grep or ripgrep.

        Args:
            params: Must contain 'name' key with the symbol name to search

        Returns:
            ExecutionResult with matching files and line numbers
        """
        name = params.get("name")
        if not name:
            # Fallback: use _extract_by_position for backward compatibility
            name = self._extract_by_position(params, 1)
        if not name:
            return ExecutionResult(
                success=False,
                results=[],
                error="No name specified in query",
            )

        # Use ripgrep if available, otherwise grep
        if self._ripgrep_available:
            cmd = [
                "rg",
                "--type=py",  # TODO: detect file type from params
                "--no-heading",
                "--line-number",
                "--with-filename",
                name,
                str(self.project_root),
            ]
        else:
            cmd = [
                "grep",
                "-r",
                "-n",
                "--include=*.py",  # TODO: detect file type from params
                name,
                str(self.project_root),
            ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            if result.returncode != 0:
                return ExecutionResult(
                    success=True,
                    results=[],
                    error=f"No matches found for: {name}",
                )

            # Parse output into structured results
            results = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) >= 3:
                    file_path = parts[0]
                    line_number = parts[1]
                    content = ":".join(parts[2:])
                    results.append({
                        "file": file_path,
                        "line": line_number,
                        "content": content.strip(),
                    })

            return ExecutionResult(
                success=True,
                results=results,
                tool_used="ripgrep" if self._ripgrep_available else "grep",
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                results=[],
                error="Search timed out (5s limit)",
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                results=[],
                error=f"Search failed: {e}",
            )

    def _grep_in_files(self, params: dict[str, Any]) -> ExecutionResult:
        """
        Find code in specific file types.

        Args:
            params: Must contain file type and search term

        Returns:
            ExecutionResult with matching code
        """
        # Extract file type and search term from params
        # This is a simplified implementation
        search_term = params.get("term") or self._extract_by_position(
            params, 1
        )
        file_type = (
            params.get("filetype")
            or self._extract_by_position(params, 2)
            or "py"
        )

        if not search_term:
            return ExecutionResult(
                success=False,
                results=[],
                error="No search term specified",
            )

        # Map common file type names to extensions
        ext_map = {
            "python": ".py",
            "py": ".py",
            "javascript": ".js",
            "js": ".js",
            "typescript": ".ts",
            "ts": ".ts",
            "java": ".java",
            "go": ".go",
            "rust": ".rs",
        }

        ext = ext_map.get(file_type.lower(), f".{file_type.lower()}")

        if self._ripgrep_available:
            cmd = [
                "rg",
                "--no-heading",
                "--line-number",
                "--with-filename",
                "-g",
                f"*{ext}",
                search_term,
                str(self.project_root),
            ]
        else:
            cmd = [
                "grep",
                "-r",
                "-n",
                f"--include=*{ext}",
                search_term,
                str(self.project_root),
            ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            if result.returncode != 0:
                return ExecutionResult(
                    success=True,
                    results=[],
                    error=f"No matches found in {file_type} files",
                )

            results = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) >= 3:
                    results.append({
                        "file": parts[0],
                        "line": parts[1],
                        "content": ":".join(parts[2:]).strip(),
                    })

            return ExecutionResult(
                success=True,
                results=results,
                tool_used="ripgrep" if self._ripgrep_available else "grep",
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                results=[],
                error="Search timed out (5s limit)",
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                results=[],
                error=f"Search failed: {e}",
            )

    def _dependency_of(self, params: dict[str, Any]) -> ExecutionResult:
        """
        Find dependencies of a symbol using existing MCP tools.

        This is a placeholder that would integrate with dependency_query tool.

        Args:
            params: Symbol name to find dependencies for

        Returns:
            ExecutionResult with dependency information
        """
        symbol = params.get("symbol") or self._extract_by_position(params, 1)

        # Placeholder: would call dependency_query MCP tool here
        return ExecutionResult(
            success=True,
            results=[{
                "symbol": symbol,
                "message": "Dependency integration pending (Sprint 2)",
            }],
            tool_used="dependency_query (placeholder)",
        )

    def _what_calls(self, params: dict[str, Any]) -> ExecutionResult:
        """
        Find what calls a symbol using existing MCP tools.

        This is a placeholder that would integrate with trace_impact tool.

        Args:
            params: Symbol name to find callers for

        Returns:
            ExecutionResult with caller information
        """
        symbol = params.get("symbol") or self._extract_by_position(params, 1)

        # Placeholder: would call trace_impact MCP tool here
        return ExecutionResult(
            success=True,
            results=[{
                "symbol": symbol,
                "message": "Trace impact integration pending (Sprint 2)",
            }],
            tool_used="trace_impact (placeholder)",
        )
