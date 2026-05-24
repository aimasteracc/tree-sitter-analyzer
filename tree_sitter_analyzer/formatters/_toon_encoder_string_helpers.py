"""String escaping helpers for :mod:`toon_encoder`."""

_TOON_QUOTE_CHARS = (
    "\n",
    "\r",
    "\t",
    "\\",
    ":",
    "{",
    "}",
    "[",
    "]",
    '"',
)


def needs_quotes(value: str, delimiter: str) -> bool:
    """Return whether a TOON string needs quoted escaping."""
    return delimiter in value or any(char in value for char in _TOON_QUOTE_CHARS)


def escape_string(value: str) -> str:
    """Escape a TOON string for quoted output."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
