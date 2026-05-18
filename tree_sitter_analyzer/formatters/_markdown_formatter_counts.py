#!/usr/bin/env python3
"""Raw Markdown count helpers for parser variance compensation."""

from __future__ import annotations

import re

from ._markdown_formatter_elements import is_image_url


def compute_robust_counts_from_file(file_path: str) -> dict[str, int]:
    """Compute link and image counts directly from raw Markdown text."""
    counts = {"link_count": 0, "image_count": 0}
    if not file_path:
        return counts

    try:
        from ..encoding_utils import read_file_safe

        content, _ = read_file_safe(file_path)
    except Exception:
        return counts

    counts["link_count"] = count_markdown_links(content)
    counts["image_count"] = count_markdown_images(content)
    return counts


def count_markdown_links(content: str) -> int:
    """Count inline, reference, and autolink Markdown links."""
    inline_links_all = re.findall(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", content)
    inline_images = re.findall(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", content)
    ref_links_all = re.findall(r"\[[^\]]*\]\[[^\]]*\]", content)
    ref_images = re.findall(r"!\[[^\]]*\]\[[^\]]*\]", content)
    autolinks = len(autolink_pattern().findall(content))

    inline_links = max(0, len(inline_links_all) - len(inline_images))
    ref_links = max(0, len(ref_links_all) - len(ref_images))
    return inline_links + ref_links + autolinks


def autolink_pattern() -> re.Pattern[str]:
    """Return the Markdown autolink pattern."""
    return re.compile(r"<(?:https?://[^>]+|mailto:[^>]+|[^@\s]+@[^@\s]+\.[^@\s]+)>")


def count_markdown_images(content: str) -> int:
    """Count inline and reference Markdown images."""
    inline_images = re.findall(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", content)
    ref_images = re.findall(r"!\[[^\]]*\]\[[^\]]*\]", content)
    return len(inline_images) + len(ref_images) + count_used_image_definitions(content)


def count_used_image_definitions(content: str) -> int:
    """Count reference definitions used by image references or image-like URLs."""
    used_labels = image_reference_labels(content)
    image_ref_defs_used = 0
    for match in reference_definition_pattern().finditer(content):
        label = (match.group(1) or "").lower()
        url = (match.group(2) or "").lower()
        if label in used_labels or is_image_url(url):
            image_ref_defs_used += 1
    return image_ref_defs_used


def image_reference_labels(content: str) -> set[str]:
    """Return lowercased labels used by image references."""
    return {
        match.group(1).lower()
        for match in re.finditer(r"!\[[^\]]*\]\[([^\]]*)\]", content)
    }


def reference_definition_pattern() -> re.Pattern[str]:
    """Return the Markdown reference definition pattern."""
    return re.compile(r"^\[([^\]]+)\]:\s*([^\s]+)(?:\s+\"([^\"]*)\")?", re.MULTILINE)
