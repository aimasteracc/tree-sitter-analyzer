"""String escaping helpers for :mod:`toon_encoder`."""

import re

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

# Matches strings that a TOON/JSON-spec decoder would parse as a non-string
# scalar.  Such strings MUST be quoted so the type round-trips correctly.
#
# Matches (in order):
#   bool literals   — "true" / "false" (case-sensitive, JSON spec)
#   null literal    — "null"
#   JSON number     — optional sign, integer part, optional fraction, optional
#                     exponent; covers "42", "-3", "100.0", "1e5", "1.5e-3",
#                     "1E5".  The regex mirrors RFC 8259 §6 (JSON numbers) and
#                     is anchored to the full string so "1abc" stays unquoted.
_SCALAR_PATTERN = re.compile(
    r"^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+\-]?\d+)?)$"
)


def needs_quotes(value: str, delimiter: str) -> bool:
    """Return whether a TOON string needs quoted escaping.

    A string requires quoting if it:
    - contains structural TOON characters (delimiter, braces, brackets, etc.)
    - would be mis-parsed as a scalar by a spec-compliant decoder (i.e. it
      looks like a bool literal, null, or JSON number).  Quoting is the only
      way to preserve the ``str`` type across an encode-decode round-trip.
    """
    if delimiter in value or any(char in value for char in _TOON_QUOTE_CHARS):
        return True
    # Quote strings that are ambiguous with TOON/JSON scalars.
    return bool(_SCALAR_PATTERN.match(value))


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
