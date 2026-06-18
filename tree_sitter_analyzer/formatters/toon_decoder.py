"""TOON scalar decoder — inverse of :mod:`toon_encoder` for single values.

Scope (PR1 / issue #1058)
--------------------------
This module decodes the *scalar* tokens that :class:`~toon_encoder.ToonEncoder`
emits via ``encode_value``.  It is the minimum decoder needed to make a
round-trip oracle property hold: ``decode_toon(encode_toon(x)) == x`` for
every primitive the encoder produces.

Supported input shapes
----------------------
- ``null``           → ``None``
- ``true`` / ``false`` → ``bool``
- bare integer       → ``int``   (e.g. ``42``, ``-3``)
- bare float/sci     → ``float`` (e.g. ``3.14``, ``1e5``)
- ``"quoted string"`` → ``str``  (with ``\\n``, ``\\t``, ``\\r``, ``\\\\``,
                                  ``\\"`` escape sequences resolved)
- bare word          → ``str``

Out of scope (deferred to RFC-0018 / later PRs)
------------------------------------------------
- Full dict / list / array-table parsing.  That requires a context-sensitive
  line-oriented parser and belongs in the RFC-0018 surface-normalization work.
  Do NOT add dict/list parsing here without an RFC.
"""

from __future__ import annotations

import re

__all__ = ["ToonDecodeError", "decode_toon"]


class ToonDecodeError(Exception):
    """Raised when a TOON token cannot be decoded."""


# Regex matching a JSON-number token (same grammar as _SCALAR_PATTERN in the
# encoder helpers, kept in sync).
_NUMBER_PATTERN = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+\-]?\d+)?$")

# Escape sequences the encoder produces inside quoted strings.
_UNESCAPE_MAP: dict[str, str] = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "\\": "\\",
    '"': '"',
}


def _unescape(s: str) -> str:
    """Resolve backslash escape sequences inside a quoted TOON string.

    Only the sequences that :func:`~._toon_encoder_string_helpers.escape_string`
    produces are handled: ``\\n``, ``\\r``, ``\\t``, ``\\\\``, ``\\"``.
    Any other ``\\X`` is left verbatim (pass-through).
    """
    result: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            next_ch = s[i + 1]
            result.append(_UNESCAPE_MAP.get(next_ch, next_ch))
            i += 2
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def decode_toon(token: str) -> object:
    """Decode a single TOON scalar token to the corresponding Python value.

    This is the inverse of ``ToonEncoder.encode_value`` for scalar inputs.

    Args:
        token: A TOON-encoded scalar string as produced by the encoder.

    Returns:
        The decoded Python value: ``None``, ``bool``, ``int``, ``float``,
        or ``str``.

    Raises:
        ToonDecodeError: If the token is structurally invalid (e.g. an
            unterminated quoted string).
    """
    # Quoted string — highest priority so "true" stays str, not bool.
    if token.startswith('"'):
        if not token.endswith('"') or len(token) < 2:
            raise ToonDecodeError(f"Unterminated quoted string token: {token!r}")
        inner = token[1:-1]
        return _unescape(inner)

    # Null literal — nosec B105: "null" is a TOON keyword, not a password
    if token == "null":  # nosec B105
        return None

    # Bool literals (JSON-spec: lowercase only) — nosec B105: TOON keywords
    if token == "true":  # nosec B105
        return True
    if token == "false":  # nosec B105
        return False

    # Number — try int first, then float
    if _NUMBER_PATTERN.match(token):
        # If it contains '.', 'e', or 'E' it is a float; otherwise int.
        if "." in token or "e" in token or "E" in token:
            return float(token)
        return int(token)

    # Bare word → str
    return token
