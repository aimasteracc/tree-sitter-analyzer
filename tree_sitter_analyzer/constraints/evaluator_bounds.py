"""Materialization bounds for constraint evaluation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

_T = TypeVar("_T")
MAX_MATERIALIZED_ITEMS = 10_000


def materialize_bounded(
    items: Iterable[_T], capacity: int, check_callback: Callable[[], None] | None
) -> list[_T]:
    """Materialize items without exceeding the caller-owned response capacity."""
    if capacity < 0:
        raise ValueError("capacity must be non-negative")
    result: list[_T] = []
    for item in items:
        if check_callback is not None:
            check_callback()
        if len(result) >= capacity:
            raise RuntimeError("CONSTRAINT_EVALUATION_CAPACITY")
        result.append(item)
    return result
