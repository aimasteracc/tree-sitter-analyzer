"""Conservative Swift stdlib classification data (RFC-0010).

Precision over recall (the RFC-0008 lesson). The tier holds ONLY near-exclusive
Swift global free functions — the handful that are overwhelmingly the standard
library and very unlikely to be a user's own top-level function. Overloaded
generic names (``map``, ``filter``, ``sorted``, ``abs``, ``min``, ``max``,
``zip``, ``swap``) are deliberately EXCLUDED: they are common method/closure
names and classifying them risks the exact same-name mis-classification this
project exists to beat. An unknown edge is correct; a wrong one is not.
"""

from __future__ import annotations

#: Near-exclusive Swift standard-library GLOBAL functions (no receiver). These
#: are diagnostics / control-flow built-ins that projects almost never redefine
#: as a free function.
SWIFT_STDLIB_FUNCTIONS: frozenset[str] = frozenset(
    {
        "print",
        "debugPrint",
        "dump",
        "assert",
        "assertionFailure",
        "precondition",
        "preconditionFailure",
        "fatalError",
    }
)


def is_swift_stdlib_function(name: str) -> bool:
    """True for a bare (receiver-less) near-exclusive Swift stdlib global fn."""
    return name in SWIFT_STDLIB_FUNCTIONS


__all__ = ["SWIFT_STDLIB_FUNCTIONS", "is_swift_stdlib_function"]
