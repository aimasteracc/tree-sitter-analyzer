#!/usr/bin/env python3
"""
Text utility functions for safe text processing.
"""


def safe_preview(text: str | None, max_length: int = 50) -> str:
    """
    Safely truncate text to max_length characters.

    Handles:
    - None input (returns empty string)
    - Multi-line text (flattens newlines to spaces)
    - Unicode characters (no mid-character splits)
    - Long text (truncates with "..." suffix)

    Args:
        text: Input text to truncate (can be None)
        max_length: Maximum length (default 50)

    Returns:
        Truncated text string, never exceeds max_length

    Examples:
        >>> safe_preview("hello world", 50)
        'hello world'

        >>> safe_preview("a" * 100, 50)
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa...'

        >>> safe_preview("line1\\nline2\\nline3", 50)
        'line1 line2 line3'

        >>> safe_preview(None, 50)
        ''
    """
    if text is None:
        return ""

    # Flatten multi-line text to single line
    single_line = text.replace('\n', ' ').replace('\r', '').strip()

    # If under limit, return as-is
    if len(single_line) <= max_length:
        return single_line

    # Truncate with "..." suffix
    # Reserve 3 chars for "..."
    return single_line[:max_length - 3] + "..."
