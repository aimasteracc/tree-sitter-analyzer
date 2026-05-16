# Shared utilities for fd (file discovery) and rg (content search)
#!/usr/bin/env python3
"""
Shared utilities for fd/ripgrep based MCP tools.

This module centralizes subprocess execution, command building, result caps,
and JSON line parsing for ripgrep.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Re-export result utilities for backward compatibility
from .fd_rg_result_utils import (  # noqa: F401
    create_file_summary_from_count_data,
    extract_file_list_from_count_data,
    group_matches_by_file,
    optimize_match_paths,
    parse_rg_json_lines_to_matches,
    summarize_search_results,
)

# Safety caps (hard limits)
MAX_RESULTS_HARD_CAP = 10000
DEFAULT_RESULTS_LIMIT = 2000

DEFAULT_RG_MAX_FILESIZE = "10M"
RG_MAX_FILESIZE_HARD_CAP_BYTES = 200 * 1024 * 1024  # 200M

DEFAULT_RG_TIMEOUT_MS = 4000
RG_TIMEOUT_HARD_CAP_MS = 30000


def check_external_command(command: str) -> bool:
    """Check if an external command is available in the system PATH."""
    cached = _COMMAND_EXISTS_CACHE.get(command)
    if cached is not None:
        return cached
    exists = shutil.which(command) is not None
    _COMMAND_EXISTS_CACHE[command] = exists
    return exists


_COMMAND_EXISTS_CACHE: dict[str, bool] = {}


def get_missing_commands() -> list[str]:
    """Get list of missing external commands required by fd/rg tools."""
    missing = []
    if not check_external_command("fd"):
        missing.append("fd")
    if not check_external_command("rg"):
        missing.append("rg")
    return missing


def clamp_int(value: int | None, default_value: int, hard_cap: int) -> int:
    """Clamp an integer value to a safe range."""
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
    """Run a subprocess and capture output."""
    if cmd and not check_external_command(cmd[0]):
        error_msg = f"Command '{cmd[0]}' not found in PATH. Please install {cmd[0]} to use this functionality."
        return 127, b"", error_msg.encode()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        error_msg = f"Command '{cmd[0]}' not found: {e}"
        return 127, b"", error_msg.encode()

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
            # Build ripgrep command with all option flags
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

    if pattern:
        cmd.append(pattern)
    else:
        cmd.append(".")

    if roots:
        cmd += roots

    return cmd


def normalize_max_filesize(user_value: str | None) -> str:
    """Normalize max_filesize string (e.g., '1M') to bytes."""
    if not user_value:
        # Normalize file size strings to bytes
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
        cmd = ["rg", "--count-matches", "--no-heading", "--color", "never"]
    else:
        cmd = ["rg", "--json", "--no-heading", "--color", "never"]

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
        cmd.append("--multiline")

    if follow_symlinks:
        cmd.append("-L")
    if hidden:
        cmd.append("-H")
    if no_ignore:
        cmd.append("-u")

    if include_globs:
        for g in include_globs:
            cmd += ["-g", g]
    if exclude_globs:
        for g in exclude_globs:
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

    cmd += ["--max-filesize", normalize_max_filesize(max_filesize)]

    if timeout_ms is not None and timeout_ms > 0:
        # Parse ripgrep JSON output into structured match dicts
        pass

    cmd.append(query)

    if roots:
        cmd += roots

    return cmd


def parse_rg_count_output(stdout_bytes: bytes) -> dict[str, int]:
    """Parse ripgrep --count-matches output and return file->count mapping."""
    results: dict[str, int] = {}
    total_matches = 0

    for line in stdout_bytes.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue

        if ":" in line:
            file_path, count_str = line.rsplit(":", 1)
            try:
                count = int(count_str)
                results[file_path] = count
                total_matches += count
            except ValueError:
                continue

    results["__total__"] = total_matches
    return results


@dataclass
class TempFileList:
    path: str

    def __enter__(self) -> TempFileList:
        """Context manager for temporary file cleanup."""
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any
    ) -> None:
        """Clean up temporary file on context exit."""
        with contextlib.suppress(Exception):
            Path(self.path).unlink(missing_ok=True)


class contextlib:  # minimal shim for suppress without importing globally
    class suppress:
        def __init__(self, *exceptions: type[BaseException]) -> None:
            """Initialize temporary file writer."""
            self.exceptions = exceptions

        def __enter__(self) -> None:  # noqa: D401
            return None

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: Any,
            # Temporary file helper for --files-from option
        ) -> bool:
            """Clean up temp file on context exit."""
            return exc_type is not None and issubclass(exc_type, self.exceptions)


def write_files_to_temp(files: list[str]) -> TempFileList:
    """Write file list to a temporary file for --files-from option."""
    fd, temp_path = tempfile.mkstemp(prefix="rg-files-", suffix=".lst")
    os.close(fd)
    content = "\n".join(files)
    from ...encoding_utils import write_file_safe

    write_file_safe(temp_path, content)
    return TempFileList(path=temp_path)


async def run_parallel_rg_searches(
    commands: list[list[str]],
    timeout_ms: int | None = None,
    max_concurrent: int = 4,
) -> list[tuple[int, bytes, bytes]]:
    """Run multiple ripgrep commands in parallel with concurrency control."""
    if not commands:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_single_command(cmd: list[str]) -> tuple[int, bytes, bytes]:
        """Run a single command synchronously and capture output."""
        async with semaphore:
            return await run_command_capture(cmd, timeout_ms=timeout_ms)

    tasks = [run_single_command(cmd) for cmd in commands]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed_results: list[tuple[int, bytes, bytes]] = []
    for _i, result in enumerate(results):
        # Merge results from parallel rg executions
        if isinstance(result, Exception):
            error_msg = f"Command failed: {str(result)}"
            processed_results.append((1, b"", error_msg.encode()))
        elif isinstance(result, tuple) and len(result) == 3:
            processed_results.append(result)
        else:
            processed_results.append((1, b"", b"Unexpected result type"))

    return processed_results


def merge_rg_results(
    results: list[tuple[int, bytes, bytes]],
    count_only_mode: bool = False,
) -> tuple[int, bytes, bytes]:
    """Merge results from multiple ripgrep executions."""
    if not results:
        return (1, b"", b"No results to merge")

    critical_failures = []
    successful_results = []

    for rc, stdout, stderr in results:
        if rc not in (0, 1):
            critical_failures.append((rc, stdout, stderr))
        else:
            successful_results.append((rc, stdout, stderr))

    if not successful_results:
        return critical_failures[0] if critical_failures else (1, b"", b"")

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
        if rc in (0, 1):
            file_counts = parse_rg_count_output(stdout)
            for file_path, count in file_counts.items():
                if file_path != "__total__":
                    merged_counts[file_path] = merged_counts.get(file_path, 0) + count
                    total_matches += count

    output_lines = []
    for file_path, count in merged_counts.items():
        output_lines.append(f"{file_path}:{count}")

    merged_stdout = "\n".join(output_lines).encode("utf-8")
    return_code = 0 if total_matches > 0 else 1
    return (return_code, merged_stdout, b"")


def _merge_json_results(
    results: list[tuple[int, bytes, bytes]],
) -> tuple[int, bytes, bytes]:
    """Merge JSON results from multiple ripgrep executions."""
    merged_lines = []
    has_matches = False

    for rc, stdout, _stderr in results:
        if rc in (0, 1):
            if stdout.strip():
                merged_lines.extend(stdout.splitlines())
                if rc == 0:
                    has_matches = True

    merged_stdout = b"\n".join(merged_lines)
    return_code = 0 if has_matches else 1
    return (return_code, merged_stdout, b"")


def split_roots_for_parallel_processing(
    roots: list[str], max_chunks: int = 4
) -> list[list[str]]:
    """Split roots into chunks for parallel processing."""
    if not roots:
        return []

    if len(roots) <= max_chunks:
        return [[root] for root in roots]

    chunk_size = len(roots) // max_chunks
    remainder = len(roots) % max_chunks

    chunks = []
    start = 0

    for i in range(max_chunks):
        current_chunk_size = chunk_size + (1 if i < remainder else 0)
        end = start + current_chunk_size

        if start < len(roots):
            chunks.append(roots[start:end])

        start = end

    return [chunk for chunk in chunks if chunk]


# Section: quality threshold analysis (part 1)
# Section: quality threshold analysis (part 2)
