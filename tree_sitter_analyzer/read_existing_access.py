"""Shared boundary helpers for explicit read-existing adapter access."""

from __future__ import annotations

import sys
from typing import Any

from .git_path_codec import path_from_wire

READ_EXISTING_AUTHORITY_UNCERTIFIED = "READ_EXISTING_AUTHORITY_UNCERTIFIED"
DIFF_SNAPSHOT_READ_EXISTING_UNSUPPORTED = "DIFF_SNAPSHOT_READ_EXISTING_UNSUPPORTED"


def read_existing_platform_supported() -> bool:
    """Return whether this axis may run the read-existing backends.

    RFC-0022 P0.4 certifies zero-write behavior through a pinned native
    authority (the Linux strace monitor); an OS without that authority
    must return a stable unsupported result and cannot be listed as
    certified support. The read-only backends themselves are POSIX-only,
    and their strace certification is Linux-only, so the runtime enables
    them on Linux and fails closed everywhere else.
    """
    return sys.platform.startswith("linux")


def validate_read_existing_access(arguments: dict[str, Any]) -> bool:
    """Validate the explicit mode and reject capability tokens on legacy calls.

    Omission is the legacy path only when no new P0.1 consumer token is
    supplied. Legacy P0.2 diff/lease tokens retain their existing same-process
    routes when this mode is absent.
    """
    # ``diff_snapshot_id`` and ``route_lease_id`` predate P0.4 and remain
    # valid on their legacy P0.2 same-process routes.  Only the new P0.1
    # consumer pair is meaningless without the explicit access contract.
    capability_tokens = ("snapshot_id", "source_generation")
    if "access_mode" not in arguments:
        supplied = next((name for name in capability_tokens if name in arguments), None)
        if supplied is not None:
            raise ValueError(f"{supplied} requires access_mode=read_existing")
        return False
    access_mode = arguments["access_mode"]
    if not isinstance(access_mode, str) or access_mode != "read_existing":
        raise ValueError("access_mode must be the string 'read_existing'")
    return True


def validate_index_capability_pair(
    arguments: dict[str, Any], *, read_existing: bool
) -> None:
    """Require the complete non-empty P0.1 identity pair in explicit mode."""
    names = ("snapshot_id", "source_generation")
    for name in names:
        if name in arguments and (
            not isinstance(arguments[name], str) or not arguments[name]
        ):
            raise ValueError(f"{name} must be a non-empty string")
    present = tuple(name in arguments for name in names)
    if read_existing and present != (True, True):
        raise ValueError(
            "snapshot_id and source_generation are required for "
            "access_mode=read_existing"
        )


def validate_optional_index_capability_pair(arguments: dict[str, Any]) -> None:
    """Validate a P0.1 pair when a conditionally graph-backed route supplies it."""
    names = ("snapshot_id", "source_generation")
    for name in names:
        if name in arguments and (
            not isinstance(arguments[name], str) or not arguments[name]
        ):
            raise ValueError(f"{name} must be a non-empty string")
    present = tuple(name in arguments for name in names)
    if present not in {(False, False), (True, True)}:
        raise ValueError("snapshot_id and source_generation must be supplied together")


def index_capability_schema_properties() -> dict[str, dict[str, Any]]:
    """Return the shared explicit-mode index capability schema fields."""
    return {
        "access_mode": {
            "type": "string",
            "enum": ["read_existing"],
            "description": "Use only a certified existing index snapshot.",
        },
        "snapshot_id": {
            "type": "string",
            "description": "Owner-issued certified index snapshot ID.",
        },
        "source_generation": {
            "type": "string",
            "description": "Owner-issued certified source generation.",
        },
    }


def index_capability_facade_configuration(action: str) -> dict[str, Any]:
    """Return public schema and action scoping for one index-backed facade route."""
    scoped = frozenset({action})
    return {
        "extra_public_params": index_capability_schema_properties(),
        "action_scoped_params": {
            "access_mode": scoped,
            "snapshot_id": scoped,
            "source_generation": scoped,
        },
    }


def validate_read_existing_schema_values(tool: Any, arguments: dict[str, Any]) -> None:
    """Validate every supplied explicit-mode value against the tool schema."""
    if "access_mode" not in arguments:
        return
    properties = tool.get_tool_schema().get("properties", {})
    type_checks = {
        "string": lambda value: isinstance(value, str),
        "boolean": lambda value: isinstance(value, bool),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda value: (
            isinstance(value, (int, float)) and not isinstance(value, bool)
        ),
        "array": lambda value: isinstance(value, list),
        "object": lambda value: isinstance(value, dict),
    }
    for name, value in arguments.items():
        field = properties.get(name)
        if not isinstance(field, dict):
            continue
        expected_type = field.get("type")
        check = (
            type_checks.get(expected_type) if isinstance(expected_type, str) else None
        )
        if check is not None and not check(value):
            raise ValueError(f"{name} must have JSON type {expected_type}")
        if "enum" in field and value not in field["enum"]:
            raise ValueError(f"{name} must be one of {field['enum']}")
        items = field.get("items")
        if (
            expected_type == "array"
            and isinstance(items, dict)
            and items.get("type") == "string"
            and any(not isinstance(item, str) for item in value)
        ):
            raise ValueError(f"{name} must contain only strings")


def validate_required_index_access(tool: Any, arguments: dict[str, Any]) -> None:
    """Validate an explicit-required P0.1 pair and all supplied schema values."""
    read_existing = validate_read_existing_access(arguments)
    validate_index_capability_pair(arguments, read_existing=read_existing)
    validate_read_existing_schema_values(tool, arguments)


def validate_read_existing_paths(tool: Any, paths: list[str]) -> None:
    """Apply the existing project security boundary to decoded P0.2 wire paths.

    Codex P1 (#1257): fail closed when the project root was never bound
    (MCP server created without ``project_root``, caller routes before
    ``set_project_path``). Passing ``base_path=None`` into
    ``SecurityValidator.validate_file_path`` skips the project-boundary
    layer, so an arbitrary relative path would validate and the route
    could classify successfully with no boundary established. Raise the
    stable ``MISSING_PROJECT_ROOT`` error instead — path validation never
    counts as success on an unbound project.
    """
    if not tool.project_root:
        raise ValueError(
            "MISSING_PROJECT_ROOT: project_root must be bound before "
            "read_existing path validation"
        )
    for wire_path in paths:
        file_path = path_from_wire(wire_path)
        valid, error = tool.security_validator.validate_file_path(
            file_path, base_path=tool.project_root
        )
        if not valid:
            raise ValueError(f"Invalid file path: Security validation failed: {error}")


def classify_index_access(
    *,
    snapshot_id: Any,
    source_generation: Any,
    completeness: Any,
    reason: Any,
) -> dict[str, Any]:
    """Build P0.4 evidence for one P0.1 status-oracle result."""
    acquired = isinstance(snapshot_id, str) and bool(snapshot_id)
    source_snapshots = (
        [
            {
                "kind": "index",
                "snapshot_id": snapshot_id,
                "source_generation": source_generation,
            }
        ]
        if acquired
        else []
    )
    # P0.4 classifies whether the compatible P0.1 capability was acquired
    # and read, not whether P0.1 considers its contents complete/fresh.  A
    # successfully read partial capability stays access-available while its
    # existing ``completeness``/``oracle_reason`` fields carry freshness.
    available = acquired and completeness in {"complete", "partial"}
    if available:
        state = "available"
        access_reason = None
    else:
        state = (
            "missing"
            if reason in {"MISSING_INDEX", "MISSING_PROJECT_ROOT"}
            else "unknown"
        )
        access_reason = reason or "INDEX_SNAPSHOT_UNKNOWN"
    return {
        "access_mode": "read_existing",
        "access_state": state,
        "access_reason": access_reason,
        "source_snapshots": source_snapshots,
    }


def read_existing_unavailable(
    arguments: dict[str, Any],
    *,
    reason: str = READ_EXISTING_AUTHORITY_UNCERTIFIED,
    default_output_format: str = "toon",
    action_version: str | None = None,
) -> dict[str, Any] | None:
    """Return the raw classified-unavailable envelope for an explicit request."""
    if "access_mode" not in arguments:
        return None
    envelope: dict[str, Any] = {
        "success": True,
        "verdict": "WARN",
        "access_mode": "read_existing",
        "access_state": "unknown",
        "access_reason": reason,
        "source_snapshots": [],
        "output_format": arguments.get("output_format", default_output_format),
    }
    # RFC-0022 P0.5: every route fragment echoes its adapter-owned wire
    # owner version, including classified-unavailable results.
    if action_version is not None:
        envelope["action_version"] = action_version
    return envelope


def format_read_existing_unavailable(
    arguments: dict[str, Any],
    *,
    reason: str = READ_EXISTING_AUTHORITY_UNCERTIFIED,
    default_output_format: str = "toon",
    compact_only: bool = False,
    action_version: str | None = None,
) -> dict[str, Any] | None:
    """Format one unavailable classification through the normal tool boundary."""
    result = read_existing_unavailable(
        arguments,
        reason=reason,
        default_output_format=default_output_format,
        action_version=action_version,
    )
    if result is None:
        return None
    from .mcp.utils.format_helper import apply_toon_format_to_response

    return apply_toon_format_to_response(
        result,
        result["output_format"],
        compact_only=compact_only,
    )


def format_read_existing_failure(
    code: str,
    *,
    output_format: str = "toon",
    compact_only: bool = False,
    action_version: str | None = None,
    source_snapshots: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Format one classified failure envelope with P0.4 evidence.

    Used by consumers that must fail closed BEFORE reaching the shared seam
    (e.g. edit.safe's unbound-root guard, which must precede path
    validation): produces the same envelope shape the seam's except block
    emits, so the wire contract (evidence + action_version) is never lost.
    ``source_snapshots`` cites the exact capability identity actually read
    when the failure happened AFTER acquisition (Codex P2 #1299); failures
    before acquisition keep the empty list.
    """
    from .mcp.utils.format_helper import apply_toon_format_to_response

    failure: dict[str, Any] = {
        "success": False,
        "verdict": "ERROR",
        "error_code": code,
        "error": code,
        "action_version": action_version,
        "output_format": output_format,
    }
    attach_read_existing_evidence(failure, records=source_snapshots)
    return apply_toon_format_to_response(
        failure, output_format, compact_only=compact_only
    )


def read_existing_gate(
    tool: Any,
    arguments: dict[str, Any],
    *,
    reason: str,
    compact_only: bool = False,
    action_version: str | None = None,
) -> dict[str, Any] | None:
    """Validate and classify an explicit route before any adapter backend work."""
    if "access_mode" not in arguments:
        return None
    tool.validate_arguments(arguments)
    return format_read_existing_unavailable(
        arguments,
        reason=reason,
        compact_only=compact_only,
        action_version=action_version,
    )


def attach_read_existing_evidence(
    result: dict[str, Any],
    *,
    records: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Attach the exact P0.4 access-evidence fields to one classified result.

    ``records`` are the exact ``source_snapshots`` entries citing every
    primitive identity actually acquired during the route (``kind`` is
    ``diff`` for P0.2 or ``index`` for P0.1); an empty list means no
    capability was acquired. ``access_state`` is ``available`` on success
    and otherwise ``missing``/``unknown`` with the stable failure code as
    ``access_reason`` (RFC-0022 P0.4).
    """
    if result.get("success") is True:
        state: str | None = "available"
        reason: str | None = None
    else:
        code = str(
            result.get("error_code")
            or result.get("error")
            or DIFF_SNAPSHOT_READ_EXISTING_UNSUPPORTED
        )
        state = (
            "missing"
            if code in {"MISSING_INDEX", "MISSING_PROJECT_ROOT"}
            else "unknown"
        )
        reason = code
    result["access_mode"] = "read_existing"
    result["access_state"] = state
    result["access_reason"] = reason
    result["source_snapshots"] = list(records or [])
    return result


# Stable acquire/after-read failure codes a P0.1 index consumer can raise;
# anything outside this set degrades to the generic fallback code.
_INDEX_CONSUMER_STABLE_CODES = frozenset(
    {
        "INDEX_SNAPSHOT_UNKNOWN",
        "INDEX_SNAPSHOT_ROOT_MISMATCH",
        "SOURCE_GENERATION_MISMATCH",
        "INDEX_SNAPSHOT_DEADLINE",
        "INDEX_SNAPSHOT_CAPACITY",
        "INDEX_SNAPSHOT_FAILED",
        "SOURCE_SCOPE_UNKNOWN",
        "CONCURRENT_SOURCE",
        "MISSING_PROJECT_ROOT",
        "MISSING_INDEX",
        "CORRUPT_INDEX",
        "CONCURRENT_WRITER",
        "SOURCE_SCOPE_UNSAFE",
        "SOURCE_SCOPE_UNREADABLE",
        "SOURCE_SCOPE_UNSUPPORTED",
        "SOURCE_SCAN_DEADLINE",
        "SOURCE_SCOPE_UNBOUNDED",
        "SOURCE_INDEX_MISMATCH",
        "CONSTRAINED_INDEX_SCOPE",
        "INDEX_SNAPSHOT_INCOMPLETE",
        "FILE_NOT_FOUND",
        "FILE_NOT_INDEXED",
    }
)


def _stable_consumer_code(exc: Exception) -> str:
    """Map a consumer exception to its stable wire code.

    ``acquire_index_snapshot`` raises ``ValueError``/``RuntimeError`` whose
    message IS the stable code; the after-read recapture does the same; the
    unbound-root guard raises ``MISSING_PROJECT_ROOT: <detail>``. The RFC
    requires those codes as result data, never serialized exception text, so
    any message outside the stable set degrades to the generic fallback.
    """
    message = str(exc)
    token = message.split(":", 1)[0].strip()
    return token if token in _INDEX_CONSUMER_STABLE_CODES else "INDEX_SNAPSHOT_FAILED"


def read_existing_index_consumer(
    tool: Any,
    arguments: dict[str, Any],
    *,
    reader: Any,
    action_version: str,
    compact_only: bool = False,
    default_output_format: str = "toon",
) -> dict[str, Any] | None:
    """Run one explicit read_existing route against the certified index snapshot.

    Returns the formatted response envelope, or ``None`` when the request is
    not an explicit read_existing call. Non-certified axes (no Linux strace
    authority) keep the stable UNCERTIFIED envelope. On the certified axis the
    snapshot is acquired (before-read token revalidation), read through
    ``reader(snapshot, conn)``, re-captured after the read, and the ACTUALLY
    used tokens are echoed from the acquired snapshot with the P0.4 evidence.
    ``reader`` must return the full success payload (the route adds the token
    echoes, ``output_format``, and access evidence); any stable
    ``ValueError``/``RuntimeError`` is classified as a failure envelope with
    ``error_code``/``access_reason`` equal to the stable code and no result.
    """
    if "access_mode" not in arguments:
        return None
    output_format = arguments.get("output_format", default_output_format)
    if not read_existing_platform_supported():
        return format_read_existing_unavailable(
            arguments,
            compact_only=compact_only,
            default_output_format=default_output_format,
            action_version=action_version,
        )
    from .index_snapshot import read_existing_index_scope
    from .mcp.utils.format_helper import apply_toon_format_to_response

    # Codex P2 (#1299): keep the acquired capability identity so failures
    # that happen AFTER acquisition still cite the snapshot that was read
    # (auditability); pre-acquisition failures keep the empty list.
    acquired: tuple[str, str] | None = None
    try:
        # Codex-review P2 (#1299): an unbound root must be CLASSIFIED (failure
        # envelope with evidence + action_version), never a bare raise that
        # escapes the wire contract — so the check lives inside the try.
        if not tool.project_root:
            raise ValueError(
                "MISSING_PROJECT_ROOT: project_root must be bound before "
                "read_existing access"
            )
        # validate_required_index_access has already bound both tokens as
        # non-empty strings; index them directly so the acquire types cleanly.
        with read_existing_index_scope(
            arguments["snapshot_id"],
            tool.project_root,
            arguments["source_generation"],
        ) as (snapshot, conn):
            assert snapshot.snapshot_id is not None
            assert snapshot.source_generation is not None
            acquired = (snapshot.snapshot_id, snapshot.source_generation)
            payload = reader(snapshot, conn)
            if not isinstance(payload, dict):
                raise ValueError("INDEX_SNAPSHOT_FAILED")
            # The acquired capability is identity-matched to the request pair
            # (the registry raises otherwise), so both tokens are bound here.
            result = dict(payload)
            result["snapshot_id"] = snapshot.snapshot_id
            result["source_generation"] = snapshot.source_generation
            result["source_fingerprint"] = snapshot.source_fingerprint
            result["index_fingerprint"] = snapshot.index_fingerprint
            result["output_format"] = output_format
            attach_read_existing_evidence(
                result,
                records=[
                    {
                        "kind": "index",
                        "snapshot_id": snapshot.snapshot_id,
                        "source_generation": snapshot.source_generation,
                    }
                ],
            )
            return apply_toon_format_to_response(
                result, output_format, compact_only=compact_only
            )
    except (ValueError, RuntimeError) as exc:
        # Codex P2 (#1299): pre-yield failures (completeness/scope gate or
        # pre-read recapture) attach the acquired identity to the exception;
        # post-yield failures record it in ``acquired``. Either way the
        # failure envelope cites the exact capability that was acquired.
        identity = getattr(exc, "_read_existing_identity", None) or acquired
        return format_read_existing_failure(
            _stable_consumer_code(exc),
            output_format=output_format,
            compact_only=compact_only,
            action_version=action_version,
            source_snapshots=(
                [
                    {
                        "kind": "index",
                        "snapshot_id": identity[0],
                        "source_generation": identity[1],
                    }
                ]
                if identity is not None
                else None
            ),
        )
