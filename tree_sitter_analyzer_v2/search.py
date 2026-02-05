"""
Search engine implementation using fd and ripgrep.

This module provides fast file and content search capabilities by wrapping
the fd (file search) and ripgrep (content search) command-line tools.
"""

import subprocess
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.utils.binaries import get_fd_path, get_ripgrep_path


class SearchEngine:
    """
    Fast search engine using fd and ripgrep.

    Provides high-performance file and content search by leveraging
    external tools optimized for speed.
    """

    def __init__(self) -> None:
        """Initialize search engine."""
        pass  # Lazy initialization - check binaries only when needed

    def find_files(
        self,
        root_dir: str,
        pattern: str,
        file_type: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        group_by_directory: bool = False,
    ) -> list[str] | dict[str, Any]:
        """
        Find files using fd.

        Args:
            root_dir: Root directory to search in
            pattern: File pattern to match (e.g., "*.py", "sample*")
            file_type: Optional file type filter (e.g., "py", "ts", "java")
            limit: Maximum number of results to return (None = unlimited)
            offset: Number of results to skip (default: 0)
            group_by_directory: Group results by directory (default: False)

        Returns:
            If group_by_directory=False: List of absolute file paths
            If group_by_directory=True: Dict with:
                - by_directory: Dict mapping directory paths to file lists
                - summary: Dict with total_files and directories count

        Raises:
            ValueError: If root_dir does not exist, or limit/offset are negative
            RuntimeError: If fd binary not found
        """
        # Validate limit and offset
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        # Validate directory exists
        root_path = Path(root_dir)
        if not root_path.exists():
            raise ValueError(f"Directory does not exist: {root_dir}")

        # Check fd binary availability
        fd_path = get_fd_path()
        if fd_path is None:
            raise RuntimeError(
                "fd binary not found. Please install fd for file search.\n"
                "See: https://github.com/sharkdp/fd#installation"
            )

        # Build fd command
        cmd = [str(fd_path)]

        # Add file type filter if specified
        if file_type:
            cmd.extend(["--type", "f", "--extension", file_type])
        else:
            cmd.extend(["--type", "f"])

        # Add glob flag for pattern matching
        cmd.append("--glob")

        # Add options for absolute paths
        cmd.append("--absolute-path")

        # Add pattern
        cmd.append(pattern)

        # Add root directory
        cmd.append(str(root_path))

        # Execute fd
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",  # Explicitly specify UTF-8 encoding
                errors="replace",  # Replace invalid characters instead of failing
                check=True,
                timeout=10,  # 10 second timeout
            )
            files = self._parse_fd_output(result.stdout)

            # Apply offset and limit
            if offset > 0:
                files = files[offset:]
            if limit is not None:
                files = files[:limit]

            # Group by directory if requested
            if group_by_directory:
                return self._group_files_by_directory(files, root_dir)

            return files
        except subprocess.CalledProcessError as e:
            # fd returns non-zero if no files found, which is not an error
            if e.returncode == 1:
                return []
            raise RuntimeError(f"fd command failed: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("fd command timed out after 10 seconds") from e

    def search_content(
        self,
        root_dir: str,
        pattern: str,
        file_type: str | None = None,
        case_sensitive: bool = True,
        is_regex: bool = False,
        limit: int | None = None,
        offset: int = 0,
        multiline: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Search file content using ripgrep.

        Args:
            root_dir: Root directory to search in
            pattern: Content pattern to search for
            file_type: Optional file type filter (e.g., "py", "ts", "java")
            case_sensitive: Whether search is case-sensitive (default: True)
            is_regex: Whether pattern is a regex (default: False)
            limit: Maximum number of results to return (None = unlimited)
            offset: Number of results to skip (default: 0)
            multiline: Enable multiline mode where . matches newlines (default: False)

        Returns:
            List of dicts with keys: file, line_number, line_content

        Raises:
            ValueError: If root_dir does not exist, or limit/offset are negative
            RuntimeError: If ripgrep binary not found
        """
        # Validate limit and offset
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        # Validate directory exists
        root_path = Path(root_dir)
        if not root_path.exists():
            raise ValueError(f"Directory does not exist: {root_dir}")

        # Check ripgrep binary availability
        rg_path = get_ripgrep_path()
        if rg_path is None:
            raise RuntimeError(
                "ripgrep binary not found. Please install ripgrep for content search.\n"
                "See: https://github.com/BurntSushi/ripgrep#installation"
            )

        # Build ripgrep command
        cmd = [str(rg_path)]

        # Add line numbers
        cmd.append("--line-number")

        # Add case sensitivity
        if not case_sensitive:
            cmd.append("--ignore-case")

        # Add regex flag (ripgrep uses regex by default, but we can force it)
        if not is_regex:
            cmd.append("--fixed-strings")

        # Add file type filter if specified
        if file_type:
            cmd.extend(["--type", file_type])

        # Add multiline support
        if multiline:
            cmd.append("--multiline")
            cmd.append("--multiline-dotall")

        # Add pattern
        cmd.append(pattern)

        # Add root directory
        cmd.append(str(root_path))

        # Execute ripgrep
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",  # Explicitly specify UTF-8 encoding (Issue #11)
                errors="replace",  # Replace invalid characters instead of failing
                check=False,  # Don't raise on non-zero exit
                timeout=10,  # 10 second timeout
            )

            # ripgrep returns 0 if matches found, 1 if no matches, >1 for errors
            if result.returncode == 0:
                results = self._parse_rg_output(result.stdout)

                # Apply offset and limit
                if offset > 0:
                    results = results[offset:]
                if limit is not None:
                    results = results[:limit]

                return results
            elif result.returncode == 1:
                # No matches found
                return []
            else:
                # Actual error
                raise RuntimeError(
                    f"ripgrep command failed with code {result.returncode}: {result.stderr}"
                )

        except subprocess.TimeoutExpired as e:
            raise RuntimeError("ripgrep command timed out after 10 seconds") from e

    def _parse_fd_output(self, output: str) -> list[str]:
        """
        Parse fd output format.

        fd outputs one file path per line.

        Args:
            output: Raw fd stdout

        Returns:
            List of file paths
        """
        if not output or not output.strip():
            return []

        lines = output.strip().split("\n")
        return [line.strip() for line in lines if line.strip()]

    def _group_files_by_directory(
        self, files: list[str], root_dir: str
    ) -> dict[str, Any]:
        """
        Group files by their directory.

        Args:
            files: List of absolute file paths
            root_dir: Root directory (for calculating relative paths)

        Returns:
            Dict with:
                - by_directory: Dict mapping relative directory paths to file lists
                - summary: Dict with total_files and directories count
        """
        from collections import defaultdict

        root_path = Path(root_dir).resolve()
        by_directory: dict[str, list[str]] = defaultdict(list)

        for file_path in files:
            file_path_obj = Path(file_path).resolve()

            # Get directory relative to root
            try:
                dir_relative = file_path_obj.parent.relative_to(root_path)
                dir_key = str(dir_relative) if str(dir_relative) != "." else "."
            except ValueError:
                # File is outside root_dir, use absolute directory
                dir_key = str(file_path_obj.parent)

            # Store just the filename (not full path)
            by_directory[dir_key].append(file_path_obj.name)

        # Convert defaultdict to regular dict
        by_directory_dict = dict(by_directory)

        return {
            "by_directory": by_directory_dict,
            "summary": {
                "total_files": len(files),
                "directories": len(by_directory_dict),
            },
        }

    def _parse_rg_output(self, output: str) -> list[dict[str, Any]]:
        r"""
        Parse ripgrep output format.

        ripgrep with --line-number outputs: file:line_number:line_content
        On Windows, paths contain colons (C:\path), so we need robust parsing.

        Args:
            output: Raw ripgrep stdout

        Returns:
            List of dicts with file, line_number, line_content
        """
        if not output or not output.strip():
            return []

        results: list[dict[str, Any]] = []
        lines = output.strip().split("\n")

        for line in lines:
            if not line.strip():
                continue

            # Parse format: file:line_number:line_content
            # On Windows, paths can be like "C:\path\file.txt:42:content"
            # We need to find the line number part which is always an integer

            # Find all colons in the line
            colon_indices = [i for i, c in enumerate(line) if c == ":"]

            if len(colon_indices) < 2:
                continue  # Need at least 2 colons (file:line:content)

            # Try each possible position for the line number
            for i in range(len(colon_indices) - 1):
                file_part = line[: colon_indices[i]]
                line_num_part = line[colon_indices[i] + 1 : colon_indices[i + 1]]

                try:
                    line_number = int(line_num_part)
                    # Found valid line number, rest is content
                    line_content = line[colon_indices[i + 1] + 1 :]

                    results.append(
                        {
                            "file": file_part,
                            "line_number": line_number,
                            "line_content": line_content,
                        }
                    )
                    break  # Successfully parsed, move to next line

                except ValueError:
                    # This wasn't the line number, try next colon
                    continue

        return results
