"""Hyphae lexer.

Mirrors mycelium-hyphae/src/lexer.rs. The prefix symbols ``#``/``.``/``:`` each
absorb the following identifier as their value (``#login`` → ``HASH("login")``),
which removes the ambiguity between ``.kind`` and a path like ``src/lib.rs``:
a leading ``.`` starts a DOT token, while ``.`` inside an IDENT (``src/lib.rs``)
is just part of the path.
"""

from __future__ import annotations

import string
from dataclasses import dataclass

# Characters allowed in a #name / .kind / :pseudo identifier.
_NAME_CHARS = frozenset(string.ascii_letters + string.digits + "_-")
# Characters allowed in a bare IDENT (attribute value / pseudo path arg): adds
# path separators ``/`` and ``.``.
_IDENT_CHARS = _NAME_CHARS | frozenset("./")

_SINGLE = {
    "*": "STAR",
    ">": "GT",
    "~": "TILDE",
    ",": "COMMA",
    "(": "LPAREN",
    ")": "RPAREN",
    "[": "LBRACKET",
    "]": "RBRACKET",
    "=": "EQ",
}


@dataclass(frozen=True)
class Token:
    """A lexical token. ``value`` carries the identifier for HASH/DOT/COLON/IDENT
    and the integer text for NUMBER; it is empty for structural tokens."""

    type: str
    value: str = ""


def _read_while(text: str, start: int, allowed: frozenset[str]) -> tuple[str, int]:
    i = start
    n = len(text)
    while i < n and text[i] in allowed:
        i += 1
    return text[start:i], i


def tokenize(text: str) -> list[Token]:
    """Tokenize a Hyphae selector string.

    Raises:
        ValueError: on an unexpected character.
    """
    tokens: list[Token] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            j = i
            while j < n and text[j].isspace():
                j += 1
            # Collapse runs of whitespace into a single WS (descendant combinator).
            tokens.append(Token("WS"))
            i = j
        elif ch == "#":
            name, i = _read_while(text, i + 1, _NAME_CHARS)
            tokens.append(Token("HASH", name))
        elif ch == ":":
            name, i = _read_while(text, i + 1, _NAME_CHARS)
            tokens.append(Token("COLON", name))
        elif ch == ".":
            # A leading dot is a .kind selector; absorb the kind name.
            name, i = _read_while(text, i + 1, _NAME_CHARS)
            tokens.append(Token("DOT", name))
        elif ch in _SINGLE:
            tokens.append(Token(_SINGLE[ch]))
            i += 1
        elif ch.isdigit():
            num, i = _read_while(text, i, frozenset("0123456789"))
            tokens.append(Token("NUMBER", num))
        elif ch in _IDENT_CHARS:
            ident, i = _read_while(text, i, _IDENT_CHARS)
            tokens.append(Token("IDENT", ident))
        else:
            raise ValueError(f"Hyphae lexer: unexpected character {ch!r} at {i}")
    tokens.append(Token("EOF"))
    return tokens
