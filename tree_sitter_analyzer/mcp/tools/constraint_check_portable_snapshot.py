"""Platform policy for portable read-only constraint snapshots."""

from __future__ import annotations

import os


def portable_snapshot_required() -> bool:
    """Return whether descriptor-path snapshot authority is unavailable."""
    return os.name != "posix" or not os.path.exists("/dev/fd")
