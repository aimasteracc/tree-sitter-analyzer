"""Serialized compatibility wrappers around source-generation capture."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")
_LOCK = threading.RLock()


def source_generation(project_root: str | None, mode: str = "diff") -> str:
    """Return one source generation under the compatibility serialization lock."""
    from .source_oracle_git import oracle_generation

    with _LOCK:
        return oracle_generation(project_root, mode)[0]


def capture_consistent(
    project_root: str | None, capture: Callable[[], _T]
) -> tuple[str | None, _T]:
    """Capture a value only while the ctime-inclusive generation stays stable."""
    from .source_oracle_git import oracle_generation

    with _LOCK:
        before, _ = oracle_generation(project_root)
        value = capture()
        after, _ = oracle_generation(project_root)
    return (before if before == after else None), value
