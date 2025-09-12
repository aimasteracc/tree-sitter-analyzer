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
    # Create process
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if input_data is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Compute timeout seconds
    timeout_s: float | None = None
    if timeout_ms and timeout_ms > 0:
        timeout_s = timeout_ms / 1000.0

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_data), timeout=timeout_s
        )
        return proc.returncode, stdout, stderr
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
    if pattern:
        cmd.append(pattern)

    # Append roots
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
) -> list[str]:
    """Build ripgrep command with JSON output and options."""
    cmd: list[str] = [
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

    # Only add timeout if supported (check if timeout_ms is provided and > 0)
    # Note: --timeout flag may not be available in all ripgrep versions
    # For now, we'll skip the timeout flag to ensure compatibility
    # effective_timeout = clamp_int(timeout_ms, DEFAULT_RG_TIMEOUT_MS, RG_TIMEOUT_HARD_CAP_MS)
    # cmd += ["--timeout", str(effective_timeout)]

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
    for raw_line in stdout_bytes.splitlines():
        if not raw_line.strip():
            continue
        try:
            evt = json.loads(raw_line.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):  # nosec B112
            continue
        if evt.get("type") != "match":
            continue
        data = evt.get("data", {})
        path_text = (data.get("path", {}) or {}).get("text")
        line_number = data.get("line_number")
        line_text = (data.get("lines", {}) or {}).get("text")
        submatches_raw = data.get("submatches", []) or []
        submatches: list[dict[str, Any]] = []
        for sm in submatches_raw:
            submatches.append(
                {
                    "start": sm.get("start"),
                    "end": sm.get("end"),
                    "match": ((sm.get("match") or {}).get("text")),
                }
            )
        results.append(
            {
                "file": path_text,
                "abs_path": str(Path(path_text).resolve()) if path_text else None,
                "line_number": line_number,
                "line": line_text,
                "submatches": submatches,
            }
        )
    return results


@dataclass
class TempFileList:
    path: str

    def __enter__(self) -> TempFileList:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        with contextlib.suppress(Exception):
            Path(self.path).unlink(missing_ok=True)


class contextlib:  # minimal shim for suppress without importing globally
    class suppress:
        def __init__(self, *exceptions: type[BaseException]) -> None:
            self.exceptions = exceptions

        def __enter__(self) -> None:  # noqa: D401
            return None

        def __exit__(self, exc_type, exc, tb) -> bool:
            return exc_type is not None and issubclass(exc_type, self.exceptions)


def write_files_to_temp(files: list[str]) -> TempFileList:
    fd, temp_path = tempfile.mkstemp(prefix="rg-files-", suffix=".lst")
    os.close(fd)
    content = "\n".join(files)
    Path(temp_path).write_text(content, encoding="utf-8")
    return TempFileList(path=temp_path)
