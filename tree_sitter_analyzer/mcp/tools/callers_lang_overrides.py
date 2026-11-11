"""#1937 / #1938: route C#, PHP and Swift declarations to their override gate.

A declaration row of the target is checked by the gate of its file's language;
as in the Kotlin gate, when a row's declaring type is named like the target's
owner only those rows count (``V2.m`` is not ``V1.m``), and a row that could not
be read leaves the check not run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .callers_supertypes import SupertypeFinding

#: ``(project_root, rel, line, bare, cache) -> (owner type name, finding)``
RowCheck = Callable[
    [str, str, int, str, Any], tuple[str | None, SupertypeFinding | None]
]


def _checks() -> dict[tuple[str, ...], RowCheck]:
    from .callers_csharp_overrides import CSHARP_SUFFIXES, csharp_row_finding
    from .callers_php_overrides import PHP_SUFFIXES, php_row_finding
    from .callers_swift_overrides import SWIFT_SUFFIXES, swift_row_finding

    return {
        CSHARP_SUFFIXES: csharp_row_finding,
        PHP_SUFFIXES: php_row_finding,
        SWIFT_SUFFIXES: swift_row_finding,
    }


def lang_override_finding(
    project_root: str,
    declarations: list[tuple[str, int, str]],
    bare: str,
    cache: Any,
    owner: str = "",
) -> SupertypeFinding | None:
    """The first C# / PHP / Swift row of ``bare`` that may be reached unseen."""
    checks = _checks()
    results: list[tuple[str | None, SupertypeFinding | None]] = []
    for rel, line, _language in declarations:
        lowered = rel.lower()
        check = next(
            (fn for suffixes, fn in checks.items() if lowered.endswith(suffixes)),
            None,
        )
        if check is not None:
            results.append(check(project_root, rel, line, bare, cache))
    if not results:
        return None
    wanted = owner.rpartition(".")[2]
    own = [found for name, found in results if wanted and name == wanted]
    candidates = own if own else [found for _name, found in results]
    unread = [found for _n, found in results if found is not None and found.unchecked]
    return next((f for f in [*unread, *candidates] if f is not None), None)


__all__ = ["lang_override_finding"]
