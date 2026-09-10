"""In-process CLI-handler bridge for RFC-0022 process-local controls.

Codex P1 (#1257): RFC-0022 task routing composes ``index.status``,
``nav.context`` and ``edit`` snapshot consumers inside one process. Those
process-local facade controls (``access_mode``, ``snapshot_id``,
``source_generation``, ``diff_snapshot_id``, ``route_lease_id``) must be
forwardable on the CLI-handler path — not MCP-only. This module owns the
forwarding helper and the ``(facade, action) -> controls`` table that the
contract test ``test_rfc0022_process_local_cli_parity_exception_is_exact``
asserts stays in lockstep with the action-scoped facade params.

The bridge is intentionally non-public: the flags themselves stay MCP
action-scoped (no new user-facing CLI flags), while any in-process caller
that builds a CLI args namespace carrying these attributes — the RFC-0022
task router, tests, or future CLI flags — gets them forwarded verbatim.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

#: RFC-0022 process-local controls the bridge can forward. The attribute
#: name on a CLI args namespace equals the MCP tool parameter name, so a
#: single name covers both sides of the bridge.
READ_EXISTING_BRIDGED_CONTROLS: tuple[str, ...] = (
    "access_mode",
    "snapshot_id",
    "source_generation",
    "diff_snapshot_id",
    "route_lease_id",
)

#: (facade, action) -> controls forwarded by that CLI handler route. Only
#: consumer controls are bridged: producer-only tokens (``capture_diff_
#: snapshot``) and controls with their own dedicated CLI affordance
#: (``scope_paths`` via ``--change-impact-scope``, ``persist`` via
#: ``--constraints-read-only``) stay outside the bridge.
READ_EXISTING_BRIDGE_BY_ACTION: dict[tuple[str, str], frozenset[str]] = {
    ("index", "status"): frozenset({"access_mode"}),
    ("nav", "context"): frozenset({"access_mode", "snapshot_id", "source_generation"}),
    ("edit", "safe"): frozenset({"access_mode", "snapshot_id", "source_generation"}),
    ("edit", "impact"): frozenset({"access_mode"}),
    ("edit", "constraints"): frozenset(
        {
            "access_mode",
            "diff_snapshot_id",
            "snapshot_id",
            "source_generation",
        }
    ),
    ("edit", "classify"): frozenset({"access_mode", "diff_snapshot_id"}),
    ("edit", "ast_diff"): frozenset({"access_mode", "diff_snapshot_id"}),
}


def _forward_read_existing_controls(
    args: Any,
    tool_args: dict[str, Any],
    *,
    controls: Iterable[str],
) -> dict[str, Any]:
    """Copy present bridged controls from a CLI namespace into tool args.

    Only attributes actually present on the namespace (and not ``None``)
    are forwarded, so ordinary CLI invocations — whose parser never
    populates these attributes — see zero change, while in-process
    RFC-0022 routers that construct namespaces carrying the controls get
    them forwarded verbatim.
    """
    allowed = frozenset(controls)
    for name in READ_EXISTING_BRIDGED_CONTROLS:
        if name not in allowed:
            continue
        value = getattr(args, name, None)
        if value is not None:
            tool_args[name] = value
    return tool_args


__all__ = [
    "READ_EXISTING_BRIDGED_CONTROLS",
    "READ_EXISTING_BRIDGE_BY_ACTION",
    "_forward_read_existing_controls",
]
