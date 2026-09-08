"""Observability for node types the symbol walker does not handle.

The walker in :mod:`tree_sitter_analyzer.cache.extraction` dispatches on
``node.type`` through a chain of membership tests. Historically the chain
had no terminal ``else``: a node type nobody had added to a set produced no
symbol, no warning and no counter, so the resulting data loss stayed silent
until someone noticed rows missing from the index months later. Every
extractor-version bump from v3 to v17 fixed one instance of that pattern.

This module is the missing feedback channel. It is **off by default and
free when off** — the walker calls :func:`record_unhandled` only when
:data:`ENABLED` is true, which is decided once at import time from the
``TSA_TRACK_UNHANDLED_NODES`` environment variable.

Usage::

    TSA_TRACK_UNHANDLED_NODES=1 uv run python -m tree_sitter_analyzer ...

Tests drive it through :func:`tracking_enabled`, which flips the flag and
restores it afterwards regardless of the environment.
"""

from __future__ import annotations

import os
from collections import Counter
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "ENABLED",
    "record_unhandled",
    "get_unhandled",
    "get_suspicious",
    "is_declaration_like",
    "reset_unhandled",
    "tracking_enabled",
]

# A walk visits every named node, so the raw counts are dominated by
# ``identifier`` / ``comment`` / ``*_literal`` noise. The signal we want is
# the narrow band of node types that *introduce a name into a scope* — those
# are the ones a symbol index is expected to cover, and an unhandled one is
# a candidate for exactly the defect class this module exists to surface.
_DECLARATION_SUFFIXES = (
    "_declaration",
    "_definition",
    "_item",
    "_spec",
)
# Node types matching a declaration suffix that are nonetheless not symbols:
# type machinery, parameter lists, and C/C++ declarator plumbing.
_NOT_A_SYMBOL = (
    "abstract_",
    "parameter",
    "argument",
    "_type",
    "type_",
    "attribute",
    "storage_class",
    "access_specifier",
    "virtual_specifier",
    "throw_specifier",
    "specifier_qualifier",
    "lambda_capture",
    "variadic",
    "new_declarator",
    "_list",
)


def is_declaration_like(node_type: str) -> bool:
    """Whether ``node_type`` plausibly introduces a named symbol.

    Deliberately conservative: it is a triage filter for humans reading a
    report, not a specification. False positives are cheap (one glance);
    false negatives would recreate the blind spot this module removes.
    """
    if not any(node_type.endswith(s) for s in _DECLARATION_SUFFIXES):
        return False
    return not any(marker in node_type for marker in _NOT_A_SYMBOL)


_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_enabled() -> bool:
    return os.environ.get("TSA_TRACK_UNHANDLED_NODES", "").strip().lower() in _TRUTHY


ENABLED: bool = _env_enabled()

# (language, node_type) -> occurrences. Process-local; the multiprocessing
# indexing workers each keep their own and are not aggregated — this is a
# diagnostic aid, not a metric that must be exact across processes.
_unhandled: Counter[tuple[str, str]] = Counter()


def record_unhandled(language: str, node_type: str) -> None:
    """Note that ``node_type`` reached the walker's fall-through branch."""
    _unhandled[(language, node_type)] += 1


def get_unhandled() -> dict[tuple[str, str], int]:
    """Return a snapshot of the counts recorded so far."""
    return dict(_unhandled)


def get_suspicious() -> dict[tuple[str, str], int]:
    """Return only the unhandled node types that look like declarations.

    This is the report worth acting on: each entry is a construct the
    grammar produces, that names something, and that the index drops.
    """
    return {
        key: count for key, count in _unhandled.items() if is_declaration_like(key[1])
    }


def reset_unhandled() -> None:
    """Clear the counts (used between test cases)."""
    _unhandled.clear()


@contextmanager
def tracking_enabled() -> Iterator[Counter[tuple[str, str]]]:
    """Enable tracking for the duration of the block, then restore.

    Yields the live counter, cleared on entry, so callers can assert on it
    without reaching for module globals.
    """
    global ENABLED
    previous = ENABLED
    ENABLED = True
    reset_unhandled()
    try:
        yield _unhandled
    finally:
        ENABLED = previous
