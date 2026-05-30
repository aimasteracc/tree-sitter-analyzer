"""
README-reading helpers for project_index.

Functions here extract useful text from README files and apply
noise filtering to produce concise project descriptions.
"""

from __future__ import annotations

import re
from pathlib import Path


def _is_language_count_excluded(filepath: str) -> bool:
    """True if ``filepath`` should not influence language_distribution.

    Uses simple substring match against ``_LANGUAGE_COUNT_EXCLUDED_SEGMENTS``
    so it's both fast and platform-agnostic (works for ``/`` and ``\\``).
    """
    from ._models import _LANGUAGE_COUNT_EXCLUDED_SEGMENTS

    normalized = filepath.replace("\\", "/")
    return any(seg in normalized for seg in _LANGUAGE_COUNT_EXCLUDED_SEGMENTS)


def _clean_readme_line(line: str) -> str:
    """Strip markdown formatting and HTML tags from a README line.

    r37ct: lifted from a nested closure to flatten ``_extract_readme_excerpt``.
    """
    s = re.sub(r"<[^>]+>", "", line)
    s = re.sub(r"\*\*|(?<!\*)\*(?!\*)|`", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return s.strip()


def _is_readme_noise_line(line: str) -> bool:
    """Return True for README lines that are not useful descriptions.

    Noise categories: empty, heading, badge/shield, image, language-navigation
    tables (``|``-heavy), and code fence markers.
    """
    s = line.strip()
    if not s:
        return True
    if s.startswith("#"):
        return True
    # Badge / shield lines
    if "shields.io" in s or s.startswith("[!["):
        return True
    # Image lines
    if s.startswith("!["):
        return True
    # Language-navigation lines (many pipe characters)
    if s.count("|") >= 2:
        return True
    # Code fence lines
    if s.startswith("```") or s.startswith("~~~"):
        return True
    return False


def _excerpt_from_blockquotes(text: str) -> str:
    """First non-noise blockquote line in ``text``, cleaned and truncated.

    Returns empty string when no blockquote yields a useful line.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(">"):
            continue
        inner = stripped.lstrip(">").strip()
        if not inner or _is_readme_noise_line(inner):
            continue
        cleaned = _clean_readme_line(inner)
        if cleaned:
            return cleaned[:200]
    return ""


def _excerpt_from_paragraphs(text: str) -> str:
    """First non-noise non-blockquote line in ``text``, cleaned and truncated.

    Used as the fallback when ``_excerpt_from_blockquotes`` finds nothing.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if _is_readme_noise_line(stripped):
            continue
        cleaned = _clean_readme_line(stripped)
        if cleaned:
            return cleaned[:200]
    return ""


def _read_directory_readme_title(readme_path: Path) -> str:
    """Return the first meaningful line from a directory's README.md.

    Used by ``_describe_dir`` as the second-tier source for directory
    descriptions (after ``__init__.py`` docstring). Returns the heading
    text when the file starts with ``#`` headings, otherwise the first
    non-badge non-empty line. Empty string when the file is missing /
    unreadable / contains only noise.

    r37ct (dogfood): lifted out of ``_describe_dir`` to flatten nesting 7 → 2.
    """
    if not readme_path.is_file():
        return ""
    try:
        text = readme_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            # Extract title from heading, strip HTML
            title = re.sub(r"<[^>]+>", "", stripped.lstrip("#")).strip()
            if title:
                return title[:80]
            continue
        if stripped.startswith("[![") or "shields.io" in stripped:
            continue
        return re.sub(r"<[^>]+>", "", stripped).strip()[:80]
    return ""
