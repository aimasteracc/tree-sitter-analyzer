"""Process-local frozen snapshot routes exposed by the edit facade."""

from __future__ import annotations

from typing import Any

from ..utils.format_helper import apply_toon_format_to_response


async def release_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    """Release one process-local RFC-0022 lease through the live MCP process."""
    from ...diff_snapshot_registry import REGISTRY

    snapshot_id = arguments.get("diff_snapshot_id")
    lease_id = arguments.get("route_lease_id")
    output_format = arguments.get("output_format", "toon")
    if not isinstance(snapshot_id, str) or not isinstance(lease_id, str):
        raise ValueError("diff_snapshot_id and route_lease_id are required")
    error = REGISTRY.release_route_lease(snapshot_id, lease_id)
    result: dict[str, Any] = {
        "success": error is None,
        "verdict": "INFO" if error is None else "ERROR",
        "diff_snapshot_id": snapshot_id,
        "released": error is None,
        "output_format": output_format,
    }
    if error is not None:
        result.update(error=error, error_code=error)
    return apply_toon_format_to_response(result, output_format)
