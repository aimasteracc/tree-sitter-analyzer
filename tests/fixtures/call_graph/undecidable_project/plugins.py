"""Handler registry whose dispatch is invisible to a text search.

``handle_alpha`` and ``handle_beta`` are real functions reached from
``dispatch_by_name``, but no source line spells their names at a call: the
registration is by string and the invocation is by dictionary lookup. A caller
that searches for a call to either name finds the definition and nothing else,
which is exactly the shape that tempts a confident "no callers".

This docstring deliberately avoids writing a name immediately followed by an
opening parenthesis: the corpus must defeat a *text* search, and an explanatory
mention would give the naive tool a hit it should not have.
"""

from __future__ import annotations

from collections.abc import Callable

HANDLERS: dict[str, Callable[[], int]] = {}


def register(name: str):
    """Register a handler under a string key."""

    def decorate(fn: Callable[[], int]) -> Callable[[], int]:
        HANDLERS[name] = fn
        return fn

    return decorate


@register("alpha")
def handle_alpha() -> int:
    return 1


@register("beta")
def handle_beta() -> int:
    return 2


def dispatch_by_name(name: str) -> int:
    """Invoke a registered handler by string key."""
    return HANDLERS[name]()
