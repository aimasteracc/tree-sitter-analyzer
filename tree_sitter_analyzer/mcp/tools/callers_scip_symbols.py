"""SCIP symbol strings: the subset of the grammar the callers evidence layer reads.

A global symbol is ``<scheme> <manager> <package> <version> <descriptors>``;
descriptors end in ``/`` (namespace), ``#`` (type), ``.`` (term), ``:`` (meta),
``!`` (macro), ``(disambiguator).`` (method), ``(name)`` (parameter) or
``[name]`` (type parameter). A name may be backtick-quoted (doubled backticks
escape one). ``local <id>`` symbols are document-local.

See https://github.com/sourcegraph/scip/blob/main/scip.proto (``Symbol``).
"""

from __future__ import annotations

from functools import lru_cache

#: Characters that end an unquoted descriptor name.
_STOP = frozenset("/#.:!([")

Descriptor = tuple[str, str, int]  # (kind, name, end offset in the symbol)


def is_local(symbol: str) -> bool:
    return symbol.startswith("local ")


def _read_name(text: str, i: int) -> tuple[str, int]:
    if text[i] == "`":
        j = i + 1
        out = []
        while j < len(text):
            if text[j] == "`":
                if j + 1 < len(text) and text[j + 1] == "`":
                    out.append("`")
                    j += 2
                    continue
                return "".join(out), j + 1
            out.append(text[j])
            j += 1
        return "".join(out), j
    j = i
    while j < len(text) and text[j] not in _STOP:
        j += 1
    return text[i:j], j


def _header(symbol: str) -> tuple[tuple[str, ...], int]:
    parts: list[str] = []
    current: list[str] = []
    i = 0
    while len(parts) < 4 and i < len(symbol):
        char = symbol[i]
        if char == " ":
            if i + 1 < len(symbol) and symbol[i + 1] == " ":
                current.append(" ")
                i += 2
                continue
            parts.append("".join(current))
            current = []
            i += 1
            continue
        current.append(char)
        i += 1
    return tuple(parts), i


def _closing(text: str, start: int, char: str) -> int:
    end = text.find(char, start)
    if end < 0:
        raise ValueError("unterminated descriptor")
    return end


@lru_cache(maxsize=65536)
def parse(symbol: str) -> tuple[tuple[str, ...], tuple[Descriptor, ...]] | None:
    """``(header, descriptors)``; ``None`` for local or unparseable symbols."""
    if not symbol or is_local(symbol):
        return None
    try:
        return _parse(symbol)
    except (ValueError, IndexError):
        return None


def _parse(symbol: str) -> tuple[tuple[str, ...], tuple[Descriptor, ...]]:
    header, base = _header(symbol)
    text = symbol[base:]
    out: list[Descriptor] = []
    k = 0
    while k < len(text):
        char = text[k]
        if char in "([":
            end = _closing(text, k, ")" if char == "(" else "]")
            kind = "param" if char == "(" else "typeparam"
            out.append((kind, text[k + 1 : end], base + end + 1))
            k = end + 1
            continue
        name, k = _read_name(text, k)
        if k >= len(text):
            out.append(("?", name, base + k))
            break
        suffix = text[k]
        if suffix == "(":
            k = _closing(text, k, ")") + 1
            if k < len(text) and text[k] == ".":
                k += 1
            out.append(("method", name, base + k))
            continue
        kind = {"/": "ns", "#": "type", ".": "term", ":": "meta", "!": "macro"}.get(
            suffix, "?"
        )
        k += 1
        out.append((kind, name, base + k))
    return header, tuple(out)


def last_name(symbol: str) -> str | None:
    parsed = parse(symbol)
    if not parsed or not parsed[1]:
        return None
    kind, name, _end = parsed[1][-1]
    return None if kind in ("param", "typeparam") else name


def last_kind(symbol: str) -> str | None:
    parsed = parse(symbol)
    return parsed[1][-1][0] if parsed and parsed[1] else None


def owner(symbol: str) -> str | None:
    """The innermost enclosing *type* of a member symbol, else ``None``.

    A member of a function or a variable (``f().inner().``) has no owner type.
    """
    parsed = parse(symbol)
    if not parsed or len(parsed[1]) < 2:
        return None
    for kind, _name, end in reversed(parsed[1][:-1]):
        if kind == "type":
            return symbol[:end]
        if kind in ("method", "term"):
            return None
    return None


def qual_names(symbol: str) -> list[str] | None:
    """Type / term / method names along the descriptor path (``['Text', 'join']``)."""
    parsed = parse(symbol)
    if not parsed:
        return None
    return [
        name for kind, name, _end in parsed[1] if kind in ("type", "term", "method")
    ]


def package(symbol: str) -> str | None:
    parsed = parse(symbol)
    return parsed[0][2] if parsed and len(parsed[0]) > 2 else None


__all__ = [
    "is_local",
    "last_kind",
    "last_name",
    "owner",
    "package",
    "parse",
    "qual_names",
]
