"""#1884: a Java method may override a supertype method without ``@Override``.

``@Override`` is optional in Java. PR-2's override gate
(:mod:`.callers_java_overrides`) ran only on annotated methods, so in

.. code-block:: java

    abstract class A<T> { T run() { return make(); } abstract T make(); }
    class B extends A<String> { String make() { return "b"; } }  // no @Override

``B.make`` answered ``complete`` with 0 callers, although ``make()`` in
``A.run`` dispatches to it: the call edge is bound to ``A.make``, and the index
has no ``extends`` edge for the generic supertype ``A<String>`` (#1880) that
could offer the override.

The ``supertype_dispatch`` check therefore runs the same proof
(:func:`~.callers_java_overrides.override_proof` with ``annotated=False``) on
every Java declaration row of the target that is a method which can override:

* static and private methods are skipped (they are hidden, not overridden), so
  are rows that are not a method (a constructor, a field, a type);
* a method of a named type without ``extends`` / ``implements`` is skipped
  unless it is named like a ``java.lang.Object`` method (every class inherits
  them); an anonymous class body or an enum constant body always has a
  supertype;
* otherwise the method passes only when every supertype resolves in the project
  and none declares the name, or one does and every call edge named like it is
  bound to this declaration or outside the project. Anything else is
  ``OVERRIDE_DISPATCH``, with the proof's reason in ``next_step``.

A file that cannot be read or parsed leaves the check not run
(``DYNAMIC_SUPERTYPE`` with ``unchecked``). For a qualified target, rows of
other types in the same file (``Outer.go`` vs ``Outer.In.go``) are skipped when
a row of the target's own type exists.
"""

from __future__ import annotations

import os
from typing import Any

from .callers_java_overrides import (
    OBJECT_METHODS,
    OVERRIDE_REASON,
    _direct_supertypes,
    _method_at,
    _name,
    _owner_type,
    _parse,
    override_proof,
)
from .callers_java_subtypes import SUBTYPE_VERB, subtype_proof
from .callers_supertypes import SupertypeFinding
from .evidence_file_cache import FILE_CACHE

#: Modifiers that make a method impossible to override.
_NOT_OVERRIDABLE = frozenset({"static", "private"})
#: Owner bodies that always have a supertype.
_ANONYMOUS = frozenset({"object_creation_expression", "enum_constant"})
_JAVA_SUFFIX = ".java"


def java_supertype_finding(
    project_root: str,
    declarations: list[tuple[str, int, str]],
    bare: str,
    cache: Any,
    owner: str = "",
) -> SupertypeFinding | None:
    """The first Java row of ``bare`` that may override a supertype method."""
    wanted = owner.rpartition(".")[2]
    results: list[tuple[str | None, SupertypeFinding | None]] = []
    for rel, line, _language in declarations:
        if not rel.lower().endswith(_JAVA_SUFFIX):
            continue
        results.append(_row_finding(project_root, rel, line, bare, cache))
    own = [found for name, found in results if wanted and name == wanted]
    candidates = own if own else [found for _name, found in results]
    unread = [found for _n, found in results if found is not None and found.unchecked]
    return next((f for f in [*unread, *candidates] if f is not None), None)


def _row_finding(
    project_root: str, rel: str, line: int, bare: str, cache: Any
) -> tuple[str | None, SupertypeFinding | None]:
    """``(owner type name, finding)`` of one declaration row."""
    text = FILE_CACHE.read_text(os.path.join(project_root, rel))
    if text is None:
        return None, _unchecked(rel, "the declaring file could not be read")
    parsed = _parse(text)
    if parsed is None:
        return None, _unchecked(rel, "the declaring file could not be parsed")
    method = _method_at(parsed, line, bare)
    if method is None or _modifiers(parsed.source, method) & _NOT_OVERRIDABLE:
        return None, None
    owner = _owner_type(method)
    name = None if owner is None else _name(parsed, owner)
    if owner is None or _has_supertype(owner) or bare in OBJECT_METHODS:
        proof = override_proof(
            cache, project_root, rel, text, line, bare, annotated=False
        )
        if not proof.proved:
            return name, _override_finding(bare, rel, line, name, proof.detail)
    # #1894: a subtype may inherit it as the method of another of its supertypes.
    subtype, inherited = subtype_proof(cache, project_root, rel, text, line, bare)
    if inherited.proved:
        return name, None
    if not subtype:
        return name, _override_finding(bare, rel, line, name, inherited.detail)
    return name, _override_finding(
        subtype, rel, line, name, inherited.detail, verb=SUBTYPE_VERB
    )


def _override_finding(
    clause: str,
    rel: str,
    line: int,
    name: str | None,
    detail: str,
    verb: str = "declares",
) -> SupertypeFinding:
    return SupertypeFinding(
        clause,
        rel,
        line,
        name or "<anonymous>",
        detail,
        verb=verb,
        reason=OVERRIDE_REASON,
    )


def _has_supertype(owner: Any) -> bool:
    return owner.type in _ANONYMOUS or bool(_direct_supertypes(owner))


def _modifiers(source: bytes, method: Any) -> set[str]:
    found: set[str] = set()
    for child in method.children:
        if child.type == "modifiers":
            found.update(
                source[part.start_byte : part.end_byte].decode("utf-8", "replace")
                for part in child.children
            )
    return found


def _unchecked(rel: str, why: str) -> SupertypeFinding:
    return SupertypeFinding("", rel, 0, "", why, unchecked=True)


__all__ = ["java_supertype_finding"]
