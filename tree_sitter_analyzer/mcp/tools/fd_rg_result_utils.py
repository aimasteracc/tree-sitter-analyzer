#!/usr/bin/env python3
"""
Result parsing and summarization for ripgrep output.

Extracted from fd_rg_utils.py to reduce file size.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_MAX_RESULTS_HARD_CAP = 10000


# parse_rg_json_lines_to_matches: implementation
def parse_rg_json_lines_to_matches(stdout_bytes: bytes) -> list[dict[str, Any]]:
    """Parse ripgrep JSON event stream and keep only match events."""
    results: list[dict[str, Any]] = []
    lines = stdout_bytes.splitlines()

    for raw_line in lines:
        if not raw_line.strip():
            continue
        try:
            line_str = raw_line.decode("utf-8", errors="replace")
            evt = json.loads(line_str)
        except (json.JSONDecodeError, UnicodeDecodeError):  # nosec B112
            continue

        if evt.get("type") != "match":
            continue

        data = evt.get("data", {})
        if not data:
            continue

        path_data = data.get("path", {})
        path_text = path_data.get("text") if path_data else None
        if not path_text:
            continue

        line_number = data.get("line_number")
        lines_data = data.get("lines", {})
        line_text = lines_data.get("text") if lines_data else ""

        normalized_line = " ".join(line_text.split()) if line_text else ""

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

        if len(results) >= _MAX_RESULTS_HARD_CAP:
            break

    return results


# group_matches_by_file: implementation
def group_matches_by_file(matches: list[dict[str, Any]]) -> dict[str, Any]:
    """Group matches by file to eliminate file path duplication."""
    if not matches:
        return {"success": True, "count": 0, "files": []}

    file_groups: dict[str, list[dict[str, Any]]] = {}
    total_matches = 0

    for match in matches:
        file_path = match.get("file", "unknown")
        if file_path not in file_groups:
            file_groups[file_path] = []

        match_entry = {
            "line": match.get("line", match.get("line_number", "?")),
            "text": match.get("text", match.get("line", "")),
            "positions": match.get("matches", match.get("submatches", [])),
        }
        file_groups[file_path].append(match_entry)
        total_matches += 1

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


# optimize_match_paths: implementation
def optimize_match_paths(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Optimize file paths in match results to reduce token consumption."""
    if not matches:
        return matches

    file_paths = [match.get("file", "") for match in matches if match.get("file")]
    common_prefix = ""
    if len(file_paths) > 1:
        try:
            common_prefix = os.path.commonpath(file_paths)
        except (ValueError, TypeError):
            common_prefix = ""

    optimized_matches = []
    for match in matches:
        optimized_match = match.copy()
        file_path = match.get("file")
        if file_path:
            optimized_match["file"] = _optimize_file_path(file_path, common_prefix)
        optimized_matches.append(optimized_match)

    return optimized_matches


# _optimize_file_path: implementation
def _optimize_file_path(file_path: str, common_prefix: str = "") -> str:
    """Optimize file path for token efficiency by removing common prefixes and shortening."""
    if not file_path:
        return file_path

    if common_prefix and file_path.startswith(common_prefix):
        optimized = file_path[len(common_prefix) :].lstrip("/\\")
        if optimized:
            return optimized

    path_obj = Path(file_path)
    parts = path_obj.parts

    if len(parts) > 4:
        return str(Path(parts[0]) / "..." / Path(*parts[-3:]))

    return file_path


def _group_matches_by_file(
    matches: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], str]:
    """Group matches by file path; return ``(groups, common_prefix)``.

    ``common_prefix`` is the longest shared filesystem prefix (empty when
    only one file is present). Used downstream to shorten display paths.
    """
    file_groups: dict[str, list[dict[str, Any]]] = {}
    all_file_paths: list[str] = []
    for match in matches:
        file_path = match.get("file", "unknown")
        all_file_paths.append(file_path)
        file_groups.setdefault(file_path, []).append(match)

    common_prefix = ""
    if len(all_file_paths) > 1:
        common_prefix = os.path.commonpath(all_file_paths)
    return file_groups, common_prefix


def _build_sample_lines(
    file_matches: list[dict[str, Any]], remaining_lines: int
) -> tuple[list[str], int]:
    """Return ``(sample_lines, lines_consumed)`` for up to 3 matches.

    Truncates each line to 60 chars and collapses whitespace; falls back
    to a "Found N matches" placeholder when no non-empty line text is
    present. ``lines_consumed`` debits the caller's overall line budget.
    """
    sample_lines: list[str] = []
    lines_to_include = min(3, remaining_lines, len(file_matches))
    consumed = 0
    for match in file_matches[:lines_to_include]:
        line_num = match.get("line", match.get("line_number", "?"))
        line_text = match.get("text", match.get("line", "")).strip()
        if not line_text:
            continue
        truncated = " ".join(line_text.split())[:60]
        if len(line_text) > 60:
            truncated += "..."
        sample_lines.append(f"L{line_num}: {truncated}")
        consumed += 1
    if not sample_lines and file_matches:
        sample_lines.append(f"Found {len(file_matches)} matches")
    return sample_lines, consumed


def _collect_top_files(
    file_groups: dict[str, list[dict[str, Any]]],
    common_prefix: str,
    max_files: int,
    max_total_lines: int,
) -> list[dict[str, Any]]:
    """Build the ``top_files`` rows ordered by descending match count.

    Stops once ``max_files`` files are emitted **or** the cumulative line
    budget (``max_total_lines``) is exhausted, whichever comes first.
    """
    sorted_files = sorted(file_groups.items(), key=lambda x: len(x[1]), reverse=True)
    top_files: list[dict[str, Any]] = []
    remaining_lines = max_total_lines
    for file_path, file_matches in sorted_files[:max_files]:
        sample_lines, consumed = _build_sample_lines(file_matches, remaining_lines)
        remaining_lines -= consumed
        top_files.append(
            {
                "file": _optimize_file_path(file_path, common_prefix),
                "match_count": len(file_matches),
                "sample_lines": sample_lines,
            }
        )
        if remaining_lines <= 0:
            break
    return top_files


def summarize_search_results(
    matches: list[dict[str, Any]], max_files: int = 10, max_total_lines: int = 50
) -> dict[str, Any]:
    """Summarize search results to reduce context size while preserving key information.

    r37ez (dogfood): 87 → ~15 lines of orchestration. ``_group_matches_by_file``
    splits the by-file index + common-prefix calc; ``_collect_top_files``
    builds the per-file rows (delegating sample-line truncation to
    ``_build_sample_lines``); this body composes the final envelope.
    """
    if not matches:
        return {
            "total_matches": 0,
            "total_files": 0,
            "summary": "No matches found",
            "top_files": [],
        }

    file_groups, common_prefix = _group_matches_by_file(matches)
    top_files = _collect_top_files(
        file_groups, common_prefix, max_files, max_total_lines
    )

    total_matches = len(matches)
    total_files = len(file_groups)
    if total_files <= max_files:
        summary = f"Found {total_matches} matches in {total_files} files"
    else:
        summary = (
            f"Found {total_matches} matches in {total_files} files "
            f"(showing top {len(top_files)})"
        )

    return {
        "total_matches": total_matches,
        "total_files": total_files,
        "summary": summary,
        "top_files": top_files,
        "truncated": total_files > max_files,
    }


# extract_file_list_from_count_data: implementation
def extract_file_list_from_count_data(count_data: dict[str, int]) -> list[str]:
    """Extract file list from count data, excluding the special __total__ key."""
    return [file_path for file_path in count_data.keys() if file_path != "__total__"]


# create_file_summary_from_count_data: implementation
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
        "derived_from_count": True,
    }
