"""Text processing utilities module."""

from .validator import is_valid_text


def clean_text(text):
    """Clean and normalize text.

    Cross-file calls:
    - is_valid_text() from processors/validator.py (relative import)

    Same-file calls:
    - _sanitize() (private function)

    Args:
        text: Text to clean

    Returns:
        str: Cleaned text
    """
    if not is_valid_text(text):
        return ""

    # Sanitize the text
    sanitized = _sanitize(text)

    # Normalize whitespace
    normalized = " ".join(sanitized.split())

    return normalized


def _sanitize(text):
    """Sanitize text by removing special characters (private helper).

    Args:
        text: Text to sanitize

    Returns:
        str: Sanitized text
    """
    # Remove special characters (simple implementation)
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")
    return "".join(c for c in text if c in allowed_chars)


def format_text(text, max_length=100):
    """Format text to specific length.

    Args:
        text: Text to format
        max_length: Maximum length

    Returns:
        str: Formatted text
    """
    cleaned = clean_text(text)
    if len(cleaned) > max_length:
        return cleaned[:max_length] + "..."
    return cleaned
