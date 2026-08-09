"""Shared closed worst-case bounds for the NO1-008A execution pipeline."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

AUTHORITY_COMMAND_TIMEOUT_SECONDS = 120
DEBUGFS_FIXED_OVERHEAD_SECONDS = 30
DEBUGFS_MIN_THROUGHPUT_BYTES_PER_SECOND = 16 * 1024 * 1024
# Covers bounded hashing, fsync, audit construction, signing, and response assembly.
AUTHORITY_HASH_SIGN_MARGIN_SECONDS = 120
POST_AUTHORITY_SERVICE_PHASES = 4  # executor, approver, verifier, decision
CONTRACT_EXPIRY_MARGIN_SECONDS = 30


def debugfs_payload_timeout_seconds(payload_bytes: int) -> int:
    """Return the extraction bound shared by authority execution and preflight."""
    if type(payload_bytes) is not int or payload_bytes < 0:
        raise ValueError("debugfs payload size is invalid")
    return (
        DEBUGFS_FIXED_OVERHEAD_SECONDS
        + (payload_bytes + DEBUGFS_MIN_THROUGHPUT_BYTES_PER_SECOND - 1)
        // DEBUGFS_MIN_THROUGHPUT_BYTES_PER_SECOND
    )


def extraction_timeout_seconds(
    payload_bytes: int, *, deadline_monotonic: float | None = None
) -> float:
    """Bound extraction by image size and an optional service-wide deadline."""
    timeout = float(debugfs_payload_timeout_seconds(payload_bytes))
    if deadline_monotonic is not None:
        if type(deadline_monotonic) not in {int, float}:
            raise ValueError("extraction deadline is invalid")
        remaining = float(deadline_monotonic) - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("extraction contract deadline expired")
        timeout = min(timeout, remaining)
    return max(0.001, timeout)


def authority_cell_budget_seconds(plan: Mapping[str, Any]) -> int:
    """Return the closed per-cell authority wall bound from signed plan ceilings."""
    wall = plan.get("wall_timeout_seconds")
    ceilings = plan.get("resource_ceilings")
    payload = ceilings.get("io_bytes") if type(ceilings) is dict else None
    if type(wall) is not int or wall < 1 or type(payload) is not int or payload < 0:
        raise ValueError("authority budget inputs are invalid")
    # mkfs, lost+found debugfs mutation, and veritysetup each use the common
    # command bound.  The integrity extraction has its payload-derived bound.
    return (
        wall
        + 3 * AUTHORITY_COMMAND_TIMEOUT_SECONDS
        + debugfs_payload_timeout_seconds(payload)
        + AUTHORITY_HASH_SIGN_MARGIN_SECONDS
    )
