"""Argument boundary for frozen constraint snapshot consumers."""

from __future__ import annotations

from typing import Any


def validate_snapshot_arguments(arguments: dict[str, Any]) -> None:
    """Reject ambiguous or writable frozen-snapshot argument combinations."""
    persist = arguments.get("persist", True)
    if not isinstance(persist, bool):
        raise ValueError("persist must be a boolean")
    snapshot_id = arguments.get("diff_snapshot_id")
    scope_paths = arguments.get("scope_paths")
    if snapshot_id is not None:
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise ValueError("diff_snapshot_id must be a non-empty string")
        if persist:
            raise ValueError("diff_snapshot_id requires persist=false")
        if not isinstance(scope_paths, list) or any(
            not isinstance(path, str) for path in scope_paths
        ):
            raise ValueError("diff_snapshot_id requires scope_paths as strings")
        if arguments.get("path_filter"):
            raise ValueError("DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS")
    elif scope_paths is not None:
        raise ValueError("scope_paths requires diff_snapshot_id")
