"""RFC-0043 Phase C: which names a Python text spells in a class header or a rename.

The subclass search of :mod:`.callers_py_class_index` (#1896) keeps, among the
files whose text contains one of the wanted names, those where a name appears
in a class header or a module-level assignment (``shape="header"``), or in a
rename (``shape="rename"``). It did that with one regular expression over the
whole text, per file and per request: on pydantic the largest share of the
Python subtype gate's warm cost.

For one shape, whether :func:`shape_pattern` matches ``names`` is whether one
of the names is in the set :func:`spelled_words` reads from the text (a match
of an alternation is a match of one of its branches, and the set collects
every word each branch can match). The set is a pure function of the text and
is kept per content digest (:mod:`...resident.parse_facts`); the text is still
read live on every request. ``tests/unit/mcp/tools/test_callers_py_shapes.py``
compares the two for every word of a corpus of texts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: ``class C(`` up to its bases; the bases run to the first ``:`` after it.
_CLASS_OPEN = re.compile(r"\bclass\s+\w+\s*\(")
#: A module-level assignment (annotation allowed); group 1 is its value up to
#: the next ``=`` or the end of the line.
_ASSIGNED = re.compile(r"^\w+[ \t]*(?::[^=\n]*)?=([^=\n]*)", re.MULTILINE)
#: A name followed by ``as`` and another name (``import X as Y``).
_RENAMED = re.compile(r"\b\w+(?=\s+as\s+\w)")
#: ``Y = X`` / ``Y = m.X`` alone on a line (a trailing comment allowed).
_REBOUND = re.compile(
    r"^[ \t]*\w+[ \t]*=[ \t]*(?:[\w.]+\.)?(\w+)[ \t]*(?:#.*)?$", re.MULTILINE
)
_WORD = re.compile(r"\w+")
SHAPES = ("header", "rename")


def shape_pattern(names: list[str], shape: str) -> re.Pattern[str]:
    """The expression a file must match for ``names`` (the reference)."""
    alternation = "|".join(map(re.escape, names))
    if shape == "rename":
        return re.compile(
            rf"\b(?:{alternation})\s+as\s+\w"
            rf"|^[ \t]*\w+[ \t]*=[ \t]*(?:[\w.]+\.)?(?:{alternation})[ \t]*(?:#.*)?$",
            re.MULTILINE,
        )
    # A class header naming it, or a module-level assignment naming it
    # (``Base = mix(A)``: only module-level bindings are read).
    return re.compile(
        rf"\bclass\s+\w+\s*\([^:]*?\b(?:{alternation})\b"
        rf"|^\w+[ \t]*(?::[^=\n]*)?=[^=\n]*\b(?:{alternation})\b",
        re.MULTILINE,
    )


def spelled_words(text: str, shape: str) -> frozenset[str]:
    """Every word :func:`shape_pattern` can match in ``text`` (live, no memo)."""
    words: set[str] = set()
    if shape == "rename":
        words.update(_RENAMED.findall(text))
        words.update(_REBOUND.findall(text))
        return frozenset(words)
    for opening in _CLASS_OPEN.finditer(text):
        start = opening.end()
        colon = text.find(":", start)
        words.update(_WORD.findall(text, start, colon if colon >= 0 else len(text)))
    for value in _ASSIGNED.findall(text):
        words.update(_WORD.findall(value))
    return frozenset(words)


def mentions(text: str, names: Iterable[str], shape: str) -> bool:
    """Whether ``text`` names one of ``names`` in ``shape`` (memoized per digest)."""
    from ...resident import parse_facts

    wanted = sorted(set(names))
    if not wanted:
        return False
    if not parse_facts.enabled():
        return shape_pattern(wanted, shape).search(text) is not None
    words = parse_facts.facts(
        "py.shape_words", "python", text, lambda: spelled_words(text, shape), (shape,)
    )
    return not words.isdisjoint(wanted)


__all__ = ["SHAPES", "mentions", "shape_pattern", "spelled_words"]
