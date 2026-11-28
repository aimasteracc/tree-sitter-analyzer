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
    from .callers_decorators import python_definition_table

    table = python_definition_table(text)
    if table is None:
        return set()
    return {
        header
        for name, first, header, _decorators in table
        if name == bare and any(first <= line <= header for line in recorded)
    }


def _tree_sitter_name_lines(
    text: str, recorded: frozenset[int], language: str, bare: str
) -> set[int]:
    table = _tree_sitter_declarations(text, language)
    return {
        name_line
        for name, start, name_line in table
        if name == bare and any(start <= line <= name_line for line in recorded)
    }


#: RFC-0043: one named declaration of a file: (name, first line, name line), 1-based.
_Declaration = tuple[str, int, int]


def _tree_sitter_declarations(text: str, language: str) -> tuple[_Declaration, ...]:
    """Every named declaration node of ``text``; empty when it cannot be parsed.

    RFC-0043: a pure function of the text, reused per content digest
    (:mod:`...resident.parse_facts`); no syntax tree is kept.
    """
    from ...resident import parse_facts

    return parse_facts.facts(
        "ts.declarations",
        language,
        text,
        lambda: _build_tree_sitter_declarations(text, language),
    )


def _build_tree_sitter_declarations(
    text: str, language: str
) -> tuple[_Declaration, ...]:
    from ...language_loader import create_parser_safely

    try:
        parser = create_parser_safely(language)
        if parser is None:
            return ()
        source = text.encode("utf-8")
        root = parser.parse(source).root_node
    except Exception:  # noqa: BLE001 — a grammar failure adds nothing (conservative)
        return ()
    found: list[_Declaration] = []
    stack: list[Any] = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if not str(node.type).endswith(_TS_DECLARATION_SUFFIXES):
            continue
        name = node.child_by_field_name("name")
        if name is None:
            continue
        found.append(
            (
                source[name.start_byte : name.end_byte].decode("utf-8", "replace"),
                int(node.start_point[0]) + 1,
                int(name.start_point[0]) + 1,
            )
        )
    return tuple(found)


__all__ = ["name_lines", "sole_occurrence", "without_header_names"]
