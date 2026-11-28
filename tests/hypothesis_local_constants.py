"""Keep Hypothesis from AST-scanning every loaded project module.

Since Hypothesis 6.131 the default provider mixes string/int/float literals
harvested from "local" modules (every module in ``sys.modules`` that lives under
the project) into generated values.  The harvest parses each such module with
``ast`` the first time a string strategy is drawn, and again for any module
imported since.  Inside a full test shard that is thousands of modules, so the
whole cost (>10 s locally, >30 s on a loaded macOS runner) lands on whichever
``@given`` test happens to run first and trips the per-test timeout, while a
test run in isolation never sees it.

None of this suite's properties depend on project literals, so the harvest is
turned off: example generation cost becomes independent of how many modules the
process has imported.
"""

from __future__ import annotations

from typing import Any


def disable_local_constants() -> bool:
    """Make Hypothesis report no local constants; return True when applied.

    ``_get_local_constants`` is a private Hypothesis hook, so a future release
    that moves it simply leaves the default behaviour in place (returns False)
    instead of breaking collection.
    """
    try:
        from hypothesis.internal.conjecture import providers
    except ImportError:  # pragma: no cover - hypothesis layout changed
        return False

    original: Any = getattr(providers, "_get_local_constants", None)
    constants_cls: Any = getattr(providers, "Constants", None)
    if original is None or constants_cls is None:  # pragma: no cover
        return False

    empty = constants_cls()

    def _no_local_constants() -> Any:
        return empty

    providers._get_local_constants = _no_local_constants
    return True
