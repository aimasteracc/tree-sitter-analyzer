"""#1941: a method that may override a method of a class outside the project.

``nav action=callers`` counts the call sites *in the project*. Its supertype gate
stops at a known external base (``io.RawIOBase``, ``logging.Handler``): no
project call can dispatch through it, so ``_Reader.writable`` answers
``complete`` with 0 callers. That is a true statement about project callers and
a false one about liveness -- the standard library calls ``writable()`` on the
reader. A dead-code list must not claim it.

:func:`external_override` walks the declaring class and every project class
above it (with the import resolver of :mod:`.callers_py_supertypes`) and names
the first base that is not a project class, unless that base cannot dispatch to
a subclass method by name (``object``, ``ABC``, ``Generic``). A base the
resolver cannot follow blocks the claim too. Members of other languages are not
walked: :data:`OVERRIDE_UNCHECKED_REASON` says so instead of certifying them.
"""

from __future__ import annotations

import ast
from collections.abc import Callable

from .callers_py_supertypes import (
    PY_SUFFIX,
    _base_value,
    _Class,
    _owner_class,
    _Reader,
    _scopes_for,
)

#: The member's class has (or may have) a base outside the project.
EXTERNAL_SUPERTYPE_REASON = "EXTERNAL_SUPERTYPE"
#: The member's class chain was not walked (a language without this check).
OVERRIDE_UNCHECKED_REASON = "OVERRIDE_UNCHECKED"
#: External bases that never call a subclass method by name.
_INERT_BASES = frozenset(
    {
        "object",
        "ABC",
        "abc.ABC",
        "Generic",
        "typing.Generic",
        "typing_extensions.Generic",
    }
)
#: Project classes visited in one walk.
_CLASSES_MAX = 64


def external_override(
    project_root: str,
    rel: str,
    line: int,
    bare: str,
    tops: Callable[[], frozenset[str] | None],
) -> str | None:
    """Why ``bare`` (declared at ``rel:line``) may be called from outside the project.

    ``None`` when it is not a class member, or every base above its class is a
    project class or an inert external one.
    """
    if not rel.lower().endswith(PY_SUFFIX):
        return None
    reader = _Reader(project_root, tops)
    module = reader.module(rel)
    if module is None:
        return "the declaring file could not be read or parsed"
    owner = _owner_class(module, line, bare)
    if owner is None:
        return None
    stack = [_Class(module, owner)]
    seen: set[tuple[str, int]] = set()
    while stack:
        cls = stack.pop()
        key = (cls.module.rel, id(cls.node))
        if key in seen:
            continue
        if len(seen) >= _CLASSES_MAX:
            return f"class `{owner.name}` has too many bases to follow"
        seen.add(key)
        found, bases = _bases(reader, cls)
        if found is not None:
            return found
        stack.extend(bases)
    return None


def _bases(reader: _Reader, cls: _Class) -> tuple[str | None, list[_Class]]:
    scopes = _scopes_for(cls.module, cls.node)
    bases: list[_Class] = []
    for expr in cls.node.bases:
        try:
            value = _base_value(reader, cls.module, scopes, expr)
        except RecursionError:
            value = "a base too deeply nested to follow"
        if isinstance(value, _Class):
            bases.append(value)
            continue
        clause = _clause(expr)
        where = f"class `{cls.node.name}` ({cls.module.rel}:{cls.node.lineno})"
        if value is None:
            if clause in _INERT_BASES:
                continue
            return f"{where} has external base `{clause}`", []
        why = value if isinstance(value, str) else "a module, not a class"
        return f"{where} has base `{clause}`, {why}", []
    return None, bases


def _clause(expr: ast.expr) -> str:
    target = expr.value if isinstance(expr, ast.Subscript) else expr
    return " ".join(ast.unparse(target).split())[:80]


__all__ = [
    "EXTERNAL_SUPERTYPE_REASON",
    "OVERRIDE_UNCHECKED_REASON",
    "external_override",
]
