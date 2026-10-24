"""Query-scoped memoisation for work that is invariant within one answer.

RFC-0041: a unified query asks the same producers (``nav callers``) about
many symbols against one index state. Some of their sub-steps read data that
does not depend on the symbol (e.g. every ES alias edge in the index). Inside
:func:`query_scope` such a step may be computed once; outside a scope every
call computes live, so ordinary single-call behaviour is unchanged.

The scope lives in a :class:`contextvars.ContextVar`, so it follows the
awaiting task and never leaks into concurrent requests.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar

T = TypeVar("T")

_SCOPE: ContextVar[dict[Hashable, Any] | None] = ContextVar(
    "tsa_query_scope", default=None
)


@contextmanager
def query_scope() -> Iterator[None]:
    """Memoise :func:`scoped` computations until the block exits."""
    token = _SCOPE.set({})
    try:
        yield
    finally:
        _SCOPE.reset(token)


def scoped(key: Hashable, compute: Callable[[], T]) -> T:
    """``compute()`` once per active scope and ``key``; live when unscoped."""
    memo = _SCOPE.get()
    if memo is None:
        return compute()
    if key not in memo:
        memo[key] = compute()
    return memo[key]  # type: ignore[no-any-return]


def in_scope() -> bool:
    return _SCOPE.get() is not None
