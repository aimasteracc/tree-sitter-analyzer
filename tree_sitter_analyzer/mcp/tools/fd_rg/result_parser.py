#!/usr/bin/env python3
"""
Result parsers for fd and ripgrep output.

This module handles parsing of command output into structured data,
separating parsing logic from command execution and formatting.
"""

from __future__ import annotations

import json
from typing import Any

# Safety caps (hard limits)
MAX_RESULTS_HARD_CAP = 10000
DEFAULT_RESULTS_LIMIT = 2000


class FdResultParser:
    """Parses fd command output.

    Responsibilities:
    - Parse fd stdout into file list
    - Handle empty results
    - Apply result limits

    Single Responsibility: fd output parsing only.
    """

    def parse(self, stdout: str | bytes, limit: int | None = None) -> list[str]:
        """Parse fd output into list of file paths.

        Args:
            stdout: Raw stdout from fd command (str or bytes)
            limit: Optional limit on number of results

        Returns:
            List of file paths
        """
        if not stdout:
            return []

        # Convert bytes to str if needed
        if isinstance(stdout, bytes):
            stdout_str = stdout.decode("utf-8", errors="replace")
        else:
            stdout_str = stdout

        # Split into lines
        lines = stdout_str.splitlines()

        # Filter empty lines
        files = [line.strip() for line in lines if line.strip()]

        # Apply limit if specified
        if limit is not None:
            files = files[:limit]

        return files


class RgResultParser:
    """Parses ripgrep command output.

    Responsibilities:
    - Parse ripgrep JSON output into match objects
    - Parse ripgrep count output into file counts
    - Handle empty results
    - Apply result limits

    Single Responsibility: ripgrep output parsing only.
    """

    def parse(self, stdout: str | bytes) -> list[dict[str, Any]]:
        """Parse ripgrep JSON output (convenience method).

        Args:
            stdout: Raw stdout from ripgrep --json command (str or bytes)

        Returns:
            List of match dictionaries
        """
        # Convert str to bytes if needed
        if isinstance(stdout, str):
            stdout_bytes = stdout.encode("utf-8")
        else:
            stdout_bytes = stdout

        return self.parse_json_matches(stdout_bytes)

    def parse_count(self, stdout: str | bytes) -> dict[str, int]:
        """Parse ripgrep count output (convenience method).

        Args:
            stdout: Raw stdout from ripgrep --count-matches command (str or bytes)

        Returns:
            Dictionary mapping file paths to match counts
        """
        # Convert str to bytes if needed
        if isinstance(stdout, str):
            stdout_bytes = stdout.encode("utf-8")
        else:
            stdout_bytes = stdout

        return self.parse_count_output(stdout_bytes)

    def parse_json_matches(self, stdout_bytes: bytes) -> list[dict[str, Any]]:
        """Parse ripgrep JSON event stream and extract match events.

        Args:
            stdout_bytes: Raw stdout from ripgrep --json command

        Returns:
            List of match dictionaries with simplified structure
        """
        results: list[dict[str, Any]] = []
        lines = stdout_bytes.splitlines()

        # Batch process lines for better performance
        for raw_line in lines:
            if not raw_line.strip():
                continue

            try:
                # Decode once and parse JSON
                line_str = raw_line.decode("utf-8", errors="replace")
                evt = json.loads(line_str)
            except (json.JSONDecodeError, UnicodeDecodeError):  # nosec B112
                continue

            # Quick type check to skip non-match events
            if evt.get("type") != "match":
                continue

            data = evt.get("data", {})
            if not data:
                continue

            # Extract data with safe defaults
            path_data = data.get("path", {})
            path_text = path_data.get("text") if path_data else None
            if not path_text:
                continue

            line_number = data.get("line_number")
            lines_data = data.get("lines", {})
            line_text = lines_data.get("text") if lines_data else ""

            # Normalize line content to reduce token usage (optimized)
            normalized_line = " ".join(line_text.split()) if line_text else ""

            # Simplify submatches - keep only essential position data
            submatches_raw = data.get("submatches", [])
            simplified_matches = []
            if submatches_raw:
                for sm in submatches_raw:
                    start = sm.get("start")
                    end = sm.get("end")
                    if start is not None and end is not None:
                        simplified_matches.append([start, end])

            results.append(
                {
                    "file": path_text,
                    "line": line_number,
                    "text": normalized_line,
                    "matches": simplified_matches,
                }
            )

            # Early exit if we have too many results to prevent memory issues
            if len(results) >= MAX_RESULTS_HARD_CAP:
                break

        return results

    def parse_count_output(self, stdout_bytes: bytes) -> dict[str, int]:
        """Parse ripgrep --count-matches output.

        Args:
            stdout_bytes: Raw stdout from ripgrep --count-matches command

        Returns:
            Dictionary mapping file paths to match counts,
            with special "__total__" key for total count
        """
        results: dict[str, int] = {}
        total_matches = 0

        for line in stdout_bytes.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue

            # Format: "file_path:count"
            if ":" in line:
                file_path, count_str = line.rsplit(":", 1)
                try:
                    count = int(count_str)
                    results[file_path] = count
                    total_matches += count
                except ValueError:
                    # Skip lines that don't have valid count format
                    continue

        # Add total count as special key
        results["__total__"] = total_matches
        return results


class RgResultTransformer:
    """Transforms ripgrep results into various output formats.

    Responsibilities:
    - Group matches by file
    - Optimize file paths
    - Summarize results
    - Create file summaries from count data

    Single Responsibility: Result transformation only.
    """

    def group_by_file(self, matches: list[dict[str, Any]]) -> dict[str, Any]:
        """Group matches by file to eliminate file path duplication.

        Args:
            matches: List of match dictionaries

        Returns:
            Grouped structure with files and their matches
        """
        if not matches:
            return {"success": True, "count": 0, "files": []}

        # Group matches by file
        file_groups: dict[str, list[dict[str, Any]]] = {}
        total_matches = 0

        for match in matches:
            file_path = match.get("file", "unknown")
            if file_path not in file_groups:
                file_groups[file_path] = []

            # Create match entry without file path
            match_entry = {
                "line": match.get("line", match.get("line_number", "?")),
                "text": match.get("text", match.get("line", "")),
                "positions": match.get("matches", match.get("submatches", [])),
            }
            file_groups[file_path].append(match_entry)
            total_matches += 1

        # Convert to grouped structure
        files = []
        for file_path, file_matches in file_groups.items():
            files.append(
                {
                    "file": file_path,
                    "matches": file_matches,
                    "match_count": len(file_matches),
                }
            )

        return {"success": True, "count": total_matches, "files": files}

    def optimize_paths(self, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Optimize file paths in match results to reduce token consumption.

        Args:
            matches: List of match dictionaries

        Returns:
            Matches with optimized file paths
        """
        if not matches:
            return matches

        # Find common prefix among all file paths
        file_paths = [match.get("file", "") for match in matches if match.get("file")]
        common_prefix = ""
        if len(file_paths) > 1:
            import os

            try:
                common_prefix = os.path.commonpath(file_paths)
            except (ValueError, TypeError):
                common_prefix = ""

        # Optimize each match
        optimized_matches = []
        for match in matches:
            optimized_match = match.copy()
            file_path = match.get("file")
            if file_path:
                optimized_match["file"] = self._optimize_file_path(
                    file_path, common_prefix
                )
            optimized_matches.append(optimized_match)

        return optimized_matches

    def summarize(
        self,
        matches: list[dict[str, Any]],
        max_files: int = 10,
        max_total_lines: int = 50,
    ) -> dict[str, Any]:
        """Summarize search results to reduce context size.

        Args:
            matches: List of match dictionaries
            max_files: Maximum number of files to include in summary
            max_total_lines: Maximum total sample lines across all files

        Returns:
            Summary dictionary with top files and sample matches
        """
        if not matches:
            return {
                "total_matches": 0,
                "total_files": 0,
                "summary": "No matches found",
                "top_files": [],
            }

        # Group matches by file and find common prefix for optimization
        file_groups: dict[str, list[dict[str, Any]]] = {}
        all_file_paths = []
        for match in matches:
            file_path = match.get("file", "unknown")
            all_file_paths.append(file_path)
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(match)

        # Find common prefix to optimize paths
        common_prefix = ""
        if len(all_file_paths) > 1:
            import os

            common_prefix = os.path.commonpath(all_file_paths) if all_file_paths else ""

        # Sort files by match count (descending)
        sorted_files = sorted(
            file_groups.items(), key=lambda x: len(x[1]), reverse=True
        )

        # Create summary
        total_matches = len(matches)
        total_files = len(file_groups)

        # Top files with match counts
        top_files = []
        remaining_lines = max_total_lines

        for file_path, file_matches in sorted_files[:max_files]:
            match_count = len(file_matches)

            # Include a few sample lines from this file
            sample_lines = []
            lines_to_include = min(3, remaining_lines, len(file_matches))

            for _i, match in enumerate(file_matches[:lines_to_include]):
                line_num = match.get("line", match.get("line_number", "?"))
                line_text = match.get("text", match.get("line", "")).strip()
                if line_text:
                    # Truncate long lines and remove extra whitespace to save tokens
                    truncated_line = " ".join(line_text.split())[:60]
                    if len(line_text) > 60:
                        truncated_line += "..."
                    sample_lines.append(f"L{line_num}: {truncated_line}")
                    remaining_lines -= 1

            # Ensure we have at least some sample lines if matches exist
            if not sample_lines and file_matches:
                # Fallback: create a simple summary line
                sample_lines.append(f"Found {len(file_matches)} matches")

            # Optimize file path for token efficiency
            optimized_path = self._optimize_file_path(file_path, common_prefix)

            top_files.append(
                {
                    "file": optimized_path,
                    "match_count": match_count,
                    "sample_lines": sample_lines,
                }
            )

            if remaining_lines <= 0:
                break

        # Create summary text
        if total_files <= max_files:
            summary = f"Found {total_matches} matches in {total_files} files"
        else:
            summary = f"Found {total_matches} matches in {total_files} files (showing top {len(top_files)})"

        return {
            "total_matches": total_matches,
            "total_files": total_files,
            "summary": summary,
            "top_files": top_files,
            "truncated": total_files > max_files,
        }

    def create_file_summary_from_count(
        self, count_data: dict[str, int]
    ) -> dict[str, Any]:
        """Create a file summary structure from count data.

        Args:
            count_data: Dictionary from parse_count_output()

        Returns:
            File summary with match counts
        """
        file_list = [
            file_path for file_path in count_data.keys() if file_path != "__total__"
        ]
        total_matches = count_data.get("__total__", 0)

        return {
            "success": True,
            "total_matches": total_matches,
            "file_count": len(file_list),
            "files": [
                {"file": file_path, "match_count": count_data[file_path]}
                for file_path in file_list
            ],
            "derived_from_count": True,
        }

    def _optimize_file_path(self, file_path: str, common_prefix: str = "") -> str:
        """Optimize file path for token efficiency.

        Args:
            file_path: Original file path
            common_prefix: Common prefix to remove

        Returns:
            Optimized file path
        """
        if not file_path:
            return file_path

        # Remove common prefix if provided
        if common_prefix and file_path.startswith(common_prefix):
            optimized = file_path[len(common_prefix) :].lstrip("/\\")
            if optimized:
                return optimized

        # For very long paths, show only the last few components
        from pathlib import Path

        path_obj = Path(file_path)
        parts = path_obj.parts

        if len(parts) > 4:
            # Show first part + ... + last 3 parts
            return str(Path(parts[0]) / "..." / Path(*parts[-3:]))

        return file_path


# ============================================================================
# Convenience functions for backward compatibility
# ============================================================================


def group_matches_by_file(matches: list[dict[str, Any]]) -> dict[str, Any]:
    """Group matches by file (convenience function).

    Args:
        matches: List of match dictionaries

    Returns:
        Grouped structure with files and their matches
    """
    transformer = RgResultTransformer()
    return transformer.group_by_file(matches)


def summarize_search_results(
    matches: list[dict[str, Any]], max_files: int = 10, max_total_lines: int = 50
) -> dict[str, Any]:
    """Summarize search results (convenience function).

    Args:
        matches: List of match dictionaries
        max_files: Maximum number of files to include in summary
        max_total_lines: Maximum total lines to show across all files

    Returns:
        Summary dictionary with statistics and top files
    """
    transformer = RgResultTransformer()
    return transformer.summarize(matches, max_files, max_total_lines)


def optimize_match_paths(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Optimize file paths in matches (convenience function).

    Args:
        matches: List of match dictionaries

    Returns:
        Matches with optimized file paths
    """
    transformer = RgResultTransformer()
    return transformer.optimize_paths(matches)
