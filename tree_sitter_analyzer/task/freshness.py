"""RFC-0022 task-outcome/v1 freshness and snapshot truth (Phase A).

Freshness states are ``fresh|stale|missing|not_applicable|unknown``.
``fresh`` is allowed only when the authoritative oracle is complete and
every graph result echoes its token. Without that oracle, repository/index
fingerprints are null, reason is ``AUTHORITATIVE_SNAPSHOT_UNAVAILABLE``, and
graph-dependent status is at most partial. Outcomes never claim a mixed
snapshot is complete (RFC-0022 §Freshness and snapshot truth).
"""

from __future__ import annotations

from dataclasses import dataclass

Freshness = str  # fresh|stale|missing|not_applicable|unknown

FRESHNESS_STATES: frozenset[str] = frozenset(
    {"fresh", "stale", "missing", "not_applicable", "unknown"}
)


@dataclass(frozen=True)
class SnapshotTruth:
    """One snapshot-truth judgement from the authoritative oracle."""

    oracle_complete: bool
    snapshot_id: str | None = None
    source_generation: str | None = None
    graph_tokens: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.oracle_complete) is not bool:
            raise ValueError("oracle_complete must be a bool")
        if self.snapshot_id is not None and (
            type(self.snapshot_id) is not str or not self.snapshot_id
        ):
            raise ValueError("snapshot_id must be a non-empty string or null")
        if any(type(token) is not str for token in self.graph_tokens):
            raise ValueError("graph_tokens must be strings")

    @property
    def freshness(self) -> tuple[str, str | None]:
        """Return (freshness, reason) per RFC-0022.

        - not_applicable: no graph evidence was used (nothing to judge).
        - fresh: oracle complete AND every graph result echoes its token.
        - stale: oracle complete but a graph token disagrees.
        - missing: no snapshot id from the oracle.
        - unknown: oracle incomplete (AUTHORITATIVE_SNAPSHOT_UNAVAILABLE).
        """
        if not self.graph_tokens:
            return "not_applicable", None
        if not self.oracle_complete:
            return "unknown", "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE"
        if self.snapshot_id is None:
            return "missing", "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE"
        if any(token != self.snapshot_id for token in self.graph_tokens):
            return "stale", "SNAPSHOT_TOKEN_MISMATCH"
        return "fresh", None

    @property
    def graph_status_cap(self) -> str:
        """Graph-dependent status is at most partial without a fresh oracle."""
        freshness, _ = self.freshness
        if freshness == "fresh":
            return "complete"
        return "partial"
