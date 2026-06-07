"""Conservative stdlib / external name tiers for the C++ resolver (RFC-0010).

The RFC-0008 lesson is MANDATORY here: method-name classification without
receiver-type inference has a low precision ceiling, so a name is included in a
classified tier ONLY when it is (near-)exclusively that stdlib API and very
unlikely to be a user-defined method. For C++ this is even harsher than Java —
nearly every "stdlib container" method (``push_back``, ``size``, ``begin``,
``insert``, ``find``, ``at``, ``emplace``…) is routinely defined by user
containers, ranges, and domain wrappers, and free functions like ``move`` /
``swap`` / ``sort`` collide with project helpers. So the bare-method-name
stdlib tier is **intentionally EMPTY**: everything stays ``project`` / ``local``
/ ``unknown`` unless it carries the unambiguous ``std::`` qualifier (handled in
``cpp.py`` by the qualified-namespace prefix tier — not by these name sets).

An empty tier is correct and acceptable: an ``unknown`` edge is never a
mis-wire, whereas an over-broad name set would mis-classify user methods — the
exact CodeGraph failure this project exists to beat.
"""

from __future__ import annotations

# Namespace-qualifier prefixes that are (near-)certainly the C++ standard
# library. A call whose receiver/qualifier begins with one of these (e.g.
# ``std::sort``, ``std::make_unique``, ``std::chrono::now``, ``__gnu_cxx::…``)
# is platform-provided, never project code. ``std::`` is the canonical, almost
# unspoofable signal — user code does not define members under ``namespace std``
# (doing so is undefined behaviour). Kept deliberately tiny: only namespaces a
# project would never own.
STDLIB_NAMESPACE_PREFIXES: tuple[str, ...] = (
    "std::",
    "__gnu_cxx::",
    "__cxx11::",
)

# Bare *method/function* names classified ``stdlib`` on an UNRESOLVED receiver.
# INTENTIONALLY EMPTY (see module docstring): without receiver-type evidence,
# every candidate (``push_back``, ``size``, ``begin``, ``c_str``, ``move`` …)
# collides with user containers / wrappers / free helpers. Precision over
# recall — an unknown edge is correct; a mis-classified one is a moat breach.
STDLIB_METHODS_CPP: frozenset[str] = frozenset()

# Bare names classified ``external`` (third-party). INTENTIONALLY EMPTY for the
# first PR: C++ has no single dominant third-party library whose bare method
# names are safe to hardcode the way JUnit's ``assertX`` family is for Java
# (GoogleTest's ``EXPECT_*`` / ``ASSERT_*`` are macros, not call edges, and
# do not appear as resolvable callees). Stays empty until a safe set is proven.
EXTERNAL_METHODS_CPP: frozenset[str] = frozenset()


def is_stdlib_qualifier(qualifier: str) -> bool:
    """True when ``qualifier`` begins with a known C++ stdlib namespace prefix.

    ``qualifier`` is the receiver/namespace portion of a call's full name
    (e.g. ``std`` from ``std::sort`` or ``std::chrono`` from
    ``std::chrono::now``). The check is prefix-based so nested stdlib
    namespaces (``std::chrono``, ``std::filesystem``) are covered.
    """
    if not qualifier:
        return False
    normalized = qualifier if qualifier.endswith("::") else qualifier + "::"
    return any(normalized.startswith(prefix) for prefix in STDLIB_NAMESPACE_PREFIXES)


__all__ = [
    "EXTERNAL_METHODS_CPP",
    "STDLIB_METHODS_CPP",
    "STDLIB_NAMESPACE_PREFIXES",
    "is_stdlib_qualifier",
]
