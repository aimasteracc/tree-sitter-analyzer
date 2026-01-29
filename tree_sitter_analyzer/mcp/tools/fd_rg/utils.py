#!/usr/bin/env python3
"""
Utility functions for fd and ripgrep operations.

This module contains shared utility functions that don't fit into
other specialized modules (command building, parsing, etc.).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Command existence cache (module-level for performance)
_COMMAND_EXISTS_CACHE: dict[str, bool] = {}


def check_external_command(command: str) -> bool:
    """Check if an external command is available in the system PATH.

    Args:
        command: Command name to check (e.g., "fd", "rg")

    Returns:
        True if command exists in PATH, False otherwise

    Note:
        Results are cached for performance (especially on Windows).
    """
    # On Windows, repeated shutil.which() calls can be surprisingly expensive.
    # Cache results for the lifetime of the process (safe for tests/tools).
    cached = _COMMAND_EXISTS_CACHE.get(command)
    if cached is not None:
        return cached
    exists = shutil.which(command) is not None
    _COMMAND_EXISTS_CACHE[command] = exists
    return exists


def get_missing_commands() -> list[str]:
    """Get list of missing external commands required by fd/rg tools.

    Returns:
        List of missing command names (e.g., ["fd", "rg"])
    """
    missing = []
    if not check_external_command("fd"):
        missing.append("fd")
    if not check_external_command("rg"):
        missing.append("rg")
    return missing


def sanitize_error_message(error_message: str) -> str:
    """Sanitize error messages to prevent information leakage.

    Removes sensitive system paths and file information from error messages
    to prevent security information disclosure.

    Args:
        error_message: Raw error message from command execution

    Returns:
        Sanitized error message with sensitive information redacted

    Examples:
        >>> sanitize_error_message("rg: /private/etc/passwd: Permission denied")
        "Permission denied accessing restricted paths"

        >>> sanitize_error_message("rg: C:\\Windows\\System32\\config\\SAM: Access denied")
        "Permission denied accessing restricted paths"
    """
    if not error_message:
        return error_message

    # Patterns that indicate permission/access errors
    permission_patterns = [
        r"permission denied",
        r"access denied",
        r"access is denied",
        r"operation not permitted",
        r"\(os error 13\)",  # EACCES
        r"\(os error 5\)",  # Windows ACCESS_DENIED
    ]

    # Check if this is a permission error
    is_permission_error = any(
        re.search(pattern, error_message, re.IGNORECASE)
        for pattern in permission_patterns
    )

    if is_permission_error:
        # Count how many permission errors occurred
        lines = error_message.strip().split("\n")
        permission_lines = [
            line
            for line in lines
            if any(re.search(p, line, re.IGNORECASE) for p in permission_patterns)
        ]

        if len(permission_lines) > 1:
            return (
                f"Permission denied accessing {len(permission_lines)} restricted paths"
            )
        else:
            return "Permission denied accessing restricted paths"

    # Patterns for sensitive system paths to redact
    sensitive_path_patterns = [
        # Unix/Linux/macOS system paths
        (r"/etc/[^\s:]+", "/etc/[redacted]"),
        (r"/private/etc/[^\s:]+", "/private/etc/[redacted]"),
        (r"/var/[^\s:]+", "/var/[redacted]"),
        (r"/sys/[^\s:]+", "/sys/[redacted]"),
        (r"/proc/[^\s:]+", "/proc/[redacted]"),
        (r"/root/[^\s:]+", "/root/[redacted]"),
        (r"/boot/[^\s:]+", "/boot/[redacted]"),
        # Windows system paths
        (
            r"[A-Z]:\\Windows\\System32\\[^\s:]+",
            "C:\\\\Windows\\\\System32\\\\[redacted]",
        ),
        (r"[A-Z]:\\Windows\\[^\s:]+", "C:\\\\Windows\\\\[redacted]"),
        (r"[A-Z]:\\Program Files\\[^\s:]+", "C:\\\\Program Files\\\\[redacted]"),
        # UNC paths
        (r"\\\\[^\s\\]+\\[^\s:]+", "\\\\\\\\[redacted]"),
    ]

    sanitized = error_message
    for pattern, replacement in sensitive_path_patterns:
        # Use lambda with default argument to properly bind replacement value
        sanitized = re.sub(
            pattern,
            lambda m, repl=replacement: repl,  # type: ignore[misc]
            sanitized,
            flags=re.IGNORECASE,
        )

    return sanitized


def clamp_int(value: int | None, default_value: int, hard_cap: int) -> int:
    """Clamp an integer value between 0 and a hard cap.

    Args:
        value: Value to clamp (None uses default)
        default_value: Default if value is None or invalid
        hard_cap: Maximum allowed value

    Returns:
        Clamped integer value
    """
    if value is None:
        return default_value
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default_value
    return max(0, min(v, hard_cap))


async def run_command_capture(
    cmd: list[str],
    input_data: bytes | None = None,
    timeout_ms: int | None = None,
) -> tuple[int, bytes, bytes]:
    """Run a subprocess and capture output.

    Args:
        cmd: Command and arguments as list
        input_data: Optional stdin data
        timeout_ms: Optional timeout in milliseconds

    Returns:
        Tuple of (returncode, stdout, stderr)
        On timeout, kills process and returns (124, b"", error_message)
        On command not found, returns (127, b"", error_message)

    Note:
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


async def run_parallel_commands(
    commands: list[list[str]],
    timeout_ms: int | None = None,
    max_concurrent: int = 4,
) -> list[tuple[int, bytes, bytes]]:
    """Run multiple commands in parallel with concurrency control.

    Args:
        commands: List of command lists to execute
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


def merge_command_results(
    results: list[tuple[int, bytes, bytes]],
    count_only_mode: bool = False,
) -> tuple[int, bytes, bytes]:
    """Merge results from multiple command executions.

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
    """Merge count-only results from multiple executions."""
    from .result_parser import RgResultParser

    parser = RgResultParser()
    merged_counts: dict[str, int] = {}
    total_matches = 0

    for rc, stdout, _stderr in results:
        if rc in (0, 1):  # Success or no matches
            file_counts = parser.parse_count_output(stdout)
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
    """Merge JSON results from multiple executions."""
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
    """Split roots into chunks for parallel processing.

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


@dataclass
class TempFileList:
    """Context manager for temporary file lists.

    Used to write file lists to temporary files for command input.
    Automatically cleans up the temporary file on exit.
    """

    path: str

    def __enter__(self) -> TempFileList:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any
    ) -> None:
        with contextlib.suppress(Exception):
            Path(self.path).unlink(missing_ok=True)


def write_files_to_temp(files: list[str]) -> TempFileList:
    """Write a list of files to a temporary file.

    Args:
        files: List of file paths

    Returns:
        TempFileList context manager

    Note:
        Caller should use as context manager to ensure cleanup.
    """
    fd, temp_path = tempfile.mkstemp(prefix="rg-files-", suffix=".lst")
    os.close(fd)
    content = "\n".join(files)
    from tree_sitter_analyzer.encoding_utils import write_file_safe

    write_file_safe(temp_path, content)
    return TempFileList(path=temp_path)
