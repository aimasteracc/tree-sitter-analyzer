"""TQL selector boundary: parse, validate, and classify predicates.

The Hyphae evaluator raises on an unknown pseudo-class only when it reaches
it, and silently returns nothing for an unknown ``[attribute=...]`` (#RFC-0041
§4 finding). This module rejects both at parse time with a did-you-mean fix,
so a typo can never look like an empty answer.

It also classifies each predicate for completeness (RFC-0041 §3): attribute,
path, position and containment predicates are evaluated exhaustively over the
indexed symbol rows; edge, temporal, rule and branch predicates read relation
or history tables that carry no coverage proof, so a selector using them can
never make its stage ``complete``. The relation stages (``callers()`` ...)
are the proof-carrying way to ask those questions.
"""

from __future__ import annotations

import difflib

from ..hyphae.ast import Combined, PseudoClass, SelectorList, SimpleSelector
from ..hyphae.parser import HyphaeSyntaxError, parse
from .errors import (
    SELECTOR_SYNTAX,
    UNKNOWN_PSEUDO_CLASS,
    Err,
    Ok,
    QueryError,
    Result,
)

#: Pseudo-classes the evaluator implements and whose answer is exhaustive over
#: the symbol rows of the index.
EXHAUSTIVE_PSEUDOS = frozenset(
    {"in", "not", "has", "nth-child", "first-child", "only-child"}
)
#: Pseudo-classes backed by relation/history tables without a coverage proof.
UNPROVEN_PSEUDOS = frozenset(
    {
        "calls",
        "callees",
        "called-by",
        "extends",
        "implements",
        "subclasses",
        "imports",
        "reaches",
        "hot",
        "recently_modified",
        "stale",
        "hotspot",
        "violates",
        "branch",
    }
)
KNOWN_PSEUDOS = EXHAUSTIVE_PSEUDOS | UNPROVEN_PSEUDOS
KNOWN_ATTRIBUTES = frozenset({"file", "language", "class", "kind"})

#: Relation stage that answers an unproven edge pseudo-class with coverage.
_RELATION_FOR = {
    "calls": "symbol('X').callers()",
    "reaches": "symbol('X').callers(depth=N)",
    "callees": "symbol('X').callees()",
    "called-by": "symbol('X').callees()",
}


def parse_selector(text: str) -> Result[SelectorList]:
    """Parse and validate a TQL selector."""
    try:
        selector = parse(text)
    except (HyphaeSyntaxError, ValueError) as exc:
        return Err(
            QueryError(
                SELECTOR_SYNTAX,
                f"TQL syntax error: {exc}",
                fragment=text[:200],
                suggestion=(
                    "Selectors look like '.function:in(src/)', '#Name', "
                    "'.class:has(#method)'; call search action=tql_schema "
                    "for the grammar."
                ),
            )
        )
    problem = _validate(selector, text)
    if problem is not None:
        return Err(problem)
    return Ok(selector)


def _validate(selector: SelectorList, text: str) -> QueryError | None:
    for simple in _simple_selectors(selector):
        for attr in simple.attributes:
            if attr.name not in KNOWN_ATTRIBUTES:
                return _unknown(
                    f"[{attr.name}=...]",
                    attr.name,
                    KNOWN_ATTRIBUTES,
                    text,
                    kind="attribute",
                )
        for pc in simple.pseudo_classes:
            if pc.name not in KNOWN_PSEUDOS:
                return _unknown(f":{pc.name}", pc.name, KNOWN_PSEUDOS, text)
    return None


def _unknown(
    fragment: str,
    name: str,
    known: frozenset[str],
    text: str,
    *,
    kind: str = "pseudo-class",
) -> QueryError:
    close = difflib.get_close_matches(name, sorted(known), n=1)
    fixed = None
    if close:
        old = f"[{name}=" if kind == "attribute" else f":{name}"
        new = f"[{close[0]}=" if kind == "attribute" else f":{close[0]}"
        fixed = text.replace(old, new, 1)
    known_list = ", ".join(sorted(known))
    return QueryError(
        UNKNOWN_PSEUDO_CLASS if kind == "pseudo-class" else SELECTOR_SYNTAX,
        f"unknown {kind} {fragment!r}; known: {known_list}",
        fragment=fragment,
        suggestion=f"Did you mean {close[0]!r}?" if close else None,
        fixed_query=fixed,
    )


def _simple_selectors(selector: SelectorList) -> list[SimpleSelector]:
    out: list[SimpleSelector] = []

    def walk_selector(node: SimpleSelector | Combined) -> None:
        if isinstance(node, Combined):
            walk_selector(node.left)
            walk_selector(node.right)
            return
        out.append(node)
        for pc in node.pseudo_classes:
            if isinstance(pc.arg, SelectorList):
                for inner in pc.arg.selectors:
                    walk_selector(inner)

    for sel in selector.selectors:
        walk_selector(sel)
    return out


def unproven_predicates(selector: SelectorList) -> tuple[str, ...]:
    """Unproven pseudo-class names used anywhere in ``selector`` (sorted)."""
    names = {
        pc.name
        for simple in _simple_selectors(selector)
        for pc in simple.pseudo_classes
        if pc.name in UNPROVEN_PSEUDOS
    }
    return tuple(sorted(names))


def relation_hint(names: tuple[str, ...]) -> str | None:
    """The proof-carrying relation stage for the first edge pseudo, if any."""
    for name in names:
        if name in _RELATION_FOR:
            return (
                f":{name} reads call edges without a coverage proof; "
                f"{_RELATION_FOR[name]} answers the same question with "
                "nav-callers completeness."
            )
    return None


def name_selector(name: str, *, cls: str | None, file: str | None) -> SelectorList:
    """``#name[class=cls][file=file]`` built as an AST (no text round-trip)."""
    from ..hyphae.ast import AttributeSelector

    attrs: list[AttributeSelector] = []
    if cls:
        attrs.append(AttributeSelector("class", cls))
    if file:
        attrs.append(AttributeSelector("file", file))
    return SelectorList((SimpleSelector(("name", name), tuple(attrs), ()),))


__all__ = [
    "EXHAUSTIVE_PSEUDOS",
    "KNOWN_ATTRIBUTES",
    "KNOWN_PSEUDOS",
    "UNPROVEN_PSEUDOS",
    "PseudoClass",
    "name_selector",
    "parse_selector",
    "relation_hint",
    "unproven_predicates",
]
