"""Bounded streaming copy primitives for portable constraint indexes."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any


def copy_pinned_database(
    fd: int,
    expected: tuple[int, int, int, int, int],
    stream: Any,
    *,
    deadline: float,
    byte_limit: int,
    check_deadline: Callable[[float], None],
    stat_identity: Callable[[os.stat_result], tuple[int, int, int, int, int]],
) -> None:
    """Stream one pinned database under exact size, deadline, and write bounds."""
    size = expected[2]
    if size > byte_limit:
        raise RuntimeError("INDEX_BACKUP_BUDGET")
    remaining = size
    while remaining:
        check_deadline(deadline)
        chunk = os.read(fd, min(64 * 1024, remaining))
        if not chunk:
            raise ValueError("CONCURRENT_WRITER")
        view = memoryview(chunk)
        while view:
            check_deadline(deadline)
            written = stream.write(view)
            if not isinstance(written, int) or written <= 0 or written > len(view):
                raise OSError("INDEX_STAGE_WRITE_FAILED")
            view = view[written:]
            check_deadline(deadline)
        remaining -= len(chunk)
    check_deadline(deadline)
    if os.read(fd, 1):
        raise ValueError("CONCURRENT_WRITER")
    check_deadline(deadline)
    if stat_identity(os.fstat(fd)) != expected:
        raise ValueError("CONCURRENT_WRITER")
    check_deadline(deadline)
