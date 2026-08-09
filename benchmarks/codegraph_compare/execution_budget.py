"""Shared closed worst-case bounds for the NO1-008A execution pipeline."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

AUTHORITY_COMMAND_TIMEOUT_SECONDS = 120
HOST_AUDIT_COMMAND_TIMEOUT_SECONDS = 30
# Every independently bounded authority subprocess on the successful path.  The
# preflight entries run before reservation but inside the operator deadline.
AUTHORITY_COMMAND_OPERATIONS_PER_CELL = (
    "preflight_inputs_docker_inspect",
    "preflight_cgroup_docker_info",
    "execution_inputs_docker_inspect",
    "execution_cgroup_docker_info",
    "docker_create",
    "docker_start",
    "docker_started_inspect",
    "launch_gate_docker_inspect",
    "truncate_data_image",
    "mkfs_ext4",
    "debugfs_remove_lost_found",
    "truncate_hash_image",
    "verity_format",
    "docker_remove",
)
HOST_AUDIT_OPERATIONS_PER_CELL = (
    "launch_docker_inspect",
    "terminal_docker_inspect",
    "terminal_docker_events",
)
DEBUGFS_FIXED_OVERHEAD_SECONDS = 30
DEBUGFS_MIN_THROUGHPUT_BYTES_PER_SECOND = 16 * 1024 * 1024
# Covers bounded hashing, fsync, audit construction, signing, and response assembly.
AUTHORITY_HASH_SIGN_MARGIN_SECONDS = 120
# Both receipt roles independently extract once to build a body and once again
# during full semantic verification.  The fresh verifier extracts once per cell.
RECEIPT_ROLE_EXTRACTIONS_PER_CELL = 2
VERIFIER_EXTRACTIONS_PER_CELL = 1
VERITY_VERIFY_OPERATIONS_PER_CELL = 3
EXECUTOR_HASH_SIGN_MARGIN_SECONDS = 120
APPROVER_HASH_SIGN_MARGIN_SECONDS = 120
VERIFIER_HASH_SIGN_MARGIN_SECONDS = 120
DECISION_SERVICE_MARGIN_SECONDS = 120
CONTRACT_EXPIRY_MARGIN_SECONDS = 30
_EXT4_METADATA_MIN_BYTES = 64 * 1024 * 1024
_EXT4_ROUND_BYTES = 4 * 1024 * 1024


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
    # Producer wait owns ``wall``.  Every other subprocess has its own maximum;
    # debugfs extraction is size-derived, while audit/hash/sign work is explicit.
    return (
        wall
        + len(AUTHORITY_COMMAND_OPERATIONS_PER_CELL) * AUTHORITY_COMMAND_TIMEOUT_SECONDS
        + len(HOST_AUDIT_OPERATIONS_PER_CELL) * HOST_AUDIT_COMMAND_TIMEOUT_SECONDS
        + debugfs_payload_timeout_seconds(payload)
        + AUTHORITY_HASH_SIGN_MARGIN_SECONDS
    )


def sealed_image_upper_bound_bytes(output: int) -> int:
    """Return the ext4 image ceiling implied by a signed output ceiling."""
    if type(output) is not int or output < 0:
        raise ValueError("sealed image budget input is invalid")
    maximum = _EXT4_METADATA_MIN_BYTES + (output * 5 + 3) // 4
    return ((maximum + _EXT4_ROUND_BYTES - 1) // _EXT4_ROUND_BYTES) * _EXT4_ROUND_BYTES


def post_authority_cell_budget_seconds(plan: Mapping[str, Any]) -> int:
    """Bound both receipt signers and fresh verification for one sealed cell."""
    ceilings = plan.get("resource_ceilings")
    output = ceilings.get("io_bytes") if type(ceilings) is dict else None
    if type(output) is not int:
        raise ValueError("post-authority budget input is invalid")
    extraction = debugfs_payload_timeout_seconds(sealed_image_upper_bound_bytes(output))
    extraction_count = (
        2 * RECEIPT_ROLE_EXTRACTIONS_PER_CELL + VERIFIER_EXTRACTIONS_PER_CELL
    )
    margins = (
        EXECUTOR_HASH_SIGN_MARGIN_SECONDS
        + APPROVER_HASH_SIGN_MARGIN_SECONDS
        + VERIFIER_HASH_SIGN_MARGIN_SECONDS
    )
    return (
        extraction_count * extraction
        + VERITY_VERIFY_OPERATIONS_PER_CELL * AUTHORITY_COMMAND_TIMEOUT_SECONDS
        + margins
    )


def exact14_execution_budget_seconds(plans: Mapping[Any, Mapping[str, Any]]) -> int:
    """Return the closed serial authority-to-decision budget for staged plans."""
    return (
        sum(
            authority_cell_budget_seconds(plan)
            + post_authority_cell_budget_seconds(plan)
            for plan in plans.values()
        )
        + DECISION_SERVICE_MARGIN_SECONDS
    )
