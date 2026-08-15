"""RFC-0022 P0.5 wire ownership: one authoritative version per route.

Every RFC-0022 route result must echo its adapter-owned ``action_version``
so consumers can tell which adapter contract produced a wire fragment. The
registry is the single source of truth; each adapter imports its own
constant from here (or stays bound to a pre-existing constant, as
``index.status`` does via ``index_snapshot.ACTION_VERSION``).
"""

from __future__ import annotations

from .index_snapshot import ACTION_VERSION as INDEX_STATUS_ACTION_VERSION

#: Canonical wire owner versions, keyed by ``(facade, action)``.
#: ``index.status`` reuses the pre-existing constant so the two definitions
#: cannot drift; every other route owns exactly one entry here.
ACTION_VERSIONS: dict[tuple[str, str], str] = {
    ("index", "status"): INDEX_STATUS_ACTION_VERSION,
    ("nav", "context"): "nav.context/v1",
    ("edit", "safe"): "edit.safe/v1",
    ("edit", "impact"): "edit.impact/v1",
    ("edit", "ast_diff"): "edit.ast_diff/v1",
    ("edit", "classify"): "edit.classify/v1",
    ("edit", "constraints"): "edit.constraints/v1",
}

NAV_CONTEXT_ACTION_VERSION = ACTION_VERSIONS[("nav", "context")]
EDIT_SAFE_ACTION_VERSION = ACTION_VERSIONS[("edit", "safe")]
EDIT_IMPACT_ACTION_VERSION = ACTION_VERSIONS[("edit", "impact")]
EDIT_AST_DIFF_ACTION_VERSION = ACTION_VERSIONS[("edit", "ast_diff")]
EDIT_CLASSIFY_ACTION_VERSION = ACTION_VERSIONS[("edit", "classify")]
EDIT_CONSTRAINTS_ACTION_VERSION = ACTION_VERSIONS[("edit", "constraints")]

#: All route versions must be unique — a shared version would let two
#: adapters silently masquerade as one contract.
assert len(set(ACTION_VERSIONS.values())) == len(ACTION_VERSIONS), (
    "wire owner versions must be unique per route"
)
