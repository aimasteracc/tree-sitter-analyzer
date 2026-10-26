"""Index-snapshot completeness on the RFC-0040 response vocabulary (#1811).

The snapshot registry describes an index as ``complete``, ``partial`` or
``unknown`` and explains a non-complete snapshot with a free-form reason
(``oracle_reason``). Query tools answer under the same ``completeness`` key
with ``complete`` / ``incomplete`` / ``unknown`` plus reason codes from a
closed set. Index-status responses translate here so an agent can read the
key the same way on every tool:

* ``complete`` stays ``complete``, with no reason codes;
* ``partial`` becomes ``incomplete``: some files are certified, the whole
  project is not, so the index is known to miss part of the answer;
* ``unknown`` stays ``unknown``.

The mapping never moves a snapshot toward ``complete``. The raw snapshot
reason is still reported in ``oracle_reason``.
"""

from __future__ import annotations

from typing import Any

#: The index has files but no exact full-index certification.
INDEX_NOT_CERTIFIED = "INDEX_NOT_CERTIFIED"
#: The snapshot could not be acquired or read.
INDEX_SNAPSHOT_UNAVAILABLE = "INDEX_SNAPSHOT_UNAVAILABLE"
#: A full-index rebuild holds the index; retry after it finishes.
INDEX_BUILD_IN_PROGRESS = "INDEX_BUILD_IN_PROGRESS"
#: No project root is bound, so no index can be located.
PROJECT_ROOT_MISSING = "PROJECT_ROOT_MISSING"
#: An index run did not cover the whole source scope.
INDEX_SCOPE_INCOMPLETE = "INDEX_SCOPE_INCOMPLETE"
#: Source files are left out of the index (e.g. their grammar is missing).
#: Same code as ``mcp.tools.unindexed_sources.UNINDEXED_REASON``.
UNINDEXED_SOURCE_FILES = "UNINDEXED_SOURCE_FILES"

INDEX_COMPLETENESS_REASONS: frozenset[str] = frozenset(
    {
        INDEX_NOT_CERTIFIED,
        INDEX_SNAPSHOT_UNAVAILABLE,
        INDEX_BUILD_IN_PROGRESS,
        PROJECT_ROOT_MISSING,
        INDEX_SCOPE_INCOMPLETE,
    }
)

#: Snapshot reasons with a closed-set code of their own. ``MISSING_INDEX``,
#: ``SOURCE_INDEX_MISMATCH`` and ``SOURCE_SCOPE_UNKNOWN`` already belong to
#: the shared vocabulary and pass through unchanged.
_SNAPSHOT_REASON_CODES: dict[str, str] = {
    "MISSING_INDEX": "MISSING_INDEX",
    "SOURCE_INDEX_MISMATCH": "SOURCE_INDEX_MISMATCH",
    "SOURCE_SCOPE_UNKNOWN": "SOURCE_SCOPE_UNKNOWN",
    "CONCURRENT_WRITER": INDEX_BUILD_IN_PROGRESS,
    "MISSING_PROJECT_ROOT": PROJECT_ROOT_MISSING,
}

_RESPONSE_STATUS: dict[str, str] = {
    "complete": "complete",
    "partial": "incomplete",
    "incomplete": "incomplete",
}


def snapshot_completeness_fields(
    snapshot_completeness: str | None, reason: str | None
) -> dict[str, Any]:
    """``completeness`` plus its reason codes for one index snapshot."""
    status = _RESPONSE_STATUS.get(str(snapshot_completeness), "unknown")
    if status == "complete":
        return {"completeness": "complete"}
    default = (
        INDEX_NOT_CERTIFIED if status == "incomplete" else INDEX_SNAPSHOT_UNAVAILABLE
    )
    code = _SNAPSHOT_REASON_CODES.get(str(reason), default)
    return {
        "completeness": status,
        "completeness_reason": code,
        "completeness_reasons": [code],
    }


__all__ = [
    "INDEX_BUILD_IN_PROGRESS",
    "INDEX_COMPLETENESS_REASONS",
    "INDEX_NOT_CERTIFIED",
    "INDEX_SCOPE_INCOMPLETE",
    "INDEX_SNAPSHOT_UNAVAILABLE",
    "PROJECT_ROOT_MISSING",
    "UNINDEXED_SOURCE_FILES",
    "snapshot_completeness_fields",
]
