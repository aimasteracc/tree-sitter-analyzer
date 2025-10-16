#!/usr/bin/env python3
"""
Shared utilities for fd/ripgrep based MCP tools.

This module centralizes subprocess execution, command building, result caps,
and JSON line parsing for ripgrep.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Safety caps (hard limits)
MAX_RESULTS_HARD_CAP = 10000
DEFAULT_RESULTS_LIMIT = 2000

DEFAULT_RG_MAX_FILESIZE = "10M"
RG_MAX_FILESIZE_HARD_CAP_BYTES = 200 * 1024 * 1024  # 200M

DEFAULT_RG_TIMEOUT_MS = 4000
RG_TIMEOUT_HARD_CAP_MS = 30000


def check_external_command(command: str) -> bool:
    """Check if an external command is available in the system PATH."""
    return shutil.which(command) is not None


def get_missing_commands() -> list[str]:
    """Get list of missing external commands required by fd/rg tools."""
    missing = []
    if not check_external_command("fd"):
        missing.append("fd")
    if not check_external_command("rg"):
        missing.append("rg")
    return missing


def clamp_int(value: int | None, default_value: int, hard_cap: int) -> int:
    if value is None:
        return default_value
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default_value
    return max(0, min(v, hard_cap))


def parse_size_to_bytes(size_str: str) -> int | None:
    """Parse ripgrep --max-filesize strings like '10M', '200K' to bytes."""
    if not size_str:
        return None
    s = size_str.strip().upper()
    try:
        if s.endswith("K"):
            return int(float(s[:-1]) * 1024)
        if s.endswith("M"):
            return int(float(s[:-1]) * 1024 * 1024)
        if s.endswith("G"):
            return int(float(s[:-1]) * 1024 * 1024 * 1024)
        return int(s)
    except ValueError:
        return None


async def run_command_capture(
    cmd: list[str],
    input_data: bytes | None = None,
    timeout_ms: int | None = None,
) -> tuple[int, bytes, bytes]:
    """Run a subprocess and capture output.

    Returns (returncode, stdout, stderr). On timeout, kills process and returns 124.
    Separated into a util for easy monkeypatching in tests.
    """
    # Check if command exists before attempting to run
    if cmd and not check_external_command(cmd[0]):
        error_msg = f"Command '{cmd[0]}' not found in PATH. Please install {cmd[0]} to use this functionality."
        return 127, b"", error_msg.encode()

    try:
        # Create process
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        error_msg = f"Command '{cmd[0]}' not found: {e}"
        return 127, b"", error_msg.encode()

    # Compute timeout seconds
    timeout_s: float | None = None
    if timeout_ms and timeout_ms > 0:
        timeout_s = timeout_ms / 1000.0

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_data), timeout=timeout_s
        )
        return proc.returncode or 0, stdout, stderr
    except asyncio.TimeoutError:
        try:
            proc.kill()
        finally:
            with contextlib.suppress(Exception):
                await proc.wait()
        return 124, b"", f"Timeout after {timeout_ms} ms".encode()


def build_fd_command(
    *,
    pattern: str | None,
    glob: bool,
    types: list[str] | None,
    extensions: list[str] | None,
    exclude: list[str] | None,
    depth: int | None,
    follow_symlinks: bool,
    hidden: bool,
    no_ignore: bool,
    size: list[str] | None,
    changed_within: str | None,
    changed_before: str | None,
    full_path_match: bool,
    absolute: bool,
    limit: int | None,
    roots: list[str],
) -> list[str]:
    """Build an fd command with appropriate flags."""
    cmd: list[str] = ["fd", "--color", "never"]
    if glob:
        cmd.append("--glob")
    if full_path_match:
        cmd.append("-p")
    if absolute:
        cmd.append("-a")
    if follow_symlinks:
        cmd.append("-L")
    if hidden:
        cmd.append("-H")
    if no_ignore:
        cmd.append("-I")
    if depth is not None:
        cmd += ["-d", str(depth)]
    if types:
        for t in types:
            cmd += ["-t", str(t)]
    if extensions:
        for ext in extensions:
            if ext.startswith("."):
                ext = ext[1:]
            cmd += ["-e", ext]
    if exclude:
        for ex in exclude:
            cmd += ["-E", ex]
    if size:
        for s in size:
            cmd += ["-S", s]
    if changed_within:
        cmd += ["--changed-within", str(changed_within)]
    if changed_before:
        cmd += ["--changed-before", str(changed_before)]
    if limit is not None:
        cmd += ["--max-results", str(limit)]

    # Pattern goes before roots if present
    # If no pattern is specified, use '.' to match all files (required to prevent roots being interpreted as pattern)
    if pattern:
        cmd.append(pattern)
    else:
        cmd.append(".")

    # Append roots - these are search directories, not patterns
    if roots:
        cmd += roots

    return cmd


def normalize_max_filesize(user_value: str | None) -> str:
    if not user_value:
        return DEFAULT_RG_MAX_FILESIZE
    bytes_val = parse_size_to_bytes(user_value)
    if bytes_val is None:
        return DEFAULT_RG_MAX_FILESIZE
    if bytes_val > RG_MAX_FILESIZE_HARD_CAP_BYTES:
        return "200M"
    return user_value


def build_rg_command(
    *,
    query: str,
    case: str | None,
    fixed_strings: bool,
    word: bool,
    multiline: bool,
    include_globs: list[str] | None,
    exclude_globs: list[str] | None,
    follow_symlinks: bool,
    hidden: bool,
    no_ignore: bool,
    max_filesize: str | None,
    context_before: int | None,
    context_after: int | None,
    encoding: str | None,
    max_count: int | None,
    timeout_ms: int | None,
    roots: list[str] | None,
    files_from: str | None,
    count_only_matches: bool = False,
) -> list[str]:
    """Build ripgrep command with JSON output and options."""
    if count_only_matches:
        # Use --count-matches for count-only mode (no JSON output)
        cmd = [
            "rg",
            "--count-matches",
            "--no-heading",
            "--color",
            "never",
        ]
    else:
        # Use --json for full match details
        cmd = [
            "rg",
            "--json",
            "--no-heading",
            "--color",
            "never",
        ]

    # Case sensitivity
    if case == "smart":
        cmd.append("-S")
    elif case == "insensitive":
        cmd.append("-i")
    elif case == "sensitive":
        cmd.append("-s")

    if fixed_strings:
        cmd.append("-F")
    if word:
        cmd.append("-w")
    if multiline:
        # Prefer --multiline (does not imply binary)
        cmd.append("--multiline")

    if follow_symlinks:
        cmd.append("-L")
    if hidden:
        cmd.append("-H")
    if no_ignore:
        # Use -u (respect ignore but include hidden); do not escalate to -uu automatically
        cmd.append("-u")

    if include_globs:
        for g in include_globs:
            cmd += ["-g", g]
    if exclude_globs:
        for g in exclude_globs:
            # ripgrep exclusion via !pattern
            if not g.startswith("!"):
                cmd += ["-g", f"!{g}"]
            else:
                cmd += ["-g", g]

    if context_before is not None:
        cmd += ["-B", str(context_before)]
    if context_after is not None:
        cmd += ["-A", str(context_after)]
    if encoding:
        cmd += ["--encoding", encoding]
    if max_count is not None:
        cmd += ["-m", str(max_count)]

    # Normalize filesize
    cmd += ["--max-filesize", normalize_max_filesize(max_filesize)]

    # Add timeout if provided and > 0 (enable timeout for performance optimization)
    if timeout_ms is not None and timeout_ms > 0:
        # effective_timeout = clamp_int(
        #     timeout_ms, DEFAULT_RG_TIMEOUT_MS, RG_TIMEOUT_HARD_CAP_MS
        # )  # Commented out as not used yet
        # Use timeout in milliseconds for better control
        # Note: We'll handle timeout at the process level instead of ripgrep flag
        # to ensure compatibility across ripgrep versions
        pass

    # Query must be last before roots/files
    cmd.append(query)

    # Skip --files-from flag as it's not supported in this ripgrep version
    # Use roots instead for compatibility
    if roots:
        cmd += roots
    # Note: files_from functionality is disabled for compatibility

    return cmd


def parse_rg_json_lines_to_matches(stdout_bytes: bytes) -> list[dict[str, Any]]:
    """Parse ripgrep JSON event stream and keep only match events."""
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


def group_matches_by_file(matches: list[dict[str, Any]]) -> dict[str, Any]:
    """Group matches by file to eliminate file path duplication."""
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
        files.append({
            "file": file_path,
            "matches": file_matches,
            "match_count": len(file_matches)
        })

    return {"success": True, "count": total_matches, "files": files}


def optimize_match_paths(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Optimize file paths in match results to reduce token consumption."""
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
            optimized_match["file"] = _optimize_file_path(file_path, common_prefix)
        optimized_matches.append(optimized_match)

    return optimized_matches


def _optimize_file_path(file_path: str, common_prefix: str = "") -> str:
    """Optimize file path for token efficiency by removing common prefixes and shortening."""
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


def summarize_search_results(
    matches: list[dict[str, Any]], max_files: int = 10, max_total_lines: int = 50
) -> dict[str, Any]:
    """Summarize search results to reduce context size while preserving key information."""
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
    sorted_files = sorted(file_groups.items(), key=lambda x: len(x[1]), reverse=True)

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
            line_num = match.get(
                "line", match.get("line_number", "?")
            )  # Support both old and new format
            line_text = match.get(
                "text", match.get("line", "")
            ).strip()  # Support both old and new format
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
        optimized_path = _optimize_file_path(file_path, common_prefix)

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


def parse_rg_count_output(stdout_bytes: bytes) -> dict[str, int]:
    """Parse ripgrep --count-matches output and return file->count mapping."""
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


def extract_file_list_from_count_data(count_data: dict[str, int]) -> list[str]:
    """Extract file list from count data, excluding the special __total__ key."""
    return [file_path for file_path in count_data.keys() if file_path != "__total__"]


def create_file_summary_from_count_data(count_data: dict[str, int]) -> dict[str, Any]:
    """Create a file summary structure from count data."""
    file_list = extract_file_list_from_count_data(count_data)
    total_matches = count_data.get("__total__", 0)

    return {
        "success": True,
        "total_matches": total_matches,
        "file_count": len(file_list),
        "files": [
            {"file": file_path, "match_count": count_data[file_path]}
            for file_path in file_list
        ],
        "derived_from_count": True,  # 标识这是从count数据推导的
    }


@dataclass
class TempFileList:
    path: str

    def __enter__(self) -> TempFileList:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any
    ) -> None:
        with contextlib.suppress(Exception):
            Path(self.path).unlink(missing_ok=True)


class contextlib:  # minimal shim for suppress without importing globally
    class suppress:
        def __init__(self, *exceptions: type[BaseException]) -> None:
            self.exceptions = exceptions

        def __enter__(self) -> None:  # noqa: D401
            return None

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: Any,
        ) -> bool:
            return exc_type is not None and issubclass(exc_type, self.exceptions)


def write_files_to_temp(files: list[str]) -> TempFileList:
    fd, temp_path = tempfile.mkstemp(prefix="rg-files-", suffix=".lst")
    os.close(fd)
    content = "\n".join(files)
    Path(temp_path).write_text(content, encoding="utf-8")
    return TempFileList(path=temp_path)


async def run_parallel_rg_searches(
    commands: list[list[str]],
    timeout_ms: int | None = None,
    max_concurrent: int = 4,
) -> list[tuple[int, bytes, bytes]]:
    """
    Run multiple ripgrep commands in parallel with concurrency control.

    Args:
        commands: List of ripgrep command lists to execute
        timeout_ms: Timeout in milliseconds for each command
        max_concurrent: Maximum number of concurrent processes (default: 4)

    Returns:
        List of (returncode, stdout, stderr) tuples in the same order as commands
    """
    if not commands:
        return []

    # Create semaphore to limit concurrent processes
    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_single_command(cmd: list[str]) -> tuple[int, bytes, bytes]:
        async with semaphore:
            return await run_command_capture(cmd, timeout_ms=timeout_ms)

    # Execute all commands concurrently
    tasks = [run_single_command(cmd) for cmd in commands]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle exceptions and convert to proper format
    processed_results: list[tuple[int, bytes, bytes]] = []
    for _i, result in enumerate(results):
        if isinstance(result, Exception):
            # Convert exception to error result
            error_msg = f"Command failed: {str(result)}"
            processed_results.append((1, b"", error_msg.encode()))
        elif isinstance(result, tuple) and len(result) == 3:
            processed_results.append(result)
        else:
            # Fallback for unexpected result types
            processed_results.append((1, b"", b"Unexpected result type"))

    return processed_results


def merge_rg_results(
    results: list[tuple[int, bytes, bytes]],
    count_only_mode: bool = False,
) -> tuple[int, bytes, bytes]:
    """
    Merge results from multiple ripgrep executions.

    Args:
        results: List of (returncode, stdout, stderr) tuples
        count_only_mode: Whether the results are from count-only mode

    Returns:
        Merged (returncode, stdout, stderr) tuple
    """
    if not results:
        return (1, b"", b"No results to merge")

    # Check if any command failed critically (not just "no matches found")
    critical_failures = []
    successful_results = []

    for rc, stdout, stderr in results:
        if rc not in (0, 1):  # 0=matches found, 1=no matches, others=errors
            critical_failures.append((rc, stdout, stderr))
        else:
            successful_results.append((rc, stdout, stderr))

    # If all commands failed critically, return the first failure
    if not successful_results:
        return critical_failures[0] if critical_failures else (1, b"", b"")

    # Merge successful results
    if count_only_mode:
        return _merge_count_results(successful_results)
    else:
        return _merge_json_results(successful_results)


def _merge_count_results(
    results: list[tuple[int, bytes, bytes]],
) -> tuple[int, bytes, bytes]:
    """Merge count-only results from multiple ripgrep executions."""
    merged_counts: dict[str, int] = {}
    total_matches = 0

    for rc, stdout, _stderr in results:
        if rc in (0, 1):  # Success or no matches
            file_counts = parse_rg_count_output(stdout)
            # Remove the __total__ key and merge file counts
            for file_path, count in file_counts.items():
                if file_path != "__total__":
                    merged_counts[file_path] = merged_counts.get(file_path, 0) + count
                    total_matches += count

    # Format as ripgrep count output
    output_lines = []
    for file_path, count in merged_counts.items():
        output_lines.append(f"{file_path}:{count}")

    merged_stdout = "\n".join(output_lines).encode("utf-8")

    # Return code 0 if we have matches, 1 if no matches
    return_code = 0 if total_matches > 0 else 1
    return (return_code, merged_stdout, b"")


def _merge_json_results(
    results: list[tuple[int, bytes, bytes]],
) -> tuple[int, bytes, bytes]:
    """Merge JSON results from multiple ripgrep executions."""
    merged_lines = []
    has_matches = False

    for rc, stdout, _stderr in results:
        if rc in (0, 1):  # Success or no matches
            if stdout.strip():
                merged_lines.extend(stdout.splitlines())
                if rc == 0:  # Has matches
                    has_matches = True

    merged_stdout = b"\n".join(merged_lines)
    return_code = 0 if has_matches else 1
    return (return_code, merged_stdout, b"")


def split_roots_for_parallel_processing(
    roots: list[str], max_chunks: int = 4
) -> list[list[str]]:
    """
    Split roots into chunks for parallel processing.

    Args:
        roots: List of root directories
        max_chunks: Maximum number of chunks to create

    Returns:
        List of root chunks for parallel processing
    """
    if not roots:
        return []

    if len(roots) <= max_chunks:
        # Each root gets its own chunk
        return [[root] for root in roots]

    # Distribute roots across chunks
    chunk_size = len(roots) // max_chunks
    remainder = len(roots) % max_chunks

    chunks = []
    start = 0

    for i in range(max_chunks):
        # Add one extra item to first 'remainder' chunks
        current_chunk_size = chunk_size + (1 if i < remainder else 0)
        end = start + current_chunk_size

        if start < len(roots):
            chunks.append(roots[start:end])

        start = end

    return [chunk for chunk in chunks if chunk]  # Remove empty chunks
