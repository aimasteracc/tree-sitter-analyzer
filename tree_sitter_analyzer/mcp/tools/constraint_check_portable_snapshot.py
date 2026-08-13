"""Platform policy for portable read-only constraint snapshots."""

from __future__ import annotations

import os
from typing import Any

from ...index_source_snapshot import capture_current_source_snapshot
from ...portable_source_snapshot import capture_portable_source_snapshot


def portable_snapshot_required() -> bool:
    """Return whether descriptor-path snapshot authority is unavailable."""
    return os.name != "posix" or not os.path.exists("/dev/fd")


def capture_constraint_sources(
    root: str,
    source_scope: Any,
    deadline: float,
    *,
    required: Any = portable_snapshot_required,
) -> Any:
    """Select the secure source certifier available on the current platform."""
    if required():
        return capture_portable_source_snapshot(root, source_scope, deadline=deadline)
    return capture_current_source_snapshot(root, source_scope, deadline=deadline)
