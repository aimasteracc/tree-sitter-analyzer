"""Rust std-library path prefixes and distinctively-std associated functions.

A Rust call whose ``callee_full`` carries a ``std::`` / ``core::`` / ``alloc::``
path, or whose receiver is one of a very small set of ``final``-style std types
whose associated fn is near-exclusively the std API, is tagged ``stdlib`` — a
*terminal* resolution that keeps it out of the backfill re-scan set.

CURATION RULE — PRECISION over recall (the RFC-0008 Java lesson).
The Rust resolver carries no trait/type inference at this tier, so a bare
associated-fn name (``new``/``from``/``with_capacity``) cannot be told apart from
a project type's identically-named associated fn. Therefore:

* A ``std::``/``core::``/``alloc::``-PATHED call is unambiguous std → kept.
* A ``Type::fn`` associated call is kept ONLY when ``Type`` is a concrete std
  container/smart-pointer whose name a project type essentially never reuses
  (``Vec``/``Box``/``Rc``/``Arc``/``HashMap``/...), AND ``fn`` is a constructor-
  family name. ``Option``/``Result`` method names (``unwrap``/``map``/``and_then``)
  are DELIBERATELY EXCLUDED: they are receiver-style instance methods that domain
  ``Result``-like / monadic types and crates (``anyhow``, ``thiserror`` wrappers)
  routinely define, and without receiver-type evidence they would be mislabelled.
* Everything else stays ``unknown``. An empty/strict tier beats a false positive.

Kept in a dedicated module so the literal sets stay out of the resolver logic and
the file-size rule is honoured.
"""

from __future__ import annotations

# Path prefixes that are part of the Rust standard distribution. Any
# fully-pathed call (``std::mem::swap``, ``core::convert::From::from``,
# ``alloc::vec::Vec::new``) is std-provided, not project code.
STD_PATH_PREFIXES: frozenset[str] = frozenset(
    {
        "std::",
        "core::",
        "alloc::",
    }
)

# Concrete std container / smart-pointer TYPES whose names a project type
# essentially never reuses. A ``Type::fn`` associated call where ``Type`` is one
# of these AND ``fn`` is a constructor-family name (below) classifies stdlib.
# These are all concrete structs (not traits), so a domain type cannot *be* one.
_STD_ASSOC_TYPES: frozenset[str] = frozenset(
    {
        "Vec",
        "Box",
        "Rc",
        "Arc",
        "VecDeque",
        "BinaryHeap",
        "LinkedList",
        "HashMap",
        "BTreeMap",
        "HashSet",
        "BTreeSet",
    }
)

# Constructor-family associated-fn names. Combined with a std container receiver
# (above) these are distinctively the std API. ``new``/``with_capacity`` are the
# canonical container constructors; bare (receiver-less) occurrences of these
# names are NOT classified — only the ``StdType::name`` qualified form is.
_STD_ASSOC_FNS: frozenset[str] = frozenset(
    {
        "new",
        "with_capacity",
        "from_iter",
        "default",
    }
)


def is_std_path(callee_full: str) -> bool:
    """True when ``callee_full`` begins with a std distribution path prefix."""
    return any(callee_full.startswith(prefix) for prefix in STD_PATH_PREFIXES)


def is_std_assoc_call(receiver: str, simple: str) -> bool:
    """True for a ``StdContainer::ctor`` associated call (``Vec::new``).

    ``receiver`` is the segment before the final ``::`` (already stripped of any
    leading path), ``simple`` the associated-fn name. Only the curated
    std-container × constructor-family combination matches; everything else is
    left to the resolver's ``unknown`` fall-through.
    """
    return receiver in _STD_ASSOC_TYPES and simple in _STD_ASSOC_FNS


__all__ = [
    "STD_PATH_PREFIXES",
    "is_std_assoc_call",
    "is_std_path",
]
