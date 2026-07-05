"""JSDoc extraction helpers for the JavaScript extractor."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

from ...utils import log_debug

Cleaner: TypeAlias = Callable[[str], str]


def extract_jsdoc_for_line(
    content_lines: list[str],
    target_line: int,
    jsdoc_cache: dict[int, str],
    clean_jsdoc: Cleaner,
) -> str | None:
    """Extract JSDoc comment immediately before the specified line."""
    if target_line in jsdoc_cache:
        return jsdoc_cache[target_line]

    try:
        if not content_lines or target_line <= 1:
            return None

        current_line = _previous_content_line(content_lines, target_line)
        if current_line <= 0:
            jsdoc_cache[target_line] = ""
            return None

        line = content_lines[current_line - 1].strip()
        if line.startswith("/**") and line.endswith("*/"):
            return _cache_cleaned_jsdoc(line, target_line, jsdoc_cache, clean_jsdoc)
        if line.endswith("*/"):
            return _extract_multiline_jsdoc(
                content_lines,
                current_line,
                target_line,
                jsdoc_cache,
                clean_jsdoc,
            )

        jsdoc_cache[target_line] = ""
        return None
    except Exception as e:
        log_debug(f"Failed to extract JSDoc: {e}")
        return None


def clean_jsdoc(jsdoc_text: str) -> str:
    """Clean JSDoc text by removing comment markers."""
    if not jsdoc_text:
        return ""

    cleaned_lines = []
    for line in jsdoc_text.split("\n"):
        line = _strip_jsdoc_marker(line)
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


def _extract_multiline_jsdoc(
    content_lines: list[str],
    current_line: int,
    target_line: int,
    jsdoc_cache: dict[int, str],
    clean_jsdoc: Cleaner,
) -> str | None:
    jsdoc_lines = [content_lines[current_line - 1]]
    current_line -= 1

    while current_line > 0:
        line_content = content_lines[current_line - 1]
        jsdoc_lines.append(line_content)

        if line_content.strip().startswith("/**"):
            jsdoc_lines.reverse()
            jsdoc_text = "\n".join(jsdoc_lines)
            return _cache_cleaned_jsdoc(
                jsdoc_text,
                target_line,
                jsdoc_cache,
                clean_jsdoc,
            )
        current_line -= 1

    jsdoc_cache[target_line] = ""
    return None


def _cache_cleaned_jsdoc(
    jsdoc_text: str,
    target_line: int,
    jsdoc_cache: dict[int, str],
    clean_jsdoc: Cleaner,
) -> str:
    cleaned = clean_jsdoc(jsdoc_text)
    jsdoc_cache[target_line] = cleaned
    return cleaned


def _strip_jsdoc_marker(line: str) -> str:
    line = line.strip()
    if line.startswith("/**"):
        return line[3:].strip()
    if line.startswith("*/"):
        return line[2:].strip()
    if line.startswith("*"):
        return line[1:].strip()
    return line
