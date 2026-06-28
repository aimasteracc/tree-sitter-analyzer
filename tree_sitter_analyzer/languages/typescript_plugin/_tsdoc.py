"""TSDoc extraction helpers for the TypeScript extractor."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

from ...utils import log_debug

Cleaner: TypeAlias = Callable[[str], str]


def extract_tsdoc_for_line(
    content_lines: list[str],
    target_line: int,
    tsdoc_cache: dict[int, str],
    clean_tsdoc: Cleaner,
) -> str | None:
    """Extract TSDoc comment immediately before the specified line."""
    if target_line in tsdoc_cache:
        return tsdoc_cache[target_line]

    try:
        if not content_lines or target_line <= 1:
            return None

        current_line = _previous_content_line(content_lines, target_line)
        if current_line <= 0:
            tsdoc_cache[target_line] = ""
            return None

        line = content_lines[current_line - 1].strip()
        if line.startswith("/**") and line.endswith("*/"):
            return _cache_cleaned_tsdoc(line, target_line, tsdoc_cache, clean_tsdoc)
        if line.endswith("*/"):
            return _extract_multiline_tsdoc(
                content_lines, current_line, target_line, tsdoc_cache, clean_tsdoc
            )

        tsdoc_cache[target_line] = ""
        return None
    except Exception as e:
        log_debug(f"Failed to extract TSDoc: {e}")
        return None


def clean_tsdoc(tsdoc_text: str) -> str:
    """Clean TSDoc text by removing comment markers."""
    if not tsdoc_text:
        return ""

    cleaned_lines = []
    for line in tsdoc_text.split("\n"):
        line = _strip_tsdoc_marker(line)
        if line:
            cleaned_lines.append(line)

    return " ".join(cleaned_lines) if cleaned_lines else ""


def _previous_content_line(content_lines: list[str], target_line: int) -> int:
    current_line = target_line - 1

    while current_line > 0:
        line = content_lines[current_line - 1].strip()
        if line:
            break
        current_line -= 1

    return current_line


def _extract_multiline_tsdoc(
    content_lines: list[str],
    current_line: int,
    target_line: int,
    tsdoc_cache: dict[int, str],
    clean_tsdoc: Cleaner,
) -> str | None:
    tsdoc_lines = [content_lines[current_line - 1]]
    current_line -= 1

    while current_line > 0:
        line_content = content_lines[current_line - 1]
        tsdoc_lines.append(line_content)

        if line_content.strip().startswith("/**"):
            tsdoc_lines.reverse()
            tsdoc_text = "\n".join(tsdoc_lines)
            return _cache_cleaned_tsdoc(
                tsdoc_text, target_line, tsdoc_cache, clean_tsdoc
            )
        current_line -= 1

    tsdoc_cache[target_line] = ""
    return None


def _cache_cleaned_tsdoc(
    tsdoc_text: str,
    target_line: int,
    tsdoc_cache: dict[int, str],
    clean_tsdoc: Cleaner,
) -> str:
    cleaned = clean_tsdoc(tsdoc_text)
    tsdoc_cache[target_line] = cleaned
    return cleaned


def _strip_tsdoc_marker(line: str) -> str:
    line = line.strip()
    if line.startswith("/**"):
        return line[3:].strip()
    if line.startswith("*/"):
        return line[2:].strip()
    if line.startswith("*"):
        return line[1:].strip()
    return line
