"""Resolve duplicate ``--case`` CLI flags into a canonical bool + emit warnings.

Argparse's default ``store`` action silently keeps the last value when a flag
is passed multiple times. For ``--case`` that means a caller passing
``--case sensitive --case insensitive`` gets case-insensitive results with no
hint that their first value was discarded.

This helper:
- Detects duplicate ``--case`` occurrences via ``sys.argv``.
- Emits a single ``warning:`` line to stderr listing what was seen and what
  won.
- Returns the canonical ``case_sensitive`` boolean for echoing in the
  response. Default ``smart`` and explicit ``insensitive`` both map to
  ``False``; only ``sensitive`` maps to ``True``.

This module is import-side-effect-free and safe to call from both the
``find-and-grep`` and ``search-content`` CLIs.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import IO

_CASE_FLAG = "--case"


def collect_case_args(argv: Iterable[str] | None = None) -> list[str]:
    """Return every ``--case`` value seen on the command line, in order.

    Handles both space-separated (``--case sensitive``) and equals-style
    (``--case=sensitive``) forms.
    """
    args = list(sys.argv if argv is None else argv)
    seen: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if token == _CASE_FLAG and i + 1 < len(args):
            seen.append(args[i + 1])
            i += 2
            continue
        if token.startswith(_CASE_FLAG + "="):
            seen.append(token.split("=", 1)[1])
        i += 1
    return seen


def case_to_sensitive_bool(case: str | None) -> bool:
    """Map the textual ``--case`` value to the canonical bool echo.

    Returns ``False`` for ``None``, ``"smart"``, ``"insensitive"``, or any
    unrecognized value; only ``"sensitive"`` returns ``True``. This keeps the
    response ``case_sensitive`` field a strict bool — never ``None``.
    """
    return case == "sensitive"


def warn_on_duplicate_case(
    resolved: str | None,
    *,
    argv: Iterable[str] | None = None,
    stream: IO[str] | None = None,
) -> bool:
    """Emit a stderr warning when ``--case`` is passed more than once.

    Returns ``True`` when a duplicate was detected (a warning was written),
    ``False`` otherwise. The CLI keeps argparse's last-wins behavior — the
    warning only surfaces which value won so callers know what to expect.
    """
    seen = collect_case_args(argv)
    if len(seen) <= 1:
        return False
    out = stream if stream is not None else sys.stderr
    out.write(
        "warning: --case was passed multiple times "
        f"({', '.join(seen)}); using last value: {resolved!r}.\n"
    )
    return True


__all__ = [
    "collect_case_args",
    "case_to_sensitive_bool",
    "warn_on_duplicate_case",
]
