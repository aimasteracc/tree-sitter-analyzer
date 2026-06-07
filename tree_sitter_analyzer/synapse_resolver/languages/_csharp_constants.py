"""Conservative stdlib classification tiers for the C# resolver (RFC-0010).

The RFC-0008 lesson is MANDATORY here: a name is classified into a stdlib tier
ONLY when it is (near-)exclusively that BCL API and very unlikely to be a
user-defined symbol. Two signals carry the C# stdlib tier, in descending order
of confidence:

1. A **fully-qualified ``System.`` namespace prefix** (``System.Console.WriteLine``,
   ``System.Linq.Enumerable.Select``). This is the C# analogue of C++'s
   ``std::`` — ``namespace System`` is reserved BCL territory and user code never
   legitimately owns it, so the qualifier alone is near-unspoofable evidence.
   Handled by :func:`is_system_qualifier` (no shadow gate needed).

2. A small, hand-audited set of **bare BCL static-type heads**
   (``Console.WriteLine``, ``Math.Max``, ``Convert.ToInt32``,
   ``Enumerable.Select``, ``String.Format``). These are static types whose
   members are called through the TYPE NAME (not an instance), and whose names
   are very unlikely to be a user class. This tier IS shadow-gated in
   ``csharp.py``: if the project itself defines a same-language symbol of that
   name (``class Console { ... }``), the BCL claim is suppressed (precision over
   recall). Pruned HARD — common domain names (``File``, ``Path``, ``Directory``,
   ``Task``, ``Environment``, ``Guid``) are LEFT OUT because they collide with
   real project types; their calls stay ``unknown`` (an unknown edge is correct,
   a mis-classified one is a moat breach).

The **bare-method-name** tiers (``STDLIB_METHODS_CSHARP`` /
``EXTERNAL_METHODS_CSHARP``) are INTENTIONALLY EMPTY: without receiver-type
inference, a bare method name (``Add`` / ``Select`` / ``ToString`` / ``Contains``)
collides massively with user methods. An empty tier is correct (RFC-0010).
"""

from __future__ import annotations

#: The fully-qualified BCL root namespace. A call whose qualifier begins with
#: this token (``System``, ``System.Console``, ``System.Linq.Enumerable``) is
#: platform-provided, never project code — the C# analogue of ``std::``. The
#: check is on the ``System.`` token boundary so a user namespace that merely
#: starts with the letters ``System`` (``SystemExt``, ``MySystem``) does NOT
#: match.
SYSTEM_NAMESPACE_ROOT: str = "System"

#: Bare BCL static-type heads classified ``stdlib`` when a call is qualified by
#: one of them (``Console.WriteLine``) AND the project does not itself define a
#: compatible-language symbol of that name (shadow gate in ``csharp.py``). Each
#: entry is a static (or static-method-bearing) BCL type whose members are
#: idiomatically called through the type name and whose name is near-exclusively
#: the BCL type. Deliberately tiny: when in doubt a type is LEFT OUT.
#:
#:   Console     — ``Console.WriteLine`` / ``Console.ReadLine``; never a domain class.
#:   Math        — ``Math.Max`` / ``Math.Floor``; a static math facade.
#:   Convert     — ``Convert.ToInt32`` / ``Convert.ToBase64String``; BCL converter.
#:   Enumerable  — ``Enumerable.Select`` / ``Enumerable.Range``; the LINQ statics.
#:   String      — ``String.Format`` / ``String.IsNullOrEmpty``; the ``string``
#:                 alias type, effectively reserved (user code does not define a
#:                 type named ``String``).
#:
#: NOT included (collide with common domain types): File, Path, Directory, Task,
#: Environment, Guid, Encoding, Regex, DateTime, TimeSpan, Tuple.
BCL_STATIC_TYPES_CSHARP: frozenset[str] = frozenset(
    {
        "Console",
        "Math",
        "Convert",
        "Enumerable",
        "String",
    }
)

#: Bare *method/function* names classified ``stdlib`` on an UNRESOLVED receiver.
#: INTENTIONALLY EMPTY (see module docstring): without receiver-type evidence,
#: every candidate (``ToString``/``Add``/``Select``/``Contains`` …) collides
#: with user methods. Precision over recall — an unknown edge is correct.
STDLIB_METHODS_CSHARP: frozenset[str] = frozenset()

#: Bare names classified ``external`` (third-party). INTENTIONALLY EMPTY for the
#: first PR: C# has no single dominant third-party library whose bare method
#: names are safe to hardcode without receiver evidence. Stays empty until a
#: safe set is proven.
EXTERNAL_METHODS_CSHARP: frozenset[str] = frozenset()


def is_system_qualifier(qualifier: str) -> bool:
    """True when ``qualifier`` is the BCL ``System`` namespace (or a child).

    ``qualifier`` is the receiver/namespace portion of a call's full name
    (``System`` from ``System.WriteLine``; ``System.Console`` from
    ``System.Console.WriteLine``). The match is on the ``System.`` token
    boundary so a user namespace that merely starts with the letters ``System``
    (``SystemExt``, ``MySystem``) is correctly rejected. ``System`` by itself
    (the bare root) matches.
    """
    if not qualifier:
        return False
    return qualifier == SYSTEM_NAMESPACE_ROOT or qualifier.startswith(
        SYSTEM_NAMESPACE_ROOT + "."
    )


__all__ = [
    "BCL_STATIC_TYPES_CSHARP",
    "EXTERNAL_METHODS_CSHARP",
    "STDLIB_METHODS_CSHARP",
    "SYSTEM_NAMESPACE_ROOT",
    "is_system_qualifier",
]
