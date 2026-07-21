"""Scaladoc comment text parsing."""

from __future__ import annotations


def _parse_scaladoc_text(comment_text: str) -> str | None:
    """Convert raw ``/** ... */`` scaladoc to the cleaned multi-line string.

    Returns ``None`` when the block isn't a Scaladoc comment (must start
    with ``/**`` but not ``/***``) or yields no non-empty lines. Strips
    the opening ``/**`` and closing ``*/``, then trims each line and
    removes a leading ``*`` for the canonical multi-line Scaladoc shape.

    r37dw (dogfood): lifted from ``_extract_docstring`` to flatten the
    inner for/if chain from depth 6 to a pure transform.
    """
    if not comment_text.startswith("/**") or comment_text.startswith("/***"):
        return None
    content = comment_text[3:]
    if content.endswith("*/"):
        content = content[:-2]
    cleaned_lines: list[str] = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        if stripped:
            cleaned_lines.append(stripped)
    if not cleaned_lines:
        return None
    return "\n".join(cleaned_lines)
