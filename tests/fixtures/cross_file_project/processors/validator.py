"""Validation utilities module."""


def is_valid_text(text):
    """Validate that text is not empty and contains valid characters.

    Args:
        text: Text to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not text or not isinstance(text, str):
        return False

    # Must contain at least one alphanumeric character
    return any(c.isalnum() for c in text)


def is_valid_email(email):
    """Validate email format (simple validation).

    Args:
        email: Email to validate

    Returns:
        bool: True if valid email format
    """
    return "@" in email and "." in email


def is_valid_length(text, min_len=1, max_len=1000):
    """Validate text length.

    Args:
        text: Text to validate
        min_len: Minimum length
        max_len: Maximum length

    Returns:
        bool: True if length is valid
    """
    if not text:
        return False
    return min_len <= len(text) <= max_len
