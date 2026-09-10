"""Settings loader with two pre-registered seams (NO1-010B).

Seam for task ``0009-refactor-split-load``: ``load`` parses and validates in
one body; the registered refactor splits it into ``parse`` + ``validate``
without changing any accepted or rejected input.

Seam for task ``0010-migration-coerce-typed-values``: every value is returned
as a string; the registered migration routes numeric settings through
``coerce`` so ``retries`` becomes an ``int``.
"""

from __future__ import annotations

REQUIRED = ("host", "retries")


def coerce(key: str, value: str) -> object:
    """Return ``value`` in its declared type. Not yet wired into ``load``."""
    if key == "retries":
        return int(value)
    return value


def load(raw: dict[str, str]) -> dict[str, object]:
    """Return the validated settings mapping for ``raw``."""
    missing = [key for key in REQUIRED if key not in raw]
    if missing:
        raise ValueError(f"missing required settings: {sorted(missing)}")
    return dict(raw)
