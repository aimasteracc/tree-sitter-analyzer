"""JSON loading and text diff helpers for analyze_differences."""

import difflib
import json
from pathlib import Path
from typing import Any


def analyze_text_difference(
    file_a: Path, file_b: Path, version_a: str, version_b: str
) -> dict[str, Any]:
    """Analyze a text file difference."""
    try:
        content_a = file_a.read_text(encoding="utf-8")
        content_b = file_b.read_text(encoding="utf-8")
    except Exception as exc:
        return {"type": "file_read_error", "error": str(exc), "severity": "high"}

    if content_a == content_b:
        return {"type": "identical", "severity": "none"}

    diff_lines = _unified_diff_lines(
        content_a, content_b, file_a, file_b, version_a, version_b
    )
    added_lines = _count_diff_lines(diff_lines, "+", "+++")
    removed_lines = _count_diff_lines(diff_lines, "-", "---")

    return {
        "type": "text_difference",
        "added_lines": added_lines,
        "removed_lines": removed_lines,
        "diff": "".join(diff_lines),
        "severity": "medium" if added_lines + removed_lines > 10 else "low",
    }


def load_json_pair(file_a: Path, file_b: Path) -> tuple[Any, Any] | dict[str, Any]:
    """Load two JSON files or return the legacy error payload."""
    try:
        return json.loads(file_a.read_text(encoding="utf-8")), json.loads(
            file_b.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        return {"type": "json_parse_error", "error": str(exc), "severity": "high"}
    except Exception as exc:
        return {"type": "file_read_error", "error": str(exc), "severity": "high"}


def _unified_diff_lines(
    content_a: str,
    content_b: str,
    file_a: Path,
    file_b: Path,
    version_a: str,
    version_b: str,
) -> list[str]:
    return list(
        difflib.unified_diff(
            content_a.splitlines(keepends=True),
            content_b.splitlines(keepends=True),
            fromfile=f"v{version_a}/{file_a.name}",
            tofile=f"v{version_b}/{file_b.name}",
        )
    )


def _count_diff_lines(diff_lines: list[str], prefix: str, excluded_prefix: str) -> int:
    return sum(
        1
        for line in diff_lines
        if line.startswith(prefix) and not line.startswith(excluded_prefix)
    )
