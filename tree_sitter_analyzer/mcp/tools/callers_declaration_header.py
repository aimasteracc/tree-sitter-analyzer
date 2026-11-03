"""PR-2: a declaration's own name is not a reference to it, wherever its header starts.

The non-call reference scan (#1593) skips the lines on which the index records a
declaration named like the target. The index records a declaration at the start
of its node, and for a Java method that is the first annotation or modifier:

.. code-block:: java

    @SuppressWarnings("fallthrough")          // line 805: the recorded line
    private void beforeValue() throws ... {   // line 806: the name

so line 806 was reported as a non-call reference to ``beforeValue`` and the answer
could never be ``complete`` (gson ``JsonWriter.beforeValue``, r15). The same holds
for a decorated Python ``def`` or class recorded at its first decorator.

The fix is deliberately narrower than "skip the whole header":

* only the line that holds the declaration's **name token** is added, and only for
  a declaration whose header (first decorator / annotation / modifier through the
  name) holds the recorded line and whose name is exactly the target's bare name;
* that line is skipped only when the name occurs on it **once** (that occurrence is
  the name token). A parameter default (``def f(x=f)``), an annotation argument or
  a body on the same line that mentions the name again keeps the line a
  reference. Lines after the name (the rest of the parameter list, the body) are
  never added.

Any read or parse failure adds nothing, which keeps the line a reference.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

#: Declaration node suffixes for tree-sitter grammars (same set as the decorator gate).
_TS_DECLARATION_SUFFIXES = ("declaration", "definition", "_item", "signature")
_PY_LANGUAGES = frozenset({"python"})


def name_lines(
    text: str, rows: Iterable[int], language: str, bare: str
) -> frozenset[int]:
    """Lines holding the name token of a ``bare`` declaration recorded at ``rows``.

    Only lines other than the recorded ones are returned (those are already
    skipped by the scan). Empty when the text cannot be parsed.
    """
    recorded = frozenset(rows)
    if not recorded:
        return frozenset()
    if language in _PY_LANGUAGES:
        found = _python_name_lines(text, recorded, bare)
    else:
        found = _tree_sitter_name_lines(text, recorded, language, bare)
    return frozenset(found - recorded)


def sole_occurrence(text_line: str, pattern: re.Pattern[str]) -> bool:
    """The (comment- and prose-stripped) line names the target exactly once."""
    return len(pattern.findall(text_line)) == 1


def without_header_names(
    lines: list[int],
    stripped_text: str,
    data: bytes,
    language: str,
    recorded: Iterable[int],
    pattern: re.Pattern[str],
    bare: str,
) -> list[int]:
    """``lines`` minus the name lines that hold only the declaration's own name.

    ``stripped_text`` is the scanned (comment- and prose-stripped, line-preserving)
    text; ``data`` the raw file bytes the declarations are parsed from.
    """
    names = name_lines(data.decode("utf-8", "replace"), recorded, language, bare)
    if not names:
        return lines
    stripped = stripped_text.split("\n")
    return [
        line
        for line in lines
        if not (
            line in names
            and line <= len(stripped)
            and sole_occurrence(stripped[line - 1], pattern)
        )
    ]


def _python_name_lines(text: str, recorded: frozenset[int], bare: str) -> set[int]:
    from .callers_decorators import _parsed_python, _python_definitions

    parsed = _parsed_python(text)
    if parsed is None:
        return set()
    found: set[int] = set()
    for first, header, node in _python_definitions(text, parsed[0]):
        if node.name != bare:
            continue
        if any(first <= line <= header for line in recorded):
            found.add(int(header))
    return found


def _tree_sitter_name_lines(
    text: str, recorded: frozenset[int], language: str, bare: str
) -> set[int]:
    from ...language_loader import create_parser_safely

    try:
        parser = create_parser_safely(language)
        if parser is None:
            return set()
        source = text.encode("utf-8")
        root = parser.parse(source).root_node
    except Exception:  # noqa: BLE001 — a grammar failure adds nothing (conservative)
        return set()
    found: set[int] = set()
    stack: list[Any] = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if not str(node.type).endswith(_TS_DECLARATION_SUFFIXES):
            continue
        name = node.child_by_field_name("name")
        if name is None:
            continue
        if source[name.start_byte : name.end_byte].decode("utf-8", "replace") != bare:
            continue
        start = int(node.start_point[0]) + 1
        name_line = int(name.start_point[0]) + 1
        if any(start <= line <= name_line for line in recorded):
            found.add(name_line)
    return found


__all__ = ["name_lines", "sole_occurrence", "without_header_names"]
