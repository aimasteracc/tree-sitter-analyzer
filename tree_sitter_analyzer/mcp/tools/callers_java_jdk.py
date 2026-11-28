"""#1884: JDK supertypes whose overridable members are a known, closed set.

An unannotated Java method may override a supertype method, so a supertype the
project does not declare used to fail the override proof outright. For a few
JDK interfaces every member a subtype can override is known: the walk can stop
there instead (``Excluder implements Cloneable``: ``withVersion`` overrides
nothing). A method named like one of the members still overrides a JDK method,
reached by the JDK or a library: that keeps the gate shut.

The names are the JDK 21 members of each type and of its superinterfaces
(``java.lang.Object`` methods are handled separately). ``Serializable`` lists
the private and protected hooks that serialization calls reflectively.

A simple name denotes the JDK type only when nothing can shadow it: no project
type of that name anywhere (a same-package, nested or inherited member type),
and, outside ``java.lang``, an exact single-type import of it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KnownType:
    """A JDK supertype and every member name a subtype can override in it."""

    qualified: str
    members: frozenset[str]


_KNOWN: dict[str, frozenset[str]] = {
    "java.lang.Cloneable": frozenset(),
    "java.lang.AutoCloseable": frozenset({"close"}),
    "java.lang.Runnable": frozenset({"run"}),
    "java.lang.Comparable": frozenset({"compareTo"}),
    "java.lang.Iterable": frozenset({"iterator", "forEach", "spliterator"}),
    "java.io.Closeable": frozenset({"close"}),
    "java.io.Flushable": frozenset({"flush"}),
    "java.io.Serializable": frozenset(
        {"writeObject", "readObject", "readObjectNoData", "writeReplace", "readResolve"}
    ),
}
_JAVA_LANG = "java.lang"


def known_type(cache: Any, name: str, imported_package: str | None) -> KnownType | None:
    """The JDK type ``name`` denotes in a file, or None when it cannot be proved.

    ``imported_package`` is the package of a single-type import of ``name`` in
    the file (None without one).
    """
    package = _JAVA_LANG if imported_package is None else imported_package
    qualified = f"{package}.{name}"
    members = _KNOWN.get(qualified)
    if members is None:
        return None
    try:
        shadowing = (
            cache.get_conn()
            .execute(
                "SELECT 1 FROM ast_symbol_rows WHERE name = ? AND kind = 'class' "
                "AND language = 'java' LIMIT 1",
                (name,),
            )
            .fetchone()
        )
    except (sqlite3.Error, AttributeError):
        return None
    return None if shadowing else KnownType(qualified, members)


__all__ = ["KnownType", "known_type"]
